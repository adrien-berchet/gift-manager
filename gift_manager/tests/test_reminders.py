"""Tests for the reminder digest builder (selection, permissions and signed links)."""

from datetime import date
from datetime import timedelta

import pytest
from django.core import signing

from gift_manager.models import Event
from gift_manager.reminders import build_digest
from gift_manager.reminders import build_unplanned_events
from gift_manager.reminders import make_unsubscribe_token
from gift_manager.reminders import read_unsubscribe_token
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

TODAY = date(2026, 9, 30)


def make_plan(user, *, due_in=None, status="Planned", **kwargs):
    """Create a plan visible to user, due ``due_in`` days from TODAY (no due date if None)."""
    return RelationFactory(
        due_date=None if due_in is None else TODAY + timedelta(days=due_in),
        status=RelationStatusFactory(status=status),
        shared_with=[user],
        **kwargs,
    )


@pytest.mark.django_db
class TestPlanSelection:
    def test_overdue_and_due_soon_plans_are_listed(self, user):
        overdue = make_plan(user, due_in=-3)
        due_soon = make_plan(user, due_in=5)

        digest = build_digest(user, TODAY, 7)

        assert digest.overdue == [overdue]
        assert digest.due_soon == [due_soon]
        assert not digest.is_empty

    @pytest.mark.parametrize(("lookahead", "expected"), [(7, 0), (14, 1), (30, 1)])
    def test_lookahead_widens_the_due_soon_window(self, user, lookahead, expected):
        make_plan(user, due_in=12)

        assert len(build_digest(user, TODAY, lookahead).due_soon) == expected

    def test_plans_beyond_the_window_are_not_listed(self, user):
        make_plan(user, due_in=45)

        assert build_digest(user, TODAY, 30).is_empty

    @pytest.mark.parametrize("status", ["Given", "Abandoned"])
    def test_finished_plans_are_not_listed(self, user, status):
        make_plan(user, due_in=-3, status=status)

        assert build_digest(user, TODAY, 14).overdue == []

    def test_nothing_to_report_is_an_empty_digest(self, user):
        assert build_digest(user, TODAY, 14).is_empty

    def test_default_lookahead_comes_from_the_profile(self, user):
        user.profile.digest_lookahead_days = 30
        user.profile.save()
        make_plan(user, due_in=25)

        assert len(build_digest(user, TODAY).due_soon) == 1


@pytest.mark.django_db
class TestPermissionFiltering:
    def test_plans_of_other_users_are_never_listed(self, user):
        stranger = UserFactory()
        RelationFactory(
            due_date=TODAY - timedelta(days=2),
            status=RelationStatusFactory(status="Planned"),
            shared_with=[stranger],
        )

        assert build_digest(user, TODAY, 14).is_empty

    def test_a_plan_stops_being_listed_when_access_is_revoked(self, user):
        plan = make_plan(user, due_in=-1)
        assert build_digest(user, TODAY, 14).overdue == [plan]

        plan.relationpermission_set.filter(user=user).delete()

        assert build_digest(user, TODAY, 14).is_empty

    def test_birthdays_of_people_the_user_cannot_see_are_never_listed(self, user):
        PersonFactory(first_name="Hidden", birthday_day=5, birthday_month=10, shared_with=None)

        assert build_digest(user, TODAY, 30).birthdays == []

    def test_events_the_user_cannot_see_are_never_listed(self, user):
        EventFactory(date=TODAY + timedelta(days=3), recurrence="yearly")

        assert build_digest(user, TODAY, 14).events == []


@pytest.mark.django_db
class TestBirthdays:
    def test_upcoming_birthdays_are_listed_with_plan_coverage(self, user):
        person = PersonFactory(
            first_name="Anna", birthday_day=5, birthday_month=10, shared_with=[user]
        )

        digest = build_digest(user, TODAY, 14)

        assert [item["person"] for item in digest.birthdays] == [person]
        assert digest.birthdays[0]["has_plan"] is False

    def test_birthdays_follow_the_lookahead(self, user):
        PersonFactory(birthday_day=20, birthday_month=10, shared_with=[user])

        assert build_digest(user, TODAY, 14).birthdays == []
        assert len(build_digest(user, TODAY, 30).birthdays) == 1


