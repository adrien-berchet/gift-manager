"""Tests for the step forms and helpers of the guided gift plan flow."""

from datetime import date

import pytest

from gift_manager.guided_plan import GuidedGiftForm
from gift_manager.guided_plan import GuidedOccasionForm
from gift_manager.guided_plan import GuidedRecipientForm
from gift_manager.guided_plan import build_relation_data
from gift_manager.guided_plan import create_inline_objects
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _idea_status() -> RelationStatus:
    status, _ = RelationStatus.objects.get_or_create(status_en="Idea", defaults={"status": "Idea"})
    return status


class TestRecipientForm:
    def test_recipient_form_accepts_accessible_person(self, user):
        person = PersonFactory(shared_with=[user])

        form = GuidedRecipientForm({"recipient": f"person:{person.person_id}"}, user=user)

        assert form.is_valid(), form.errors

    def test_recipient_form_rejects_inaccessible_person(self, user):
        person = PersonFactory()

        form = GuidedRecipientForm({"recipient": f"person:{person.person_id}"}, user=user)

        assert not form.is_valid()
        assert "recipient" in form.errors


class TestGiftForm:
    def test_gift_form_requires_gift_or_new_name(self, user):
        form = GuidedGiftForm({}, user=user)

        assert not form.is_valid()
        assert form.non_field_errors() or form.errors

    def test_gift_form_accepts_existing_gift(self, user):
        gift = GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift": gift.pk}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["gift"] == gift

    def test_gift_form_accepts_new_name_stripped(self, user):
        form = GuidedGiftForm({"new_gift_name": "  Scarf  "}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["new_gift_name"] == "Scarf"

    def test_gift_form_rejects_both(self, user):
        gift = GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift": gift.pk, "new_gift_name": "Scarf"}, user=user)

        assert not form.is_valid()

    def test_gift_form_rejects_whitespace_name(self, user):
        form = GuidedGiftForm({"new_gift_name": "   "}, user=user)

        assert not form.is_valid()

    def test_gift_form_rejects_inaccessible_gift(self, user):
        gift = GiftFactory()

        form = GuidedGiftForm({"gift": gift.pk}, user=user)

        assert not form.is_valid()
        assert "gift" in form.errors


class TestOccasionForm:
    def test_occasion_form_event_is_optional(self, user):
        form = GuidedOccasionForm({}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["event"] is None
        assert form.cleaned_data["due_date"] is None

    def test_occasion_form_defaults_due_date_from_event(self, user):
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))

        form = GuidedOccasionForm({"event": event.pk}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] == date(2030, 12, 25)

    def test_occasion_form_explicit_due_date_wins(self, user):
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))

        form = GuidedOccasionForm({"event": event.pk, "due_date": "2030-12-01"}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] == date(2030, 12, 1)

    def test_occasion_form_defaults_due_date_from_new_event_date(self, user):
        form = GuidedOccasionForm(
            {"new_event_name": "Housewarming", "new_event_date": "2030-05-04"}, user=user
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] == date(2030, 5, 4)

    @pytest.mark.parametrize(
        "data",
        [
            {"new_event_name": "Housewarming"},
            {"new_event_date": "2030-05-04"},
            {"new_event_name": "   ", "new_event_date": "2030-05-04"},
        ],
    )
    def test_occasion_form_new_event_needs_name_and_date(self, user, data):
        form = GuidedOccasionForm(data, user=user)

        assert not form.is_valid()

    def test_occasion_form_rejects_event_and_new_event(self, user):
        event = EventFactory(shared_with=[user])

        form = GuidedOccasionForm(
            {"event": event.pk, "new_event_name": "Party", "new_event_date": "2030-05-04"},
            user=user,
        )

        assert not form.is_valid()

    def test_occasion_form_rejects_inaccessible_event(self, user):
        event = EventFactory()

        form = GuidedOccasionForm({"event": event.pk}, user=user)

        assert not form.is_valid()
        assert "event" in form.errors

    def test_occasion_form_birthday_event_without_date_leaves_due_date_empty(self, user):
        birthday = Event.objects.get_birthday_event()

        form = GuidedOccasionForm({"event": birthday.pk}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] is None


class TestInlineObjects:
    def test_create_inline_objects_creates_owned_gift_and_one_time_event(self, user):
        gift_form = GuidedGiftForm({"new_gift_name": "Scarf"}, user=user)
        occasion_form = GuidedOccasionForm(
            {"new_event_name": "Housewarming", "new_event_date": "2030-05-04"}, user=user
        )
        assert gift_form.is_valid() and occasion_form.is_valid()

        gift, event = create_inline_objects(user, gift_form, occasion_form)

        assert gift.name == "Scarf"
        assert PermissionService.get_effective_permission(gift, user) == PermissionLevel.OWNER
        assert event.name == "Housewarming"
        assert event.schedule_type == Event.ScheduleType.ONE_TIME
        assert event.date == date(2030, 5, 4)
        assert PermissionService.get_effective_permission(event, user) == PermissionLevel.OWNER

    def test_create_inline_objects_reuses_existing_objects(self, user):
        gift = GiftFactory(shared_with=[user])
        event = EventFactory(shared_with=[user])
        gift_form = GuidedGiftForm({"gift": gift.pk}, user=user)
        occasion_form = GuidedOccasionForm({"event": event.pk}, user=user)
        assert gift_form.is_valid() and occasion_form.is_valid()

        assert create_inline_objects(user, gift_form, occasion_form) == (gift, event)

    def test_create_inline_objects_without_event_returns_none(self, user):
        gift_form = GuidedGiftForm({"new_gift_name": "Scarf"}, user=user)
        occasion_form = GuidedOccasionForm({}, user=user)
        assert gift_form.is_valid() and occasion_form.is_valid()

        _, event = create_inline_objects(user, gift_form, occasion_form)

        assert event is None


class TestBuildRelationData:
    def _forms(self, user, recipient_value, **occasion):
        recipient_form = GuidedRecipientForm({"recipient": recipient_value}, user=user)
        occasion_form = GuidedOccasionForm(occasion, user=user)
        assert recipient_form.is_valid() and occasion_form.is_valid()
        return recipient_form, occasion_form

    def test_build_relation_data_defaults_status_to_idea(self, user):
        person = PersonFactory(shared_with=[user])
        gift = GiftFactory(shared_with=[user])
        idea = _idea_status()
        recipient_form, occasion_form = self._forms(
            user, f"person:{person.person_id}", comment="Wrap it"
        )

        data = build_relation_data(user, recipient_form, occasion_form, gift, None)

        assert data["status"] == idea.pk
        assert data["gift"] == gift.pk
        assert data["event"] == ""
        assert data["comment"] == "Wrap it"
        assert data["recipient"] == f"person:{person.person_id}"

    def test_build_relation_data_applies_default_surprise(self, user):
        other_user = UserFactory()
        person = PersonFactory(shared_with=[user], user_link=other_user)
        gift = GiftFactory(shared_with=[user])
        _idea_status()
        recipient_form, occasion_form = self._forms(user, f"person:{person.person_id}")

        data = build_relation_data(user, recipient_form, occasion_form, gift, None)

        assert data["is_surprise"] is True
