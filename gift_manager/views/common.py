"""Common utilities and type definitions for views."""

from calendar import monthrange
from datetime import date
from datetime import timedelta
from typing import TypeAlias

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_GET

from gift_manager.gift_plan_actions import build_gift_plan_quick_actions
from gift_manager.gift_plan_actions import gift_plan_has_contextual_edit_action
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.statuses import is_idea_status
from gift_manager.statuses import is_terminal_status
from gift_manager.statuses import relation_status_slug

# Type definitions for clarity
ModelType: TypeAlias = type[Model]
SharedObjectType = Person | PersonGroup | Gift | Event | Relation

DASHBOARD_ACTION_WINDOW_DAYS = 30
DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS = 7
DASHBOARD_STALE_AFTER_DAYS = 30
DASHBOARD_PAGINATED_ACTION_GROUPS = frozenset(("upcoming", "incomplete"))


def _gift_plan_status_class(status) -> str:
    """Return the shared gift-plan status CSS class."""
    return f"gift-plan-status--{relation_status_slug(status)}"


def _is_completed_status(status) -> bool:
    """Return whether a gift-plan status is considered completed."""
    return is_terminal_status(status)


def _gift_plan_requires_planning_fields(relation: Relation) -> bool:
    """Return whether a gift plan expects concrete planning details."""
    return not is_idea_status(relation.status) and not _is_completed_status(relation.status)


def _safe_date(year: int, month: int, day: int) -> date:
    """Build a date, clamping the day to the target month when needed."""
    return date(year, month, min(day, monthrange(year, month)[1]))


def _next_monthly_occurrence(usual_date: date, today: date) -> date:
    """Return the next monthly occurrence for an event's usual date."""
    candidate = _safe_date(today.year, today.month, usual_date.day)
    if candidate >= today:
        return candidate

    month = today.month + 1
    year = today.year
    if month > 12:
        month = 1
        year += 1
    return _safe_date(year, month, usual_date.day)


def _next_event_occurrence(event: Event, today: date, window_end: date) -> date | None:
    """Return an event's next occurrence in the dashboard window."""
    if event.absolute_date and today <= event.absolute_date <= window_end:
        return event.absolute_date

    if not event.usual_date:
        return None

    if event.recurrence == "daily":
        occurrence = today
    elif event.recurrence == "weekly":
        days_until = (event.usual_date.weekday() - today.weekday()) % 7
        occurrence = today + timedelta(days=days_until)
    elif event.recurrence == "monthly":
        occurrence = _next_monthly_occurrence(event.usual_date, today)
    elif event.recurrence == "yearly":
        occurrence = _safe_date(today.year, event.usual_date.month, event.usual_date.day)
        if occurrence < today:
            occurrence = _safe_date(today.year + 1, event.usual_date.month, event.usual_date.day)
    else:
        occurrence = event.usual_date

    if today <= occurrence <= window_end:
        return occurrence
    return None


def _dashboard_quick_action_urgency_key(
    relation: Relation,
    urgency_key: str,
    today: date,
) -> str:
    """Return the urgency key used to choose dashboard quick actions."""
    if (
        urgency_key == "due_soon"
        and relation.due_date
        and relation.due_date > today + timedelta(days=DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS)
    ):
        if _gift_plan_requires_planning_fields(relation) and relation.event_id is None:
            return "needs_details"
        return "later"
    return urgency_key


def _build_dashboard_action_item(
    relation: Relation,
    action_key: str,
    user,
    *,
    today: date,
) -> dict:
    """Return presentation data for a dashboard gift-plan action."""
    urgency_key = {
        "upcoming": "due_soon",
        "incomplete": "needs_details",
        "stale": "later",
    }.get(action_key, action_key)
    quick_action_urgency_key = _dashboard_quick_action_urgency_key(relation, urgency_key, today)
    permission = PermissionService.get_permission(relation, user)
    can_edit = permission >= PermissionLevel.EDITOR
    quick_actions = build_gift_plan_quick_actions(
        relation,
        quick_action_urgency_key,
        can_edit=can_edit,
    )
    return {
        "relation": relation,
        "action_key": action_key,
        "urgency_key": urgency_key,
        "status_class": _gift_plan_status_class(relation.status),
        "detail_url": reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id}),
        "edit_url": reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
        "quick_action_url": reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
        ),
        "quick_actions": quick_actions,
        "has_contextual_edit_action": gift_plan_has_contextual_edit_action(quick_actions),
        "event_options": [],
        "can_edit": can_edit,
    }


