"""Tests for the step forms and helpers of the guided gift plan flow."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import translation

from gift_manager.forms import decode_email
from gift_manager.guided_plan import GuidedGiftForm
from gift_manager.guided_plan import GuidedOccasionForm
from gift_manager.guided_plan import GuidedRecipientForm
from gift_manager.guided_plan import build_relation_data
from gift_manager.guided_plan import create_inline_objects
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _idea_status() -> RelationStatus:
    status, _ = RelationStatus.objects.get_or_create(status_en="Idea", defaults={"status": "Idea"})
    return status


def _owned(user, obj):
    create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


def _editable_group(user):
    return _owned(user, PersonGroupFactory())


def _person_data(**extra) -> dict:
    data = {
        "new_person-first_name": "Anna",
        "new_person-family_name": "Martin",
        "new_person-email_address": "anna@example.com",
        "new_person-birthday_day": "4",
        "new_person-birthday_month": "5",
        "new_person-notes": "Likes tea",
    }
    data.update(extra)
    return data


def _gift_data(**extra) -> dict:
    data = {
        "new_gift-name": "Scarf",
        "new_gift-comment": "Wool",
        "new_gift-url": "https://example.com/scarf",
        "new_gift-price": "19.90",
    }
    data.update(extra)
    return data


def _event_data(**extra) -> dict:
    data = {
        "new_event-name": "Housewarming",
        "new_event-schedule_type": "one_time",
        "new_event-date": "2030-05-04",
    }
    data.update(extra)
    return data


class TestRecipientForm:
    def test_recipient_form_accepts_accessible_person(self, user):
        person = PersonFactory(shared_with=[user])

        form = GuidedRecipientForm({"recipient": f"person:{person.person_id}"}, user=user)

        assert form.is_valid(), form.errors
        assert not form.new_requested

    def test_recipient_form_rejects_inaccessible_person(self, user):
        person = PersonFactory()

        form = GuidedRecipientForm({"recipient": f"person:{person.person_id}"}, user=user)

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_recipient_form_requires_existing_or_new(self, user):
        form = GuidedRecipientForm({}, user=user)

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_recipient_form_accepts_new_person_with_details(self, user):
        group = _editable_group(user)
        tag = _owned(user, GiftTagFactory())

        form = GuidedRecipientForm(
            _person_data(**{"new_person-groups": [group.pk], "new_person-interests": [tag.pk]}),
            user=user,
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.new_requested
        assert form.new_form.cleaned_data["groups"].get() == group

    def test_recipient_form_ignores_new_person_details_without_first_name(self, user):
        form = GuidedRecipientForm({"new_person-email_address": "a@b.com"}, user=user)

        assert not form.is_valid()
        assert "recipient" in form.errors
        assert not form.new_requested
        assert form.new_form.initial["email_address"] == "a@b.com"

    def test_recipient_form_rejects_both_existing_and_new(self, user):
        person = PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(
            {"recipient": f"person:{person.person_id}", **_person_data()}, user=user
        )

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_recipient_form_validates_new_person_when_requested(self, user):
        form = GuidedRecipientForm(
            _person_data(**{"new_person-birthday_day": "31", "new_person-birthday_month": "2"}),
            user=user,
        )

        assert not form.is_valid()
        assert form.new_form.errors

    def test_recipient_form_does_not_validate_new_person_when_existing_chosen(self, user):
        person = PersonFactory(shared_with=[user])

        form = GuidedRecipientForm(
            {"recipient": f"person:{person.person_id}", "new_person-birthday_day": "31"},
            user=user,
        )

        assert form.is_valid(), form.errors
        assert not form.new_form.errors

    def test_recipient_form_rejects_inaccessible_group_for_new_person(self, user):
        foreign_group = PersonGroupFactory()

        form = GuidedRecipientForm(
            _person_data(**{"new_person-groups": [foreign_group.pk]}), user=user
        )

        assert not form.is_valid()
        assert "groups" in form.new_form.errors


class TestGiftForm:
    def test_gift_form_requires_gift_or_new_name(self, user):
        form = GuidedGiftForm({}, user=user)

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_gift_form_accepts_existing_gift(self, user):
        gift = GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift": gift.pk}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["gift"] == gift

    def test_gift_form_accepts_new_gift_with_comment_price_url_tags(self, user):
        tag = _owned(user, GiftTagFactory())

        form = GuidedGiftForm(_gift_data(**{"new_gift-tags": [tag.pk]}), user=user)

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.new_form.cleaned_data["price"] == Decimal("19.90")
        assert list(form.new_form.cleaned_data["tags"]) == [tag]

    def test_gift_form_rejects_inaccessible_tag(self, user):
        tag = GiftTagFactory()

        form = GuidedGiftForm(_gift_data(**{"new_gift-tags": [tag.pk]}), user=user)

        assert not form.is_valid()
        assert "tags" in form.new_form.errors

    def test_gift_form_rejects_both(self, user):
        gift = GiftFactory(shared_with=[user])

        form = GuidedGiftForm({"gift": gift.pk, "new_gift-name": "Scarf"}, user=user)

        assert not form.is_valid()

    def test_gift_form_rejects_whitespace_name(self, user):
        form = GuidedGiftForm({"new_gift-name": "   "}, user=user)

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_gift_form_rejects_inaccessible_gift(self, user):
        gift = GiftFactory()

        form = GuidedGiftForm({"gift": gift.pk}, user=user)

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_gift_form_rejects_invalid_new_gift_url(self, user):
        form = GuidedGiftForm(_gift_data(**{"new_gift-url": "ftp://nope"}), user=user)

        assert not form.is_valid()
        assert "url" in form.new_form.errors


class TestOccasionForm:
    def test_occasion_form_event_is_optional(self, user):
        _idea_status()

        form = GuidedOccasionForm({"status": _idea_status().pk, "is_surprise": "false"}, user=user)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["event"] is None
        assert form.cleaned_data["due_date"] is None

    def test_occasion_form_defaults_due_date_from_event(self, user):
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))

        form = GuidedOccasionForm(
            {"event": event.pk, "status": _idea_status().pk, "is_surprise": "false"}, user=user
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] == date(2030, 12, 25)

    def test_occasion_form_explicit_due_date_wins(self, user):
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))

        form = GuidedOccasionForm(
            {
                "event": event.pk,
                "due_date": "2030-12-01",
                "status": _idea_status().pk,
                "is_surprise": "false",
            },
            user=user,
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] == date(2030, 12, 1)

    def test_occasion_form_defaults_due_date_from_new_event_date(self, user):
        form = GuidedOccasionForm(
            {**_event_data(), "status": _idea_status().pk, "is_surprise": "false"}, user=user
        )

        assert form.is_valid(), (form.errors, form.new_form.errors)
        assert form.cleaned_data["due_date"] == date(2030, 5, 4)

    def test_occasion_form_new_event_defaults_to_one_time(self, user):
        form = GuidedOccasionForm(user=user)

        assert form.new_form["schedule_type"].value() == Event.ScheduleType.ONE_TIME

    def test_occasion_form_new_recurring_event_needs_recurrence(self, user):
        form = GuidedOccasionForm(
            {
                **_event_data(**{"new_event-schedule_type": "recurring"}),
                "status": _idea_status().pk,
                "is_surprise": "false",
            },
            user=user,
        )

        assert not form.is_valid()
        assert "recurrence" in form.new_form.errors

    def test_occasion_form_new_event_without_date_is_invalid_for_one_time(self, user):
        data = _event_data()
        del data["new_event-date"]

        form = GuidedOccasionForm(
            {**data, "status": _idea_status().pk, "is_surprise": "false"}, user=user
        )

        assert not form.is_valid()
        assert "date" in form.new_form.errors

    def test_occasion_form_new_event_details_without_name_are_rejected_and_kept(self, user):
        form = GuidedOccasionForm(
            {"new_event-comment": "x", "status": _idea_status().pk, "is_surprise": "false"},
            user=user,
        )

        assert not form.is_valid()
        assert "event" in form.errors
        assert not form.new_requested
        assert form.new_form.initial["comment"] == "x"

    def test_occasion_form_rejects_event_and_new_event(self, user):
        event = EventFactory(shared_with=[user])

        form = GuidedOccasionForm(
            {
                "event": event.pk,
                **_event_data(),
                "status": _idea_status().pk,
                "is_surprise": "false",
            },
            user=user,
        )

        assert not form.is_valid()
        assert "event" in form.errors

    def test_occasion_form_rejects_inaccessible_event(self, user):
        event = EventFactory()

        form = GuidedOccasionForm(
            {"event": event.pk, "status": _idea_status().pk, "is_surprise": "false"}, user=user
        )

        assert not form.is_valid()
        assert "event" in form.errors

    def test_occasion_form_birthday_event_without_date_leaves_due_date_empty(self, user):
        birthday = Event.objects.get_birthday_event()

        form = GuidedOccasionForm(
            {"event": birthday.pk, "status": _idea_status().pk, "is_surprise": "false"}, user=user
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["due_date"] is None

    def test_occasion_form_plan_fields_defaults(self, user):
        idea = _idea_status()

        form = GuidedOccasionForm(user=user)

        assert form.fields["status"].initial == idea.pk
        assert form.fields["is_surprise"].initial == "false"

    def test_occasion_form_surprise_default_for_linked_recipient(self, user):
        person = PersonFactory(shared_with=[user], user_link=UserFactory())

        form = GuidedOccasionForm(user=user, recipient_value=f"person:{person.person_id}")

        assert form.fields["is_surprise"].initial == "true"

    def test_occasion_form_accepts_plan_details(self, user):
        planned, _ = RelationStatus.objects.get_or_create(
            status_en="Planned", defaults={"status": "Planned"}
        )

        form = GuidedOccasionForm(
            {
                "status": planned.pk,
                "url": "https://example.com/override",
                "price": "12.50",
                "comment": "Notes",
                "is_surprise": "true",
            },
            user=user,
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["status"] == planned
        assert form.cleaned_data["is_surprise"] is True

    def test_occasion_form_input_names_include_prefixed_fields(self, user):
        names = GuidedOccasionForm(user=user).input_names()

        assert {"event", "due_date", "comment", "status", "url", "price", "is_surprise"} <= set(
            names
        )
        assert {"new_event-name", "new_event-date", "new_event-schedule_type"} <= set(names)

    def test_recipient_input_names_include_multi_valued_fields(self, user):
        names = GuidedRecipientForm(user=user).input_names()

        assert {"recipient", "new_person-first_name", "new_person-groups"} <= set(names)
        assert "new_person-interests" in names


class TestOccasionPlanDetails:
    def test_occasion_form_ignores_carried_surprise_for_another_recipient(self, user):
        other = PersonFactory(shared_with=[user])
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())

        form = GuidedOccasionForm(
            user=user,
            recipient_value=f"person:{linked.person_id}",
            initial_values={"is_surprise": "false", "surprise_for": f"person:{other.person_id}"},
        )

        assert "is_surprise" not in form.initial
        assert form.fields["is_surprise"].initial == "true"
        assert form.initial["surprise_for"] == f"person:{linked.person_id}"

    def test_occasion_form_keeps_carried_surprise_for_the_same_recipient(self, user):
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())
        value = f"person:{linked.person_id}"

        form = GuidedOccasionForm(
            user=user,
            recipient_value=value,
            initial_values={"is_surprise": "false", "surprise_for": value},
        )

        assert form.initial["is_surprise"] == "false"

    def test_occasion_form_ignores_carried_surprise_without_recipient_marker(self, user):
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())

        form = GuidedOccasionForm(
            user=user,
            recipient_value=f"person:{linked.person_id}",
            initial_values={"is_surprise": "false"},
        )

        assert "is_surprise" not in form.initial

    def test_occasion_form_event_date_without_name_is_rejected(self, user):
        form = GuidedOccasionForm(
            {
                "new_event-date": "2030-05-04",
                "status": _idea_status().pk,
                "is_surprise": "false",
            },
            user=user,
        )

        assert not form.is_valid()
        assert "event" in form.errors

    def test_occasion_form_default_schedule_alone_is_not_a_new_event(self, user):
        form = GuidedOccasionForm(
            {
                "new_event-schedule_type": "one_time",
                "status": _idea_status().pk,
                "is_surprise": "false",
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_plan_details_closed_for_defaults(self, user):
        _idea_status()

        assert not GuidedOccasionForm(user=user).plan_details_open

    def test_plan_details_open_for_a_non_default_status(self, user):
        planned, _ = RelationStatus.objects.get_or_create(
            status_en="Planned", defaults={"status": "Planned"}
        )
        _idea_status()

        form = GuidedOccasionForm(user=user, initial_values={"status": str(planned.pk)})

        assert form.plan_details_open

    def test_plan_details_open_for_a_non_default_surprise(self, user):
        _idea_status()
        value = ""

        form = GuidedOccasionForm(
            user=user,
            recipient_value=value,
            initial_values={"is_surprise": "true", "surprise_for": value},
        )

        assert form.plan_details_open


def _forms(user, *, recipient, gift, occasion):
    recipient_form = GuidedRecipientForm(recipient, user=user)
    gift_form = GuidedGiftForm(gift, user=user)
    occasion_form = GuidedOccasionForm(
        {**occasion, "status": _idea_status().pk, "is_surprise": "false"}, user=user
    )
    for form in (recipient_form, gift_form, occasion_form):
        assert form.is_valid(), (form.errors, form.new_form.errors)
    return recipient_form, gift_form, occasion_form


class TestInlineObjects:
    def test_create_inline_objects_creates_person_gift_event_with_all_data(self, user):
        group = _editable_group(user)
        tag = _owned(user, GiftTagFactory())
        recipient_form, gift_form, occasion_form = _forms(
            user,
            recipient=_person_data(**{"new_person-groups": [group.pk]}),
            gift=_gift_data(**{"new_gift-tags": [tag.pk]}),
            occasion=_event_data(),
        )

        inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)

        person = Person.objects.get(first_name="Anna")
        assert inline.recipient_value == f"person:{person.person_id}"
        assert person.family_name == "Martin"
        assert decode_email(person.email_address) == "anna@example.com"
        assert (person.birthday_day, person.birthday_month) == (4, 5)
        assert person.notes == "Likes tea"
        assert list(person.groups.all()) == [group]
        assert PermissionService.get_effective_permission(person, user) == PermissionLevel.OWNER
        assert inline.gift.price == Decimal("19.90")
        assert list(inline.gift.tags.all()) == [tag]
        assert (
            PermissionService.get_effective_permission(inline.gift, user) == PermissionLevel.OWNER
        )
        assert inline.event.schedule_type == Event.ScheduleType.ONE_TIME
        assert inline.event.date == date(2030, 5, 4)
        assert (
            PermissionService.get_effective_permission(inline.event, user) == PermissionLevel.OWNER
        )

    def test_create_inline_objects_reuses_existing_objects(self, user):
        person = PersonFactory(shared_with=[user])
        gift = GiftFactory(shared_with=[user])
        event = EventFactory(shared_with=[user])
        recipient_form, gift_form, occasion_form = _forms(
            user,
            recipient={"recipient": f"person:{person.person_id}"},
            gift={"gift": gift.pk},
            occasion={"event": event.pk},
        )

        inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)

        assert inline.recipient_value == f"person:{person.person_id}"
        assert (inline.gift, inline.event) == (gift, event)

    def test_create_inline_objects_without_event_returns_none(self, user):
        person = PersonFactory(shared_with=[user])
        recipient_form, gift_form, occasion_form = _forms(
            user,
            recipient={"recipient": f"person:{person.person_id}"},
            gift=_gift_data(),
            occasion={},
        )

        assert create_inline_objects(user, recipient_form, gift_form, occasion_form).event is None

    def test_created_objects_match_regular_create_views(self, user, authenticated_client):
        group = _editable_group(user)
        tag = _owned(user, GiftTagFactory())
        person_data = {"first_name": "Anna", "family_name": "Martin", "notes": "Likes tea"}
        person_data.update(
            email_address="anna@example.com",
            birthday_day="4",
            birthday_month="5",
            groups=[group.pk],
            interests=[tag.pk],
        )
        gift_data = {
            "name": "Scarf",
            "comment": "Wool",
            "url": "https://example.com/scarf",
            "price": "19.90",
            "tags": [tag.pk],
        }
        event_data = {
            "name": "Housewarming",
            "comment": "Party",
            "schedule_type": "recurring",
            "date": "2030-05-04",
            "recurrence": "yearly",
        }
        authenticated_client.post(reverse("gift_manager:person_create"), person_data)
        authenticated_client.post(reverse("gift_manager:gift_create"), gift_data)
        authenticated_client.post(reverse("gift_manager:event_create"), event_data)
        via_views = (
            Person.objects.get(),
            Gift.objects.get(),
            Event.objects.get(name="Housewarming"),
        )
        for obj in via_views:
            obj.delete()

        recipient_form, gift_form, occasion_form = _forms(
            user,
            recipient={f"new_person-{k}": v for k, v in person_data.items()},
            gift={f"new_gift-{k}": v for k, v in gift_data.items()},
            occasion={f"new_event-{k}": v for k, v in event_data.items()},
        )
        inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)
        person = Person.objects.get()

        expected_person, expected_gift, expected_event = via_views
        assert decode_email(person.email_address) == decode_email(expected_person.email_address)
        for field in ("first_name", "family_name", "birthday_day", "notes"):
            assert getattr(person, field) == getattr(expected_person, field), field
        assert person.user_link == expected_person.user_link
        assert set(person.groups.all()) == {group}
        assert set(person.interests.all()) == {tag}
        for field in ("name", "comment", "url", "price"):
            assert getattr(inline.gift, field) == getattr(expected_gift, field), field
        for field in ("name", "comment", "schedule_type", "date", "recurrence"):
            assert getattr(inline.event, field) == getattr(expected_event, field), field
        assert GiftTag.objects.count() == 1


class TestBuildRelationData:
    def test_build_relation_data_carries_plan_fields(self, user):
        person = PersonFactory(shared_with=[user])
        gift = GiftFactory(shared_with=[user])
        planned, _ = RelationStatus.objects.get_or_create(
            status_en="Planned", defaults={"status": "Planned"}
        )
        recipient_form = GuidedRecipientForm({"recipient": f"person:{person.person_id}"}, user=user)
        occasion_form = GuidedOccasionForm(
            {
                "status": planned.pk,
                "url": "https://example.com/o",
                "price": "5",
                "comment": "Wrap it",
                "is_surprise": "true",
            },
            user=user,
        )
        gift_form = GuidedGiftForm({"gift": gift.pk}, user=user)
        assert recipient_form.is_valid() and gift_form.is_valid() and occasion_form.is_valid()
        inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)

        data = build_relation_data(user, inline, occasion_form)

        assert data["recipient"] == f"person:{person.person_id}"
        assert data["gift"] == gift.pk
        assert data["event"] == ""
        assert data["status"] == planned.pk
        assert data["url"] == "https://example.com/o"
        assert data["price"] == Decimal(5)
        assert data["comment"] == "Wrap it"
        assert data["is_surprise"] is True

    def test_build_relation_data_for_new_person_uses_person_recipient_value(self, user):
        recipient_form, gift_form, occasion_form = _forms(
            user, recipient=_person_data(), gift=_gift_data(), occasion={}
        )
        inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)

        data = build_relation_data(user, inline, occasion_form)

        assert data["recipient"] == inline.recipient_value
        assert data["recipient"].startswith("person:")
        assert data["status"] == _idea_status().pk


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            GuidedRecipientForm.both_message,
            "Choisissez un destinataire existant ou saisissez une nouvelle personne, pas les deux.",
        ),
        (
            GuidedGiftForm.both_message,
            "Choisissez un cadeau existant ou saisissez-en un nouveau, pas les deux.",
        ),
        (
            GuidedOccasionForm.both_message,
            "Choisissez un événement existant ou saisissez-en un nouveau, pas les deux.",
        ),
    ],
)
def test_french_messages_are_exactly_translated(message, expected):
    with translation.override("fr"):
        assert str(message) == expected


class TestStepThreeWording:
    def test_event_fields_are_labelled_as_event_fields(self, user):
        form = GuidedOccasionForm(user=user)

        labels = {name: str(field.label) for name, field in form.new_form.fields.items()}
        assert labels["name"] == "Event name"
        assert labels["date"] == "Event date"
        assert labels["comment"] == "Event comment"

    def test_gift_plan_fields_are_labelled_as_gift_plan_fields(self, user):
        form = GuidedOccasionForm(user=user)

        assert str(form.fields["comment"].label) == "Gift plan comment"
        assert str(form.fields["due_date"].label) == "Due date"
