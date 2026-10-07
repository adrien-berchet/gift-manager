"""Tests for the existing / new / no-event mode of the guided step forms."""

import pytest
from django.utils import translation

from gift_manager.guided_plan import GuidedGiftForm
from gift_manager.guided_plan import GuidedOccasionForm
from gift_manager.guided_plan import GuidedRecipientForm
from gift_manager.models import Event
from gift_manager.models import RelationStatus
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


def _plan_fields() -> dict:
    status, _ = RelationStatus.objects.get_or_create(status_en="Idea", defaults={"status": "Idea"})
    return {"status": status.pk, "is_surprise": "false"}


class TestRecipientMode:
    def test_default_mode_is_existing_when_people_exist(self, user):
        PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(user=user)

        assert form.mode == "existing"
        assert form.show_mode_choice
        assert [value for value, _ in form.mode_choices] == ["existing", "new"]

    def test_choice_is_skipped_without_existing_people_or_groups(self, user):
        form = GuidedRecipientForm(user=user)

        assert form.mode == "new"
        assert not form.show_mode_choice
        assert [value for value, _ in form.mode_choices] == ["new"]

    def test_new_mode_validates_the_new_person_and_ignores_the_chooser(self, user):
        stranger = PersonFactory()
        PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(
            {
                "recipient_mode": "new",
                "recipient": f"person:{stranger.person_id}",
                "new_person-first_name": "Anna",
            },
            user=user,
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.new_requested

    def test_new_mode_requires_a_first_name(self, user):
        PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(
            {"recipient_mode": "new", "new_person-notes": "Likes tea"}, user=user
        )

        assert not form.is_valid()
        assert "first_name" in form.new_form.errors

    def test_existing_mode_ignores_the_new_person_fields(self, user):
        person = PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(
            {
                "recipient_mode": "existing",
                "recipient": f"person:{person.person_id}",
                "new_person-birthday_day": "31",
            },
            user=user,
        )

        assert form.is_valid(), form.errors
        assert not form.new_requested
        assert not form.new_form.errors

    def test_existing_mode_requires_a_choice(self, user):
        PersonFactory(shared_with=[user])

        form = GuidedRecipientForm({"recipient_mode": "existing"}, user=user)

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_mode_is_inferred_from_what_is_filled_when_missing_or_invalid(self, user):
        person = PersonFactory(shared_with=[user])

        by_chooser = GuidedRecipientForm(
            {"recipient_mode": "bogus", "recipient": f"person:{person.person_id}"}, user=user
        )
        by_name = GuidedRecipientForm({"new_person-first_name": "Anna"}, user=user)

        assert by_chooser.mode == "existing"
        assert by_name.mode == "new"

    def test_input_names_include_the_mode(self, user):
        assert "recipient_mode" in GuidedRecipientForm(user=user).input_names()

    def test_unbound_form_prefills_the_posted_mode(self, user):
        PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(user=user, initial_values={"recipient_mode": "new"})

        assert form.mode == "new"


class TestGiftMode:
    def test_default_mode_is_existing_when_gifts_exist(self, user):
        GiftFactory(shared_with=[user])

        form = GuidedGiftForm(user=user)

        assert (form.mode, form.show_mode_choice) == ("existing", True)

    def test_choice_is_skipped_without_existing_gifts(self, user):
        form = GuidedGiftForm(user=user)

        assert (form.mode, form.show_mode_choice) == ("new", False)

    def test_new_mode_requires_a_name(self, user):
        GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift_mode": "new"}, user=user)

        assert not form.is_valid()
        assert "name" in form.new_form.errors

    def test_existing_mode_requires_a_choice(self, user):
        GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift_mode": "existing"}, user=user)

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_new_mode_ignores_a_stale_chooser_value(self, user):
        stale = GiftFactory()

        form = GuidedGiftForm(
            {"gift_mode": "new", "gift": stale.pk, "new_gift-name": "Scarf"}, user=user
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.new_requested


class TestEventMode:
    def test_choices_are_existing_new_and_none(self, user):
        form = GuidedOccasionForm(user=user)

        assert [value for value, _ in form.mode_choices] == ["existing", "new", "none"]
        assert form.mode == "existing"

    def test_default_is_none_when_no_event_exists(self, user):
        Event.objects.all().delete()

        form = GuidedOccasionForm(user=user)

        assert [value for value, _ in form.mode_choices] == ["new", "none"]
        assert form.mode == "none"

    def test_none_mode_ignores_the_chooser_and_the_new_event(self, user):
        event = EventFactory(shared_with=[user])

        form = GuidedOccasionForm(
            {
                "event_mode": "none",
                "event": event.pk,
                "new_event-name": "Party",
                **_plan_fields(),
            },
            user=user,
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.cleaned_data["event"] is None
        assert not form.new_requested

    def test_existing_mode_without_a_choice_means_no_event(self, user):
        form = GuidedOccasionForm({"event_mode": "existing", **_plan_fields()}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["event"] is None

    def test_new_mode_requires_a_name(self, user):
        form = GuidedOccasionForm(
            {"event_mode": "new", "new_event-date": "2030-05-04", **_plan_fields()}, user=user
        )

        assert not form.is_valid()
        assert "name" in form.new_form.errors

    def test_new_mode_creates_the_event_even_with_a_stale_chooser_value(self, user):
        event = EventFactory(shared_with=[user])

        form = GuidedOccasionForm(
            {
                "event_mode": "new",
                "event": event.pk,
                "new_event-name": "Party",
                "new_event-schedule_type": "one_time",
                "new_event-date": "2030-05-04",
                **_plan_fields(),
            },
            user=user,
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.new_requested
        assert str(form.cleaned_data["due_date"]) == "2030-05-04"


class TestModeLabels:
    def test_labels_use_the_workflow_words(self, user):
        assert dict(GuidedRecipientForm(user=user).mode_choices_all) == {
            "existing": "Existing recipient",
            "new": "New person",
        }
        assert dict(GuidedGiftForm(user=user).mode_choices_all) == {
            "existing": "Existing gift",
            "new": "New gift",
        }
        assert dict(GuidedOccasionForm(user=user).mode_choices_all) == {
            "existing": "Existing event",
            "new": "New event",
            "none": "No event",
        }

    def test_labels_are_translated(self, user):
        with translation.override("fr"):
            labels = {
                key: str(label) for key, label in GuidedOccasionForm(user=user).mode_choices_all
            }

        assert labels == {
            "existing": "Événement existant",
            "new": "Nouvel événement",
            "none": "Aucun événement",
        }
