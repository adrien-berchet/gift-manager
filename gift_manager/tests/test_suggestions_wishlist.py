"""Tests for AI and catalogue suggestions integration with user wishlist and profile preferences."""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import Wish
from gift_manager.models import WishPriority
from gift_manager.suggestions.ai.prompt import build_ai_payload
from gift_manager.suggestions.catalogue import CatalogueStrategy
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.suggestions.types import SuggestionContext
from gift_manager.tests.factories import GiftFactory


def _make_friends(user1: User, user2: User) -> None:
    user1.profile.friends.add(user2.profile)


@pytest.mark.django_db
def test_ai_prompt_includes_self_profile_when_enabled(user: User):
    friend = User.objects.create_user(
        username="friend_alice",
        first_name="Alice",
        last_name="Bouvier",
        email="alice@example.com",
    )
    _make_friends(user, friend)

    person = Person.objects.create(first_name="Alice", account=friend)

    pub_tag = GiftTag.objects.create(name="Board Games", is_public=True)
    friend.profile.public_interests.add(pub_tag)
    friend.profile.preferences_notes = "Shoe size 39, loves blue"
    friend.profile.avoid_notes = "Peanut allergy\nNo plastic trinkets"
    friend.profile.ai_share_self_profile = True
    friend.profile.save()

    Wish.objects.create(
        wisher=friend,
        title="Dune Imperium",
        priority=WishPriority.HIGH,
    )

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=["Board Games"],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert "Board Games" in payload["interests"]
    assert "Board Games" in payload["recipient"]["interests"]
    assert any("Peanut allergy" in av for av in payload["avoid"])
    assert any("No plastic trinkets" in av for av in payload["avoid"])
    assert "wishes" in payload
    assert "Dune Imperium" in payload["wishes"]
    assert "notes" in payload["recipient"]
    assert "Preferences: Shoe size 39, loves blue" in payload["recipient"]["notes"]


@pytest.mark.django_db
def test_ai_prompt_excludes_self_profile_when_disabled(user: User):
    friend = User.objects.create_user(
        username="friend_bob",
        first_name="Bob",
        last_name="Dylan",
    )
    _make_friends(user, friend)

    person = Person.objects.create(first_name="Bob", account=friend)

    pub_tag = GiftTag.objects.create(name="Astronomy", is_public=True)
    friend.profile.public_interests.add(pub_tag)
    friend.profile.preferences_notes = "Size L"
    friend.profile.avoid_notes = "No horror books"
    friend.profile.ai_share_self_profile = False  # Explicitly disabled (default)
    friend.profile.save()

    Wish.objects.create(wisher=friend, title="Telescope", priority=WishPriority.HIGH)

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=["Astronomy"],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert "Astronomy" not in payload["interests"]
    assert "Astronomy" not in payload["recipient"]["interests"]
    assert not any("horror" in av.lower() for av in payload["avoid"])
    assert "wishes" not in payload
    assert "notes" not in payload["recipient"]


@pytest.mark.django_db
def test_ai_prompt_excludes_claimed_and_fulfilled_wishes(user: User):
    friend = User.objects.create_user(
        username="friend_clara",
        first_name="Clara",
    )
    third_user = User.objects.create_user(username="other_charlie")
    _make_friends(user, friend)
    _make_friends(friend, third_user)

    person = Person.objects.create(first_name="Clara", account=friend)
    friend.profile.ai_share_self_profile = True
    friend.profile.save()

    # Active unclaimed wish -> should be included
    Wish.objects.create(wisher=friend, title="Unclaimed Book", priority=WishPriority.HIGH)

    # Claimed by viewer -> should be excluded
    Wish.objects.create(
        wisher=friend,
        title="Claimed by Viewer",
        claimed_by=user,
        claimed_at=timezone.now(),
        priority=WishPriority.HIGH,
    )

    # Claimed by third friend -> should be excluded
    Wish.objects.create(
        wisher=friend,
        title="Claimed by Charlie",
        claimed_by=third_user,
        claimed_at=timezone.now(),
        priority=WishPriority.HIGH,
    )

    # Fulfilled wish -> should be excluded
    Wish.objects.create(
        wisher=friend,
        title="Fulfilled Coffee Maker",
        is_fulfilled=True,
        priority=WishPriority.HIGH,
    )

    # Archived wish -> should be excluded
    Wish.objects.create(
        wisher=friend,
        title="Archived Painting",
        is_archived=True,
        priority=WishPriority.HIGH,
    )

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert "wishes" in payload
    assert "Unclaimed Book" in payload["wishes"]
    assert "Claimed by Viewer" not in payload["wishes"]
    assert "Claimed by Charlie" not in payload["wishes"]
    assert "Fulfilled Coffee Maker" not in payload["wishes"]
    assert "Archived Painting" not in payload["wishes"]


