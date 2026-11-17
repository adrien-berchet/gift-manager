"""Tests for the getting-started card on the dashboard, and hiding or showing it."""

import pytest
from django.urls import reverse

from gift_manager.getting_started import compute_getting_started
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import WishFactory

CARD_ID = 'id="getting-started"'


def _home_html(client):
    return client.get(reverse("gift_manager:home")).content.decode()


def _card_html(client):
    html = _home_html(client)
    card = html[html.index(CARD_ID) :]
    return card[: card.index("</section>")]


def _complete_every_step(user, user_factory):
    PersonFactory(owner=user)
    for obj in (GiftFactory(), RelationFactory(status=RelationStatusFactory(status="Given"))):
        create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    WishFactory(wisher=user)
    user.profile.friends.add(user_factory().profile)


@pytest.mark.django_db
class TestGettingStartedCard:
    """The dashboard card, the Hide action and the Show again action."""

    def test_new_user_sees_card(self, authenticated_client):
        """A new user sees the card with its Hide button and its first step."""
        html = _home_html(authenticated_client)

        assert CARD_ID in html
        assert reverse("gift_manager:getting_started_hide") in html
        assert "Add a recipient" in html
        assert "0/4" in html

    def test_card_is_inside_the_live_block(self, authenticated_client):
        """The card sits in the HTMX-refreshed block so ticks update after a create."""
        html = _home_html(authenticated_client)

        assert html.index('id="dashboard-live"') < html.index(CARD_ID)
        assert html.index(CARD_ID) < html.index('id="next-action-heading"')

    def test_card_shows_all_set_state_when_everything_done(
        self, authenticated_client, user, user_factory
    ):
        """With every step done the card stays, says so, and still offers Hide."""
        _complete_every_step(user, user_factory)

        html = _home_html(authenticated_client)

        assert CARD_ID in html
        assert "You're all set" in html
        assert reverse("gift_manager:getting_started_hide") in html
        assert "4/4" in html

    def test_unfinished_steps_link_to_their_action(self, authenticated_client):
        """Unfinished steps link to the page where you do them; plan has a guided link."""
        html = _card_html(authenticated_client)

        assert reverse("gift_manager:person_create") in html
        assert reverse("gift_manager:relation_guided_create") in html

    def test_finished_step_has_no_action_link(self, authenticated_client, user):
        """A finished step shows a tick and no action link."""
        create_or_update_permission(user, GiftFactory(), permission_level=PermissionLevel.OWNER)

        card = _card_html(authenticated_client)

        assert reverse("gift_manager:gift_create") not in card
        assert "fa-circle-check" in card

    def test_hide_removes_card_and_redirects_home(self, authenticated_client, user):
        """Hide sets the timestamp and goes back to the dashboard without the card."""
        response = authenticated_client.post(reverse("gift_manager:getting_started_hide"))

        assert response.status_code == 302
        assert response.url == reverse("gift_manager:home")
        user.profile.refresh_from_db()
        assert user.profile.getting_started_hidden_at is not None
        assert CARD_ID not in _home_html(authenticated_client)

    def test_hidden_card_stays_hidden_when_data_changes(self, authenticated_client, user):
        """Deleting data after hiding never brings the card back."""
        wish = WishFactory(wisher=user)
        authenticated_client.post(reverse("gift_manager:getting_started_hide"))
        wish.delete()

        assert CARD_ID not in _home_html(authenticated_client)

    def test_repeated_hide_keeps_first_timestamp(self, authenticated_client, user):
        """A second Hide changes nothing and still redirects."""
        authenticated_client.post(reverse("gift_manager:getting_started_hide"))
        user.profile.refresh_from_db()
        first = user.profile.getting_started_hidden_at

        response = authenticated_client.post(reverse("gift_manager:getting_started_hide"))

        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.getting_started_hidden_at == first

    def test_help_index_offers_show_again_only_when_hidden(
        self, authenticated_client, user, client
    ):
        """The Help index offers Show again only to a signed-in user who hid the card."""
        show_url = reverse("gift_manager:getting_started_show")
        index_url = reverse("gift_manager:help_index")

        assert show_url not in authenticated_client.get(index_url).content.decode()
        assert show_url not in client.get(index_url).content.decode()

        authenticated_client.post(reverse("gift_manager:getting_started_hide"))
        html = authenticated_client.get(index_url).content.decode()

        assert f'action="{show_url}"' in html
        assert 'method="post"' in html

    def test_show_again_restores_card(self, authenticated_client, user):
        """Show again clears the timestamp and the card comes back."""
        authenticated_client.post(reverse("gift_manager:getting_started_hide"))

        response = authenticated_client.post(reverse("gift_manager:getting_started_show"))

        assert response.status_code == 302
        assert response.url == reverse("gift_manager:home")
        user.profile.refresh_from_db()
        assert user.profile.getting_started_hidden_at is None
        assert CARD_ID in _home_html(authenticated_client)

    def test_repeated_show_keeps_card_visible(self, authenticated_client, user):
        """Show again on a visible card changes nothing and still redirects."""
        response = authenticated_client.post(reverse("gift_manager:getting_started_show"))

        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.getting_started_hidden_at is None

    @pytest.mark.parametrize("name", ["getting_started_hide", "getting_started_show"])
    def test_logged_out_post_redirects_to_login(self, client, name):
        """Signed-out visitors are sent to the login page."""
        response = client.post(reverse(f"gift_manager:{name}"))

        assert response.status_code == 302
        assert reverse("account_login") in response.url

    @pytest.mark.parametrize("name", ["getting_started_hide", "getting_started_show"])
    def test_get_is_not_allowed(self, authenticated_client, user, name):
        """Only POST changes the state."""
        response = authenticated_client.get(reverse(f"gift_manager:{name}"))

        assert response.status_code == 405
        user.profile.refresh_from_db()
        assert user.profile.getting_started_hidden_at is None

    def test_card_links_each_step_to_help(self, authenticated_client, user):
        """Every step has a "What's this?" link to its Help topic."""
        html = _card_html(authenticated_client)

        for step in compute_getting_started(user).steps:
            assert f'href="{step.help_url}"' in html

    def test_only_panel_ready_steps_open_in_the_side_panel(self, authenticated_client):
        """Pages without a side-panel version (invitation, plans list) open as normal pages."""
        card = _card_html(authenticated_client)
        invite_url = reverse("gift_manager:send_invitation")
        relations_url = reverse("gift_manager:relations")

        assert f'href="{invite_url}">' in card
        assert f'href="{relations_url}">' in card
        assert f'href="{reverse("gift_manager:gift_create")}" data-action="create"' in card
