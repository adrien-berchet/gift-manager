"""Tests for the received gift form: giver and occasion modes."""

from datetime import date

import pytest

from gift_manager.forms import ReceivedGiftForm
from gift_manager.forms import RelationRevealForm
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


def _data(**overrides):
    data = {"title": "Scarf", "received_on": "2026-11-09"}
    data.update(overrides)
    return data


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def marie(user):
    return _own(user, PersonFactory(first_name="Marie", family_name="Dupont"))


@pytest.fixture
def paul(user):
    return _own(user, PersonFactory(first_name="Paul", family_name="Dupont"))


@pytest.fixture
def family(user):
    return _own(user, PersonGroupFactory(name="Dupont family"))


@pytest.fixture
def birthday(user):
    return _own(user, EventFactory(name="Birthday 2026"))


@pytest.mark.django_db
class TestGiverChoices:
    def test_people_and_groups_are_two_sections_of_one_field(self, user, marie, paul, family):
        form = ReceivedGiftForm(user=user)

        sections = [
            (label, [option.choice_label for option in options])
            for label, options in form.giver_sections
        ]
        assert sections == [
            ("People", [str(marie), str(paul)]),
            ("Groups", ["Dupont family"]),
        ]
        values = [
            value for _label, options in form.fields["givers"].choices for value, _ in options
        ]
        assert values == [
            f"person:{marie.person_id}",
            f"person:{paul.person_id}",
            f"group:{family.group_id}",
        ]

    def test_inaccessible_people_are_not_offered(self, user, marie):
        PersonFactory(first_name="Stranger")

        form = ReceivedGiftForm(user=user)

        assert [o.choice_label for _l, opts in form.giver_sections for o in opts] == [str(marie)]

    def test_contacts_mode_is_the_default_when_contacts_exist(self, user, marie):
        form = ReceivedGiftForm(user=user)

        assert form.giver_contacts_available is True
        assert form["giver_mode"].value() == "contacts"

    def test_free_text_is_the_only_mode_without_contacts(self, user):
        form = ReceivedGiftForm(user=user)

        assert form.giver_contacts_available is False
        assert form["giver_mode"].value() == "other"


@pytest.mark.django_db
class TestGiverModes:
    def test_contacts_mode_saves_people_and_groups(self, user, marie, paul, family):
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="contacts",
                givers=[f"person:{marie.person_id}", f"group:{family.group_id}"],
                # Typed earlier in the hidden free-text panel: ignored in contacts mode
                giver_label="Aunt Marie",
            ),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        gift = form.save()

        assert list(gift.giver_persons.all()) == [marie]
        assert list(gift.giver_groups.all()) == [family]
        assert gift.giver_label == ""

    def test_other_mode_keeps_only_the_free_text(self, user, marie):
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="other",
                givers=[f"person:{marie.person_id}"],
                giver_label="  Aunt Marie  ",
            ),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        gift = form.save()

        assert gift.giver_label == "Aunt Marie"
        assert not gift.giver_persons.exists()
        assert not gift.giver_groups.exists()

    def test_contacts_mode_requires_a_giver(self, user, marie):
        form = ReceivedGiftForm(data=_data(giver_mode="contacts", giver_label="Aunt"), user=user)

        assert not form.is_valid()
        assert form.errors["givers"] == ["Select at least one person or group."]

    def test_other_mode_requires_a_name(self, user, marie):
        form = ReceivedGiftForm(
            data=_data(giver_mode="other", givers=[f"person:{marie.person_id}"]), user=user
        )

        assert not form.is_valid()
        assert form.errors["giver_label"] == ["Enter who gave this gift."]

    def test_inaccessible_giver_is_rejected(self, user):
        stranger = PersonFactory(first_name="Stranger")

        form = ReceivedGiftForm(
            data=_data(giver_mode="contacts", givers=[f"person:{stranger.person_id}"]), user=user
        )

        assert not form.is_valid()
        assert "givers" in form.errors

    @pytest.mark.parametrize(
        ("extra", "expected_label"),
        [
            ({"giver_label": "Aunt Marie"}, "Aunt Marie"),
            ({}, None),
        ],
    )
    def test_mode_is_inferred_when_not_posted(self, user, marie, extra, expected_label):
        form = ReceivedGiftForm(data=_data(**extra), user=user)

        if expected_label is None:
            assert not form.is_valid()
            assert "Please specify who gave this gift" in str(form.errors)
        else:
            form.instance.recipient_user = user
            assert form.is_valid(), form.errors
            assert form.save().giver_label == expected_label

    def test_edit_starts_in_the_mode_of_the_saved_givers(self, user, marie, family):
        by_contacts = ReceivedGiftFactory(recipient_user=user, giver_label="")
        by_contacts.giver_persons.set([marie])
        by_contacts.giver_groups.set([family])
        by_name = ReceivedGiftFactory(recipient_user=user, giver_label="Aunt Marie")

        contacts_form = ReceivedGiftForm(instance=by_contacts, user=user)
        name_form = ReceivedGiftForm(instance=by_name, user=user)

        assert contacts_form["giver_mode"].value() == "contacts"
        assert sorted(contacts_form["givers"].value()) == sorted(
            [f"person:{marie.person_id}", f"group:{family.group_id}"]
        )
        assert name_form["giver_mode"].value() == "other"

    def test_edit_keeps_a_giver_whose_access_was_revoked(self, user, marie):
        former = PersonFactory(first_name="Former", family_name="Friend")
        gift = ReceivedGiftFactory(recipient_user=user, giver_label="")
        gift.giver_persons.set([former])

        form = ReceivedGiftForm(
            instance=gift,
            data=_data(
                giver_mode="contacts",
                givers=[f"person:{former.person_id}", f"person:{marie.person_id}"],
            ),
            user=user,
        )

        assert form.is_valid(), form.errors
        form.save()
        assert set(gift.giver_persons.all()) == {former, marie}


