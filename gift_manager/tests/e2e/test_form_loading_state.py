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
  <button id="probe-submit" type="submit">Save</button>
</form>
<div id="probe-result"></div>
"""


def open_probe_form(page: Page, live_server, submit_status: int):
    """Inject a probe form whose HTMX endpoints are mocked and delayed."""
    login(page, live_server.url)
    page.goto(f"{live_server.url}/", wait_until="networkidle")
    page.wait_for_function("typeof window.htmx?.process === 'function'")

    def respond(route):
        page.wait_for_timeout(500)
        status = submit_status if route.request.method == "POST" else 200
        route.fulfill(status=status, content_type="text/html", body="<p>done</p>")

    page.route("**/__probe/**", respond)
    page.evaluate(
        """(html) => {
            document.body.insertAdjacentHTML('beforeend', html);
            htmx.process(document.getElementById('probe-form'));
        }""",
        FORM_HTML,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestFormLoadingState:
    def test_background_request_does_not_lock_form(self, page: Page, live_server, seed_data_e2e):
        open_probe_form(page, live_server, submit_status=200)

        page.locator("#probe-background").click()

        expect(page.locator("#probe-name")).to_be_enabled()
        expect(page.locator("#probe-select")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_be_enabled()
        expect(page.locator("#probe-result")).to_have_text("done")

    @pytest.mark.parametrize("status", [200, 422])
    def test_submission_locks_then_unlocks_form(
        self, page: Page, live_server, seed_data_e2e, status
    ):
        open_probe_form(page, live_server, submit_status=status)

        page.locator("#probe-submit").click()

        expect(page.locator("#probe-name")).to_be_disabled()
        expect(page.locator("#probe-select")).to_be_disabled()
        expect(page.locator("#probe-submit")).to_be_disabled()

        expect(page.locator("#probe-name")).to_be_enabled()
        expect(page.locator("#probe-select")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_be_enabled()
        expect(page.locator("#probe-submit")).to_have_text("Save")
        # Controls disabled before the submission stay disabled afterwards
        expect(page.locator("#probe-locked")).to_be_disabled()
