"""Common utilities and type definitions for views."""

from datetime import date
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

from gift_manager.birthdays import build_upcoming_birthdays
from gift_manager.gift_plan_cards import build_dashboard_summary
from gift_manager.gift_plan_cards import build_gift_plan_action_groups
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import birthday_event_name_q
from gift_manager.statuses import is_terminal_status

# Type definitions for clarity
ModelType: TypeAlias = type[Model]
SharedObjectType = Person | PersonGroup | Gift | Event | Relation


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


def _find_next_upcoming_item(gift_plans: list[Relation], user, today: date) -> dict | None:
    """Return the soonest open gift plan or event occurrence from today onwards, if any."""
    candidates = []

    open_plans = [
        plan
        for plan in gift_plans
        if plan.due_date and plan.due_date >= today and not is_terminal_status(plan.status)
    ]
    if open_plans:
        plan = min(open_plans, key=lambda item: item.due_date)
        candidates.append(
            {
                "kind": "gift_plan",
                "title": f"{plan.gift.name} → {plan.recipient_name}",
                "date": plan.due_date,
                "url": reverse("gift_manager:relation_detail", kwargs={"pk": plan.relation_id}),
            }
        )

    # Recurring events store their first date, so rank them by their next occurrence
    event_occurrences = [
        (occurrence, event)
        for event in Event.objects.accessible_by(user).filter(date__isnull=False, is_birthday=False)
        if (occurrence := event.next_occurrence(today)) is not None
    ]
    if event_occurrences:
        occurrence, event = min(event_occurrences, key=lambda pair: pair[0])
        candidates.append(
            {
                "kind": "event",
                "title": event.name,
                "date": occurrence,
                "url": reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}),
            }
        )

    if not candidates:
        return None
    item = min(candidates, key=lambda candidate: candidate["date"])
    item["days_until"] = (item["date"] - today).days
    return item


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
        action_groups = build_gift_plan_action_groups(
            gift_plans,
            user=user,
            today=today,
            now=now,
        )

        # Only plans the user can see count: a hidden surprise plan must not make a gift look
        # planned to its recipient
        unassigned_gift_count = (
            Gift.objects.accessible_by(user)
            .exclude(pk__in=Relation.objects.accessible_by(user).values("gift_id"))
            .distinct()
            .count()
        )
        context["dashboard_action_groups"] = action_groups
        context["dashboard_summary"] = build_dashboard_summary(
            action_groups,
            unassigned_gift_count,
        )

        context["upcoming_birthdays"] = build_upcoming_birthdays(user, today)

        if not action_groups:
            context["next_upcoming_item"] = _find_next_upcoming_item(gift_plans, user, today)

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

    # Search Gift Plans (by gift, recipient or event name)
    gift_plans = (
        Relation.objects.accessible_by(user)
        .with_related_objects()
        .filter(
            Q(gift__name__icontains=query)
            | Q(person__first_name__icontains=query)
            | Q(person__family_name__icontains=query)
            | Q(group__name__icontains=query)
            | Q(event__name__icontains=query)
            | birthday_event_name_q(query, "event__")
        )
        .order_by("-creation_date")[:max_per_category]
    )
    results = [
        {
            "type": "gift_plan",
            "icon": "fa-hand-holding-heart",
            "title": plan.gift.name,
            "subtitle": " · ".join(
                part
                for part in (plan.recipient_name, plan.event.name if plan.event else "")
                if part
            ),
            "url": reverse("gift_manager:relation_detail", kwargs={"pk": plan.relation_id}),
        }
        for plan in gift_plans
    ]

    # Search Gifts
    gifts = (
        Gift.objects.accessible_by(user)
        .filter(Q(name__icontains=query) | Q(comment__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    results.extend(
        {
            "type": "gift",
            "icon": "fa-gift",
            "title": gift.name,
            "subtitle": gift.comment[:50] + "..."
            if gift.comment and len(gift.comment) > 50
            else gift.comment or "",
            "url": reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id}),
        }
        for gift in gifts
    )

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
            "url": reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}),
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
            "url": reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id}),
        }
        for group in groups
    )

    # Search Events
    events = (
        Event.objects.accessible_by(user)
        .filter(
            Q(name__icontains=query) | Q(comment__icontains=query) | birthday_event_name_q(query)
        )
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
            "url": reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}),
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
            "url": reverse("gift_manager:gift_tag_detail", kwargs={"pk": tag.tag_id}),
        }
        for tag in tags
    )

    return JsonResponse({"results": results})
