"""Tests for ReceivedGift model, constraints, privacy, and wish synchronization."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from gift_manager.gift_history import find_regift_warnings
from gift_manager.models import PermissionLevel
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory
from gift_manager.wishlist import format_claimer_label


@pytest.mark.django_db
def test_received_gift_creation_and_defaults():
    user = UserFactory()
    gift = ReceivedGift.objects.create(
        recipient_user=user,
        title="Bluetooth Speaker",
        giver_label="Uncle Bob",
    )
    assert gift.received_gift_id is not None
    assert gift.received_on == timezone.localdate()
    assert gift.thank_you_sent is False
    assert gift.description == ""
    assert gift.url == ""
    assert gift.reaction_rating is None
    assert str(gift) == f"Bluetooth Speaker ({user.username})"


@pytest.mark.django_db
def test_received_gift_rating_range_constraint():
    user = UserFactory()
    with pytest.raises(IntegrityError):
        ReceivedGift.objects.create(
            recipient_user=user,
            title="Out of range gift",
            giver_label="Someone",
            reaction_rating=6,
        )


@pytest.mark.django_db
def test_occasion_text_copied_from_event_when_empty():
    user = UserFactory()
    event = EventFactory(name="New Year Party")
    gift = ReceivedGift.objects.create(
        recipient_user=user,
        title="Champagne",
        giver_label="Friend",
        event=event,
    )
    assert gift.occasion_text == "New Year Party"


@pytest.mark.django_db
def test_occasion_text_preserved_if_already_set():
    user = UserFactory()
    event = EventFactory(name="New Year Party")
    gift = ReceivedGift.objects.create(
        recipient_user=user,
        title="Champagne",
        giver_label="Friend",
        event=event,
        occasion_text="Custom Occasion",
    )
    assert gift.occasion_text == "Custom Occasion"


@pytest.mark.django_db
def test_received_gift_strict_privacy_isolation():
    user_a = UserFactory()
    user_b = UserFactory()
    person = PersonFactory(first_name="Marie", family_name="Curie")
    PermissionService.create_or_update_permission(
        user_a, person, permission_level=PermissionLevel.OWNER
    )
    PermissionService.create_or_update_permission(
        user_b, person, permission_level=PermissionLevel.OWNER
    )

    gift_a = ReceivedGift.objects.create(
        recipient_user=user_a,
        title="Secret Chemistry Kit",
        giver_label="Family",
    )
    gift_a.giver_persons.add(person)

    # user_a sees their gift
    assert ReceivedGift.objects.for_user(user_a).filter(pk=gift_a.pk).exists()

    # user_b MUST NEVER see user_a's received gift
    assert not ReceivedGift.objects.for_user(user_b).filter(pk=gift_a.pk).exists()
    assert ReceivedGift.objects.for_user(user_b).count() == 0

    # Reverse relations on Person must be non-existent or inaccessible
    assert not hasattr(person, "received_gifts")
    assert not hasattr(person, "gifts_given_to_me")


@pytest.mark.django_db
def test_wish_fulfillment_sync_on_received_gift_lifecycle():
    wisher = UserFactory()
    wish = WishFactory(wisher=wisher, title="Noise Cancelling Headphones")
    assert wish.is_fulfilled is False

    # Recording a received gift marks the wish as fulfilled
    gift = ReceivedGift.objects.create(
        recipient_user=wisher,
        title="Noise Cancelling Headphones",
        giver_label="Parents",
        wish=wish,
    )
    wish.refresh_from_db()
    assert wish.is_fulfilled is True

    # Deleting the received gift resets the wish to unfulfilled
    gift.delete()
    wish.refresh_from_db()
    assert wish.is_fulfilled is False


@pytest.mark.django_db
def test_wish_fulfillment_sync_when_changing_wish_on_received_gift():
    wisher = UserFactory()
    wish1 = WishFactory(wisher=wisher, title="Wish 1")
    wish2 = WishFactory(wisher=wisher, title="Wish 2")

    gift = ReceivedGift.objects.create(
        recipient_user=wisher,
        title="Gift",
        giver_label="Friend",
        wish=wish1,
    )
    wish1.refresh_from_db()
    wish2.refresh_from_db()
    assert wish1.is_fulfilled is True
    assert wish2.is_fulfilled is False

    # Move gift to wish2
    gift.wish = wish2
    gift.save()

    wish1.refresh_from_db()
    wish2.refresh_from_db()
    assert wish1.is_fulfilled is False
    assert wish2.is_fulfilled is True


@pytest.mark.django_db
def test_claimer_label_shows_already_received_when_fulfilled_without_claimers_given_plan():
    wisher = UserFactory()
    friend = UserFactory()
    other_friend = UserFactory()
    wisher.profile.friends.add(friend.profile)
    friend.profile.friends.add(wisher.profile)
    wisher.profile.friends.add(other_friend.profile)
    other_friend.profile.friends.add(wisher.profile)
    friend.profile.friends.add(other_friend.profile)
    other_friend.profile.friends.add(friend.profile)

    wish = WishFactory(wisher=wisher, title="Coffee Grinder")
    wish.claimed_by = friend
    wish.claimed_at = timezone.now()
    wish.save()

    # Before fulfillment, friend sees "Claimed by you"
    assert format_claimer_label(wish, friend) == "Claimed by you"
    # Other friend sees "Claimed by @username"
    assert format_claimer_label(wish, other_friend) == f"Claimed by @{friend.username}"

    # Wisher records receiving it from someone else
    ReceivedGift.objects.create(
        recipient_user=wisher,
        title="Coffee Grinder",
        giver_label="Cousin",
        wish=wish,
    )
    wish.refresh_from_db()
    assert wish.is_fulfilled is True

    # Friend (the claimer) sees "Already received" warning!
    assert format_claimer_label(wish, friend) == "Already received"
    # Other friend still sees "Claimed by @username"
    assert format_claimer_label(wish, other_friend) == f"Claimed by @{friend.username}"


@pytest.mark.django_db
def test_claimer_label_shows_claimed_by_you_when_friend_gave_the_gift():
    wisher = UserFactory()
    friend = UserFactory()
    wisher.profile.friends.add(friend.profile)
    friend.profile.friends.add(wisher.profile)

    person = PersonFactory(account=wisher)
    PermissionService.create_or_update_permission(
        friend, person, permission_level=PermissionLevel.OWNER
    )

    wish = WishFactory(wisher=wisher, title="Espresso Machine")
    wish.claimed_by = friend
    wish.claimed_at = timezone.now()
    wish.save()

    # Friend has an active Given plan for this wish
    from gift_manager.tests.factories import GiftFactory

    given_status, _ = RelationStatus.objects.get_or_create(status_en="Given")
    plan = Relation.objects.create(
        person=person,
        gift=GiftFactory(),
        wish=wish,
        status=given_status,
    )
    PermissionService.create_or_update_permission(
        friend, plan, permission_level=PermissionLevel.OWNER, object_attr="relation"
    )
    wish.refresh_from_db()
    assert wish.is_fulfilled is True

    # Friend is the one who gave it, so they still see "Claimed by you"
    assert format_claimer_label(wish, friend) == "Claimed by you"


@pytest.mark.django_db
def test_find_regift_warnings():
    user = UserFactory()
    person = PersonFactory(first_name="Alice", family_name="Smith")
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.OWNER
    )

    # Record a received gift from Alice
    received = ReceivedGift.objects.create(
        recipient_user=user,
        title="Vintage   Teapot",
        received_on=timezone.localdate(),
    )
    received.giver_persons.add(person)

    # Exact match
    matches = find_regift_warnings(user, person, "Vintage Teapot")
    assert len(matches) == 1
    assert matches[0] == received

    # Case-insensitive and whitespace normalized match
    matches_case = find_regift_warnings(user, person, "  vintage teapot  ")
    assert len(matches_case) == 1

    # Unrelated person should not match
    other_person = PersonFactory(first_name="Bob", family_name="Jones")
    PermissionService.create_or_update_permission(
        user, other_person, permission_level=PermissionLevel.OWNER
    )
    assert len(find_regift_warnings(user, other_person, "Vintage Teapot")) == 0

    # Unrelated gift name
    assert len(find_regift_warnings(user, person, "Coffee Mug")) == 0


@pytest.mark.django_db
def test_find_regift_warnings_through_group_hierarchy():
    user = UserFactory()
    parent_group = PersonGroupFactory(name="Smith Family")
    child_group = PersonGroupFactory(name="Smith Cousins")
    child_group.parent_groups.add(parent_group)

    person = PersonFactory(first_name="Charlie", family_name="Smith")
    person.groups.add(child_group)

    # Received gift from the parent group
    received = ReceivedGift.objects.create(
        recipient_user=user,
        title="Board Game",
        received_on=timezone.localdate(),
    )
    received.giver_groups.set([parent_group])

    # Planning gift for Charlie should warn because Charlie is in a child group of Smith Family
    matches = find_regift_warnings(user, person, "Board Game")
    assert len(matches) == 1
    assert matches[0] == received


@pytest.mark.django_db
def test_received_gift_can_link_a_wish_without_marking_it_received():
    """Wishes received again and again (e.g. food) stay open when the gift opts out."""
    user = UserFactory()
    wish = WishFactory(wisher=user, title="Chocolate")

    gift = ReceivedGift.objects.create(
        recipient_user=user, title="Chocolate", wish=wish, fulfills_wish=False
    )
    wish.refresh_from_db()
    assert wish.is_fulfilled is False

    gift.fulfills_wish = True
    gift.save()
    wish.refresh_from_db()
    assert wish.is_fulfilled is True

    gift.fulfills_wish = False
    gift.save()
    wish.refresh_from_db()
    assert wish.is_fulfilled is False


@pytest.mark.django_db
def test_received_gift_fulfills_its_wish_by_default():
    user = UserFactory()
    wish = WishFactory(wisher=user)

    gift = ReceivedGift.objects.create(recipient_user=user, title="Gift", wish=wish)

    assert gift.fulfills_wish is True
    wish.refresh_from_db()
    assert wish.is_fulfilled is True


@pytest.mark.django_db
def test_plan_change_does_not_mark_received_a_wish_whose_gift_opted_out():
    from gift_manager.tests.factories import GiftFactory

    user = UserFactory()
    wish = WishFactory(wisher=user, title="Chocolate")
    ReceivedGift.objects.create(
        recipient_user=user, title="Chocolate", wish=wish, fulfills_wish=False
    )
    planned_status, _ = RelationStatus.objects.get_or_create(status_en="Planned")

    # Saving a (not given) plan for the wish re-derives its fulfilled flag
    Relation.objects.create(
        person=PersonFactory(account=user), gift=GiftFactory(), wish=wish, status=planned_status
    )

    wish.refresh_from_db()
    assert wish.is_fulfilled is False