@pytest.mark.django_db
class TestOccasionModes:
    def test_event_mode_replaces_the_free_text_with_the_event_name(self, user, marie, birthday):
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="contacts",
                givers=[f"person:{marie.person_id}"],
                occasion_mode="event",
                event=birthday.pk,
                occasion_text="Christmas",
            ),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        gift = form.save()

        assert gift.event == birthday
        # The typed text is dropped; the model snapshots the event name instead
        assert gift.occasion_text == "Birthday 2026"

    def test_other_mode_clears_the_event(self, user, marie, birthday):
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="contacts",
                givers=[f"person:{marie.person_id}"],
                occasion_mode="other",
                event=birthday.pk,
                occasion_text="Housewarming",
            ),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        gift = form.save()

        assert gift.event is None
        assert gift.occasion_text == "Housewarming"

    def test_occasion_stays_optional(self, user, marie, birthday):
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="contacts", givers=[f"person:{marie.person_id}"], occasion_mode="event"
            ),
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_initial_mode(self, user, birthday):
        with_event = ReceivedGiftFactory(recipient_user=user, giver_label="A", event=birthday)
        with_text = ReceivedGiftFactory(
            recipient_user=user, giver_label="A", occasion_text="Christmas", event=None
        )

        assert ReceivedGiftForm(user=user)["occasion_mode"].value() == "event"
        assert ReceivedGiftForm(instance=with_event, user=user)["occasion_mode"].value() == "event"
        assert ReceivedGiftForm(instance=with_text, user=user)["occasion_mode"].value() == "other"

    def test_edit_keeps_an_event_whose_access_was_revoked(self, user, marie):
        private_event = EventFactory(name="Their wedding")
        # Saving snapshots the event name into occasion_text
        gift = ReceivedGiftFactory(
            recipient_user=user, giver_label="A", event=private_event, occasion_text=""
        )
        form = ReceivedGiftForm(instance=gift, user=user)

        assert form["occasion_mode"].value() == "event"
        assert str(form["event"].value()) == str(private_event.pk)

        data = _data(
            giver_mode="other",
            giver_label="A",
            occasion_mode="event",
            event=private_event.pk,
            occasion_text=gift.occasion_text,  # the hidden panel's input is posted too
        )
        form = ReceivedGiftForm(instance=gift, data=data, user=user)
        assert form.is_valid(), form.errors
        form.save()
        gift.refresh_from_db()
        assert gift.event == private_event
        assert gift.occasion_text == "Their wedding"

    def test_inaccessible_event_cannot_be_newly_chosen(self, user, marie):
        private_event = EventFactory(name="Their wedding")
        form = ReceivedGiftForm(
            data=_data(
                giver_mode="other", giver_label="A", occasion_mode="event", event=private_event.pk
            ),
            user=user,
        )

        assert not form.is_valid()
        assert "event" in form.errors

    def test_free_text_is_the_only_mode_without_events(self, user):
        # Global events (Christmas, ...) are visible to everyone
        Event.objects.filter(is_global=True).delete()
        form = ReceivedGiftForm(user=user)

        assert form.event_choices_available is False
        assert form["occasion_mode"].value() == "other"