@pytest.mark.django_db
class TestUnplannedEvents:
    def test_event_without_a_plan_is_listed(self, user):
        event = EventFactory(date=TODAY + timedelta(days=4), shared_with=[user])

        items = build_unplanned_events(user, TODAY, 14)

        assert [item["event"] for item in items] == [event]
        assert items[0]["date"] == TODAY + timedelta(days=4)

    def test_only_the_next_occurrence_of_a_recurring_event_is_considered(self, user):
        # Christmas-like yearly event first set up in 2020: the next one is in the window,
        # the ones after it never are
        EventFactory(
            name="Christmas", date=date(2020, 10, 5), recurrence="yearly", shared_with=[user]
        )

        items = build_unplanned_events(user, TODAY, 14)

        assert [item["date"] for item in items] == [date(2026, 10, 5)]

    def test_event_with_its_next_occurrence_out_of_the_window_is_not_listed(self, user):
        EventFactory(date=date(2020, 12, 25), recurrence="yearly", shared_with=[user])

        assert build_unplanned_events(user, TODAY, 14) == []

    @pytest.mark.parametrize("recurrence", ["daily", "weekly", "monthly"])
    def test_frequent_recurrences_are_not_listed(self, user, recurrence):
        EventFactory(date=TODAY - timedelta(days=100), recurrence=recurrence, shared_with=[user])

        assert build_unplanned_events(user, TODAY, 14) == []

    def test_one_time_event_in_the_past_is_not_listed(self, user):
        EventFactory(
            schedule_type=Event.ScheduleType.ONE_TIME,
            recurrence=None,
            date=TODAY - timedelta(days=2),
            shared_with=[user],
        )

        assert build_unplanned_events(user, TODAY, 14) == []

    def test_unscheduled_events_are_not_listed(self, user):
        EventFactory(
            schedule_type=Event.ScheduleType.UNSCHEDULED,
            recurrence=None,
            date=None,
            shared_with=[user],
        )

        assert build_unplanned_events(user, TODAY, 14) == []

    def test_event_with_a_live_plan_is_not_listed(self, user):
        event = EventFactory(date=TODAY + timedelta(days=4), shared_with=[user])
        make_plan(user, due_in=4, event=event)

        assert build_unplanned_events(user, TODAY, 14) == []

    def test_event_with_an_open_undated_plan_is_not_listed(self, user):
        event = EventFactory(date=TODAY + timedelta(days=4), shared_with=[user])
        make_plan(user, due_in=None, event=event)

        assert build_unplanned_events(user, TODAY, 14) == []

    def test_abandoned_plan_does_not_cover_the_event(self, user):
        event = EventFactory(date=TODAY + timedelta(days=4), shared_with=[user])
        make_plan(user, due_in=4, status="Abandoned", event=event)

        assert len(build_unplanned_events(user, TODAY, 14)) == 1

    def test_plan_given_for_last_years_occurrence_does_not_hide_this_one(self, user):
        event = EventFactory(date=date(2020, 10, 5), recurrence="yearly", shared_with=[user])
        make_plan(user, due_in=-300, status="Given", event=event)
        make_plan(user, due_in=None, status="Given", event=event)

        assert len(build_unplanned_events(user, TODAY, 14)) == 1

    def test_plan_the_user_cannot_see_does_not_cover_the_event(self, user):
        event = EventFactory(date=TODAY + timedelta(days=4), shared_with=[user])
        RelationFactory(
            event=event,
            due_date=TODAY + timedelta(days=4),
            status=RelationStatusFactory(status="Planned"),
            shared_with=[UserFactory()],
        )

        assert len(build_unplanned_events(user, TODAY, 14)) == 1

    def test_events_are_ordered_by_date(self, user):
        later = EventFactory(date=TODAY + timedelta(days=9), shared_with=[user])
        sooner = EventFactory(date=TODAY + timedelta(days=2), shared_with=[user])

        items = build_unplanned_events(user, TODAY, 14)

        assert [item["event"] for item in items] == [sooner, later]


@pytest.mark.django_db
class TestUnsubscribeToken:
    def test_round_trip(self, user):
        assert read_unsubscribe_token(make_unsubscribe_token(user)) == user.pk

    def test_tampered_token_is_rejected(self, user):
        token = make_unsubscribe_token(user)

        assert read_unsubscribe_token(token[:-2] + "xx") is None
        assert read_unsubscribe_token("garbage") is None

    def test_token_signed_for_another_purpose_is_rejected(self, user):
        assert read_unsubscribe_token(signing.dumps(user.pk, salt="other")) is None
