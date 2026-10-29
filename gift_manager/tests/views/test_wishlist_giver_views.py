"""Tests for giver wishlist and preferences UI on linked Person page."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import WishPriority
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def _befriend(user1, user2):
    user1.profile.friends.add(user2.profile)


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


def _view_only(user, obj):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=PermissionLevel.VIEWER
    )


@pytest.fixture
def wisher():
    return UserFactory(username="alice")


@pytest.fixture
def giver(wisher):
    bob = UserFactory(username="bob")
    _befriend(wisher, bob)
    return bob


@pytest.fixture
def other_friend(wisher):
    carol = UserFactory(username="carol")
    _befriend(wisher, carol)
    return carol


@pytest.fixture
def linked_person(giver, wisher):
    person = PersonFactory(account=wisher, first_name="Alice", family_name="Smith")
    _own(giver, person)
    return person


def test_person_detail_displays_friend_preferences_and_wishlist(
    client, giver, wisher, linked_person
):
    """Giver viewing a linked person record sees friend's preferences and wishes."""
    public_tag = GiftTagFactory(name="Gardening", is_public=True)
    wisher.profile.preferences_notes = "Size M, favorite color green"
    wisher.profile.avoid_notes = "Peanut allergy, no plastic"
    wisher.profile.save()
    wisher.profile.public_interests.add(public_tag)

    wish = WishFactory(
        wisher=wisher,
        title="Pruning shears",
        url="https://example.com/shears",
        price_hint=Decimal("29.99"),
        priority=WishPriority.HIGH,
        notes="Ergonomic handle please",
    )

    client.force_login(giver)
    url = reverse("gift_manager:person_detail", kwargs={"pk": linked_person.person_id})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Preferences & avoid notes
    assert "Size M, favorite color green" in content
    assert "Peanut allergy, no plastic" in content
    assert "Gardening" in content

    # Wish item
    assert "Pruning shears" in content
    assert "https://example.com/shears" in content
    assert "29.99" in content
    assert "Ergonomic handle please" in content

    # Available badge & actions
    assert "Available" in content
    assert (
        reverse(
            "gift_manager:wish_claim_toggle",
            kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
        )
        in content
    )
    assert (
        reverse(
            "gift_manager:wish_plan",
            kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
        )
        in content
    )


def test_person_detail_own_record_shows_profile_redirect_notice(client, wisher):
    """Viewing one's own person record shows a notice linking to profile and wishlist."""
    own_person = PersonFactory(account=wisher, first_name="Alice", family_name="Smith")
    _own(wisher, own_person)

    client.force_login(wisher)
    url = reverse("gift_manager:person_detail", kwargs={"pk": own_person.person_id})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Notice linking to profile and personal wishlist
    profile_url = reverse("gift_manager:profile_detail")
    wishlist_url = reverse("gift_manager:wishlist_list")
    assert profile_url in content or wishlist_url in content
    assert "Wishlist & preferences" not in content


