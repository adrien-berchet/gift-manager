"""Derive upcoming occasions and events for suggestion steering."""

from datetime import date
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext as _

from gift_manager.models import Event
from gift_manager.models import Person
from gift_manager.models import PersonGroup


def get_upcoming_occasions(
    user: User,
    recipient: Person | PersonGroup,
    today: date | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Return soonest upcoming occasions (birthday, accessible scheduled events) within a year."""
    if today is None:
        today = timezone.localdate()

    candidates: list[dict[str, Any]] = []

    # 1. Birthday (for Person with birthday recorded)
    if isinstance(recipient, Person) and recipient.has_birthday:
        bday = recipient.next_birthday(today)
        if bday:
            days = (bday - today).days
            if 0 <= days <= 365:
                candidates.append(
                    {
                        "name": str(_("Birthday")),
                        "date": bday,
                        "days_until": days,
                        "is_birthday": True,
                    }
                )

    # 2. Accessible scheduled events (excluding birthday event to avoid duplicate)
    events = (
        Event.objects.accessible_by(user)
        .filter(date__isnull=False, is_birthday=False)
        .only("name", "date", "schedule_type", "recurrence")
    )
    for event in events:
        occ = event.next_occurrence(today)
        if occ is not None:
            days = (occ - today).days
            if 0 <= days <= 365:
                candidates.append(
                    {
                        "name": event.name,
                        "date": occ,
                        "days_until": days,
                        "is_birthday": False,
                    }
                )

    candidates.sort(key=lambda c: (c["days_until"], c["name"].lower()))

    seen_names: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for cand in candidates:
        norm = cand["name"].casefold()
        if norm not in seen_names:
            seen_names.add(norm)
            deduped.append(cand)
            if len(deduped) >= limit:
                break

    return deduped


def derive_default_occasion(occasions: list[dict[str, Any]], max_days: int = 60) -> str:
    """Return the name of the soonest occasion if within max_days, otherwise empty string."""
    if occasions and occasions[0]["days_until"] <= max_days:
        return occasions[0]["name"]
    return ""
