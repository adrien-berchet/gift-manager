"""Givers of a revealed gift as the recipient sees them.

A revealed gift keeps every plan owner in ``giver_accounts``. Owners the recipient has as a
contact show as that contact, owners who are the recipient's friends show by name, and the
others are counted ("and 1 other") without revealing who they are.
"""

import pytest
from django.urls import reverse

from gift_manager.forms import ReceivedGiftForm
from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.received_gifts import annotate_snapshot_givers
from gift_manager.received_gifts import reveal_plan
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


def _given():
    return RelationStatus.objects.get_or_create(status_en="Given", defaults={"status": "Given"})[0]


@pytest.fixture
def recipient():
    return UserFactory(username="charlie", first_name="Charlie", last_name="Recipient")


@pytest.fixture
def revealer(recipient):
    user = UserFactory(username="alice", first_name="Alice", last_name="Smith")
    user.profile.friends.add(recipient.profile)
    return user


@pytest.fixture
def stranger():
    """A co-owner of the plan who is neither a contact nor a friend of the recipient."""
    return UserFactory(username="bob", first_name="Bob", last_name="Jones")


def _reveal(revealer, recipient, *co_owners, title="Leather Bag"):
    plan = Relation.objects.create(
        gift=GiftFactory(name=title),
        person=PersonFactory(account=recipient),
        status=_given(),
    )
    for owner in (revealer, *co_owners):
        _own(owner, plan)
    [gift] = reveal_plan(plan, revealer)
    return gift


class TestRevealSnapshot:
    def test_reveal_does_not_copy_owner_names_into_the_free_text_giver(
        self, revealer, recipient, stranger
    ):
        gift = _reveal(revealer, recipient, stranger)

        assert gift.giver_label == ""
        assert set(gift.giver_accounts.all()) == {revealer, stranger}


class TestAnnotateSnapshotGivers:
    def test_contact_is_shown_and_unknown_co_owner_is_counted(self, revealer, recipient, stranger):
        contact = _own(recipient, PersonFactory(first_name="Ali", account=revealer))
        gift = _reveal(revealer, recipient, stranger)

        annotate_snapshot_givers(recipient, [gift])

        assert list(gift.giver_persons.all()) == [contact]
        assert gift.snapshot_giver_names == []
        assert gift.other_givers_count == 1
        assert gift.other_givers_label == "and 1 other"

    def test_friend_without_contact_is_shown_by_name(self, revealer, recipient, stranger):
        gift = _reveal(revealer, recipient, stranger)

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_names == ["Alice Smith"]
        assert gift.other_givers_count == 1
        assert gift.other_givers_label == "and 1 other"

    def test_only_unknown_givers_are_counted_without_and(self, recipient, stranger):
        gift = ReceivedGiftFactory(recipient_user=recipient, giver_label="")
        other = UserFactory()
        gift.giver_accounts.set([stranger, other])

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_names == []
        assert gift.other_givers_count == 2
        assert gift.other_givers_label == "2 other givers"

    def test_free_text_giver_replaces_the_snapshot_givers(self, revealer, recipient, stranger):
        gift = _reveal(revealer, recipient, stranger)
        gift.giver_label = "Aunt Marie"
        gift.save(update_fields=["giver_label"])

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_names == []
        assert gift.other_givers_count == 0
        assert gift.other_givers_label == ""

    def test_manual_gift_has_no_snapshot_givers(self, recipient):
        gift = ReceivedGiftFactory(recipient_user=recipient)

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_names == []
        assert gift.other_givers_count == 0

    def test_query_count_does_not_grow_with_the_number_of_gifts(
        self, revealer, recipient, stranger, django_assert_max_num_queries
    ):
        gifts = [_reveal(revealer, recipient, stranger, title=f"Gift {i}") for i in range(5)]
        loaded = list(
            ReceivedGift.objects.filter(pk__in=[g.pk for g in gifts]).prefetch_related(
                "giver_persons", "giver_groups", "giver_accounts"
            )
        )
        with django_assert_max_num_queries(3):
            annotate_snapshot_givers(recipient, loaded)

    def test_contact_added_after_the_reveal_is_shown_as_that_contact(
        self, revealer, recipient, stranger
    ):
        gift = _reveal(revealer, recipient, stranger)
        contact = _own(recipient, PersonFactory(first_name="Bobby", account=stranger))

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_persons == [contact]
        assert gift.snapshot_giver_names == ["Alice Smith"]
        assert gift.other_givers_count == 0
        assert list(gift.giver_persons.all()) == []

    @pytest.mark.parametrize("change", ["unfriend", "deactivate"])
    def test_friend_who_is_no_longer_one_is_only_counted(
        self, revealer, recipient, stranger, change
    ):
        gift = _reveal(revealer, recipient, stranger)
        if change == "unfriend":
            recipient.profile.friends.remove(revealer.profile)
        else:
            revealer.is_active = False
            revealer.save(update_fields=["is_active"])

        annotate_snapshot_givers(recipient, [gift])

        assert gift.snapshot_giver_names == []
        assert gift.other_givers_count == 2
        assert gift.other_givers_label == "2 other givers"

    def test_label_can_be_ignored_to_summarise_the_plan_givers(self, revealer, recipient, stranger):
        gift = _reveal(revealer, recipient, stranger)
        gift.giver_label = "Aunt Marie"

        annotate_snapshot_givers(recipient, [gift], ignore_label=True)

        assert gift.snapshot_giver_names == ["Alice Smith"]
        assert gift.other_givers_count == 1


