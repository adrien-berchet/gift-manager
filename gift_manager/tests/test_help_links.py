"""Tests for the "Learn more" links to Help and the gifts empty state."""

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory


def _help(topic, anchor=None):
    url = reverse("gift_manager:help_topic", args=[topic])
    return f"{url}#{anchor}" if anchor else url


def _html(client, url_name, query=""):
    return client.get(reverse(f"gift_manager:{url_name}") + query).content.decode()


@pytest.mark.django_db
class TestHelpLinks:
    """Empty states and intro lines link to their Help topic."""

    @pytest.mark.parametrize(
        ("url_name", "topic", "anchor"),
        [
            ("relations", "how-it-works", "gift-plans"),
            ("recipients", "how-it-works", "recipients"),
            ("wishlist_list", "wishlist", None),
            ("received_gift_list", "received-gifts", None),
            ("secret_santa_list", "secret-santa", None),
            ("share_objects", "friends-and-sharing", None),
            ("profile_detail", "wishlist", None),
            ("profile_detail", "quick-capture", None),
            ("profile_detail", "received-gifts", None),
        ],
    )
    def test_page_links_to_its_help_topic(self, authenticated_client, url_name, topic, anchor):
        """An empty account sees a Learn more link to the matching topic."""
        html = _html(authenticated_client, url_name)

        assert f'href="{_help(topic, anchor)}"' in html
        assert "help-learn-more" in html

    def test_wishlist_has_a_single_learn_more_when_empty(self, authenticated_client):
        """The intro line carries the link, so the empty state does not repeat it."""
        html = _html(authenticated_client, "wishlist_list")

        assert html.count(f'href="{_help("wishlist")}"') == 1

    def test_received_gifts_has_a_single_learn_more_when_empty(self, authenticated_client):
        """Same for received gifts."""
        html = _html(authenticated_client, "received_gift_list")

        assert html.count(f'href="{_help("received-gifts")}"') == 1


@pytest.mark.django_db
class TestGiftListEmptyState:
    """The gift list shows its own empty state when the user can access no gift."""

    def test_gift_list_shows_empty_state_without_gifts(self, authenticated_client):
        """No accessible gift: empty state with a create button and a Help link, no grid."""
        html = _html(authenticated_client, "gifts")

        assert 'id="gift-grid"' not in html
        assert "No gifts yet." in html
        assert f'href="{reverse("gift_manager:gift_create")}"' in html
        assert f'href="{_help("how-it-works", "gifts")}"' in html

    def test_gift_list_shows_grid_with_gifts(self, authenticated_client, user):
        """With an accessible gift the grid shows and the empty state does not."""
        GiftFactory(shared_with=[user])

        html = _html(authenticated_client, "gifts")

        assert 'id="gift-grid"' in html
        assert "No gifts yet." not in html

    def test_unassigned_filter_with_no_match_keeps_grid(self, authenticated_client, user):
        """The empty state depends on accessible gifts, not on the filter."""
        gift = GiftFactory()
        create_or_update_permission(user, gift, permission_level=PermissionLevel.OWNER)
        plan = RelationFactory(gift=gift)
        create_or_update_permission(user, plan, permission_level=PermissionLevel.OWNER)

        html = _html(authenticated_client, "gifts", "?unassigned=1")

        assert 'id="gift-grid"' in html
        assert "No gifts yet." not in html
