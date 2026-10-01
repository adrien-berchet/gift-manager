"""Private iCalendar (RFC 5545) feed of a user's gift plans, events and birthdays.

Everything is read through ``accessible_by(user)``, so the feed only holds what the user can
see. All entries are all-day events. Events and birthdays repeat through an ``RRULE`` instead
of being expanded, so the feed stays small whatever the horizon of the calendar client.
"""

from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils import translation
from django.utils.translation import gettext

from gift_manager.models import Event
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.statuses import is_terminal_status

PRODID = "-//Gift Manager//Calendar feed//EN"
CONTENT_TYPE = "text/calendar; charset=utf-8"
MAX_LINE_OCTETS = 75
_RECURRENCE_FREQUENCIES = {
    "daily": "DAILY",
    "weekly": "WEEKLY",
    "monthly": "MONTHLY",
}


def escape_text(value: str) -> str:
    """Escape a TEXT value (RFC 5545 section 3.3.11)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold_line(line: str) -> str:
    """Fold a content line to at most 75 octets, never splitting a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= MAX_LINE_OCTETS:
        return line
    chunks = []
    current = b""
    limit = MAX_LINE_OCTETS
    for char in line:
        char_bytes = char.encode("utf-8")
        if len(current) + len(char_bytes) > limit:
            chunks.append(current.decode("utf-8"))
            current = b""
            limit = MAX_LINE_OCTETS - 1  # continuation lines start with one space
        current += char_bytes
    chunks.append(current.decode("utf-8"))
    return "\r\n ".join(chunks)


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _yearly_rule(month: int, day: int) -> str:
    """Return a yearly RRULE; a February 29 date falls on the last day of February."""
    if (month, day) == (2, 29):
        return "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"
    return f"FREQ=YEARLY;BYMONTH={month};BYMONTHDAY={day}"


def _all_day_event(
    *,
    uid: str,
    start: date,
    summary: str,
    stamp: str,
    rrule: str | None = None,
    description: str | None = None,
    url: str | None = None,
) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{_format_date(start)}",
        f"DTEND;VALUE=DATE:{_format_date(start + timedelta(days=1))}",
        f"SUMMARY:{escape_text(summary)}",
    ]
    if rrule:
        lines.append(f"RRULE:{rrule}")
    if description:
        lines.append(f"DESCRIPTION:{escape_text(description)}")
    if url:
        lines.append(f"URL:{url}")
    lines.append("TRANSP:TRANSPARENT")
    lines.append("END:VEVENT")
    return lines


def _uid_domain() -> str:
    base = settings.SITE_BASE_URL.split("://", 1)[-1]
    return base or "gift-manager.invalid"


def _absolute(path: str) -> str | None:
    return f"{settings.SITE_BASE_URL}{path}" if settings.SITE_BASE_URL else None


def _plan_entries(user, stamp: str) -> list[list[str]]:
    plans = (
        Relation.objects.accessible_by(user)
        .with_related_objects()
        .filter(due_date__isnull=False)
        .order_by("due_date", "pk")
    )
    return [
        _all_day_event(
            uid=f"plan-{plan.relation_id}@{_uid_domain()}",
            start=plan.due_date,
            summary=gettext("%(gift)s for %(recipient)s")
            % {"gift": plan.gift.name, "recipient": plan.recipient_name},
            stamp=stamp,
            description=gettext("Status: %(status)s") % {"status": plan.status},
            url=_absolute(plan.get_absolute_url()),
        )
        for plan in plans
        if not is_terminal_status(plan.status)
    ]


def _event_rule(event: Event) -> str | None:
    if not event.is_recurring:
        return None
    if event.recurrence == "yearly":
        return _yearly_rule(event.date.month, event.date.day)
    return f"FREQ={_RECURRENCE_FREQUENCIES[event.recurrence]}"


def _occasion_entries(user, stamp: str) -> list[list[str]]:
    entries = []
    for event in (
        Event.objects.accessible_by(user).filter(date__isnull=False).order_by("date", "pk")
    ):
        if not event.is_scheduled:
            continue
        entries.append(
            _all_day_event(
                uid=f"event-{event.event_id}@{_uid_domain()}",
                start=event.date,
                summary=event.name,
                stamp=stamp,
                rrule=_event_rule(event),
                description=event.comment or None,
                url=_absolute(reverse("gift_manager:event_detail", kwargs={"pk": event.event_id})),
            )
        )
    return entries


def _birthday_entries(user, today: date, stamp: str) -> list[list[str]]:
    people = Person.objects.accessible_by(user).filter(
        birthday_day__isnull=False, birthday_month__isnull=False
    )
    return [
        _all_day_event(
            uid=f"birthday-{person.person_id}@{_uid_domain()}",
            # Start at the next birthday: older occurrences would only add noise
            start=person.next_birthday(today),
            summary=gettext("Birthday of %(name)s") % {"name": person},
            stamp=stamp,
            rrule=_yearly_rule(person.birthday_month, person.birthday_day),
            url=_absolute(reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})),
        )
        for person in people.order_by("pk")
    ]


def build_calendar(user, *, today: date | None = None, now: datetime | None = None) -> str:
    """Return the iCalendar document of a user, in the language of their profile."""
    today = today or timezone.localdate()
    stamp = (now or datetime.now(dt_timezone.utc)).strftime("%Y%m%dT%H%M%SZ")

    with translation.override(user.profile.language):
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{PRODID}",
            "CALSCALE:GREGORIAN",
            f"X-WR-CALNAME:{escape_text('Gift Manager')}",
        ]
        for entry in (
            *_plan_entries(user, stamp),
            *_occasion_entries(user, stamp),
            *_birthday_entries(user, today, stamp),
        ):
            lines.extend(entry)
        lines.append("END:VCALENDAR")

    return "".join(f"{fold_line(line)}\r\n" for line in lines)