class TestGiverRendering:
    def test_list_and_detail_hide_unknown_co_owner_names(
        self, client, revealer, recipient, stranger
    ):
        _own(recipient, PersonFactory(first_name="Ali", family_name="Contact", account=revealer))
        gift = _reveal(revealer, recipient, stranger)
        client.force_login(recipient)

        for url in (
            reverse("gift_manager:received_gift_list"),
            reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id}),
        ):
            content = client.get(url).content.decode()
            assert "Ali Contact" in content
            assert "and 1 other" in content
            assert "Bob" not in content
            assert "Jones" not in content

    def test_friend_without_contact_is_rendered_by_name(
        self, client, revealer, recipient, stranger
    ):
        gift = _reveal(revealer, recipient, stranger)
        client.force_login(recipient)

        url = reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id})
        content = client.get(url).content.decode()

        assert "Alice Smith" in content
        assert "and 1 other" in content
        assert "Bob Jones" not in content


class TestEditingARevealedGift:
    def _post_data(self, gift, **overrides):
        data = {
            "gift_mode": "new",
            "title": gift.title,
            "received_on": gift.received_on.isoformat(),
            "giver_mode": "contacts",
            "occasion_mode": "other",
            "reaction_rating": "4",
        }
        data.update(overrides)
        return data

    def test_can_be_saved_without_picking_a_contact(self, revealer, recipient, stranger):
        gift = _reveal(revealer, recipient, stranger)

        form = ReceivedGiftForm(self._post_data(gift), instance=gift, user=recipient)

        assert form.is_valid(), form.errors
        form.save()
        gift.refresh_from_db()
        assert gift.reaction_rating == 4
        assert set(gift.giver_accounts.all()) == {revealer, stranger}

    def test_form_summarises_the_snapshot_givers(self, revealer, recipient, stranger):
        gift = _reveal(revealer, recipient, stranger)

        form = ReceivedGiftForm(instance=gift, user=recipient)

        assert form.snapshot_givers_summary == "Alice Smith, and 1 other"

    def test_unticking_a_contact_drops_its_account(self, revealer, recipient, stranger):
        ali = _own(recipient, PersonFactory(first_name="Ali", account=revealer))
        bobby = _own(recipient, PersonFactory(first_name="Bobby", account=stranger))
        gift = _reveal(revealer, recipient, stranger)
        assert set(gift.giver_persons.all()) == {ali, bobby}

        form = ReceivedGiftForm(
            self._post_data(gift, givers=[f"person:{bobby.person_id}"]),
            instance=gift,
            user=recipient,
        )

        assert form.is_valid(), form.errors
        form.save()
        assert list(gift.giver_persons.all()) == [bobby]
        assert set(gift.giver_accounts.all()) == {stranger}

    def test_free_text_giver_keeps_the_plan_givers(self, revealer, recipient, stranger):
        _own(recipient, PersonFactory(first_name="Ali", family_name="Contact", account=revealer))
        gift = _reveal(revealer, recipient, stranger)

        form = ReceivedGiftForm(
            self._post_data(gift, giver_mode="other", giver_label="The whole office"),
            instance=gift,
            user=recipient,
        )

        assert form.is_valid(), form.errors
        form.save()
        gift.refresh_from_db()
        assert gift.giver_label == "The whole office"
        assert list(gift.giver_persons.all()) == []
        assert set(gift.giver_accounts.all()) == {revealer, stranger}
        edit_form = ReceivedGiftForm(instance=gift, user=recipient)
        assert edit_form.snapshot_givers_summary == "Ali Contact, and 1 other"

    def test_recipient_without_contacts_can_save_the_rendered_form(
        self, client, revealer, recipient, stranger
    ):
        gift = _reveal(revealer, recipient, stranger)
        client.force_login(recipient)
        url = reverse("gift_manager:received_gift_edit", kwargs={"pk": gift.received_gift_id})
        assert 'name="giver_mode" value="other"' in client.get(url).content.decode()

        response = client.post(
            url, self._post_data(gift, giver_mode="other", giver_label=""), HTTP_HX_REQUEST="true"
        )

        assert response.status_code == 200
        gift.refresh_from_db()
        assert gift.reaction_rating == 4

    def test_choosing_someone_else_with_contacts_still_needs_a_name(
        self, revealer, recipient, stranger
    ):
        _own(recipient, PersonFactory(first_name="Marie"))
        gift = _reveal(revealer, recipient, stranger)

        form = ReceivedGiftForm(
            self._post_data(gift, giver_mode="other", giver_label=""),
            instance=gift,
            user=recipient,
        )

        assert not form.is_valid()
        assert "giver_label" in form.errors

    def test_manual_gift_still_requires_a_giver(self, recipient):
        contact = _own(recipient, PersonFactory(first_name="Marie"))
        gift = ReceivedGiftFactory(recipient_user=recipient, giver_label="")
        gift.giver_persons.set([contact])

        form = ReceivedGiftForm(self._post_data(gift), instance=gift, user=recipient)

        assert not form.is_valid()
        assert "givers" in form.errors