@pytest.mark.django_db
def test_catalogue_matches_public_interests(user: User):
    friend = User.objects.create_user(username="friend_david")
    _make_friends(user, friend)

    person = Person.objects.create(first_name="David", account=friend)

    woodworking_tag = GiftTag.objects.create(name="Woodworking", is_public=True)
    friend.profile.public_interests.add(woodworking_tag)
    # Ensure catalogue suggestion works regardless of AI share flag
    friend.profile.ai_share_self_profile = False
    friend.profile.save()

    chisel_gift = GiftFactory(
        name="Japanese Chisel Set",
        tags=[woodworking_tag],
        shared_with=[user],
    )

    history = build_recipient_history(user, person)
    ctx = SuggestionContext(
        user=user,
        recipient=person,
        history=history,
        excluded_gift_ids=frozenset(),
        blocked_names=frozenset(),
    )

    candidates = CatalogueStrategy().suggest(ctx, limit=5)
    matching_candidate = next((c for c in candidates if c.gift == chisel_gift), None)

    assert matching_candidate is not None
    assert matching_candidate.reason.code == "interests"
    assert "Woodworking" in matching_candidate.reason.tag_names


@pytest.mark.django_db
def test_ai_prompt_excludes_unfriended_or_unlinked_account(user: User):
    stranger = User.objects.create_user(username="stranger_eva")
    # NOT friends with user
    person_stranger = Person.objects.create(first_name="Eva", account=stranger)
    stranger.profile.ai_share_self_profile = True
    stranger.profile.preferences_notes = "Secret sizes"
    stranger.profile.avoid_notes = "Secret dislikes"
    stranger.profile.save()
    Wish.objects.create(wisher=stranger, title="Secret Wish")

    history_stranger = build_recipient_history(user, person_stranger)
    payload_stranger = build_ai_payload(
        history_stranger,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )
    assert "wishes" not in payload_stranger
    assert "notes" not in payload_stranger["recipient"]
    assert not any("Secret" in av for av in payload_stranger["avoid"])

    # Unlinked person
    unlinked_person = Person.objects.create(first_name="Frank", account=None)
    history_unlinked = build_recipient_history(user, unlinked_person)
    payload_unlinked = build_ai_payload(
        history_unlinked,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )
    assert "wishes" not in payload_unlinked
    assert "notes" not in payload_unlinked["recipient"]


@pytest.mark.django_db
def test_ai_prompt_scrubs_account_identifiers(user: User):
    friend = User.objects.create_user(
        username="alicesmith99",
        first_name="Alice",
        last_name="Smith",
        email="alice.smith@example.com",
    )
    _make_friends(user, friend)

    person = Person.objects.create(first_name="Alice", account=friend)
    friend.profile.ai_share_self_profile = True
    friend.profile.avoid_notes = (
        "alicesmith99 hates dairy products and alice.smith@example.com email spam"
    )
    friend.profile.preferences_notes = "Send Alice Smith size 38"
    friend.profile.save()

    Wish.objects.create(wisher=friend, title="Special book for Alice Smith")

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert "alicesmith99" not in str(payload["avoid"])
    assert "alice.smith@example.com" not in str(payload["avoid"])
    assert "Alice Smith" not in payload["recipient"]["notes"]
    assert "Alice Smith" not in payload["wishes"][0]


