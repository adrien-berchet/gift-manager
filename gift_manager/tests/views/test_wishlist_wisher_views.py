"""Tests for wisher profile preferences and wishlist management UI views."""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from gift_manager import wishlist
from gift_manager.forms import ProfilePreferencesForm
from gift_manager.forms import WishForm
from gift_manager.models import Wish
from gift_manager.models import WishPriority
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return UserFactory(username="alice")


@pytest.fixture
def other_user():
    return UserFactory(username="bob")


# --- 1. Profile Preferences Form & Views ------------------------------------------------------


def test_profile_preferences_form_saves_preferences_and_tags(user):
    """ProfilePreferencesForm saves preferences_notes, avoid_notes, public tags, and AI toggle."""
    public_tag = GiftTagFactory(name="Books", is_public=True)
    private_tag = GiftTagFactory(name="Secret", is_public=False)

    form = ProfilePreferencesForm(
        data={
            "preferences_notes": "Size M, favorite color blue",
            "avoid_notes": "Peanut allergy, no physical books",
            "public_interests": [public_tag.pk],
            "ai_share_self_profile": True,
        },
        instance=user.profile,
    )
    assert form.is_valid(), form.errors
    saved_profile = form.save()

    assert saved_profile.preferences_notes == "Size M, favorite color blue"
    assert saved_profile.avoid_notes == "Peanut allergy, no physical books"
    assert list(saved_profile.public_interests.all()) == [public_tag]
    assert saved_profile.ai_share_self_profile is True

    # Private tags cannot be chosen
    form_with_private = ProfilePreferencesForm(
        data={
            "public_interests": [private_tag.pk],
        },
        instance=user.profile,
    )
    assert not form_with_private.is_valid()
    assert "public_interests" in form_with_private.errors