def test_wish_claim_toggle_htmx(client, giver, wisher, linked_person):
    """HTMX claim toggle reserves the wish, then toggles to release."""
    wish = WishFactory(wisher=wisher, title="Noise-cancelling headphones")

    client.force_login(giver)
    claim_url = reverse(
        "gift_manager:wish_claim_toggle",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )

    # 1. Claim wish
    response = client.post(claim_url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    wish.refresh_from_db()
    assert wish.claimed_by == giver
    content = response.content.decode()
    assert "Claimed by you" in content
    assert "Release claim" in content

    # 2. Release wish
    response = client.post(claim_url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    wish.refresh_from_db()
    assert wish.claimed_by is None
    content = response.content.decode()
    assert "Available" in content
    assert "Claim" in content


def test_wish_claim_toggle_conflict_htmx(client, giver, other_friend, wisher, linked_person):
    """When a friend attempts to claim an already claimed wish, an error is returned and item re-rendered."""
    wish = WishFactory(
        wisher=wisher,
        title="Smart Speaker",
        claimed_by=other_friend,
        claimed_at=timezone.now(),
    )

    client.force_login(giver)
    claim_url = reverse(
        "gift_manager:wish_claim_toggle",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )

    response = client.post(claim_url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    wish.refresh_from_db()
    assert wish.claimed_by == other_friend
    content = response.content.decode()
    assert "Claimed by" in content
    # Trigger header contains error notification
    assert "HX-Trigger" in response.headers
    assert "showNotification" in response.headers["HX-Trigger"]


def test_wish_claim_toggle_plain_post_redirects(client, giver, wisher, linked_person):
    """Non-HTMX POST redirects to person detail page."""
    wish = WishFactory(wisher=wisher, title="Cookbook")

    client.force_login(giver)
    claim_url = reverse(
        "gift_manager:wish_claim_toggle",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )

    response = client.post(claim_url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gift_manager:person_detail", kwargs={"pk": linked_person.person_id}
    )
    wish.refresh_from_db()
    assert wish.claimed_by == giver


def test_wish_plan_redirects_and_creates_relation(client, giver, wisher, linked_person):
    """Friend clicks 'Plan this gift' -> creates surprise Relation fulfilling the wish."""
    wish = WishFactory(
        wisher=wisher,
        title="Leather wallet",
        notes="Brown or black",
        url="https://example.com/wallet",
    )

    client.force_login(giver)
    plan_url = reverse(
        "gift_manager:wish_plan",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )

    # Plain POST
    response = client.post(plan_url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gift_manager:person_detail", kwargs={"pk": linked_person.person_id}
    )

    # Relation created
    relation = Relation.objects.get(wish=wish)
    assert relation.person == linked_person
    assert relation.is_surprise is True
    assert relation.gift.name == "Leather wallet"
    assert relation.gift.url == "https://example.com/wallet"
    assert relation.gift.comment == "Brown or black"

    # Wish claimed by giver
    wish.refresh_from_db()
    assert wish.claimed_by == giver

    # HTMX POST: returns HX-Redirect
    response_htmx = client.post(plan_url, HTTP_HX_REQUEST="true")
    assert response_htmx.status_code == 200
    assert response_htmx.headers.get("HX-Redirect") == reverse(
        "gift_manager:person_detail", kwargs={"pk": linked_person.person_id}
    )


def test_wish_plan_requires_editor_permission(client, wisher, linked_person):
    """User without EDITOR permission on person cannot plan a gift."""
    viewer = UserFactory(username="viewer_user")
    _befriend(wisher, viewer)
    _view_only(viewer, linked_person)

    wish = WishFactory(wisher=wisher, title="Board Game")

    client.force_login(viewer)
    plan_url = reverse(
        "gift_manager:wish_plan",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )

    response = client.post(plan_url)
    assert response.status_code == 403


def test_person_detail_non_friend_linked_account_does_not_show_wishlist(
    client, giver, linked_person
):
    """When a linked person's account is not friends with viewer, person detail renders 200 without wishlist card."""
    stranger = UserFactory(username="stranger")
    linked_person.account = stranger
    linked_person.save()

    client.force_login(giver)
    url = reverse("gift_manager:person_detail", kwargs={"pk": linked_person.person_id})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Wishlist & preferences" not in content


def test_unfriending_cleans_up_claims(client, giver, wisher, linked_person):
    """Unfriending releases claims, unlinks wishes from relations, and hides wishlist card on next GET."""
    wish = WishFactory(wisher=wisher, title="Coffee Grinder")

    # Giver plans wish
    client.force_login(giver)
    plan_url = reverse(
        "gift_manager:wish_plan",
        kwargs={"person_id": linked_person.person_id, "wish_id": wish.wish_id},
    )
    client.post(plan_url)

    wish.refresh_from_db()
    assert wish.claimed_by == giver
    relation = Relation.objects.get(wish=wish)
    assert relation is not None

    # Alice unfriends Bob
    client.force_login(wisher)
    remove_url = reverse("gift_manager:remove_friend", kwargs={"friend_id": giver.profile.pk})
    resp = client.post(remove_url)
    assert resp.status_code == 302

    # Verification: claim released, relation unlinked
    wish.refresh_from_db()
    assert wish.claimed_by is None
    relation.refresh_from_db()
    assert relation.wish is None

    # Bob views Alice's person record: 200 OK, no wishlist card
    client.force_login(giver)
    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": linked_person.person_id})
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == 200
    assert "Wishlist & preferences" not in detail_resp.content.decode()
