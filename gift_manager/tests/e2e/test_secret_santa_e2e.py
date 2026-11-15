"""End-to-end browser test of a Secret Santa draw.

1. The organizer opens "More" > "Secret Santa" and creates an exchange they take part in.
2. They add three participants (one without email) and an exclusion set of two.
3. They draw: the page says the draw is done and shows no pairing.
4. They reveal the personal link of the participant without email.
5. That link, opened by an anonymous visitor on a phone, shows a valid recipient only.
6. The organizer reveals all pairings: they match what the participant saw.
7. A redraw keeps the personal link working.
"""

import os
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.secret_santa.models import Exchange

# Set to a directory to keep screenshots of the pages for a visual check
SCREENSHOT_DIR = os.environ.get("SECRET_SANTA_SCREENSHOTS")


def login_as(page: Page, base_url: str, username: str) -> None:
    """Log in as a seed user (testuser uses testpass123; others <username>_password)."""
    password = "testpass123" if username == "testuser" else f"{username}_password"
    page.context.clear_cookies()
    page.goto(f"{base_url}/accounts/login/", wait_until="domcontentloaded")
    page.fill('input[name="login"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=30_000)


def open_page(page: Page, url: str):
    """Open a page and wait for HTMX initialization."""
    response = page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.htmx?.process === 'function'", timeout=30_000)
    return response


def screenshot(page: Page, name: str) -> None:
    if SCREENSHOT_DIR:
        page.screenshot(path=str(Path(SCREENSHOT_DIR) / f"{name}.png"), full_page=True)


def add_participant(page: Page, name: str, email: str = "") -> None:
    form = page.locator(".secret-santa-add-form")
    form.locator('input[name="name"]').fill(name)
    form.locator('input[name="email"]').fill(email)
    form.get_by_role("button", name="Add").click()
    expect(page.locator(".secret-santa-participant-name", has_text=name)).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestSecretSantaE2E:
    def test_draw_reveal_and_redraw(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        context = browser.new_context(**browser_context_args)
        page = context.new_page()
        guest_context = browser.new_context(
            **{**browser_context_args, "viewport": {"width": 390, "height": 844}}
        )
        guest = guest_context.new_page()
        try:
            login_as(page, live_server.url, "alice")

            # 1. Navigation and creation, taking part
            open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")
            page.locator("#navbarMoreDropdown").click()
            page.get_by_role("link", name="Secret Santa").click()
            page.wait_for_url("**/secret-santa/")
            page.get_by_role("link", name="New exchange").first.click()
            page.fill('input[name="name"]', "Family 2026")
            exchange_date = timezone.localdate() + timedelta(days=30)
            # The date input is replaced by a flatpickr widget: set the date through its API
            page.wait_for_function("document.getElementById('id_exchange_date')._flatpickr")
            page.evaluate(
                "(value) => document.getElementById('id_exchange_date')._flatpickr"
                ".setDate(value, true)",
                exchange_date.isoformat(),
            )
            page.fill('input[name="budget"]', "25")
            page.check('input[name="organizer_takes_part"]')
            page.get_by_role("button", name="Create").click()
            page.wait_for_url("**/secret-santa/*-*/")
            exchange = Exchange.objects.get(name="Family 2026")
            organizer_name = exchange.participants.get().name

            # 2. Three typed participants, one without email, and an exclusion set of two
            add_participant(page, "Bea", "bea@example.com")
            add_participant(page, "Chris")
            add_participant(page, "Dan", "dan@example.com")
            page.locator(".secret-santa-new-set > summary").click()
            set_form = page.locator(".secret-santa-new-set form")
            set_form.locator('input[name="name"]').fill("Chris and Dan")
            set_form.get_by_label("Chris").check()
            set_form.get_by_label("Dan").check()
            set_form.get_by_role("button", name="Save the set").click()
            expect(page.locator(".secret-santa-set", has_text="Chris and Dan")).to_be_visible()

            # 3. Draw: done, and no pairing on the page
            page.locator(".secret-santa-draw-button").click()
            expect(page.locator(".secret-santa-drawn-text")).to_be_visible()
            expect(page.locator(".secret-santa-status")).to_have_text("Draw done")
            assert "gives to" not in page.content()
            chris_row = page.locator(".secret-santa-participant", has_text="Chris")
            expect(chris_row.locator(".secret-santa-email-status")).to_contain_text(
                "Link to hand out"
            )
            screenshot(page, "organizer-detail")

            # 4. The link of the participant without email, behind a confirmation
            chris_row.locator(".secret-santa-show-link > summary").click()
            chris_row.locator(".secret-santa-show-link-confirm").click()
            link_input = chris_row.locator(".secret-santa-revealed-link input")
            # The app's loading skeleton stays a moment after the swap
            expect(chris_row.locator(".secret-santa-row-reveal")).not_to_have_class(
                re.compile(r"\bis-loading\b")
            )
            expect(link_input).to_be_in_viewport()
            chris_link = link_input.input_value()
            assert "/secret-santa/p/" in chris_link

            # 5. The anonymous phone visitor sees a valid recipient, without the app chrome
            response = guest.goto(chris_link, wait_until="domcontentloaded")
            assert response.status == 200
            recipient = guest.locator(".secret-santa-recipient strong").inner_text()
            assert recipient in {organizer_name, "Bea"}
            assert guest.locator("nav").count() == 0
            assert guest.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
            screenshot(guest, "participant-page")

            # 6. All pairings, behind the stronger warning: four lines, Chris's matches
            page.locator('button[data-bs-target="#pairingsModal"]').click()
            expect(page.locator(".secret-santa-self-warning")).to_be_visible()
            page.locator(".secret-santa-pairings-confirm").click()
            pairings = page.locator(".secret-santa-pairing")
            expect(pairings).to_have_count(4)
            expect(page.locator(".secret-santa-pairing", has_text="Chris gives to")).to_have_text(
                f"Chris gives to {recipient}"
            )
            expect(page.locator("#pairingsModal")).to_be_hidden()
            expect(page.locator(".modal-backdrop")).to_have_count(0)
            expect(page.locator("#secret-santa-reveal .secret-santa-pairings")).to_be_in_viewport()
            screenshot(page, "organizer-pairings")

            # The organizer page fits a phone too
            page.set_viewport_size({"width": 390, "height": 844})
            page.reload(wait_until="domcontentloaded")
            chris_row = page.locator(".secret-santa-participant", has_text="Chris")
            chris_row.locator(".secret-santa-show-link > summary").click()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
            screenshot(page, "organizer-detail-phone")
            page.set_viewport_size({"width": 1920, "height": 1080})

            # 7. Redraw: the personal link still works
            page.reload(wait_until="domcontentloaded")
            page.locator('button[data-bs-target="#redrawModal"]').click()
            page.locator(".secret-santa-redraw-confirm").click()
            expect(page.locator(".secret-santa-drawn-text")).to_be_visible()
            assert guest.goto(chris_link, wait_until="domcontentloaded").status == 200
            expect(guest.locator(".secret-santa-recipient strong")).to_be_visible()
        finally:
            guest_context.close()
            context.close()
