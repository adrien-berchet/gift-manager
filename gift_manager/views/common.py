"""Common utilities and type definitions for views."""

from datetime import timedelta
from typing import TypeAlias

from django.contrib.auth.models import User
from django.db.models import Model
from django.shortcuts import render
from django.utils import timezone

from gift_manager.models import Event
from gift_manager.models import Gift
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
