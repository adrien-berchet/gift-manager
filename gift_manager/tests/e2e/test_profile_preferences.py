"""Browser test: saving the profile preferences does not reload or move the page."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Profile
from gift_manager.tests.e2e.test_plan_coordination import login_as
from gift_manager.tests.e2e.test_plan_coordination import open_page


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestProfilePreferences:
    def _open_profile(self, page: Page, live_server):
        login_as(page, live_server.url, "alice")
        open_page(page, live_server.url + reverse("gift_manager:profile_detail"))
        # A marker that only survives while the document is not reloaded
        page.evaluate("window.__sameDocument = true")
        page.evaluate("window.scrollTo({top: 300, behavior: 'instant'})")
        page.wait_for_function("window.scrollY === 300")
        return page.evaluate(
            "[window.scrollY, document.querySelector('h1, h2').getBoundingClientRect().top]"
        )

    def _assert_not_reloaded(self, page: Page, before):
        assert page.evaluate("window.__sameDocument === true"), "the page was reloaded"
        after = page.evaluate(
            "[window.scrollY, document.querySelector('h1, h2').getBoundingClientRect().top]"
        )
        assert after == before, f"the page moved: {before} -> {after}"

    def test_display_preferences_save_without_reload(self, page: Page, live_server, seed_data_e2e):
        before = self._open_profile(page, live_server)

        page.locator("#view-preferences-form .view-option", has_text="Cards").first.click()
        page.locator("#view-preferences-form button[type='submit']").click()

        expect(page.locator(".toast").filter(has_text="Display preferences saved")).to_be_visible()
        self._assert_not_reloaded(page, before)
        profile = Profile.objects.get(user=seed_data_e2e.alice)
        assert profile.default_view_desktop == Profile.VIEW_CARD

    def test_reminder_preferences_save_without_reload(self, page: Page, live_server, seed_data_e2e):
        before = self._open_profile(page, live_server)

        page.locator("#reminder-preferences-form select[name='digest_frequency']").select_option(
            "weekly"
        )
        page.locator("#reminder-preferences-form button[type='submit']").click()

        expect(page.locator(".toast").filter(has_text="Reminder preferences saved")).to_be_visible()
        self._assert_not_reloaded(page, before)
        profile = Profile.objects.get(user=seed_data_e2e.alice)
        assert profile.digest_frequency == Profile.DIGEST_WEEKLY
