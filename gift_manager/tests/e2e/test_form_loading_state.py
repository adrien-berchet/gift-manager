"""Browser tests for the form loading state in loading-states.js."""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.test_dashboard_layout import login

FORM_HTML = """
<form id="probe-form" hx-post="/__probe/submit/" hx-target="#probe-result">
  <input id="probe-name" name="name" value="x">
  <select id="probe-select" name="s"><option>a</option></select>
  <input id="probe-locked" name="locked" disabled>
  <button id="probe-background" type="button"
          hx-get="/__probe/background/" hx-target="#probe-result">Background</button>
  <button id="probe-secondary" type="submit" name="action" value="more">Save and more</button>
  <button id="probe-submit" type="submit">Save</button>
</form>
<div id="probe-result"></div>
"""


class ProbeRequests:
    """Mocked HTMX endpoints that stay pending until the test releases them."""

    def __init__(self, page: Page, submit_status: int):
        self.submit_status = submit_status
        self.page = page
        self.pending = []
        page.route("**/__probe/**", self._hold)

    def _hold(self, route):
        self.pending.append(route)

    def wait_for_request(self):
        for _ in range(100):
            if self.pending:
                return
            self.page.wait_for_timeout(50)
        message = "No probe request was sent"
        raise AssertionError(message)

    def release(self):
        while self.pending:
            route = self.pending.pop()
            is_submit = route.request.method == "POST"
            route.fulfill(
                status=self.submit_status if is_submit else 200,
                content_type="text/html",
                body="<p>done</p>",
            )


def open_probe_form(page: Page, live_server, submit_status: int = 200) -> ProbeRequests:
    login(page, live_server.url)
    page.goto(f"{live_server.url}/", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.htmx?.process === 'function'")

    probes = ProbeRequests(page, submit_status)
    page.evaluate(
        """(html) => {
            document.body.insertAdjacentHTML('beforeend', html);
            htmx.process(document.getElementById('probe-form'));
        }""",
        FORM_HTML,
    )
    return probes


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestFormLoadingState:
    def test_background_request_does_not_lock_form(self, page: Page, live_server, seed_data_e2e):
        probes = open_probe_form(page, live_server)

        page.locator("#probe-background").click()
        probes.wait_for_request()

        # The request is still pending, yet nothing is locked
        expect(page.locator("#probe-name")).to_be_enabled()
        expect(page.locator("#probe-select")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_be_enabled()

        probes.release()
        expect(page.locator("#probe-result")).to_have_text("done")
        expect(page.locator("#probe-name")).to_be_enabled()

    @pytest.mark.parametrize("status", [200, 422])
    def test_submission_locks_then_unlocks_form(
        self, page: Page, live_server, seed_data_e2e, status
    ):
        probes = open_probe_form(page, live_server, submit_status=status)

        page.locator("#probe-submit").click()
        probes.wait_for_request()

        expect(page.locator("#probe-name")).to_be_disabled()
        expect(page.locator("#probe-select")).to_be_disabled()
        expect(page.locator("#probe-submit")).to_be_disabled()
        # Other submit buttons cannot trigger a duplicate submission
        expect(page.locator("#probe-secondary")).to_be_disabled()

        probes.release()

        expect(page.locator("#probe-name")).to_be_enabled()
        expect(page.locator("#probe-select")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_have_text("Save")
        expect(page.locator("#probe-secondary")).to_be_enabled()
        # Controls disabled before the submission stay disabled afterwards
        expect(page.locator("#probe-locked")).to_be_disabled()

    def test_spinner_is_on_the_clicked_submit_button(self, page: Page, live_server, seed_data_e2e):
        probes = open_probe_form(page, live_server)

        page.locator("#probe-submit").click()
        probes.wait_for_request()

        expect(page.locator("#probe-submit")).to_have_class(r"loading")
        expect(page.locator("#probe-secondary")).not_to_have_class(r"loading")
        probes.release()

    def test_submit_button_recovers_after_fallback_timeout(
        self, page: Page, live_server, seed_data_e2e
    ):
        probes = open_probe_form(page, live_server)
        page.clock.install()

        page.locator("#probe-submit").click()
        probes.wait_for_request()
        expect(page.locator("#probe-name")).to_be_disabled()

        page.clock.run_for(31000)

        expect(page.locator("#probe-name")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_have_text("Save")
        probes.release()

    def test_plan_form_hint_request_does_not_lock_form(
        self, page: Page, live_server, seed_data_e2e
    ):
        """The repeat-gift hint fires on load from inside the gift plan form."""
        login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/", wait_until="domcontentloaded")
        page.wait_for_function("typeof window.htmx?.process === 'function'")

        with page.expect_response(lambda r: "repeat-gift-hint" in r.url):
            page.locator('[data-action="create"]:visible').first.click()

        panel = page.locator("#editPanel")
        expect(panel.locator("#repeat-gift-hint")).to_be_attached()
        selects = panel.locator("form select")
        expect(selects.first).to_be_enabled()
        expect(panel.locator("form select[disabled]")).to_have_count(0)
