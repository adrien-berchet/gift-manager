"""Computed birthday occasions.

Birthdays are never stored as ``Event`` rows: they are derived from the optional birthday
of each ``Person`` the user can view, so the number of events does not grow with the
number of people or years. Gift plans created for a birthday point at the global
Birthday event (``Event.objects.get_birthday_event``) and use the next birthday as due date.
"""

from datetime import date
from datetime import timedelta
from urllib.parse import urlencode

from django.urls import reverse

from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.statuses import is_abandoned_status

UPCOMING_BIRTHDAYS_DAYS = 30
# A plan due up to this long before a birthday (bought early, or overdue) still covers it
PLAN_COVERAGE_DAYS = 60
BIRTHDAY_FOR_PARAM = "birthday_for"


def birthday_plan_url(person: Person) -> str:
    """Return the gift plan creation URL pre-filled for a person's next birthday."""
    query = urlencode({BIRTHDAY_FOR_PARAM: person.person_id})
    return f"{reverse('gift_manager:relation_create')}?{query}"


def _covering_due_dates(user, people: list[Person], since: date, until: date) -> dict:
    """Return, per person pk, the (due date, uses Birthday event) of their live plans.

    Only plans the user can see count, and abandoned plans never cover a birthday.
    """
    plans = (
        Relation.objects.accessible_by(user)
        .filter(person_id__in=[person.pk for person in people], due_date__range=(since, until))
        .select_related("status", "event")
    )
    due_dates: dict[int, list[tuple[date, bool]]] = {}
    for plan in plans:
        if is_abandoned_status(plan.status):
            continue
        is_birthday_event = plan.event is not None and plan.event.is_birthday
        due_dates.setdefault(plan.person_id, []).append((plan.due_date, is_birthday_event))
    return due_dates


def build_upcoming_birthdays(
    user, today: date, *, window_days: int = UPCOMING_BIRTHDAYS_DAYS
) -> list[dict]:
    """Return the birthdays of people the user can view within the coming window.

    Items are ordered by next occurrence (today included), then by name. Each item tells
    whether a gift plan already covers that birthday: a live (not abandoned) plan for the
    person, visible to the user, due up to ``PLAN_COVERAGE_DAYS`` before the birthday or on
    it, that uses the Birthday event or is due exactly on the birthday. Plans without a due
    date, or addressed to a group the person belongs to, are not counted.
    """
    horizon = today + timedelta(days=window_days)
    people = (
        Person.objects.accessible_by(user)
        .filter(birthday_day__isnull=False, birthday_month__isnull=False)
        .only(
            "person_id",
            "first_name",
            "family_name",
            "birthday_day",
            "birthday_month",
            "birthday_year",
        )
    )
    upcoming = []
    for person in people:
        occurrence = person.next_birthday(today)
        if occurrence <= horizon:
            upcoming.append((occurrence, person))
    if not upcoming:
        return []

    due_dates = _covering_due_dates(
        user,
        [person for _, person in upcoming],
        since=today - timedelta(days=PLAN_COVERAGE_DAYS),
        until=horizon,
    )

    items = []
    for occurrence, person in sorted(
        upcoming, key=lambda entry: (entry[0], entry[1].first_name.lower(), entry[1].pk)
    ):
        days_until = (occurrence - today).days
        items.append(
            {
                "person": person,
                "date": occurrence,
                "days_until": days_until,
                "is_today": days_until == 0,
                "has_plan": any(
                    occurrence - timedelta(days=PLAN_COVERAGE_DAYS) <= due_date <= occurrence
                    and (is_birthday_event or due_date == occurrence)
                    for due_date, is_birthday_event in due_dates.get(person.pk, [])
                ),
                "create_url": birthday_plan_url(person),
            }
        )
    return items