def _build_gift_plan_action_groups(
    relations: list[Relation],
    *,
    user,
    today: date,
    now,
) -> list[dict]:
    """Build priority-ordered dashboard action groups for gift plans."""
    window_end = today + timedelta(days=DASHBOARD_ACTION_WINDOW_DAYS)
    stale_before = now - timedelta(days=DASHBOARD_STALE_AFTER_DAYS)
    groups = {
        "overdue": {
            "key": "overdue",
            "label": gettext("Overdue"),
            "icon": "fa-triangle-exclamation",
            "items": [],
        },
        "upcoming": {
            "key": "upcoming",
            "label": gettext("Due soon"),
            "icon": "fa-clock",
            "items": [],
        },
        "incomplete": {
            "key": "incomplete",
            "label": gettext("Needs details"),
            "icon": "fa-list-check",
            "items": [],
        },
        "stale": {
            "key": "stale",
            "label": gettext("Stale"),
            "icon": "fa-hourglass-half",
            "items": [],
        },
    }

    for relation in relations:
        if _is_completed_status(relation.status):
            continue

        if relation.due_date and relation.due_date < today:
            group_key = "overdue"
        elif relation.due_date and relation.due_date <= window_end:
            group_key = "upcoming"
        elif relation.due_date is None and is_idea_status(relation.status):
            continue
        elif _gift_plan_requires_planning_fields(relation) and (
            relation.due_date is None or relation.event_id is None
        ):
            group_key = "incomplete"
        elif relation.creation_date and relation.creation_date <= stale_before:
            group_key = "stale"
        else:
            continue

        groups[group_key]["items"].append(
            _build_dashboard_action_item(relation, group_key, user, today=today)
        )

    group_order = ("overdue", "upcoming", "incomplete", "stale")
    action_groups = [groups[key] for key in group_order if groups[key]["items"]]
    for group in action_groups:
        is_paginated = group["key"] in DASHBOARD_PAGINATED_ACTION_GROUPS
        group["is_paginated"] = is_paginated
        group["display_items"] = group["items"] if is_paginated else group["items"][:4]
    return action_groups


def _build_upcoming_occasion_recipients(
    relations: list[Relation],
    *,
    today: date,
) -> list[dict]:
    """Return recipients attached to gift plans with upcoming occasions."""
    window_end = today + timedelta(days=DASHBOARD_ACTION_WINDOW_DAYS)
    items = []
    for relation in relations:
        if not relation.event or _is_completed_status(relation.status):
            continue

        occurrence = _next_event_occurrence(relation.event, today, window_end)
        if not occurrence:
            continue

        items.append(
            {
                "relation": relation,
                "event": relation.event,
                "occurrence_date": occurrence,
                "days_until": (occurrence - today).days,
                "status_class": _gift_plan_status_class(relation.status),
            }
        )

    return sorted(
        items,
        key=lambda item: (item["occurrence_date"], item["relation"].recipient_name.lower()),
    )[:5]


def _build_dashboard_summary(action_groups: list[dict], unassigned_gift_count: int) -> dict:
    """Return compact action counts for the dashboard summary strip."""
    action_counts = {group["key"]: len(group["items"]) for group in action_groups}
    attention_count = sum(action_counts.values()) + unassigned_gift_count
    return {
        "attention": attention_count,
        "overdue": action_counts.get("overdue", 0),
        "upcoming": action_counts.get("upcoming", 0),
        "incomplete": action_counts.get("incomplete", 0),
        "stale": action_counts.get("stale", 0),
        "unassigned_gifts": unassigned_gift_count,
    }


def get_user(user_id, *, return_id=False) -> tuple[User, str] | tuple[User, str, str]:
    """Get user and username by ID.

    Args:
        user_id: The user ID to look up
        return_id: If True, also return the user_id

    Returns:
        Tuple of (user, username) or (user, username, user_id) if return_id is True
    """
    user = User.objects.get(id=user_id)
    username = user.username
    if return_id:
        return user, username, user_id
    return user, username


