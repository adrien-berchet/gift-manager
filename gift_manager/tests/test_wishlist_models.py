"""Model tests for Wishlist and Profile Preferences (Task 1)."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from gift_manager.models import GiftTag
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.models import WishPriority
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_wish_creation_and_defaults():
    user = UserFactory()
    wish = Wish.objects.create(
        wisher=user,
        title="Bicycle Helmet",
    )

    assert isinstance(wish.wish_id, uuid.UUID)
    assert wish.wisher == user
    assert wish.title == "Bicycle Helmet"
    assert wish.url == ""
    assert wish.price_hint is None
    assert wish.notes == ""
    assert wish.priority == WishPriority.MEDIUM
    assert wish.is_archived is False
    assert wish.is_fulfilled is False
    assert wish.claimed_by is None
    assert wish.claimed_at is None
    assert wish.created_at is not None
    assert wish.wisher_updated_at is not None
    assert str(wish) == f"Bicycle Helmet ({user.username})"


def test_wish_check_constraint_claimed_by_requires_claimed_at():
    user = UserFactory()
    claimer = UserFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Wish.objects.create(
            wisher=user,
            title="Book",
            claimed_by=claimer,
            claimed_at=None,
        )


def test_wish_check_constraint_non_negative_price():
    user = UserFactory()

    # price_hint = 0 is allowed
    wish_zero = Wish.objects.create(
        wisher=user,
        title="Zero Price",
        price_hint=Decimal("0.00"),
    )
    assert wish_zero.price_hint == Decimal("0.00")

    # price_hint < 0 triggers IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Wish.objects.create(
            wisher=user,
            title="Negative Price",
            price_hint=Decimal("-0.01"),
        )


def test_wish_is_updated_after_claim():
    user = UserFactory()
    claimer = UserFactory()
    now = timezone.now()

    wish = Wish.objects.create(
        wisher=user,
        title="Running shoes",
        claimed_by=claimer,
        claimed_at=now,
        wisher_updated_at=now - timedelta(minutes=5),
    )
    # Claimed after last wisher update -> False
    assert wish.is_updated_after_claim() is False

    # Wisher edits content after claim -> True
    wish.wisher_updated_at = now + timedelta(minutes=5)
    wish.save(update_fields=["wisher_updated_at"])
    assert wish.is_updated_after_claim() is True

    # Claimer is deleted -> claimed_by is None, claimed_at kept -> False
    wish.claimed_by = None
    wish.save(update_fields=["claimed_by"])
    assert wish.is_updated_after_claim() is False


def test_profile_preference_fields():
    user = UserFactory()
    profile = user.profile

    assert profile.preferences_notes == ""
    assert profile.avoid_notes == ""
    assert profile.ai_share_self_profile is False
    assert profile.public_interests.count() == 0

    tag_public = GiftTag.objects.create(name="Board Games", is_public=True)
    profile.preferences_notes = "Shoe size: 42, loves navy blue"
    profile.avoid_notes = "Allergic to wool"
    profile.ai_share_self_profile = True
    profile.public_interests.add(tag_public)
    profile.save()

    profile.refresh_from_db()
    assert profile.preferences_notes == "Shoe size: 42, loves navy blue"
    assert profile.avoid_notes == "Allergic to wool"
    assert profile.ai_share_self_profile is True
    assert profile.public_interests.filter(pk=tag_public.pk).exists()


def test_relation_wish_validation_rejects_group_recipient():
    wisher = UserFactory()
    wish = Wish.objects.create(wisher=wisher, title="Coffee Grinder")
    group = PersonGroupFactory()
    gift = GiftFactory()

    relation = Relation(
        group=group,
        person=None,
        gift=gift,
        wish=wish,
    )

    with pytest.raises(ValidationError) as exc_info:
        relation.clean()
    assert "A gift plan fulfilling a wish must target a person, not a group." in str(exc_info.value)


def test_relation_wish_validation_rejects_unlinked_or_mismatched_person():
    wisher = UserFactory()
    other_user = UserFactory()
    wish = Wish.objects.create(wisher=wisher, title="Coffee Grinder")
    gift = GiftFactory()

    # Case 1: Person has account=None
    unlinked_person = PersonFactory(account=None)
    relation_unlinked = Relation(
        person=unlinked_person,
        group=None,
        gift=gift,
        wish=wish,
    )
    with pytest.raises(ValidationError) as exc_info:
        relation_unlinked.clean()
    assert "The recipient person must represent the wisher of this wish." in str(exc_info.value)

    # Case 2: Person has account=other_user != wisher
    mismatched_person = PersonFactory(account=other_user)
    relation_mismatched = Relation(
        person=mismatched_person,
        group=None,
        gift=gift,
        wish=wish,
    )
    with pytest.raises(ValidationError) as exc_info:
        relation_mismatched.clean()
    assert "The recipient person must represent the wisher of this wish." in str(exc_info.value)


def test_relation_wish_validation_accepts_matching_linked_person():
    wisher = UserFactory()
    wish = Wish.objects.create(wisher=wisher, title="Coffee Grinder")
    linked_person = PersonFactory(account=wisher)
    gift = GiftFactory()

    relation = Relation(
        person=linked_person,
        group=None,
        gift=gift,
        wish=wish,
    )
    # clean() should not raise
    relation.clean()


def test_wish_queryset_for_wisher():
    alice = UserFactory()
    bob = UserFactory()

    wish1 = Wish.objects.create(wisher=alice, title="Wish 1", is_archived=False)
    wish2 = Wish.objects.create(wisher=alice, title="Wish 2", is_archived=True)
    Wish.objects.create(wisher=bob, title="Bob's wish")

    # Anonymous user gets none
    assert Wish.objects.for_wisher(AnonymousUser()).count() == 0
    assert Wish.objects.for_wisher(None).count() == 0

    # Alice gets all her wishes (active and archived)
    alice_wishes = Wish.objects.for_wisher(alice)
    assert set(alice_wishes) == {wish1, wish2}


def test_wish_queryset_visible_to_friend():
    alice = UserFactory()
    bob = UserFactory()
    carol = UserFactory()

    # Alice and Bob are friends; Carol is not
    alice.profile.friends.add(bob.profile)

    active_unclaimed = Wish.objects.create(wisher=alice, title="Active Unclaimed")
    active_claimed_by_bob = Wish.objects.create(
        wisher=alice, title="Active Claimed", claimed_by=bob, claimed_at=timezone.now()
    )
    archived_unclaimed = Wish.objects.create(
        wisher=alice, title="Archived Unclaimed", is_archived=True
    )
    archived_claimed_by_bob = Wish.objects.create(
        wisher=alice,
        title="Archived Claimed Bob",
        is_archived=True,
        claimed_by=bob,
        claimed_at=timezone.now(),
    )
    archived_claimed_by_carol = Wish.objects.create(
        wisher=alice,
        title="Archived Claimed Carol",
        is_archived=True,
        claimed_by=carol,
        claimed_at=timezone.now(),
    )

    # Anonymous gets none
    assert Wish.objects.visible_to_friend(AnonymousUser(), alice).count() == 0

    # Carol (not friend) gets none
    assert Wish.objects.visible_to_friend(carol, alice).count() == 0

    # Bob (friend) sees active wishes and his own claimed archived wish
    bob_visible = Wish.objects.visible_to_friend(bob, alice)
    assert set(bob_visible) == {
        active_unclaimed,
        active_claimed_by_bob,
        archived_claimed_by_bob,
    }
    assert archived_unclaimed not in bob_visible
    assert archived_claimed_by_carol not in bob_visible


def test_wish_cascade_and_set_null_deletions():
    alice = UserFactory()
    bob = UserFactory()
    wish = Wish.objects.create(
        wisher=alice, title="Headphones", claimed_by=bob, claimed_at=timezone.now()
    )

    person = PersonFactory(account=alice)
    relation = RelationFactory(person=person, group=None, wish=wish)

    # Deleting the wish sets Relation.wish to NULL
    wish_id = wish.pk
    wish.delete()
    assert not Wish.objects.filter(pk=wish_id).exists()
    relation.refresh_from_db()
    assert relation.wish is None

    # Recreate wish and test wisher deletion cascades to wishes
    wish2 = Wish.objects.create(wisher=alice, title="Keyboard")
    alice.delete()
    assert not Wish.objects.filter(pk=wish2.pk).exists()
