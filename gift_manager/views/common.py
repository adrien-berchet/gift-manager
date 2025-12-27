"""Common utilities and type definitions for views."""

from datetime import timedelta
from typing import TypeAlias

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus

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


def home(request):
    """Home page view with dashboard."""
    context = {}

    if request.user.is_authenticated:
        user = request.user

        # Statistics
        context["stats"] = {
            "persons": Person.objects.accessible_by(user).count(),
            "groups": PersonGroup.objects.accessible_by(user).count(),
            "gifts": Gift.objects.accessible_by(user).count(),
            "events": Event.objects.accessible_by(user).count(),
            "relations": Relation.objects.accessible_by(user).count(),
        }

        # Recent gifts (last 5)
        context["recent_gifts"] = (
            Gift.objects.accessible_by(user).order_by("-creation_date")[:5]
        )

        # Upcoming due dates (next 30 days)
        today = timezone.now().date()
        thirty_days = today + timedelta(days=30)
        context["upcoming_giftings"] = (
            Relation.objects.accessible_by(user)
            .filter(due_date__gte=today, due_date__lte=thirty_days)
            .select_related("gift", "person", "group", "status", "event")
            .order_by("due_date")[:5]
        )

        # Giftings by status
        statuses = RelationStatus.objects.all()
        status_counts = []
        for status in statuses:
            count = Relation.objects.accessible_by(user).filter(status=status).count()
            if count > 0:
                status_counts.append({"status": status, "count": count})
        context["status_counts"] = status_counts

        # Recent persons (last 5)
        context["recent_persons"] = (
            Person.objects.accessible_by(user).order_by("-creation_date")[:5]
        )

    return render(request, "gift_manager/home.html", context)


@login_required
@require_GET
def global_search(request):
    """Global search API endpoint."""
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse({"results": []})

    user = request.user
    results = []
    max_per_category = 5

    # Search Gifts
    gifts = (
        Gift.objects.accessible_by(user)
        .filter(Q(name__icontains=query) | Q(comment__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    for gift in gifts:
        results.append({
            "type": "gift",
            "icon": "fa-gift",
            "title": gift.name,
            "subtitle": gift.comment[:50] + "..." if gift.comment and len(gift.comment) > 50 else gift.comment or "",
            "url": f"/gifts/{gift.gift_id}/",
        })

    # Search Persons
    persons = (
        Person.objects.accessible_by(user)
        .filter(Q(first_name__icontains=query) | Q(family_name__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    for person in persons:
        results.append({
            "type": "person",
            "icon": "fa-user",
            "title": str(person),
            "subtitle": "",
            "url": f"/persons/{person.person_id}/",
        })

    # Search Person Groups
    groups = (
        PersonGroup.objects.accessible_by(user)
        .filter(name__icontains=query)
        .order_by("-creation_date")[:max_per_category]
    )
    for group in groups:
        results.append({
            "type": "group",
            "icon": "fa-layer-group",
            "title": group.name,
            "subtitle": "",
            "url": f"/person_groups/{group.group_id}/",
        })

    # Search Events
    events = (
        Event.objects.accessible_by(user)
        .filter(Q(name__icontains=query) | Q(comment__icontains=query))
        .order_by("-creation_date")[:max_per_category]
    )
    for event in events:
        results.append({
            "type": "event",
            "icon": "fa-calendar-alt",
            "title": event.name,
            "subtitle": event.comment[:50] + "..." if event.comment and len(event.comment) > 50 else event.comment or "",
            "url": f"/events/{event.event_id}/",
        })

    # Search Gift Tags
    tags = (
        GiftTag.objects.accessible_by(user)
        .filter(name__icontains=query)
        .order_by("-creation_date")[:max_per_category]
    )
    for tag in tags:
        results.append({
            "type": "tag",
            "icon": "fa-tag",
            "title": tag.name,
            "subtitle": "",
            "url": f"/gift-tag/{tag.tag_id}/",
        })

    return JsonResponse({"results": results})
