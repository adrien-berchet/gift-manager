"""The gift list switches between its grid and its empty state without reloading."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.base_test import BaseCRUDTest
from gift_manager.tests.factories import GiftFactory

PASSWORD = "testpass123"
# Set on the window: still there afterwards only if the page was not reloaded
NO_RELOAD_MARKER = "window.__giftEmptyStateMarker"


@pytest.fixture
def empty_user(transactional_db):
    user = get_user_model().objects.create_user(
        username="giftless", email="giftless@example.com", password=PASSWORD
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


class TestGiftEmptyStateSwitch(BaseCRUDTest):
    """Creating the first gift shows the grid; deleting the last one brings the empty state back."""

    def _open_gift_list(self, page: Page, live_server, user):
        self.login_as_user(page, live_server, user, PASSWORD)
        page.goto(f"{live_server.url}/en/gifts/")
        page.evaluate(f"{NO_RELOAD_MARKER} = true")

    def _expect_not_reloaded(self, page: Page):
        assert page.evaluate(f"{NO_RELOAD_MARKER} === true")

    def test_first_gift_shows_grid_and_last_delete_shows_empty_state(
        self, page: Page, live_server, empty_user
    ):
        self._open_gift_list(page, live_server, empty_user)
        empty_state = page.locator("#gift-empty-state")
        list_body = page.locator("#gift-list-body")
        expect(empty_state).to_be_visible()
        expect(list_body).to_be_hidden()

        empty_state.locator("a[data-action='create']").click()
        self.wait_for_panel(page)
        self.fill_form_field(page, "name", "First idea")
        self.submit_panel_form(page)
        expect(page.locator("#editPanel")).not_to_be_visible()

        expect(list_body).to_be_visible()
        expect(page.locator("#gift-grid")).to_contain_text("First idea")
        expect(empty_state).to_be_hidden()
        self._expect_not_reloaded(page)

        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)
        self.confirm_modal_action(page)
        expect(page.locator("#confirmModal")).not_to_be_visible()

        expect(empty_state).to_be_visible()
        expect(list_body).to_be_hidden()
        self._expect_not_reloaded(page)

    def test_deleting_the_only_search_match_keeps_the_grid(
        self, page: Page, live_server, empty_user
    ):
        """An empty grid after a search is not "no gifts": the other gift still exists."""
        for name in ("Alpha lamp", "Beta scarf"):
            create_or_update_permission(
                empty_user, GiftFactory(name=name), permission_level=PermissionLevel.OWNER
            )
        self._open_gift_list(page, live_server, empty_user)
        list_body = page.locator("#gift-list-body")
        expect(list_body).to_be_visible()

        page.locator("#gift-grid-search").fill("Alpha")
        expect(self.get_list_items(page)).to_have_count(1)
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)
        self.confirm_modal_action(page)
        expect(page.locator("#confirmModal")).not_to_be_visible()

        # Leave time for the switch to fetch the server's answer, then check it kept the grid
        page.wait_for_load_state("networkidle")
        expect(list_body).to_be_visible()
        expect(page.locator("#gift-empty-state")).to_be_hidden()
        self._expect_not_reloaded(page)