@pytest.mark.django_db
def test_received_gift_from_group_hierarchy_saved_through_form_warns_regift(user, family):
    """Groups chosen in the form feed the re-gift warning (through the group hierarchy)."""
    from gift_manager.gift_history import find_regift_warnings

    member = _own(user, PersonFactory(first_name="Charlie"))
    member.groups.add(family)
    form = ReceivedGiftForm(
        data=_data(title="Board Game", giver_mode="contacts", givers=[f"group:{family.group_id}"]),
        user=user,
    )
    form.instance.recipient_user = user
    assert form.is_valid(), form.errors
    received = form.save()

    assert find_regift_warnings(user, member, "Board Game") == [received]
    assert received.received_on == date(2026, 11, 9)


@pytest.mark.django_db
class TestGiftModes:
    @pytest.fixture
    def wish(self, user):
        return WishFactory(wisher=user, title="Headphones", url="https://shop.example/hp")

    def _posted(self, marie, **overrides):
        return _data(giver_mode="contacts", givers=[f"person:{marie.person_id}"], **overrides)

    def test_wish_mode_takes_title_and_link_from_the_wish(self, user, marie, wish):
        form = ReceivedGiftForm(
            data=self._posted(
                marie, gift_mode="wish", wish=wish.pk, title="Typed", url="https://typed.example"
            ),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        gift = form.save()

        assert gift.wish == wish
        assert gift.title == "Headphones"
        assert gift.url == "https://shop.example/hp"

    def test_wish_mode_works_with_empty_title_and_link(self, user, marie, wish):
        form = ReceivedGiftForm(
            data=self._posted(marie, gift_mode="wish", wish=wish.pk, title="", url=""),
            user=user,
        )
        form.instance.recipient_user = user

        assert form.is_valid(), form.errors
        assert form.save().title == "Headphones"

    def test_wish_mode_requires_a_wish(self, user, marie, wish):
        form = ReceivedGiftForm(
            data=self._posted(marie, gift_mode="wish", title="Typed"), user=user
        )

        assert not form.is_valid()
        assert form.errors["wish"] == ["Select a wish."]

    def test_new_mode_drops_the_wish_and_requires_a_title(self, user, marie, wish):
        missing_title = ReceivedGiftForm(
            data=self._posted(marie, gift_mode="new", wish=wish.pk, title=""), user=user
        )
        assert not missing_title.is_valid()
        assert missing_title.errors["title"] == ["This field is required."]

        form = ReceivedGiftForm(
            data=self._posted(marie, gift_mode="new", wish=wish.pk, title="Scarf"), user=user
        )
        form.instance.recipient_user = user
        assert form.is_valid(), form.errors
        gift = form.save()
        assert gift.wish is None
        assert gift.title == "Scarf"

    def test_title_is_marked_required_without_blocking_wish_mode_in_the_browser(self, user):
        form = ReceivedGiftForm(user=user)

        assert form.title_required is True
        assert "required" not in form["title"].build_widget_attrs({})

    def test_initial_mode(self, user, wish):
        linked = ReceivedGiftFactory(recipient_user=user, wish=wish)
        unlinked = ReceivedGiftFactory(recipient_user=user)

        assert ReceivedGiftForm(user=user)["gift_mode"].value() == "new"
        assert ReceivedGiftForm(user=user, initial={"wish": wish})["gift_mode"].value() == "wish"
        assert ReceivedGiftForm(instance=linked, user=user)["gift_mode"].value() == "wish"
        assert ReceivedGiftForm(instance=unlinked, user=user)["gift_mode"].value() == "new"

    def test_new_gift_is_the_only_mode_without_wishes(self, user):
        form = ReceivedGiftForm(user=user)

        assert form.wish_choices_available is False
        assert form["gift_mode"].value() == "new"


@pytest.mark.django_db
class TestMarkWishReceived:
    @pytest.fixture
    def wish(self, user):
        return WishFactory(wisher=user, title="Chocolate")

    def _save(self, user, marie, **overrides):
        data = _data(giver_mode="contacts", givers=[f"person:{marie.person_id}"], **overrides)
        form = ReceivedGiftForm(data=data, user=user)
        form.instance.recipient_user = user
        assert form.is_valid(), form.errors
        return form.save()

    def test_ticked_by_default(self, user, wish):
        assert ReceivedGiftForm(user=user)["fulfills_wish"].value() is True
        assert ReceivedGiftForm(user=user, initial={"wish": wish})["fulfills_wish"].value() is True

    def test_ticked_marks_the_wish_as_received(self, user, marie, wish):
        gift = self._save(user, marie, gift_mode="wish", wish=wish.pk, fulfills_wish="on")

        assert gift.fulfills_wish is True
        wish.refresh_from_db()
        assert wish.is_fulfilled is True

    def test_unticked_keeps_the_wish_open(self, user, marie, wish):
        # An unticked checkbox is simply not posted
        gift = self._save(user, marie, gift_mode="wish", wish=wish.pk)

        assert gift.wish == wish
        assert gift.fulfills_wish is False
        wish.refresh_from_db()
        assert wish.is_fulfilled is False

    def test_edit_shows_the_saved_choice(self, user, wish):
        gift = ReceivedGiftFactory(recipient_user=user, wish=wish, fulfills_wish=False)

        assert ReceivedGiftForm(instance=gift, user=user)["fulfills_wish"].value() is False

    def test_without_the_wish_side_the_flag_is_reset(self, user, marie, wish):
        new_gift = self._save(user, marie, gift_mode="new", title="Scarf", wish=wish.pk)
        assert new_gift.fulfills_wish is True

        # Older clients post no mode and no checkbox: the wish is marked received as before
        legacy = self._save(user, marie, title="Chocolate", wish=wish.pk)
        assert legacy.fulfills_wish is True
        wish.refresh_from_db()
        assert wish.is_fulfilled is True

    def test_unused_side_errors_do_not_block_selected_mode(self, user, marie, wish):
        other_user = UserFactory()
        foreign_event = _own(other_user, EventFactory(name="Foreign"))
        form = ReceivedGiftForm(
            data={
                "gift_mode": "wish",
                "received_on": "2026-11-09",
                "title": "",
                "url": "not-a-valid-url",
                "wish": str(wish.pk),
                "fulfills_wish": "on",
                "giver_mode": "other",
                "givers": [f"person:{marie.person_id}"],
                "giver_label": "Uncle Paul",
                "occasion_mode": "other",
                "event": str(foreign_event.pk),
                "occasion_text": "Christmas",
            },
            user=user,
        )
        form.instance.recipient_user = user
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.wish == wish
        assert saved.title == wish.title
        assert saved.url == wish.url
        assert saved.giver_label == "Uncle Paul"
        assert saved.event is None

    def test_soft_deleted_existing_wish_stays_selectable_on_edit(self, user, marie, wish):
        gift = self._save(user, marie, gift_mode="wish", wish=wish.pk, fulfills_wish="on")
        wish.is_deleted_by_wisher = True
        wish.save(update_fields=["is_deleted_by_wisher"])

        form = ReceivedGiftForm(instance=gift, user=user)
        assert wish in form.fields["wish"].queryset


class TestRelationRevealForm:
    def test_valid_and_invalid_inputs(self):
        invalid_form = RelationRevealForm(
            data={
                "title": "   ",
                "url": "javascript:alert(1)",
            }
        )
        assert not invalid_form.is_valid()
        assert "title" in invalid_form.errors
        assert "url" in invalid_form.errors

        valid_form = RelationRevealForm(
            data={
                "title": "Camera",
                "url": "https://example.com/camera",
                "received_on": "2026-11-10",
                "occasion_text": "Birthday",
                "giver_note": "Line 1\nLine 2",
            }
        )
        assert valid_form.is_valid(), valid_form.errors
        assert valid_form.cleaned_data["title"] == "Camera"
        assert valid_form.cleaned_data["giver_note"] == "Line 1\nLine 2"
