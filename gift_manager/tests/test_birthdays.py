"""Tests for person birthdays, computed occasions and the global Birthday event."""

import importlib
from datetime import date
from datetime import timedelta

import pytest
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.utils import translation

from gift_manager.birthdays import build_upcoming_birthdays
from gift_manager.models import Event
from gift_manager.models import EventPermission
from gift_manager.models import EventQuerySet
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import birthday_event_name_q
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import PermissionService
from gift_manager.sharing_service import SharingService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

TODAY = date(2026, 9, 30)


def make_person(user=None, *, day=None, month=None, year=None, **kwargs):
    """Create a person (visible to user when given) with an optional birthday."""
    return PersonFactory(
        birthday_day=day,
        birthday_month=month,
        birthday_year=year,
        shared_with=[user] if user else None,
        **kwargs,
    )


@pytest.mark.django_db
class TestPersonBirthday:
    def test_person_without_birthday(self):
        person = make_person()

        assert person.has_birthday is False
        assert person.next_birthday(TODAY) is None
        assert person.birthday_display == ""

    def test_next_birthday_later_this_year(self):
        person = make_person(day=15, month=11)

        assert person.next_birthday(TODAY) == date(2026, 11, 15)

    def test_next_birthday_today_counts(self):
        person = make_person(day=30, month=9)

        assert person.next_birthday(TODAY) == TODAY

    def test_next_birthday_rolls_over_to_next_year(self):
        person = make_person(day=29, month=9)

        assert person.next_birthday(TODAY) == date(2027, 9, 29)

    def test_leap_day_birthday_falls_on_february_28_in_common_years(self):
        person = make_person(day=29, month=2)

        assert person.next_birthday(date(2027, 1, 10)) == date(2027, 2, 28)
        assert person.next_birthday(date(2027, 3, 1)) == date(2028, 2, 29)

    def test_birth_year_does_not_change_next_birthday(self):
        person = make_person(day=15, month=11, year=1990)

        assert person.next_birthday(TODAY) == date(2026, 11, 15)

    def test_birthday_display_with_and_without_year(self):
        assert make_person(day=5, month=3).birthday_display == "March 5"
        assert make_person(day=5, month=3, year=1990).birthday_display == "March 5, 1990"

    @pytest.mark.parametrize(
        ("day", "month", "year"),
        [(5, 3, None), (5, 3, 1990), (29, 2, None), (29, 2, 2000), (None, None, None)],
    )
    def test_valid_birthdays(self, day, month, year):
        person = PersonFactory.build(birthday_day=day, birthday_month=month, birthday_year=year)

        person.full_clean()

    @pytest.mark.parametrize(
        ("day", "month", "year", "field"),
        [
            (30, 2, None, "birthday_day"),
            (31, 4, None, "birthday_day"),
            (29, 2, 2001, "birthday_day"),
            (5, None, None, "birthday_day"),
            (None, 5, None, "birthday_day"),
            (None, None, 1990, "birthday_year"),
        ],
    )
    def test_invalid_birthdays(self, day, month, year, field):
        person = PersonFactory.build(birthday_day=day, birthday_month=month, birthday_year=year)

        with pytest.raises(ValidationError) as exc_info:
            person.full_clean()

        assert field in exc_info.value.message_dict

    def test_database_rejects_day_without_month(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            PersonFactory(birthday_day=5, birthday_month=None)


@pytest.mark.django_db
class TestGlobalBirthdayEvent:
    def test_migration_provisions_a_global_birthday_event(self):
        event = Event.objects.get(is_birthday=True)

        assert event.is_global is True
        assert event.schedule_type == Event.ScheduleType.UNSCHEDULED
        assert event.date is None

    def test_get_birthday_event_is_idempotent(self):
        first = Event.objects.get_birthday_event()
        second = Event.objects.get_birthday_event()

        assert first.pk == second.pk
        assert Event.objects.filter(is_birthday=True).count() == 1

    def test_get_birthday_event_recreates_a_deleted_event(self):
        Event.objects.filter(is_birthday=True).delete()

        event = Event.objects.get_birthday_event()

        assert event.is_global is True
        assert event.is_birthday is True

    def test_global_event_is_accessible_by_every_user_once(self, user):
        other = UserFactory()
        birthday_event = Event.objects.get_birthday_event()
        # A direct share on top of the global flag must not duplicate the row
        create_or_update_permission(user, birthday_event, permission_level=PermissionLevel.EDITOR)
        private = EventFactory()

        assert list(Event.objects.accessible_by(user).filter(pk=birthday_event.pk)) == [
            birthday_event
        ]
        assert Event.objects.accessible_by(other).filter(pk=birthday_event.pk).exists()
        assert not Event.objects.accessible_by(other).filter(pk=private.pk).exists()

    def test_everyone_can_view_but_not_edit_the_global_event(self, user):
        event = Event.objects.get_birthday_event()

        assert PermissionService.get_effective_permission(event, user) == PermissionLevel.VIEWER

    def test_global_floor_never_lowers_an_explicit_permission(self, user):
        event = Event.objects.get_birthday_event()
        create_or_update_permission(user, event, permission_level=PermissionLevel.OWNER)

        assert PermissionService.get_effective_permission(event, user) == PermissionLevel.OWNER

    def test_superuser_can_manage_the_global_event(self):
        admin = UserFactory(is_superuser=True)
        event = Event.objects.get_birthday_event()

        assert PermissionService.get_effective_permission(event, admin) == PermissionLevel.OWNER

    def test_regular_event_gets_no_implicit_access(self, user):
        event = EventFactory()

        assert PermissionService.get_effective_permission(event, user) == PermissionLevel.NONE


@pytest.mark.django_db
class TestBirthdayPlanSharing:
    """Sharing a plan that uses the global Birthday event must work for regular users."""

    @staticmethod
    def _owned_birthday_plan(owner, person):
        relation = RelationFactory(
            person=person,
            gift=GiftFactory(),
            event=Event.objects.get_birthday_event(),
            due_date=person.next_birthday(TODAY),
        )
        for obj in (relation, person, relation.gift):
            create_or_update_permission(owner, obj, permission_level=PermissionLevel.OWNER)
        return relation

    @pytest.mark.parametrize(
        "level", [PermissionLevel.VIEWER, PermissionLevel.EDITOR, PermissionLevel.OWNER]
    )
    def test_grant_at_any_level_does_not_require_owning_the_global_event(self, user, level):
        friend = UserFactory()
        relation = self._owned_birthday_plan(user, make_person(day=15, month=11))

        SharingService.grant(user, relation, friend, level)

        assert PermissionService.get_permission(relation, friend) == level
        assert not EventPermission.objects.filter(user=friend, event=relation.event).exists()

    def test_grant_still_cascades_regular_events(self, user):
        friend = UserFactory()
        relation = self._owned_birthday_plan(user, make_person(day=15, month=11))
        relation.event = EventFactory()
        relation.save()
        create_or_update_permission(user, relation.event, permission_level=PermissionLevel.OWNER)

        SharingService.grant(user, relation, friend, PermissionLevel.EDITOR)

        assert PermissionService.get_permission(relation.event, friend) == PermissionLevel.EDITOR

    def test_retargeting_a_shared_plan_to_the_birthday_event_needs_no_grant(self, user):
        friend = UserFactory()
        relation = self._owned_birthday_plan(user, make_person(day=15, month=11))
        relation.event = EventFactory()
        relation.save()
        RelationPermission.objects.create(
            user=friend, relation=relation, permission_type=PermissionLevel.EDITOR
        )
        previous_ids = SharingService.relation_related_ids(relation)
        relation.event = Event.objects.get_birthday_event()

        SharingService.cascade_relation_reassignment(user, relation, previous_ids)

        assert not EventPermission.objects.filter(user=friend, event=relation.event).exists()


@pytest.mark.django_db
class TestBuildUpcomingBirthdays:
    def test_lists_birthdays_in_window_ordered_by_next_occurrence(self, user):
        later = make_person(user, day=20, month=10, first_name="Later")
        sooner = make_person(user, day=2, month=10, first_name="Sooner")
        make_person(user, day=1, month=12, first_name="TooFar")
        make_person(user, first_name="NoBirthday")

        items = build_upcoming_birthdays(user, TODAY)

        assert [item["person"] for item in items] == [sooner, later]
        assert [item["days_until"] for item in items] == [2, 20]

    def test_window_boundaries(self, user):
        on_limit = make_person(user, day=30, month=10)  # exactly 30 days away
        make_person(user, day=31, month=10)  # 31 days away

        items = build_upcoming_birthdays(user, TODAY)

        assert [item["person"] for item in items] == [on_limit]

    def test_birthday_today_is_listed_first(self, user):
        make_person(user, day=1, month=10)
        today_person = make_person(user, day=30, month=9)

        items = build_upcoming_birthdays(user, TODAY)

        assert items[0]["person"] == today_person
        assert items[0]["is_today"] is True
        assert items[0]["days_until"] == 0

    def test_year_end_wraps_to_next_year(self, user):
        person = make_person(user, day=5, month=1)

        items = build_upcoming_birthdays(user, date(2026, 12, 20))

        assert [(item["person"], item["date"]) for item in items] == [(person, date(2027, 1, 5))]

    def test_leap_day_birthday_is_listed_on_february_28_in_common_years(self, user):
        person = make_person(user, day=29, month=2)

        items = build_upcoming_birthdays(user, date(2027, 2, 20))

        assert [(item["person"], item["date"]) for item in items] == [(person, date(2027, 2, 28))]

    def test_leap_day_birthday_is_listed_on_february_29_in_leap_years(self, user):
        person = make_person(user, day=29, month=2)

        items = build_upcoming_birthdays(user, date(2028, 2, 20))

        assert [(item["person"], item["date"]) for item in items] == [(person, date(2028, 2, 29))]

    def test_people_the_user_cannot_access_never_appear(self, user):
        make_person(day=5, month=10)  # not shared with user
        other = UserFactory()
        make_person(other, day=6, month=10)

        assert build_upcoming_birthdays(user, TODAY) == []

    def test_viewer_sees_the_birthday(self, user):
        person = make_person(user, day=5, month=10)  # shared with VIEWER only

        assert PermissionService.get_permission(person, user) == PermissionLevel.VIEWER
        assert [item["person"] for item in build_upcoming_birthdays(user, TODAY)] == [person]

    def test_linked_user_sees_their_own_birthday(self, user):
        person = make_person(day=5, month=10, user_link=user)

        assert [item["person"] for item in build_upcoming_birthdays(user, TODAY)] == [person]

    def test_each_person_is_listed_once_despite_several_shares(self, user):
        person = make_person(user, day=5, month=10)
        other = UserFactory()
        create_or_update_permission(other, person, permission_level=PermissionLevel.OWNER)

        assert len(build_upcoming_birthdays(user, TODAY)) == 1

    def test_no_plan_means_not_covered(self, user):
        make_person(user, day=5, month=10)

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is False

    def test_plan_with_birthday_event_before_the_birthday_covers_it(self, user):
        person = make_person(user, day=5, month=10)
        relation = RelationFactory(
            person=person,
            event=Event.objects.get_birthday_event(),
            due_date=TODAY + timedelta(days=2),  # bought early, before the birthday
        )
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is True

    def test_plan_due_on_the_birthday_covers_it_whatever_the_event(self, user):
        person = make_person(user, day=5, month=10)
        relation = RelationFactory(person=person, event=None, due_date=date(2026, 10, 5))
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is True

    def test_unrelated_plan_does_not_cover_the_birthday(self, user):
        person = make_person(user, day=5, month=10)
        relation = RelationFactory(person=person, event=EventFactory(), due_date=date(2026, 10, 3))
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is False

    def test_plan_the_user_cannot_see_does_not_cover_the_birthday(self, user):
        person = make_person(user, day=5, month=10)
        RelationFactory(
            person=person, event=Event.objects.get_birthday_event(), due_date=date(2026, 10, 5)
        )  # not shared with user

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is False

    def test_plan_due_after_the_birthday_does_not_cover_it(self, user):
        person = make_person(user, day=5, month=10)
        relation = RelationFactory(
            person=person, event=Event.objects.get_birthday_event(), due_date=date(2026, 10, 20)
        )
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is False

    def test_item_links_to_the_prefilled_plan_form(self, user):
        person = make_person(user, day=5, month=10)

        item = build_upcoming_birthdays(user, TODAY)[0]

        assert item["create_url"].endswith(f"?birthday_for={person.person_id}")

    def test_query_count_does_not_grow_with_the_number_of_people(
        self, user, django_assert_max_num_queries
    ):
        for index in range(5):
            make_person(user, day=index + 1, month=10)

        with django_assert_max_num_queries(2):
            assert len(build_upcoming_birthdays(user, TODAY)) == 5


@pytest.mark.django_db
class TestBirthdayConstraints:
    @pytest.mark.parametrize(
        ("day", "month"),
        [(0, 5), (32, 5), (5, 0), (5, 13)],
        ids=["day0", "day32", "month0", "month13"],
    )
    def test_database_rejects_out_of_range_day_or_month(self, day, month):
        with pytest.raises(IntegrityError), transaction.atomic():
            PersonFactory(birthday_day=day, birthday_month=month)

    def test_database_rejects_year_without_day_and_month(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            PersonFactory(birthday_year=1990)

    def test_out_of_range_values_are_reported_by_the_field_validators_once(self):
        person = PersonFactory.build(birthday_day=32, birthday_month=5)

        with pytest.raises(ValidationError) as exc_info:
            person.full_clean()

        assert len(exc_info.value.message_dict["birthday_day"]) == 1

    def test_year_in_the_future_is_rejected(self):
        person = PersonFactory.build(
            birthday_day=5, birthday_month=5, birthday_year=date.today().year + 1
        )

        with pytest.raises(ValidationError) as exc_info:
            person.full_clean()

        assert "birthday_year" in exc_info.value.message_dict

    def test_only_one_birthday_event_can_exist(self):
        Event.objects.get_birthday_event()

        with pytest.raises(IntegrityError), transaction.atomic():
            Event.objects.create(name="Another", is_birthday=True)

    def test_get_birthday_event_survives_a_concurrent_creation(self, monkeypatch):
        existing = Event.objects.get_birthday_event()
        original_first = EventQuerySet.first
        calls = []

        def first_misses_once(queryset):
            # Simulate a request that looked before another one created the event
            calls.append(1)
            return None if len(calls) == 1 else original_first(queryset)

        monkeypatch.setattr(EventQuerySet, "first", first_misses_once)

        assert Event.objects.get_birthday_event().pk == existing.pk
        assert Event.objects.filter(is_birthday=True).count() == 1

    def test_event_list_display_does_not_defer_the_global_flag(self, user):
        Event.objects.get_birthday_event()

        event = Event.objects.for_list_display(user).get(is_birthday=True)

        assert "is_global" not in event.get_deferred_fields()

    def test_migration_provisioning_is_idempotent(self):
        migration = importlib.import_module(
            "gift_manager.migrations.0032_create_global_birthday_event"
        )

        migration.create_birthday_event(apps, None)
        migration.create_birthday_event(apps, None)

        assert Event.objects.filter(is_birthday=True).count() == 1

    def test_global_event_cannot_be_left_by_a_regular_user(self, user):
        event = Event.objects.get_birthday_event()

        with pytest.raises(PermissionDenied):
            PermissionService.assert_can_leave_object(user, event)


@pytest.mark.django_db
class TestBirthdayCoverage:
    """Which gift plans count as covering an upcoming birthday."""

    @staticmethod
    def _covered(user, **plan_kwargs):
        person = make_person(user, day=5, month=10)
        relation = RelationFactory(person=person, **plan_kwargs)
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )
        return build_upcoming_birthdays(user, TODAY)[0]["has_plan"]

    def test_abandoned_plan_does_not_cover_the_birthday(self, user):
        assert not self._covered(
            user,
            event=Event.objects.get_birthday_event(),
            due_date=date(2026, 10, 5),
            status=RelationStatusFactory(status="Abandoned"),
        )

    def test_given_plan_still_covers_the_birthday(self, user):
        assert self._covered(
            user,
            event=Event.objects.get_birthday_event(),
            due_date=date(2026, 10, 5),
            status=RelationStatusFactory(status="Given"),
        )

    def test_overdue_plan_for_the_coming_birthday_covers_it(self, user):
        assert self._covered(
            user,
            event=Event.objects.get_birthday_event(),
            due_date=TODAY - timedelta(days=3),  # already overdue, birthday still ahead
        )

    def test_plan_for_last_years_birthday_does_not_cover_this_one(self, user):
        assert not self._covered(
            user, event=Event.objects.get_birthday_event(), due_date=date(2025, 10, 5)
        )

    def test_plan_without_due_date_is_not_counted(self, user):
        assert not self._covered(user, event=Event.objects.get_birthday_event(), due_date=None)

    def test_group_plan_is_not_counted(self, user):
        person = make_person(user, day=5, month=10)
        group = PersonGroupFactory()
        person.groups.add(group)
        relation = GroupRelationFactory(
            group=group, event=Event.objects.get_birthday_event(), due_date=date(2026, 10, 5)
        )
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        assert build_upcoming_birthdays(user, TODAY)[0]["has_plan"] is False


@pytest.mark.django_db
class TestBirthdayEventSchedule:
    """The unscheduled Birthday event explains where its dates come from."""

    SUMMARY = "Repeats yearly, on the recipient's birthday"

    def test_summary_explains_the_recipient_birthday(self):
        assert Event.objects.get_birthday_event().date_summary == self.SUMMARY

    def test_summary_is_translated(self):
        event = Event.objects.get_birthday_event()

        with translation.override("fr"):
            assert event.date_summary == (
                "Se répète annuellement, à la date d'anniversaire du destinataire"
            )

    def test_regular_unscheduled_event_still_says_no_date_yet(self):
        event = Event.objects.create(name="Someday")

        assert event.date_summary == "No date yet"

    def test_a_scheduled_birthday_event_shows_its_date(self):
        event = Event.objects.get_birthday_event()
        event.schedule_type = Event.ScheduleType.RECURRING
        event.recurrence = "yearly"
        event.date = date(2000, 5, 15)

        assert event.date_summary.startswith("Repeats yearly from")
        assert "recipient" not in event.date_summary

    def test_list_display_does_not_defer_the_birthday_flag(self, user, django_assert_num_queries):
        Event.objects.get_birthday_event()
        EventFactory(shared_with=[user])

        events = list(Event.objects.for_list_display(user))
        with django_assert_num_queries(0):
            summaries = [event.date_summary for event in events]

        assert self.SUMMARY in summaries


@pytest.mark.django_db
class TestTranslatedBirthdayEventName:
    """The global Birthday event reads in each user's language; the stored name stays English."""

    def test_name_follows_the_active_language(self):
        event = Event.objects.get_birthday_event()

        with translation.override("en"):
            assert event.name == "Birthday"
            assert str(event) == "Birthday"
        with translation.override("fr"):
            assert event.name == "Anniversaire"
            assert str(event) == "Anniversaire"

    def test_a_regular_event_keeps_the_name_its_user_typed(self):
        event = EventFactory(name="Birthday")

        with translation.override("fr"):
            assert event.name == "Birthday"

    def test_saving_never_writes_the_translation(self):
        event = Event.objects.get_birthday_event()

        with translation.override("fr"):
            event.comment = "Edited in French"
            event.save()
            event.refresh_from_db()
            assert event.name == "Anniversaire"

        assert Event.objects.filter(pk=event.pk).values_list("name", flat=True).get() == "Birthday"

    def test_a_queryset_update_is_not_affected(self):
        event = Event.objects.get_birthday_event()

        with translation.override("fr"):
            Event.objects.filter(pk=event.pk).update(comment="x")

        assert Event.objects.filter(pk=event.pk).values_list("name", flat=True).get() == "Birthday"

    def test_the_edit_form_shows_the_stored_name(self):
        from gift_manager.forms import EventForm

        event = Event.objects.get_birthday_event()

        with translation.override("fr"):
            form = EventForm(instance=event)

        assert form.initial["name"] == "Birthday"

    def test_list_display_events_are_translated(self, user):
        Event.objects.get_birthday_event()

        with translation.override("fr"):
            names = [event.name for event in Event.objects.for_list_display(user)]

        assert "Anniversaire" in names

    def test_relation_events_are_translated(self):
        plan = RelationFactory(event=Event.objects.get_birthday_event())

        with translation.override("fr"):
            plan = type(plan).objects.select_related("event").get(pk=plan.pk)
            assert plan.event.name == "Anniversaire"

    @pytest.mark.parametrize(
        ("language", "query"), [("fr", "anniv"), ("en", "birth"), ("en", "BIRTHDAY")]
    )
    def test_search_matches_the_translated_name(self, language, query):
        event = Event.objects.get_birthday_event()
        other = EventFactory(name="Christmas")

        with translation.override(language):
            found = set(Event.objects.filter(birthday_event_name_q(query)))

        assert found == {event}
        assert other not in found

    def test_search_does_not_match_other_languages_or_blank_queries(self):
        with translation.override("en"):
            assert not birthday_event_name_q("anniv")
            assert not birthday_event_name_q("   ")

    def test_search_through_a_relation(self):
        plan = RelationFactory(event=Event.objects.get_birthday_event())
        RelationFactory(event=EventFactory(name="Christmas"))

        with translation.override("fr"):
            found = set(Relation.objects.filter(birthday_event_name_q("anniv", "event__")))

        assert found == {plan}
