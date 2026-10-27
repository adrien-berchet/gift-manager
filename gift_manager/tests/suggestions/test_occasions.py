"""Tests for upcoming occasions derivation used in AI suggestion steering."""

from datetime import date
from datetime import timedelta

import pytest

from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.suggestions.occasions import get_upcoming_occasions
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_upcoming_occasions_includes_person_birthday(user, share):
    today = date(2026, 10, 20)
    # Person with birthday in 15 days (Nov 4)
    person = PersonFactory(birthday_day=4, birthday_month=11, birthday_year=1990)
    share(user, person, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) >= 1
    birthday_occ = next((o for o in occasions if o.get("is_birthday")), None)
    assert birthday_occ is not None
    assert birthday_occ["name"] == "Birthday"
    assert birthday_occ["days_until"] == 15
    assert birthday_occ["date"] == date(2026, 11, 4)


def test_upcoming_occasions_includes_accessible_scheduled_events(user, share):
    today = date(2026, 10, 20)
    person = PersonFactory(birthday_day=None, birthday_month=None)
    share(user, person, level=PermissionLevel.VIEWER)

    # Recurring yearly event "Christmas" in 66 days
    christmas = EventFactory(
        name="Christmas",
        schedule_type=Event.ScheduleType.RECURRING,
        recurrence="yearly",
        date=date(2025, 12, 25),
        is_birthday=False,
    )
    share(user, christmas, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) == 1
    assert occasions[0]["name"] == "Christmas"
    assert occasions[0]["days_until"] == 66
    assert occasions[0]["date"] == date(2026, 12, 25)


def test_upcoming_occasions_orders_soonest_first(user, share):
    today = date(2026, 10, 20)
    # Birthday in 10 days
    person = PersonFactory(birthday_day=30, birthday_month=10, birthday_year=1995)
    share(user, person, level=PermissionLevel.VIEWER)

    # Event in 5 days
    halloween = EventFactory(
        name="Halloween Party",
        schedule_type=Event.ScheduleType.ONE_TIME,
        date=date(2026, 10, 25),
        is_birthday=False,
    )
    share(user, halloween, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) == 2
    assert occasions[0]["name"] == "Halloween Party"
    assert occasions[0]["days_until"] == 5
    assert occasions[1]["name"] == "Birthday"
    assert occasions[1]["days_until"] == 10


def test_upcoming_occasions_for_group_skips_birthday(user, share):
    today = date(2026, 10, 20)
    group = PersonGroupFactory()
    share(user, group, level=PermissionLevel.VIEWER)

    event = EventFactory(
        name="Family Gathering",
        schedule_type=Event.ScheduleType.ONE_TIME,
        date=date(2026, 11, 1),
        is_birthday=False,
    )
    share(user, event, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, group, today=today)
    assert len(occasions) == 1
    assert occasions[0]["name"] == "Family Gathering"
    assert occasions[0]["days_until"] == 12


def test_upcoming_occasions_excludes_inaccessible_events(user, share):
    today = date(2026, 10, 20)
    person = PersonFactory(birthday_day=None, birthday_month=None)
    share(user, person, level=PermissionLevel.VIEWER)

    # Event shared with another user only
    other_user = UserFactory()
    secret_event = EventFactory(
        name="Secret Party",
        schedule_type=Event.ScheduleType.ONE_TIME,
        date=date(2026, 10, 25),
        is_birthday=False,
    )
    share(other_user, secret_event, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) == 0


def test_upcoming_occasions_person_birthday_without_year(user, share):
    today = date(2026, 10, 20)
    person = PersonFactory(birthday_day=25, birthday_month=10, birthday_year=None)
    share(user, person, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) == 1
    assert occasions[0]["name"] == "Birthday"
    assert occasions[0]["days_until"] == 5
    assert occasions[0]["date"] == date(2026, 10, 25)


def test_upcoming_occasions_december_to_january_rollover(user, share):
    today = date(2026, 12, 28)
    person = PersonFactory(birthday_day=5, birthday_month=1, birthday_year=1995)
    share(user, person, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today)
    assert len(occasions) == 1
    assert occasions[0]["name"] == "Birthday"
    assert occasions[0]["days_until"] == 8
    assert occasions[0]["date"] == date(2027, 1, 5)


def test_upcoming_occasions_respects_limit(user, share):
    today = date(2026, 10, 20)
    person = PersonFactory(birthday_day=None, birthday_month=None)
    share(user, person, level=PermissionLevel.VIEWER)

    for i in range(10):
        ev = EventFactory(
            name=f"Event {i}",
            schedule_type=Event.ScheduleType.ONE_TIME,
            date=today + timedelta(days=i + 1),
            is_birthday=False,
        )
        share(user, ev, level=PermissionLevel.VIEWER)

    occasions = get_upcoming_occasions(user, person, today=today, limit=4)
    assert len(occasions) == 4
