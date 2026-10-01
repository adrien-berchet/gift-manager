"""Tests for the private iCalendar feed."""

from datetime import date
from datetime import timedelta

import pytest
from django.urls import reverse
from icalendar import Calendar

from gift_manager.calendar_feed import build_calendar
from gift_manager.calendar_feed import escape_text
from gift_manager.calendar_feed import fold_line
from gift_manager.models import Event
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

TODAY = date(2026, 9, 30)


def parse(user, today=TODAY):
    """Parse the feed of a user with a standard iCalendar parser."""
    return Calendar.from_ical(build_calendar(user, today=today))


def events_by_uid_prefix(calendar, prefix):
    return [e for e in calendar.walk("VEVENT") if str(e["UID"]).startswith(prefix)]


def plan_for(user, *, due, status="Planned", **kwargs):
    return RelationFactory(
        due_date=due,
        status=RelationStatusFactory(status=status),
        shared_with=[user],
        **kwargs,
    )


@pytest.mark.django_db
class TestDocument:
    def test_empty_calendar_is_valid(self, user):
        calendar = parse(user)

        assert calendar["VERSION"] == "2.0"
        assert "PRODID" in calendar
        assert list(calendar.walk("VEVENT")) == []

    def test_uses_crlf_line_endings(self, user):
        assert build_calendar(user, today=TODAY).endswith("END:VCALENDAR\r\n")
        assert "\n" not in build_calendar(user, today=TODAY).replace("\r\n", "")

    def test_plan_is_an_all_day_event_on_its_due_date(self, user):
        plan = plan_for(user, due=TODAY + timedelta(days=3), gift=GiftFactory(name="Red scarf"))

        (event,) = events_by_uid_prefix(parse(user), "plan-")

        assert event["UID"].startswith(f"plan-{plan.relation_id}@")
        assert event["DTSTART"].dt == TODAY + timedelta(days=3)
        assert event["DTEND"].dt == TODAY + timedelta(days=4)
        assert "Red scarf" in event["SUMMARY"]

    def test_plans_without_due_date_or_already_finished_are_left_out(self, user):
        plan_for(user, due=None)
        plan_for(user, due=TODAY, status="Given")
        plan_for(user, due=TODAY, status="Abandoned")

        assert events_by_uid_prefix(parse(user), "plan-") == []

    def test_one_time_event(self, user):
        EventFactory(
            name="Party",
            schedule_type=Event.ScheduleType.ONE_TIME,
            recurrence=None,
            date=date(2026, 12, 1),
            shared_with=[user],
        )

        (event,) = events_by_uid_prefix(parse(user), "event-")

        assert event["DTSTART"].dt == date(2026, 12, 1)
        assert "RRULE" not in event

    @pytest.mark.parametrize(
        ("recurrence", "freq"),
        [("daily", "DAILY"), ("weekly", "WEEKLY"), ("monthly", "MONTHLY"), ("yearly", "YEARLY")],
    )
    def test_recurring_event_uses_an_rrule(self, user, recurrence, freq):
        EventFactory(date=date(2026, 3, 14), recurrence=recurrence, shared_with=[user])

        (event,) = events_by_uid_prefix(parse(user), "event-")

        assert event["RRULE"]["FREQ"] == [freq]

    def test_unscheduled_events_are_left_out(self, user):
        EventFactory(
            schedule_type=Event.ScheduleType.UNSCHEDULED,
            recurrence=None,
            date=None,
            shared_with=[user],
        )

        assert events_by_uid_prefix(parse(user), "event-") == []

    def test_birthday_repeats_yearly_from_the_next_one(self, user):
        person = PersonFactory(
            first_name="Anna",
            birthday_day=5,
            birthday_month=10,
            birthday_year=1990,
            shared_with=[user],
        )

        (event,) = events_by_uid_prefix(parse(user), "birthday-")

        assert event["UID"].startswith(f"birthday-{person.person_id}@")
        assert event["DTSTART"].dt == date(2026, 10, 5)
        assert event["RRULE"]["FREQ"] == ["YEARLY"]
        assert "Anna" in event["SUMMARY"]

    def test_february_29_birthday_falls_on_the_last_day_of_february(self, user):
        PersonFactory(birthday_day=29, birthday_month=2, shared_with=[user])

        (event,) = events_by_uid_prefix(parse(user), "birthday-")

        assert event["RRULE"]["BYMONTH"] == [2]
        assert event["RRULE"]["BYMONTHDAY"] == [-1]
        assert event["DTSTART"].dt == date(2027, 2, 28)

    def test_summary_text_is_escaped_and_survives_a_round_trip(self, user):
        gift = GiftFactory(name="Tea, coffee; and more\\")
        plan_for(user, due=TODAY, gift=gift)

        (event,) = events_by_uid_prefix(parse(user), "plan-")

        assert "Tea, coffee; and more\\" in event["SUMMARY"]

    def test_long_non_ascii_lines_are_folded_on_character_boundaries(self, user):
        gift = GiftFactory(name="Écharpe en laine d'agneau " * 8)
        plan_for(user, due=TODAY, gift=gift)

        document = build_calendar(user, today=TODAY)

        assert all(len(line.encode("utf-8")) <= 75 for line in document.split("\r\n"))
        (event,) = events_by_uid_prefix(Calendar.from_ical(document), "plan-")
        assert "Écharpe en laine d'agneau" in event["SUMMARY"]

    def test_feed_is_rendered_in_the_language_of_the_profile(self, user):
        user.profile.preferred_language = "fr"
        user.profile.save()
        PersonFactory(first_name="Anna", birthday_day=5, birthday_month=10, shared_with=[user])

        (event,) = events_by_uid_prefix(parse(user), "birthday-")

        assert "Anniversaire" in event["SUMMARY"]