@pytest.mark.django_db
def test_ai_prompt_notes_assembly_with_viewer_notes(user: User):
    friend = User.objects.create_user(username="friend_george")
    _make_friends(user, friend)

    user.profile.ai_share_person_notes = True
    user.profile.save()

    person = Person.objects.create(
        first_name="George",
        account=friend,
        notes="Plays tennis on Sundays",
    )
    friend.profile.ai_share_self_profile = True
    friend.profile.preferences_notes = "Size L"
    friend.profile.save()

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )

    expected = "Plays tennis on Sundays\nPreferences: Size L"
    assert payload["recipient"]["notes"] == expected


@pytest.mark.django_db
def test_ai_prompt_payload_identical_when_flag_off_vs_no_account(user: User):
    friend = User.objects.create_user(username="friend_hannah")
    _make_friends(user, friend)

    person_with_account = Person.objects.create(first_name="Hannah", account=friend)
    person_no_account = Person.objects.create(first_name="Hannah", account=None)

    # Put lots of self-profile data on friend
    pub_tag = GiftTag.objects.create(name="Pottery", is_public=True)
    friend.profile.public_interests.add(pub_tag)
    friend.profile.preferences_notes = "Secret sizes"
    friend.profile.avoid_notes = "Secret avoidances"
    friend.profile.ai_share_self_profile = False  # OFF
    friend.profile.save()
    Wish.objects.create(wisher=friend, title="Secret Wish")

    history_with_account = build_recipient_history(user, person_with_account)
    payload_with_account = build_ai_payload(
        history_with_account,
        viewer=user,
        available_tag_names=["Pottery"],
        avoid_names=[],
        count=3,
        language="en",
    )

    history_no_account = build_recipient_history(user, person_no_account)
    payload_no_account = build_ai_payload(
        history_no_account,
        viewer=user,
        available_tag_names=["Pottery"],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert payload_with_account == payload_no_account


@pytest.mark.django_db
def test_history_interest_tag_ids_decoupled_from_public_interests(user: User):
    friend = User.objects.create_user(username="friend_ian")
    _make_friends(user, friend)

    person = Person.objects.create(first_name="Ian", account=friend)
    pub_tag = GiftTag.objects.create(name="Sculpting", is_public=True)
    friend.profile.public_interests.add(pub_tag)

    history = build_recipient_history(user, person)
    # interest_tag_ids must only contain direct person interests, keeping prompt decoupled
    assert pub_tag.pk not in history.interest_tag_ids
    assert pub_tag.pk in history.public_interest_tag_ids


@pytest.mark.django_db
def test_ai_prompt_wishes_cap_ordering_and_stripping(user: User):
    friend = User.objects.create_user(
        username="friend_julia",
        first_name="Julia",
    )
    _make_friends(user, friend)

    person = Person.objects.create(first_name="Julia", account=friend)
    friend.profile.ai_share_self_profile = True
    friend.profile.save()

    # Create 12 wishes to test cap of 10
    for i in range(12):
        Wish.objects.create(
            wisher=friend,
            title=f"Wish item {i:02d}",
            priority=WishPriority.LOW if i < 5 else WishPriority.HIGH,
        )

    # Create a wish with newlines that should be stripped
    Wish.objects.create(
        wisher=friend,
        title="Multi-line\nWish\nTitle",
        priority=WishPriority.HIGH,
    )

    # Create a wish whose title is only the person's name -> scrubs to [name] -> should be dropped
    Wish.objects.create(
        wisher=friend,
        title="Julia",
        priority=WishPriority.HIGH,
    )

    history = build_recipient_history(user, person)
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert "wishes" in payload
    # Cap of at most 10
    assert len(payload["wishes"]) <= 10
    # No [name] sole string
    assert "[name]" not in payload["wishes"]
    # Newlines should be stripped/normalized
    assert not any("\n" in w for w in payload["wishes"])
