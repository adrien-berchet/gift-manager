"""Tests for gift plan reveal and reaction feedback mechanism."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_coordination import hidden_recipient_ids
from gift_manager.plan_coordination import plan_recipient_account_ids
from gift_manager.received_gifts import can_reveal_plan
from gift_manager.received_gifts import get_reveal_targets
from gift_manager.received_gifts import reveal_plan
from gift_manager.received_gifts import share_reaction_feedback
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

User = get_user_model()


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


@pytest.fixture
def given_status(db):
    return _status("Given")


@pytest.fixture
def planned_status(db):
    return _status("Planned")


@pytest.mark.django_db
class TestPlanRecipientAccountIdsParity:
    """Verify plan_recipient_account_ids parity with hidden_recipient_ids."""

    def test_single_person_recipient(self, db, given_status):
        recipient_user = UserFactory()
        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()

        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            is_surprise=True,
        )

        assert plan_recipient_account_ids(relation) == {recipient_user.id}
        assert hidden_recipient_ids(relation) == {recipient_user.id}

    def test_group_recipient_with_multiple_accounts(self, db, given_status):
        u1 = UserFactory()
        u2 = UserFactory()
        UserFactory()  # not in group
        p1 = PersonFactory(account=u1)
        p2 = PersonFactory(account=u2)
        p3 = PersonFactory(account=None)  # unlinked person

        group = PersonGroupFactory()
        p1.groups.add(group)
        p2.groups.add(group)
        p3.groups.add(group)
        gift = GiftFactory()

        relation = Relation.objects.create(
            gift=gift,
            group=group,
            status=given_status,
            is_surprise=True,
        )

        assert plan_recipient_account_ids(relation) == {u1.id, u2.id}
        assert hidden_recipient_ids(relation) == {u1.id, u2.id}

    def test_non_surprise_hidden_ids_empty_but_account_ids_preserved(self, db, given_status):
        recipient_user = UserFactory()
        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()

        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            is_surprise=False,
        )

        assert plan_recipient_account_ids(relation) == {recipient_user.id}
        assert hidden_recipient_ids(relation) == set()


@pytest.mark.django_db
class TestCanRevealPlan:
    """Verify permissions and eligibility for revealing gift plans."""

    def test_can_reveal_plan_success(self, db, given_status):
        owner = UserFactory()
        recipient_user = UserFactory()
        owner.profile.friends.add(recipient_user.profile)

        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        assert can_reveal_plan(relation, owner) is True
        targets = get_reveal_targets(relation, owner)
        assert targets == [recipient_user]

    def test_cannot_reveal_if_not_given(self, db, planned_status):
        owner = UserFactory()
        recipient_user = UserFactory()
        owner.profile.friends.add(recipient_user.profile)

        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=planned_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        assert can_reveal_plan(relation, owner) is False

    def test_cannot_reveal_if_already_revealed(self, db, given_status):
        owner = UserFactory()
        recipient_user = UserFactory()
        owner.profile.friends.add(recipient_user.profile)

        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            revealed_at=timezone.now(),
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        assert can_reveal_plan(relation, owner) is False

    def test_cannot_reveal_if_not_owner(self, db, given_status):
        owner = UserFactory()
        editor = UserFactory()
        recipient_user = UserFactory()
        owner.profile.friends.add(recipient_user.profile)
        editor.profile.friends.add(recipient_user.profile)

        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            editor, relation, permission_level=PermissionLevel.EDITOR
        )

        assert can_reveal_plan(relation, editor) is False

    def test_superuser_without_owner_permission_cannot_reveal(self, db, given_status):
        admin = UserFactory(is_superuser=True)
        owner = UserFactory()
        recipient_user = UserFactory()
        admin.profile.friends.add(recipient_user.profile)

        person = PersonFactory(account=recipient_user)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        # Superusers can view but cannot reveal plans they do not own
        assert can_reveal_plan(relation, admin) is False

    def test_cannot_reveal_if_not_friends_with_recipient(self, db, given_status):
        owner = UserFactory()
        stranger_recipient = UserFactory()
        # Not friends!

        person = PersonFactory(account=stranger_recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        assert can_reveal_plan(relation, owner) is False
        assert get_reveal_targets(relation, owner) == []


@pytest.mark.django_db
class TestRevealPlanExecution:
    """Verify reveal_plan writes correct snapshot and maintains privacy & durability."""

    def test_reveal_creates_received_gift_snapshot(self, db, given_status):
        owner1 = UserFactory(first_name="Alice", last_name="Smith")
        owner2 = UserFactory(first_name="Bob", last_name="Jones")
        recipient = UserFactory(first_name="Charlie")
        owner1.profile.friends.add(recipient.profile)

        # Charlie has an address book card for Alice
        alice_card = PersonFactory(first_name="Alice", account=owner1)
        PermissionService.create_or_update_permission(
            recipient, alice_card, permission_level=PermissionLevel.OWNER
        )

        person = PersonFactory(first_name="Charlie", account=recipient)
        gift = GiftFactory(
            name="Leather Bag",
            url="https://example.com/bag",
            comment="Internal note: bought on sale for $50",
        )
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            comment="Private coordination comment",
            price=50.00,
        )
        PermissionService.create_or_update_permission(
            owner1, relation, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            owner2, relation, permission_level=PermissionLevel.OWNER
        )

        reveal_date = date(2026, 11, 5)
        created_gifts = reveal_plan(
            relation,
            owner1,
            title="Vintage Leather Bag",
            url="https://example.com/clean-link",
            received_on=reveal_date,
            occasion_text="Birthday 2026",
            giver_note="Hope you enjoy this bag!",
        )

        assert len(created_gifts) == 1
        rg = created_gifts[0]
        assert rg.recipient_user == recipient
        assert rg.title == "Vintage Leather Bag"
        assert rg.url == "https://example.com/clean-link"
        assert rg.received_on == reveal_date
        assert rg.occasion_text == "Birthday 2026"
        assert rg.giver_note == "Hope you enjoy this bag!"
        assert rg.source_relation == relation

        # Privacy checks: no internal notes, prices, or comments leaked
        assert "50" not in rg.description
        assert "Private coordination comment" not in rg.description
        assert "Internal note" not in rg.description

        # Giver provenance checks
        assert list(rg.giver_persons.all()) == [alice_card]
        giver_accs = set(rg.giver_accounts.all())
        assert giver_accs == {owner1, owner2}
        assert "Alice Smith" in rg.source_givers_text
        assert "Bob Jones" in rg.source_givers_text

        # Relation revealed_at is set
        relation.refresh_from_db()
        assert relation.revealed_at is not None

        # Re-revealing fails
        assert can_reveal_plan(relation, owner1) is False

    def test_durability_when_relation_is_deleted(self, db, given_status):
        owner = UserFactory(first_name="Dave")
        recipient = UserFactory(first_name="Eve")
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(first_name="Eve", account=recipient)
        gift = GiftFactory(name="Smart Watch")
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created_gifts = reveal_plan(
            relation,
            owner,
            title="Smart Watch",
            giver_note="Track your runs!",
        )
        rg_id = created_gifts[0].received_gift_id

        # Delete the source relation
        relation.delete()

        # Recipient's received gift still exists and retains givers & notes!
        rg = ReceivedGift.objects.get(received_gift_id=rg_id)
        assert rg.source_relation is None
        assert rg.title == "Smart Watch"
        assert rg.giver_note == "Track your runs!"
        assert owner in rg.giver_accounts.all()
        assert "Dave" in rg.source_givers_text


@pytest.mark.django_db
class TestShareReactionFeedback:
    """Verify reaction sharing back to source plan."""

    def test_share_reaction_feedback_success(self, db, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created = reveal_plan(relation, owner, title="Headphones")
        rg = created[0]

        # Recipient updates reaction rating & note
        rg.reaction_rating = 5
        rg.reaction_note = "Incredible sound quality!"
        rg.save()

        success = share_reaction_feedback(rg, recipient)
        assert success is True

        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "Incredible sound quality!"

    def test_share_reaction_preserves_existing_giver_reaction(self, db, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            reaction_rating=4,
            reaction_note="Giver already noted they seemed pleased",
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created = reveal_plan(relation, owner, title="Headphones")
        rg = created[0]
        rg.reaction_rating = 5
        rg.reaction_note = "Recipient loves it even more"
        rg.save()

        success = share_reaction_feedback(rg, recipient)
        assert success is True

        relation.refresh_from_db()
        # Existing values are preserved
        assert relation.reaction_rating == 4
        assert relation.reaction_note == "Giver already noted they seemed pleased"

    def test_share_reaction_rejected_if_unfriended(self, db, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created = reveal_plan(relation, owner, title="Headphones")
        rg = created[0]
        rg.reaction_rating = 5
        rg.save()

        # Unfriend
        owner.profile.friends.remove(recipient.profile)

        success = share_reaction_feedback(rg, recipient)
        assert success is False


@pytest.mark.django_db
class TestRelationRevealViews:
    """Verify HTTP view endpoints for reveal and reaction sharing."""

    def test_relation_reveal_get_and_post(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory(username="recip")
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(first_name="Recip", account=recipient)
        gift = GiftFactory(name="Coffee Maker")
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        url = reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})

        # GET request renders modal partial with targets
        resp = client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Coffee Maker" in resp.content.decode()

        # POST reveals the plan
        post_resp = client.post(
            url,
            {
                "title": "Espresso Machine",
                "url": "https://example.com/espresso",
                "received_on": "2026-11-08",
                "occasion_text": "Housewarming",
                "giver_note": "Enjoy fresh coffee!",
            },
            HTTP_HX_REQUEST="true",
        )
        assert post_resp.status_code == 200
        assert "modal:close" in post_resp.headers.get("HX-Trigger", "")

        # Verify ReceivedGift was created for recipient
        rg = ReceivedGift.objects.get(recipient_user=recipient)
        assert rg.title == "Espresso Machine"
        assert rg.giver_note == "Enjoy fresh coffee!"

    def test_relation_reveal_forbidden_for_non_owner(self, client, given_status):
        owner = UserFactory()
        other = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(other)
        url = reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})

        resp = client.get(url)
        # Not accessible or 403/404
        assert resp.status_code in {403, 404}

    def test_received_gift_share_reaction_post(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created = reveal_plan(relation, owner, title="Book")
        rg = created[0]
        rg.reaction_rating = 5
        rg.reaction_note = "A masterpiece!"
        rg.save()

        client.force_login(recipient)
        share_url = reverse(
            "gift_manager:received_gift_share_reaction",
            kwargs={"pk": rg.received_gift_id},
        )
        resp = client.post(share_url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "A masterpiece!"