@pytest.mark.django_db
class TestPermissionFiltering:
    def test_nothing_the_user_cannot_see_is_in_the_feed(self, user):
        stranger = UserFactory()
        plan_for(stranger, due=TODAY)
        EventFactory(date=TODAY, shared_with=[stranger])
        PersonFactory(birthday_day=5, birthday_month=10, shared_with=[stranger])

        assert list(parse(user).walk("VEVENT")) == []

    def test_global_birthday_event_is_not_a_calendar_entry(self, user):
        Event.objects.get_birthday_event()

        assert list(parse(user).walk("VEVENT")) == []


@pytest.mark.django_db
class TestHelpers:
    def test_escape_text(self):
        assert escape_text("a,b;c\\d\ne") == r"a\,b\;c\\d\ne"

    def test_fold_line_keeps_short_lines(self):
        assert fold_line("SUMMARY:short") == "SUMMARY:short"


@pytest.mark.django_db
class TestFeedView:
    def feed_url(self, token):
        return reverse("gift_manager:calendar_feed", kwargs={"token": token})

    def test_feed_is_served_with_the_token(self, client, user):
        plan_for(user, due=date.today() + timedelta(days=2))
        token = user.profile.regenerate_calendar_token()

        response = client.get(self.feed_url(token))

        assert response.status_code == 200
        assert response["Content-Type"] == "text/calendar; charset=utf-8"
        assert response["Cache-Control"] == "private, no-store"
        assert response["Referrer-Policy"] == "no-referrer"
        assert len(list(Calendar.from_ical(response.content).walk("VEVENT"))) == 1

    def test_feed_does_not_need_a_session(self, client, user):
        token = user.profile.regenerate_calendar_token()

        assert client.get(self.feed_url(token)).status_code == 200

    def test_unknown_token_is_not_found(self, client, user):
        user.profile.regenerate_calendar_token()

        assert client.get(self.feed_url("not-the-token")).status_code == 404

    def test_disabled_feed_is_not_found(self, client, user):
        token = user.profile.regenerate_calendar_token()
        user.profile.clear_calendar_token()

        assert client.get(self.feed_url(token)).status_code == 404

    def test_regenerating_the_token_invalidates_the_old_url(self, client, user):
        old = user.profile.regenerate_calendar_token()
        new = user.profile.regenerate_calendar_token()

        assert old != new
        assert client.get(self.feed_url(old)).status_code == 404
        assert client.get(self.feed_url(new)).status_code == 200

    def test_inactive_user_feed_is_not_found(self, client, user):
        token = user.profile.regenerate_calendar_token()
        user.is_active = False
        user.save()

        assert client.get(self.feed_url(token)).status_code == 404

    def test_feed_only_accepts_get(self, client, user):
        token = user.profile.regenerate_calendar_token()

        assert client.post(self.feed_url(token)).status_code == 405

    def test_each_token_serves_its_own_user(self, client, user):
        other = UserFactory()
        plan_for(other, due=date.today() + timedelta(days=2))
        token = user.profile.regenerate_calendar_token()

        events = list(Calendar.from_ical(client.get(self.feed_url(token)).content).walk("VEVENT"))

        assert events == []