def home(request):
    """Home page view with dashboard."""
    context = {}

    if request.user.is_authenticated:
        user = request.user

        # Statistics
        person_count = Person.objects.accessible_by(user).count()
        group_count = PersonGroup.objects.accessible_by(user).count()
        context["stats"] = {
            "recipients": person_count + group_count,
            "persons": person_count,
            "groups": group_count,
            "gifts": Gift.objects.accessible_by(user).count(),
            "events": Event.objects.accessible_by(user).count(),
            "relations": Relation.objects.accessible_by(user).count(),
        }

        now = timezone.now()
        today = timezone.localdate()

        gift_plan_queryset = (
            Relation.objects.accessible_by(user)
            .with_related_objects()
            .prefetch_related("gift__tags")
            .order_by("due_date", "creation_date", "gift__name")
        )
        gift_plans = list(gift_plan_queryset)
        action_groups = _build_gift_plan_action_groups(
            gift_plans,
            user=user,
            today=today,
            now=now,
        )

        unassigned_gifts_queryset = (
            Gift.objects.accessible_by(user)
            .filter(gifts__isnull=True)
            .prefetch_related("tags")
            .distinct()
            .order_by("-creation_date")
        )
        unassigned_gift_count = unassigned_gifts_queryset.count()
        context["dashboard_action_groups"] = action_groups
        context["dashboard_has_actions"] = bool(action_groups or unassigned_gift_count)
        context["unassigned_gifts"] = unassigned_gifts_queryset[:5]
        context["upcoming_occasion_recipients"] = _build_upcoming_occasion_recipients(
            gift_plans,
            today=today,
        )
        context["dashboard_summary"] = _build_dashboard_summary(
            action_groups,
            unassigned_gift_count,
        )

        # Gift plans by status
        statuses = RelationStatus.objects.all()
        status_counts = []
        for status in statuses:
            count = Relation.objects.accessible_by(user).filter(status=status).count()
            if count > 0:
                status_counts.append({"status": status, "count": count})
        context["status_counts"] = status_counts

        # Recent gifts (last 5)
        context["recent_gifts"] = Gift.objects.accessible_by(user).order_by("-creation_date")[:5]

        # Recent persons (last 5)
        context["recent_persons"] = Person.objects.accessible_by(user).order_by("-creation_date")[
            :5
        ]

    return render(request, "gift_manager/home.html", context)


@login_required
@require_GET
def global_search(request):
    """Global search API endpoint."""
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse({"results": []})

    user = request.user
    max_per_category = 5

    # Search Gifts
    gifts = (
        Gift.objects.accessible_by(user)
        .filter(Q(name__icontains=query) | Q(comment__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    results = [
        {
            "type": "gift",
            "icon": "fa-gift",
            "title": gift.name,
            "subtitle": gift.comment[:50] + "..."
            if gift.comment and len(gift.comment) > 50
            else gift.comment or "",
            "url": f"/gifts/{gift.gift_id}/",
        }
        for gift in gifts
    ]

    # Search Persons
    persons = (
        Person.objects.accessible_by(user)
        .filter(Q(first_name__icontains=query) | Q(family_name__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    results.extend(
        {
            "type": "recipient",
            "icon": "fa-user",
            "title": str(person),
            "subtitle": gettext("Person"),
            "url": f"/persons/{person.person_id}/",
        }
        for person in persons
    )

    # Search Person Groups
    groups = (
        PersonGroup.objects.accessible_by(user)
        .filter(name__icontains=query)
        .order_by("-creation_date")[:max_per_category]
    )
    results.extend(
        {
            "type": "recipient",
            "icon": "fa-layer-group",
            "title": group.name,
            "subtitle": gettext("Group"),
            "url": f"/person_groups/{group.group_id}/",
        }
        for group in groups
    )

    # Search Events
    events = (
        Event.objects.accessible_by(user)
        .filter(Q(name__icontains=query) | Q(comment__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    results.extend(
        {
            "type": "event",
            "icon": "fa-calendar-alt",
            "title": event.name,
            "subtitle": event.comment[:50] + "..."
            if event.comment and len(event.comment) > 50
            else event.comment or "",
            "url": f"/events/{event.event_id}/",
        }
        for event in events
    )

    # Search Gift Tags
    tags = (
        GiftTag.objects.accessible_by(user)
        .filter(name__icontains=query)
        .order_by("-creation_date")[:max_per_category]
    )
    results.extend(
        {
            "type": "tag",
            "icon": "fa-tag",
            "title": tag.name,
            "subtitle": "",
            "url": f"/gift-tag/{tag.tag_id}/",
        }
        for tag in tags
    )

    return JsonResponse({"results": results})
