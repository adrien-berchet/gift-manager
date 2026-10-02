"""Reminder digest: what needs a user's attention in the coming days.

The digest reuses the dashboard rules instead of re-implementing urgency: overdue and
due-soon gift plans come from ``_build_gift_plan_action_groups`` (with the user's lookahead
as the "due soon" window) and birthdays from ``build_upcoming_birthdays``. Everything is read
through ``accessible_by(user)`` at build time, so nothing the user lost access to can leak.
"""

from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils import timezone

from gift_manager.birthdays import PLAN_COVERAGE_DAYS
from gift_manager.birthdays import build_upcoming_birthdays
from gift_manager.models import Event
from gift_manager.models import Relation
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_terminal_status
from gift_manager.views.common import _build_gift_plan_action_groups

UNSUBSCRIBE_SALT = "gift_manager.digest_unsubscribe"
# Daily, weekly and monthly events would show up in every digest: only the ones that really
# are occasions (one-time, yearly) are listed. The calendar feed carries all of them.
DIGEST_EVENT_RECURRENCES = frozenset({"yearly"})


@dataclass
class Digest:
    """Content of one reminder email."""

    today: date
    lookahead_days: int
    overdue: list[Relation] = field(default_factory=list)
    due_soon: list[Relation] = field(default_factory=list)
    birthdays: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.overdue or self.due_soon or self.birthdays or self.events)


def absolute_url(path: str) -> str:
    """Return an absolute URL for a path, from ``SITE_BASE_URL``."""
    if not settings.SITE_BASE_URL:
        msg = "SITE_BASE_URL must be set to build absolute links outside a request."
        raise ImproperlyConfigured(msg)
    return f"{settings.SITE_BASE_URL}{path}"


def make_unsubscribe_token(user) -> str:
    """Return the signed token embedded in the digest unsubscribe link."""
    return signing.dumps(user.pk, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> int | None:
    """Return the user id held by an unsubscribe token, or None when it is not valid."""
    try:
        user_id = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return user_id if isinstance(user_id, int) else None


def unsubscribe_url(user) -> str:
    """Return the absolute unsubscribe URL for a user."""
    path = reverse("gift_manager:digest_unsubscribe", args=[make_unsubscribe_token(user)])
    return absolute_url(path)


def _plan_covers_event(relation: Relation, occurrence: date) -> bool:
    """Return whether a plan counts as covering one occurrence of an event.

    Abandoned plans never do. A dated plan covers the occurrence when it is due up to
    ``PLAN_COVERAGE_DAYS`` before it or on it (so a plan given for last year's occurrence does
    not hide the next one); an undated plan only while it is still open.
    """
    if is_abandoned_status(relation.status):
        return False
    if relation.due_date is None:
        return not is_terminal_status(relation.status)
    return occurrence - timedelta(days=PLAN_COVERAGE_DAYS) <= relation.due_date <= occurrence


def build_unplanned_events(user, today: date, lookahead_days: int) -> list[dict]:
    """Return the events happening within the window that have no gift plan yet.

    Only the next occurrence of an event is considered, never the ones after it, and only
    one-time and yearly events. Events the user cannot access are never listed.
    """
    horizon = today + timedelta(days=lookahead_days)
    candidates = []
    for event in Event.objects.accessible_by(user).filter(date__isnull=False):
        if not event.is_scheduled:
            continue
        if event.is_recurring and event.recurrence not in DIGEST_EVENT_RECURRENCES:
            continue
        occurrence = event.next_occurrence(today)
        if occurrence is not None and occurrence <= horizon:
            candidates.append((occurrence, event))
    if not candidates:
        return []

    plans = (
        Relation.objects.accessible_by(user)
        .filter(event__in=[event.pk for _, event in candidates])
        .select_related("status")
    )
    plans_by_event: dict[int, list[Relation]] = {}
    for plan in plans:
        plans_by_event.setdefault(plan.event_id, []).append(plan)

    items = [
        {
            "event": event,
            "date": occurrence,
            "days_until": (occurrence - today).days,
            "url": reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}),
        }
        for occurrence, event in candidates
        if not any(
            _plan_covers_event(plan, occurrence) for plan in plans_by_event.get(event.pk, [])
        )
    ]
    return sorted(items, key=lambda item: (item["date"], item["event"].name.lower()))


def build_digest(user, today: date | None = None, lookahead_days: int | None = None) -> Digest:
    """Build the digest of a user, with the lookahead of their profile by default.

    Call it with the recipient's language active so labels are translated for them.
    """
    today = today or timezone.localdate()
    if lookahead_days is None:
        lookahead_days = user.profile.digest_lookahead_days
    now = timezone.now()

    plans = list(
        Relation.objects.accessible_by(user)
        .with_related_objects()
        .order_by("due_date", "creation_date", "gift__name")
    )
    groups = {
        group["key"]: [item["relation"] for item in group["items"]]
        for group in _build_gift_plan_action_groups(
            plans, user=user, today=today, now=now, due_soon_days=lookahead_days
        )
    }
    return Digest(
        today=today,
        lookahead_days=lookahead_days,
        overdue=groups.get("overdue", []),
        due_soon=groups.get("upcoming", []),
        birthdays=build_upcoming_birthdays(user, today, window_days=lookahead_days),
        events=build_unplanned_events(user, today, lookahead_days),
    )
