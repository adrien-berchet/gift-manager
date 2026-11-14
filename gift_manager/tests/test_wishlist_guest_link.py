"""Tests for the read-only wishlist share link."""

import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def guest_url(token):
    return reverse("gift_manager:wishlist_guest", kwargs={"token": token})


@pytest.fixture
def token(user):
    return user.profile.regenerate_wishlist_share_token()


def _cards(content):
    """Return the wish cards of a guest page, each without its title."""
    cards = re.findall(r"<article.*?</article>", content, flags=re.DOTALL)
    return [re.sub(r"<h2.*?</h2>", "", card, flags=re.DOTALL) for card in cards]


class TestGuestPage:
    def test_anonymous_visitor_sees_the_active_wishes(self, client, user, token):
        WishFactory(wisher=user, title="Red scarf", url="https://shop.example/scarf")
        WishFactory(wisher=UserFactory(), title="Someone else's wish")

        response = client.get(guest_url(token))
        content = response.content.decode()

        assert response.status_code == 200
        assert "Red scarf" in content
        assert user.username in content
        assert "Someone else" not in content

    def test_security_headers(self, client, token):
        response = client.get(guest_url(token))

        assert response["Referrer-Policy"] == "no-referrer"
        assert response["Cache-Control"] == "private, no-store"
        assert response["X-Robots-Tag"] == "noindex, nofollow"

    def test_page_keeps_the_secret_address_private(self, client, user, token):
        WishFactory(wisher=user, url="https://shop.example/scarf")

        content = client.get(guest_url(token)).content.decode()

        assert content.index('name="referrer"') < content.index("<link")
        assert (
            'href="https://shop.example/scarf" target="_blank" rel="noopener noreferrer"' in content
        )
        # The banner links must not carry the secret address into the login pages
        assert token not in content

    def test_hides_archived_deleted_and_received_wishes(self, client, user, token):
        WishFactory(wisher=user, title="Archived one", is_archived=True)
        WishFactory(wisher=user, title="Deleted one", is_deleted_by_wisher=True)
        received = WishFactory(wisher=user, title="Received one")
        ReceivedGiftFactory(recipient_user=user, wish=received, fulfills_wish=True)
        WishFactory(wisher=user, title="Still wanted")

        content = client.get(guest_url(token)).content.decode()

        assert "Still wanted" in content
        for hidden in ("Archived one", "Deleted one", "Received one"):
            assert hidden not in content

    def test_claimed_and_fulfilled_wishes_look_like_any_other(self, client, user, token):
        friend = UserFactory()
        common = {"wisher": user, "priority": 2, "notes": "", "url": "", "price_hint": None}
        WishFactory(title="Free", **common)
        WishFactory(title="Claimed", claimed_by=friend, claimed_at="2026-11-01T10:00Z", **common)
        WishFactory(title="Given by a friend", is_fulfilled=True, **common)

        content = client.get(guest_url(token)).content.decode()
        cards = _cards(content)

        assert len(cards) == 3
        assert len(set(cards)) == 1
        assert friend.username not in content

    def test_claim_columns_are_never_read(self, client, user, token):
        WishFactory(wisher=user)

        with CaptureQueriesContext(connection) as queries:
            client.get(guest_url(token))

        wish_queries = [q["sql"] for q in queries if '"gift_manager_wish"."title"' in q["sql"]]
        assert len(wish_queries) == 1
        select = wish_queries[0].split(" FROM ")[0]
        for column in ("claimed_by", "claimed_at", "is_fulfilled"):
            assert column not in select

    def test_empty_wishlist(self, client, token):
        assert client.get(guest_url(token)).status_code == 200

    def test_unknown_token_is_not_found(self, client, token):
        assert client.get(guest_url("unknown")).status_code == 404

    def test_inactive_owner_is_not_found(self, client, user, token):
        user.is_active = False
        user.save()

        assert client.get(guest_url(token)).status_code == 404

    def test_is_read_only(self, client, token):
        assert client.post(guest_url(token)).status_code == 405


class TestManagingTheLink:
    def test_wishlist_page_offers_to_enable_the_link(self, authenticated_client):
        response = authenticated_client.get(reverse("gift_manager:wishlist_list"))

        assert "wishlist_share_url" not in response.context
        assert reverse("gift_manager:wishlist_share_regenerate") in response.content.decode()

    def test_enable_shows_the_link(self, authenticated_client, user):
        response = authenticated_client.post(
            reverse("gift_manager:wishlist_share_regenerate"), follow=True
        )

        user.profile.refresh_from_db()
        token = user.profile.wishlist_share_token
        assert token
        assert response.context["wishlist_share_url"] == f"http://testserver{guest_url(token)}"
        assert 'data-copy-target="wishlist-share-url"' in response.content.decode()

    def test_regenerate_stops_the_old_link(self, authenticated_client, client, user, token):
        authenticated_client.post(reverse("gift_manager:wishlist_share_regenerate"))

        user.profile.refresh_from_db()
        assert user.profile.wishlist_share_token != token
        assert client.get(guest_url(token)).status_code == 404
        assert client.get(guest_url(user.profile.wishlist_share_token)).status_code == 200

    def test_disable_stops_the_link(self, authenticated_client, client, user, token):
        authenticated_client.post(reverse("gift_manager:wishlist_share_disable"))

        user.profile.refresh_from_db()
        assert user.profile.wishlist_share_token is None
        assert client.get(guest_url(token)).status_code == 404

    def test_a_user_only_changes_their_own_link(self, authenticated_client, user):
        other = UserFactory()
        other_token = other.profile.regenerate_wishlist_share_token()

        authenticated_client.post(reverse("gift_manager:wishlist_share_regenerate"))
        authenticated_client.post(reverse("gift_manager:wishlist_share_disable"))

        other.profile.refresh_from_db()
        assert other.profile.wishlist_share_token == other_token

    @pytest.mark.parametrize("name", ["wishlist_share_regenerate", "wishlist_share_disable"])
    def test_managing_requires_login_and_post(self, client, authenticated_client, name):
        url = reverse(f"gift_manager:{name}")

        assert client.post(url).status_code == 302
        assert "login" in client.post(url)["Location"]
        assert authenticated_client.get(url).status_code == 405
