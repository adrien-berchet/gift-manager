"""Tests for gift plan reveal and reaction feedback mechanism."""

import json
from datetime import date
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_coordination import hidden_recipient_ids
from gift_manager.plan_coordination import plan_recipient_account_ids
from gift_manager.received_gifts import ShareReactionResult
from gift_manager.received_gifts import can_reveal_plan
from gift_manager.received_gifts import can_share_reaction
from gift_manager.received_gifts import get_reveal_targets
from gift_manager.received_gifts import reveal_plan
from gift_manager.received_gifts import reveal_target_ids_by_relation
from gift_manager.received_gifts import revealable_relation_pks
from gift_manager.received_gifts import share_reaction_feedback
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

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

    def test_reveal_plan_drops_invalid_fallback_url_and_skips_deleted_wish(self, db, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        deleted_wish = WishFactory(
            wisher=recipient, title="Removed Wish", is_deleted_by_wisher=True
        )
        gift = GiftFactory(name="Gadget", url="javascript:alert(1)")
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
            wish=deleted_wish,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        created = reveal_plan(relation, owner, title="Gadget")
        assert len(created) == 1
        assert created[0].url == ""
        assert created[0].wish is None

    def test_reveal_plan_rejects_explicit_unsafe_url(self, db, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory(name="Gadget")
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        with pytest.raises(ValidationError):
            reveal_plan(relation, owner, title="Gadget", url="javascript:alert(1)")
        assert not ReceivedGift.objects.filter(recipient_user=recipient).exists()


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

        result = share_reaction_feedback(rg, recipient)
        assert result is ShareReactionResult.SHARED

        rg.refresh_from_db()
        assert rg.reaction_shared_at is not None
        assert can_share_reaction(rg, recipient) is False

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

        assert can_share_reaction(rg, recipient) is False
        result = share_reaction_feedback(rg, recipient)
        assert result is ShareReactionResult.NOTHING_NEW

        rg.refresh_from_db()
        assert rg.reaction_shared_at is None

        relation.refresh_from_db()
        # Existing values are preserved
        assert relation.reaction_rating == 4
        assert relation.reaction_note == "Giver already noted they seemed pleased"

    def test_can_share_reaction_reappears_when_note_added_later(self, db, given_status):
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

        rg = reveal_plan(relation, owner, title="Camera")[0]
        rg.reaction_rating = 5
        rg.save()

        assert can_share_reaction(rg, recipient) is True
        assert share_reaction_feedback(rg, recipient) is ShareReactionResult.SHARED
        assert can_share_reaction(rg, recipient) is False

        rg.reaction_note = "Took amazing photos on vacation!"
        rg.save()
        assert can_share_reaction(rg, recipient) is True
        assert share_reaction_feedback(rg, recipient) is ShareReactionResult.SHARED

        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "Took amazing photos on vacation!"

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

        assert can_share_reaction(rg, recipient) is False
        result = share_reaction_feedback(rg, recipient)
        assert result is ShareReactionResult.NOT_ALLOWED


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

        # GET request renders offcanvas partial with targets and form
        resp = client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Coffee Maker" in body
        assert "relation-reveal-form" in body

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
        hx_trigger = post_resp.headers.get("HX-Trigger", "")
        assert "offcanvas:close" in hx_trigger
        assert "list:update" in hx_trigger

        # Verify ReceivedGift was created for recipient
        rg = ReceivedGift.objects.get(recipient_user=recipient)
        assert rg.title == "Espresso Machine"
        assert rg.giver_note == "Enjoy fresh coffee!"

    def test_relation_reveal_invalid_url_returns_422(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory(username="recip2")
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(first_name="Recip", account=recipient)
        gift = GiftFactory(name="Laptop")
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
        post_resp = client.post(
            url,
            {"title": "Laptop", "url": "javascript:alert(1)"},
            HTTP_HX_REQUEST="true",
        )
        assert post_resp.status_code == 422
        assert "relation-reveal-form" in post_resp.content.decode()
        assert not ReceivedGift.objects.filter(recipient_user=recipient).exists()
        relation.refresh_from_db()
        assert relation.revealed_at is None

    def test_relation_reveal_full_page_get_and_post_redirects(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory(username="recip3")
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(first_name="Recip", account=recipient)
        gift = GiftFactory(name="Bicycle")
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

        get_resp = client.get(url)
        assert get_resp.status_code == 200
        assert 'data-form-type="relation_reveal"' in get_resp.content.decode()

        post_resp = client.post(url, {"title": "Mountain Bike"})
        assert post_resp.status_code == 302
        assert (
            reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
            in post_resp["Location"]
        )
        assert ReceivedGift.objects.filter(recipient_user=recipient, title="Mountain Bike").exists()

    def test_relation_reveal_forbidden_when_cannot_reveal(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)

        person = PersonFactory(account=recipient)
        gift = GiftFactory()
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=_status("Planned"),
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        url = reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})
        assert client.get(url).status_code == 403
        assert client.post(url, {"title": "Test"}).status_code == 403

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
        assert "list:update" in resp.headers.get("HX-Trigger", "")

        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "A masterpiece!"

        rg.refresh_from_db()
        assert rg.reaction_shared_at is not None

        # Detail partial hides share button once all feedback has been shared
        detail_url = reverse(
            "gift_manager:received_gift_detail", kwargs={"pk": rg.received_gift_id}
        )
        detail_resp = client.get(detail_url, HTTP_HX_REQUEST="true")
        assert detail_resp.status_code == 200
        detail_html = detail_resp.content.decode()
        assert share_url not in detail_html
        assert "Shared with givers on" in detail_html

        # Repeating the POST reports nothing new rather than falsely claiming newly shared
        second_resp = client.post(share_url, HTTP_HX_REQUEST="true")
        assert second_resp.status_code == 200
        second_trigger = second_resp.headers.get("HX-Trigger", "")
        assert "already have feedback" in second_trigger
        assert '"type": "info"' in second_trigger

        # Unfriending yields warning outcome
        owner.profile.friends.remove(recipient.profile)
        third_resp = client.post(share_url, HTTP_HX_REQUEST="true")
        assert third_resp.status_code == 200
        third_trigger = third_resp.headers.get("HX-Trigger", "")
        assert "Unable to share reaction feedback." in third_trigger
        assert '"type": "warning"' in third_trigger


@pytest.mark.django_db
class TestRevealShortcutsAndFlows:
    """Verify bulk reveal eligibility, undo safety, card/history/edit/reaction flows."""

    def test_bulk_reveal_eligibility_matches_can_reveal_plan_across_edge_cases(
        self, db, given_status, planned_status, django_assert_num_queries
    ):
        owner = UserFactory()
        co_owner = UserFactory()
        friend = UserFactory()
        stranger = UserFactory()
        owner.profile.friends.add(co_owner.profile, friend.profile)

        p_friend = PersonFactory(account=friend)
        p_co_owner = PersonFactory(account=co_owner)
        p_stranger = PersonFactory(account=stranger)
        p_unlinked = PersonFactory(account=None)

        parent_group = PersonGroupFactory(name="Parent Group")
        child_group = PersonGroupFactory(name="Child Group")
        child_group.parent_groups.add(parent_group)
        p_friend.groups.add(child_group)

        co_owner_only_group = PersonGroupFactory(name="Co-Owner Group")
        p_co_owner.groups.add(co_owner_only_group)

        # 1. Eligible direct friend plan
        r_ok = Relation.objects.create(gift=GiftFactory(), person=p_friend, status=given_status)
        PermissionService.create_or_update_permission(
            owner, r_ok, permission_level=PermissionLevel.OWNER
        )

        # 2. Group plan containing friend member and co-owner (only friend stays target)
        r_group = Relation.objects.create(
            gift=GiftFactory(), group=parent_group, status=given_status
        )
        PermissionService.create_or_update_permission(
            owner, r_group, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            co_owner, r_group, permission_level=PermissionLevel.OWNER
        )

        # 3. Group plan whose only friend member is also a co-owner -> excluded!
        r_group_co_owner_only = Relation.objects.create(
            gift=GiftFactory(), group=co_owner_only_group, status=given_status
        )
        PermissionService.create_or_update_permission(
            owner, r_group_co_owner_only, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            co_owner, r_group_co_owner_only, permission_level=PermissionLevel.OWNER
        )

        # 4. Non-friend recipient
        r_stranger = Relation.objects.create(
            gift=GiftFactory(), person=p_stranger, status=given_status
        )
        PermissionService.create_or_update_permission(
            owner, r_stranger, permission_level=PermissionLevel.OWNER
        )

        # 5. Unlinked person
        r_unlinked = Relation.objects.create(
            gift=GiftFactory(), person=p_unlinked, status=given_status
        )
        PermissionService.create_or_update_permission(
            owner, r_unlinked, permission_level=PermissionLevel.OWNER
        )

        # 6. Editor only (not owner)
        r_editor = Relation.objects.create(gift=GiftFactory(), person=p_friend, status=given_status)
        PermissionService.create_or_update_permission(
            co_owner, r_editor, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            owner, r_editor, permission_level=PermissionLevel.EDITOR
        )

        # 7. Already revealed
        r_revealed = Relation.objects.create(
            gift=GiftFactory(),
            person=p_friend,
            status=given_status,
            revealed_at=timezone.now(),
        )
        PermissionService.create_or_update_permission(
            owner, r_revealed, permission_level=PermissionLevel.OWNER
        )

        # 8. Non-Given plan
        r_planned = Relation.objects.create(
            gift=GiftFactory(), person=p_friend, status=planned_status
        )
        PermissionService.create_or_update_permission(
            owner, r_planned, permission_level=PermissionLevel.OWNER
        )

        all_relations = list(
            Relation.objects.filter(
                pk__in=[
                    r_ok.pk,
                    r_group.pk,
                    r_group_co_owner_only.pk,
                    r_stranger.pk,
                    r_unlinked.pk,
                    r_editor.pk,
                    r_revealed.pk,
                    r_planned.pk,
                ]
            ).select_related("status", "person", "group")
        )

        with django_assert_num_queries(4):
            targets_map = reveal_target_ids_by_relation(all_relations, owner)
        pks = set(targets_map.keys())

        assert pks == {r_ok.pk, r_group.pk}
        assert targets_map[r_ok.pk] == {friend.pk}
        assert targets_map[r_group.pk] == {friend.pk}
        assert r_group_co_owner_only.pk not in pks

        for rel in all_relations:
            assert (rel.pk in pks) is can_reveal_plan(rel, owner)

    def test_undo_quick_action_blocked_after_reveal(self, client, given_status, planned_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(account=recipient)
        relation = Relation.objects.create(
            gift=GiftFactory(),
            person=person,
            status=planned_status,
            due_date=date.today() - timedelta(days=1),
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        quick_url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
        )
        resp = client.post(quick_url, {"action": "given"}, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        trigger = json.loads(resp.headers["HX-Trigger"])
        undo = trigger["showNotification"]["undo"]

        relation.refresh_from_db()
        assert reveal_plan(relation, owner, title="Gift")

        undo_resp = client.post(undo["url"], {"token": undo["token"]}, HTTP_HX_REQUEST="true")
        assert undo_resp.status_code == 409
        relation.refresh_from_db()
        assert relation.status_id == given_status.pk
        assert relation.revealed_at is not None

    def test_undo_quick_action_still_allowed_after_empty_reaction_before_reveal(
        self, client, given_status, planned_status
    ):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(account=recipient)
        relation = Relation.objects.create(
            gift=GiftFactory(),
            person=person,
            status=planned_status,
            due_date=date.today() - timedelta(days=1),
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        quick_url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}
        )
        resp = client.post(quick_url, {"action": "given"}, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        undo = json.loads(resp.headers["HX-Trigger"])["showNotification"]["undo"]

        reaction_url = reverse(
            "gift_manager:relation_reaction", kwargs={"pk": relation.relation_id}
        )
        chain_resp = client.post(
            reaction_url,
            {"reaction_rating": "", "reaction_note": "", "after_save": "reveal"},
            HTTP_HX_REQUEST="true",
        )
        assert chain_resp.status_code == 200
        assert 'id="relation-reveal-form"' in chain_resp.content.decode()

        # Before reveal is confirmed, Undo still reverts status despite the empty note save.
        undo_resp = client.post(undo["url"], {"token": undo["token"]}, HTTP_HX_REQUEST="true")
        assert undo_resp.status_code == 200
        relation.refresh_from_db()
        assert relation.status_id == planned_status.pk
        assert relation.revealed_at is None

    def test_relation_reaction_chains_into_reveal_and_skips_for_inline(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(account=recipient)
        relation = Relation.objects.create(
            gift=GiftFactory(name="Leather Journal"),
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        reaction_url = reverse(
            "gift_manager:relation_reaction", kwargs={"pk": relation.relation_id}
        )
        get_resp = client.get(reaction_url, HTTP_HX_REQUEST="true")
        assert get_resp.status_code == 200
        get_html = get_resp.content.decode()
        assert 'name="after_save"' in get_html
        assert 'value="reveal"' in get_html
        assert "Save & reveal to recipient" in get_html

        # Inline card rating must NEVER chain into the reveal panel
        inline_resp = client.post(
            reaction_url,
            {"inline": "1", "reaction_rating": "5", "after_save": "reveal"},
            HTTP_HX_REQUEST="true",
        )
        assert inline_resp.status_code == 200
        assert "relation-reveal-form" not in inline_resp.content.decode()

        # Offcanvas Save & reveal chains directly into #relation-reveal-form
        relation.reaction_rating = None
        relation.save(update_fields=["reaction_rating"])
        chain_resp = client.post(
            reaction_url,
            {"reaction_rating": "5", "reaction_note": "Adored it!", "after_save": "reveal"},
            HTTP_HX_REQUEST="true",
        )
        assert chain_resp.status_code == 200
        chain_html = chain_resp.content.decode()
        assert 'id="relation-reveal-form"' in chain_html
        assert "<details" in chain_html
        assert "Adjust snapshot details" in chain_html
        assert 'id="id_giver_note"' in chain_html
        hx_trigger = json.loads(chain_resp.headers["HX-Trigger"])
        assert "list:update" in hx_trigger
        assert "offcanvas:close" not in hx_trigger
        assert hx_trigger["showNotification"]["message"] == "Reaction saved."

        # Reaction was persisted while plan awaits confirmation in the reveal form
        relation.refresh_from_db()
        assert relation.reaction_rating == 5
        assert relation.reaction_note == "Adored it!"
        assert relation.revealed_at is None

        # Non-HTMX Save & reveal redirects to full reveal page
        page_resp = client.post(
            reaction_url,
            {"reaction_rating": "4", "after_save": "reveal"},
        )
        assert page_resp.status_code == 302
        assert (
            reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})
            in page_resp["Location"]
        )

    def test_relation_update_to_given_attaches_toast_reveal_link(
        self, client, given_status, planned_status
    ):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(first_name="Sam", account=recipient)
        gift = GiftFactory(name="Watch")
        relation = Relation.objects.create(
            gift=gift,
            person=person,
            status=planned_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            owner, gift, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            owner, person, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        edit_url = reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id})
        reveal_url = reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})

        resp = client.post(
            edit_url,
            {
                "gift": gift.pk,
                "recipient": f"person:{person.person_id}",
                "status": given_status.pk,
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        triggers = json.loads(resp.headers["HX-Trigger"])
        assert triggers["showNotification"]["link"]["url"] == reveal_url

        # Editing an already-Given plan without changing status attaches no reveal toast link
        resp2 = client.post(
            edit_url,
            {
                "gift": gift.pk,
                "recipient": f"person:{person.person_id}",
                "status": given_status.pk,
                "comment": "Updated note only",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp2.status_code == 200
        triggers2 = json.loads(resp2.headers["HX-Trigger"])
        assert "showNotification" not in triggers2 or "link" not in triggers2.get(
            "showNotification", {}
        )

    def test_reveal_panel_details_collapse_and_open_on_error(self, client, given_status):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(account=recipient)
        relation = Relation.objects.create(
            gift=GiftFactory(name="Desk Lamp"),
            person=person,
            status=given_status,
        )
        PermissionService.create_or_update_permission(
            owner, relation, permission_level=PermissionLevel.OWNER
        )

        client.force_login(owner)
        reveal_url = reverse("gift_manager:relation_reveal", kwargs={"pk": relation.relation_id})
        get_html = client.get(reveal_url, HTTP_HX_REQUEST="true").content.decode()
        assert '<details class="mb-3">' in get_html
        assert '<details class="mb-3" open>' not in get_html
        assert "Desk Lamp" in get_html

        err_resp = client.post(
            reveal_url,
            {"title": "Desk Lamp", "url": "javascript:alert(1)"},
            HTTP_HX_REQUEST="true",
        )
        assert err_resp.status_code == 422
        assert '<details class="mb-3" open>' in err_resp.content.decode()

    def test_workspace_dashboard_history_and_query_invariance(
        self, client, given_status, django_assert_num_queries
    ):
        owner = UserFactory()
        recipient = UserFactory()
        owner.profile.friends.add(recipient.profile)
        person = PersonFactory(first_name="Pat", account=recipient)
        PermissionService.create_or_update_permission(
            owner, person, permission_level=PermissionLevel.OWNER
        )

        for idx in range(2):
            gift = GiftFactory(name=f"Batch Gift {idx}")
            PermissionService.create_or_update_permission(
                owner, gift, permission_level=PermissionLevel.OWNER
            )
            rel = Relation.objects.create(
                gift=gift,
                person=person,
                status=given_status,
                due_date=date.today(),
            )
            PermissionService.create_or_update_permission(
                owner, rel, permission_level=PermissionLevel.OWNER
            )

        client.force_login(owner)
        relations_url = reverse("gift_manager:relations")
        history_url = reverse("gift_manager:person_gift_history", kwargs={"pk": person.person_id})
        home_url = reverse("gift_manager:home")

        # Workspace, dashboard, and history render Reveal button before revealing
        ws_html = client.get(relations_url).content.decode()
        home_html = client.get(home_url).content.decode()
        hist_html = client.get(history_url).content.decode()
        for rel in Relation.objects.filter(person=person):
            r_url = reverse("gift_manager:relation_reveal", kwargs={"pk": rel.relation_id})
            assert r_url in ws_html
            assert r_url in home_html
            assert r_url in hist_html

        # Verify query count on RelationListView stays invariant as more Given plans are added
        with CaptureQueriesContext(connection) as ctx_2:
            client.get(relations_url)

        for idx in range(2, 5):
            gift = GiftFactory(name=f"Batch Gift {idx}")
            PermissionService.create_or_update_permission(
                owner, gift, permission_level=PermissionLevel.OWNER
            )
            rel = Relation.objects.create(
                gift=gift,
                person=person,
                status=given_status,
                due_date=date.today(),
            )
            PermissionService.create_or_update_permission(
                owner, rel, permission_level=PermissionLevel.OWNER
            )

        with django_assert_num_queries(len(ctx_2)):
            client.get(relations_url)

        # Revealing turns cards and history entries from Reveal button -> Revealed badge
        first_rel = Relation.objects.filter(person=person).order_by("pk").first()
        reveal_plan(first_rel, owner, title="Batch Gift 0")
        first_reveal_url = reverse(
            "gift_manager:relation_reveal", kwargs={"pk": first_rel.relation_id}
        )
        ws_after = client.get(relations_url).content.decode()
        hist_after = client.get(history_url).content.decode()
        assert first_reveal_url not in ws_after
        assert first_reveal_url not in hist_after
        assert "Revealed" in ws_after
        assert "Revealed" in hist_after
        assert not revealable_relation_pks([first_rel], owner)
