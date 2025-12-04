"""Common utilities and type definitions for views."""

from typing import TypeAlias

from django.contrib.auth.models import User
from django.db.models import Model
from django.shortcuts import render

from ..models import Event
from ..models import Gift
from ..models import Person
from ..models import PersonGroup
from ..models import Relation

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
    """Home page view."""
    return render(request, "gift_manager/home.html")