def test_update_profile_preferences_view_post_standard(client, user):
    """POST to /profile/update-preferences/ saves preferences and redirects with flash message."""
    client.force_login(user)
    url = reverse("gift_manager:update_profile_preferences")

    response = client.post(
        url,
        {
            "preferences_notes": "Shoe size 42",
            "avoid_notes": "No plastic",
            "ai_share_self_profile": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.preferences_notes == "Shoe size 42"
    assert user.profile.avoid_notes == "No plastic"
    assert user.profile.ai_share_self_profile is True


def test_update_profile_preferences_view_post_htmx(client, user):
    """HTMX POST to /profile/update-preferences/ returns status 204 with toast trigger."""
    client.force_login(user)
    url = reverse("gift_manager:update_profile_preferences")

    response = client.post(
        url,
        {
            "preferences_notes": "Updated via HTMX",
            "avoid_notes": "None",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 204
    assert "HX-Trigger" in response.headers
    trigger_data = json.loads(response.headers["HX-Trigger"])
    assert "showNotification" in trigger_data
    assert trigger_data["showNotification"]["type"] == "success"

    user.profile.refresh_from_db()
    assert user.profile.preferences_notes == "Updated via HTMX"
    assert user.profile.ai_share_self_profile is False


def test_profile_detail_view_supplies_preferences_form(client, user):
    """ProfileDetailView context includes preferences_form and active_wishes_count."""
    WishFactory(wisher=user, title="Active Wish 1", is_archived=False)
    WishFactory(wisher=user, title="Archived Wish", is_archived=True)

    client.force_login(user)
    response = client.get(reverse("gift_manager:profile_detail"))
    assert response.status_code == 200
    assert "preferences_form" in response.context
    assert isinstance(response.context["preferences_form"], ProfilePreferencesForm)
    assert response.context["active_wishes_count"] == 1


# --- 2. Wish Form Validation ------------------------------------------------------------------


def test_wish_form_validation():
    """WishForm validates title, price_hint >= 0, and URL."""
    # Valid form
    form = WishForm(
        data={
            "title": "Board Game",
            "url": "https://example.com/item",
            "price_hint": "35.50",
            "priority": WishPriority.HIGH,
            "notes": "English version please",
        }
    )
    assert form.is_valid(), form.errors

    # Invalid price hint (< 0)
    invalid_price = WishForm(
        data={
            "title": "Board Game",
            "price_hint": "-10.00",
        }
    )
    assert not invalid_price.is_valid()
    assert "price_hint" in invalid_price.errors

    # Invalid URL
    invalid_url = WishForm(
        data={
            "title": "Board Game",
            "url": "javascript:alert(1)",
        }
    )
    assert not invalid_url.is_valid()
    assert "url" in invalid_url.errors

    # Empty title
    empty_title = WishForm(data={"title": ""})
    assert not empty_title.is_valid()
    assert "title" in empty_title.errors


# --- 3. Wishlist Management Views -------------------------------------------------------------


def test_wishlist_list_view_renders_wisher_wishes(client, user, other_user):
    """WishListView displays active and archived wishes belonging strictly to the wisher."""
    wish_active = WishFactory(wisher=user, title="Alice Active Wish", is_archived=False)
    wish_archived = WishFactory(wisher=user, title="Alice Archived Wish", is_archived=True)
    other_wish = WishFactory(wisher=other_user, title="Bob Secret Wish")

    client.force_login(user)
    url = reverse("gift_manager:wishlist_list")
    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode("utf-8")
    assert "Alice Active Wish" in content
    assert "Alice Archived Wish" in content
    assert "Bob Secret Wish" not in content

    # Context structure
    assert "active_wishes" in response.context
    assert "archived_wishes" in response.context
    assert wish_active in response.context["active_wishes"]
    assert wish_archived in response.context["archived_wishes"]
    assert other_wish not in response.context["active_wishes"]
    assert other_wish not in response.context["archived_wishes"]


def test_wishlist_list_view_htmx_partial(client, user):
    """HTMX GET to WishListView returns partial template."""
    WishFactory(wisher=user, title="Active Item")
    client.force_login(user)
    url = reverse("gift_manager:wishlist_list")
    response = client.get(url, headers={"HX-Request": "true"})
    assert response.status_code == 200
    # Must not contain full HTML head/body tags
    content = response.content.decode("utf-8")
    assert "<!DOCTYPE html>" not in content
    assert "Active Item" in content


def test_wish_create_view_get(client, user):
    """GET /profile/wishlist/add/ renders wish form."""
    client.force_login(user)
    url = reverse("gift_manager:wish_create")

    # Standard GET
    response = client.get(url)
    assert response.status_code == 200
    assert "form" in response.context

    # HTMX GET
    response_htmx = client.get(url, headers={"HX-Request": "true"})
    assert response_htmx.status_code == 200
    content = response_htmx.content.decode("utf-8")
    assert "<!DOCTYPE html>" not in content
    assert 'data-form-type="wish"' in content


def test_wish_create_view_post_standard(client, user):
    """Standard POST to WishCreateView creates wish assigned to request.user and redirects."""
    client.force_login(user)
    url = reverse("gift_manager:wish_create")

    response = client.post(
        url,
        {
            "title": "New Telescope",
            "url": "https://example.com/telescope",
            "price_hint": "199.99",
            "priority": WishPriority.HIGH,
            "notes": "With tripod",
            # Attempt to spoof wisher or claimed_by
            "wisher": 9999,
            "claimed_by": 9999,
        },
        follow=False,
    )
    assert response.status_code == 302
    assert response.url == reverse("gift_manager:wishlist_list")

    created = Wish.objects.get(title="New Telescope")
    assert created.wisher == user
    assert created.price_hint == Decimal("199.99")
    assert created.priority == WishPriority.HIGH
    assert created.claimed_by is None


def test_wish_create_view_post_htmx(client, user):
    """HTMX POST to WishCreateView returns HX-Trigger header to close offcanvas and refresh list."""
    client.force_login(user)
    url = reverse("gift_manager:wish_create")

    response = client.post(
        url,
        {
            "title": "Coffee Grinder",
            "priority": WishPriority.MEDIUM,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code in (200, 204)
    assert "HX-Trigger" in response.headers
    trigger_data = json.loads(response.headers["HX-Trigger"])
    assert "list:update" in trigger_data
    assert "offcanvas:close" in trigger_data

    assert Wish.objects.filter(wisher=user, title="Coffee Grinder").exists()


def test_wish_update_view(client, user, other_user):
    """WishUpdateView updates fields and bumps wisher_updated_at; prevents overwriting friend claim."""
    wish = WishFactory(
        wisher=user,
        title="Old Title",
        price_hint=Decimal("20.00"),
        priority=WishPriority.LOW,
    )
    initial_updated_at = wish.wisher_updated_at

    # Other user cannot edit user's wish
    client.force_login(other_user)
    edit_url = reverse("gift_manager:wish_edit", kwargs={"wish_id": wish.wish_id})
    res_forbidden = client.get(edit_url)
    assert res_forbidden.status_code == 404

    # Wisher edits wish
    client.force_login(user)
    res_get = client.get(edit_url)
    assert res_get.status_code == 200

    # Simulate friend claiming the wish between wisher opening form and saving
    user.profile.friends.add(other_user.profile)
    wishlist.claim_wish(wish, other_user)
    wish.refresh_from_db()
    assert wish.claimed_by == other_user

    # Wisher posts updates
    res_post = client.post(
        edit_url,
        {
            "title": "Updated Title",
            "url": "https://example.com/updated",
            "price_hint": "45.00",
            "priority": WishPriority.HIGH,
            "notes": "New notes",
        },
        follow=False,
    )
    assert res_post.status_code == 302
    wish.refresh_from_db()

    assert wish.title == "Updated Title"
    assert wish.url == "https://example.com/updated"
    assert wish.price_hint == Decimal("45.00")
    assert wish.priority == WishPriority.HIGH
    assert wish.notes == "New notes"
    # wisher_updated_at must be bumped
    assert wish.wisher_updated_at > initial_updated_at
    # Concurrent friend claim was preserved!
    assert wish.claimed_by == other_user
    assert wish.claimed_at is not None


def test_wish_archive_toggle(client, user, other_user):
    """WishArchiveView toggles is_archived; rejects non-owner with 404."""
    wish = WishFactory(wisher=user, is_archived=False)
    archive_url = reverse("gift_manager:wish_archive_toggle", kwargs={"wish_id": wish.wish_id})

    # Non-owner gets 404
    client.force_login(other_user)
    assert client.post(archive_url).status_code == 404
    wish.refresh_from_db()
    assert wish.is_archived is False

    # Owner toggles archive to True
    client.force_login(user)
    res1 = client.post(archive_url, follow=True)
    assert res1.status_code == 200
    wish.refresh_from_db()
    assert wish.is_archived is True

    # Owner toggles archive back to False
    res2 = client.post(archive_url, follow=True)
    assert res2.status_code == 200
    wish.refresh_from_db()
    assert wish.is_archived is False


def test_wish_delete_view_unclaimed(client, user, other_user):
    """WishDeleteView hard-deletes an unclaimed wish."""
    wish = WishFactory(wisher=user, title="To be deleted")
    delete_url = reverse("gift_manager:wish_delete", kwargs={"wish_id": wish.wish_id})

    # Non-owner 404
    client.force_login(other_user)
    assert client.post(delete_url).status_code == 404
    assert Wish.objects.filter(pk=wish.pk).exists()

    # Owner deletes
    client.force_login(user)
    response = client.post(delete_url, follow=True)
    assert response.status_code == 200
    assert not Wish.objects.filter(pk=wish.pk).exists()


def test_wish_delete_view_claimed_identical_response(client, user, other_user):
    """WishDeleteView on claimed wish archives it in DB but returns identical success response."""
    user.profile.friends.add(other_user.profile)
    wish = WishFactory(wisher=user, title="Claimed wish to delete")
    person = PersonFactory(account=user)
    from gift_manager.models import PermissionLevel
    from gift_manager.services import PermissionService

    PermissionService.create_or_update_permission(
        other_user, person, permission_level=PermissionLevel.OWNER
    )
    wishlist.plan_wish(wish, other_user, person)

    delete_url = reverse("gift_manager:wish_delete", kwargs={"wish_id": wish.wish_id})
    client.force_login(user)
    response = client.post(delete_url, follow=True)
    assert response.status_code == 200

    # Response does NOT reveal anything about archiving
    content = response.content.decode("utf-8")
    assert "archived instead" not in content.lower()

    # In DB, preserved as archived for giver plan
    wish.refresh_from_db()
    assert wish.is_archived is True
    assert wish.claimed_by == other_user
