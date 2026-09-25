"""Common utilities and type definitions for views."""

from datetime import date
from datetime import timedelta
from typing import TypeAlias

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_GET

from gift_manager.gift_plan_actions import gift_plan_requires_planning_fields
from gift_manager.gift_plan_cards import build_gift_plan_card
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.statuses import is_idea_status
from gift_manager.statuses import is_terminal_status
from gift_manager.statuses import relation_status_slug

# Type definitions for clarity
ModelType: TypeAlias = type[Model]
SharedObjectType = Person | PersonGroup | Gift | Event | Relation

DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS = 7
DASHBOARD_STALE_AFTER_DAYS = 30
DASHBOARD_REACTION_WINDOW_DAYS = 30
DASHBOARD_PAGINATED_ACTION_GROUPS = frozenset(("overdue", "upcoming", "incomplete"))
DASHBOARD_COMPACT_ACTION_GROUPS = frozenset(("overdue", "upcoming", "incomplete"))
DASHBOARD_MAX_RENDERED_ACTIONS_PER_GROUP = 24


def _build_dashboard_action_item(
    relation: Relation,
    action_key: str,
    user,
    permission: int | None = None,
) -> dict:
    """Return presentation data for a dashboard gift-plan action."""
    urgency_key = {
        "upcoming": "due_soon",
        "incomplete": "needs_details",
        "stale": "later",
        "reaction": "completed",
    }.get(action_key, action_key)
    if permission is None:
        permission = PermissionService.get_permission(relation, user)
    return build_gift_plan_card(relation, urgency_key=urgency_key, permission=permission)


def _awaits_reaction(relation: Relation, *, today: date) -> bool:
    """Return whether a recently given, unrated gift plan is waiting for a reaction."""
    if relation_status_slug(relation.status) != "given" or relation.reaction_rating is not None:
        return False

    given_on = (
        timezone.localtime(relation.status_changed_at).date()
        if relation.status_changed_at
        else relation.due_date
    )
    return given_on is not None and given_on >= today - timedelta(
        days=DASHBOARD_REACTION_WINDOW_DAYS
    )


def _build_gift_plan_action_groups(
    relations: list[Relation],
    *,
    user,
    today: date,
    now,
) -> list[dict]:
    """Build priority-ordered dashboard action groups for gift plans."""
    due_soon_end = today + timedelta(days=DASHBOARD_QUICK_ACTION_DUE_SOON_DAYS)
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
        "reaction": {
            "key": "reaction",
            "label": gettext("Awaiting reaction"),
            "icon": "fa-heart",
            "items": [],
        },
    }

    for relation in relations:
        if is_terminal_status(relation.status):
            if _awaits_reaction(relation, today=today):
                permission = PermissionService.get_effective_permission(relation, user)
                if permission >= PermissionLevel.EDITOR:
                    groups["reaction"]["items"].append(
                        _build_dashboard_action_item(relation, "reaction", user, permission)
                    )
            continue

        if relation.due_date and relation.due_date < today:
            group_key = "overdue"
        elif relation.due_date and relation.due_date <= due_soon_end:
            group_key = "upcoming"
        elif relation.due_date is None and is_idea_status(relation.status):
            continue
        elif gift_plan_requires_planning_fields(relation) and (
            relation.due_date is None or relation.event_id is None
        ):
            group_key = "incomplete"
        elif relation.creation_date and relation.creation_date <= stale_before:
            group_key = "stale"
        else:
            continue

        groups[group_key]["items"].append(_build_dashboard_action_item(relation, group_key, user))

    group_order = ("overdue", "upcoming", "incomplete", "stale", "reaction")
    action_groups = [groups[key] for key in group_order if groups[key]["items"]]
    for group in action_groups:
        is_paginated = group["key"] in DASHBOARD_PAGINATED_ACTION_GROUPS
        group["is_paginated"] = is_paginated
        group["is_compact"] = group["key"] in DASHBOARD_COMPACT_ACTION_GROUPS
        group["workspace_focus"] = {
            "overdue": "overdue",
            "upcoming": "due_soon",
            "incomplete": "needs_details",
        }.get(group["key"], "")
        display_limit = DASHBOARD_MAX_RENDERED_ACTIONS_PER_GROUP if is_paginated else 4
        group["display_items"] = group["items"][:display_limit]
    return action_groups


def _build_dashboard_summary(action_groups: list[dict], unassigned_gift_count: int) -> dict:
    """Return compact action counts for the dashboard summary strip."""
    action_counts = {group["key"]: len(group["items"]) for group in action_groups}
    attention_count = (
        sum(count for key, count in action_counts.items() if key != "reaction")
        + unassigned_gift_count
    )
    return {
        "attention": attention_count,
        "overdue": action_counts.get("overdue", 0),
        "upcoming": action_counts.get("upcoming", 0),
        "incomplete": action_counts.get("incomplete", 0),
        "stale": action_counts.get("stale", 0),
        "reaction": action_counts.get("reaction", 0),
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

        unassigned_gift_count = (
            Gift.objects.accessible_by(user).filter(gifts__isnull=True).distinct().count()
        )
        context["dashboard_action_groups"] = action_groups
        context["dashboard_summary"] = _build_dashboard_summary(
            action_groups,
            unassigned_gift_count,
        )

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
