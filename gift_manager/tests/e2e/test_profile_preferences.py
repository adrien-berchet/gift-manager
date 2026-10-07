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

    @pytest.mark.parametrize("form_id", ["view-preferences-form", "reminder-preferences-form"])
    def test_save_button_gives_feedback_without_changing_size(
        self, page: Page, live_server, seed_data_e2e, form_id
    ):
        self._open_profile(page, live_server)
        button = page.locator(f"#{form_id} button[type='submit']")
        original_label = " ".join(button.inner_text().split())
        # Record the button box, its state and the page layout on every frame around the click
        page.evaluate(
            """(formId) => {
                const button = document.querySelector(`#${formId} button[type='submit']`);
                const heading = document.querySelector('h1, h2');
                const state = () => {
                    if (button.querySelector('.fa-spinner')) return 'saving';
                    if (button.classList.contains('btn-success')) return 'saved';
                    return 'idle';
                };
                const sample = () => {
                    const box = button.getBoundingClientRect();
                    const round = (value) => Math.round(value * 10) / 10;
                    return {
                        layout: [box.width, box.height, heading.getBoundingClientRect().top].map(round),
                        state: state(),
                        label: button.innerText.trim(),
                    };
                };
                window.__samples = [sample()];
                const loop = () => { window.__samples.push(sample()); requestAnimationFrame(loop); };
                requestAnimationFrame(loop);
            }""",
            form_id,
        )

        button.click()
        page.wait_for_timeout(2800)  # spinner (~0.4 s) + "Saved" (~1.5 s) + margin

        samples = page.evaluate("window.__samples")
        assert len(samples) > 10
        layouts = {tuple(sample["layout"]) for sample in samples}
        assert len(layouts) == 1, f"layout changed while saving: {sorted(layouts)}"
        # idle -> saving -> saved -> idle, each state seen as one uninterrupted run
        states = [sample["state"] for sample in samples]
        runs = [
            state for index, state in enumerate(states) if index == 0 or state != states[index - 1]
        ]
        assert runs == ["idle", "saving", "saved", "idle"], runs
        assert any("Saved" in sample["label"] for sample in samples if sample["state"] == "saved")
        assert " ".join(button.inner_text().split()) == original_label
        assert button.is_enabled()

    def test_save_button_does_not_claim_success_when_the_save_is_refused(
        self, page: Page, live_server, seed_data_e2e
    ):
        self._open_profile(page, live_server)
        page.route(
            "**/profile/update-reminder-preferences/",
            lambda route: route.fulfill(
                status=422,
                headers={"HX-Trigger": '{"showNotification": {"message": "No", "type": "error"}}'},
            ),
        )
        button = page.locator("#reminder-preferences-form button[type='submit']")
        original_label = " ".join(button.inner_text().split())
        page.evaluate(
            """() => {
                const button = document.querySelector("#reminder-preferences-form button[type='submit']");
                window.__states = [];
                const loop = () => {
                    window.__states.push(button.classList.contains('btn-success'));
                    requestAnimationFrame(loop);
                };
                requestAnimationFrame(loop);
            }"""
        )

        button.click()
        expect(page.locator(".toast").filter(has_text="No")).to_be_visible()
        page.wait_for_timeout(1000)

        assert not any(page.evaluate("window.__states")), "the button showed a success state"
        assert " ".join(button.inner_text().split()) == original_label
        assert button.is_enabled()

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
