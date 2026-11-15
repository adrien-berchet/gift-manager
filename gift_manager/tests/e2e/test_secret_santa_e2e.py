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
from decimal import Decimal
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Wish
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant

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


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestSecretSantaTellYourSantaE2E:
    def test_wishes_decline_account_and_plan_a_gift(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
        Wish.objects.create(wisher=bob, title="Mechanical keyboard", price_hint=Decimal(20))
        exchange = service.create_exchange(
            alice,
            name="Family 2026",
            exchange_date=timezone.localdate() + timedelta(days=30),
            budget=Decimal(30),
        )
        for name, email in (
            ("Bob", "bob@example.com"),
            ("Chris", "chris@example.com"),
            ("Dana", "dana@example.com"),
            ("Eve", "eve@example.com"),
        ):
            service.add_participant(exchange, name=name, email=email)
        token = {p.name: p.token for p in exchange.participants.all()}

        def personal(name):
            return f"{live_server.url}{reverse('gift_manager:secret_santa_participant', args=[token[name]])}"

        detail = f"{live_server.url}{reverse('gift_manager:secret_santa_detail', args=[exchange.exchange_id])}"
        organizer_context = browser.new_context(**browser_context_args)
        phone_context = browser.new_context(
            **{**browser_context_args, "viewport": {"width": 390, "height": 844}}
        )
        bob_context = browser.new_context(**browser_context_args)
        try:
            organizer = organizer_context.new_page()
            login_as(organizer, live_server.url, "alice")

            # The organizer sends the personal links before the draw
            open_page(organizer, detail)
            organizer.locator(".secret-santa-invite-button").click()
            expect(
                organizer.locator(".secret-santa-participant", has_text="Chris")
            ).to_contain_text("Invited")

            # Chris, on a phone and without an account, tells their Santa what they would like
            chris = phone_context.new_page()
            chris.goto(personal("Chris"), wait_until="domcontentloaded")
            wish_form = chris.locator(".secret-santa-wish-form")
            wish_form.locator('input[name="title"]').fill("Puzzle")
            wish_form.locator('input[name="url"]').fill("https://example.com/puzzle")
            wish_form.get_by_role("button", name="Add this wish").click()
            expect(chris.locator(".secret-santa-own-wishes")).to_contain_text("Puzzle")
            chris.locator('textarea[name="note"]').fill("Size M, no chocolate")
            chris.get_by_role("button", name="Save the note").click()
            expect(chris.locator('textarea[name="note"]')).to_have_value("Size M, no chocolate")
            assert chris.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
            screenshot(chris, "participant-tell-your-santa")

            # Eve cannot take part
            eve = phone_context.new_page()
            eve.goto(personal("Eve"), wait_until="domcontentloaded")
            eve.locator(".secret-santa-decline > summary").click()
            eve.locator(".secret-santa-decline-confirm").click()
            expect(eve.locator(".secret-santa-declined-card")).to_be_visible()

            # Bob links his account through the login page and shares a real wish
            bob_page = bob_context.new_page()
            bob_page.goto(personal("Bob"), wait_until="domcontentloaded")
            bob_page.get_by_role("button", name="I have a Gift Manager account").click()
            bob_page.wait_for_url("**/accounts/login/**")
            assert token["Bob"] not in bob_page.url
            bob_page.fill('input[name="login"]', "bob")
            bob_page.fill('input[name="password"]', "bob_password")
            bob_page.click('button[type="submit"]')
            bob_page.wait_for_url("**/secret-santa/attach/")
            bob_page.get_by_role("button", name="Link my account").click()
            bob_page.wait_for_url(f"**{token['Bob']}/")
            share_form = bob_page.locator(".secret-santa-share-form")
            # Within the budget, in the same currency: ticked in advance
            expect(share_form.get_by_label("Mechanical keyboard", exact=False)).to_be_checked()
            share_form.get_by_role("button", name="Share these wishes with my Santa").click()
            expect(bob_page.locator(".secret-santa-linked")).to_be_visible()
            screenshot(bob_page, "participant-linked")

            # The organizer draws: Eve is left out
            organizer.reload(wait_until="domcontentloaded")
            expect(organizer.locator(".secret-santa-declined")).to_contain_text("Eve")
            organizer.locator(".secret-santa-draw-button").click()
            expect(organizer.locator(".secret-santa-drawn-text")).to_be_visible()

            # Each Santa sees what their recipient shared
            by_name = {p.name: p for p in exchange.participants.all()}
            assert by_name["Eve"].gives_to_id is None
            chris_santa = ExchangeParticipant.objects.get(gives_to=by_name["Chris"])
            bob_santa = ExchangeParticipant.objects.get(gives_to=by_name["Bob"])
            santa_page = phone_context.new_page()
            santa_page.goto(personal(chris_santa.name), wait_until="domcontentloaded")
            recipient_box = santa_page.locator(".secret-santa-recipient-wishes")
            expect(recipient_box).to_contain_text("Puzzle")
            expect(recipient_box).to_contain_text("Size M, no chocolate")
            if bob_santa.name != "Bob":
                anonymous = phone_context.new_page()
                anonymous.goto(personal(bob_santa.name), wait_until="domcontentloaded")
                expect(anonymous.locator(".secret-santa-recipient-wishes")).to_contain_text(
                    "Mechanical keyboard"
                )

            # Bob's dashboard card and "Plan a gift"
            open_page(bob_page, f"{live_server.url}{reverse('gift_manager:home')}")
            card = bob_page.locator(".secret-santa-card", has_text="Family 2026")
            recipient_name = ExchangeParticipant.objects.get(pk=by_name["Bob"].gives_to_id).name
            expect(card).to_contain_text(recipient_name)
            screenshot(bob_page, "dashboard-card")
            card.get_by_role("link", name="Plan a gift").click()
            bob_page.wait_for_url("**/guided/**")
            expect(bob_page.locator('input[name="new_person-first_name"]')).to_have_value(
                recipient_name.split(" ")[0]
            )
        finally:
            bob_context.close()
            phone_context.close()
            organizer_context.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestSecretSantaAfterTheDrawE2E:
    def test_repair_close_reveal_and_copy(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        exchange = service.create_exchange(
            alice, name="Office 2026", exchange_date=timezone.localdate()
        )
        for name in ("Ann", "Ben", "Cid", "Dee", "Eli"):
            service.add_participant(exchange, name=name, email=f"{name.lower()}@example.com")
        service.run_draw(exchange)
        detail = f"{live_server.url}{reverse('gift_manager:secret_santa_detail', args=[exchange.exchange_id])}"
        context = browser.new_context(**browser_context_args)
        guest_context = browser.new_context(
            **{**browser_context_args, "viewport": {"width": 390, "height": 844}}
        )
        try:
            page = context.new_page()
            login_as(page, live_server.url, "alice")
            open_page(page, detail)

            # Remove and repair: only Cid's Santa gets a new assignment
            cid = exchange.participants.get(name="Cid")
            cid_santa = ExchangeParticipant.objects.get(gives_to=cid).name
            row = page.locator(".secret-santa-participant", has_text="Cid")
            row.locator(".secret-santa-remove > summary").click()
            row.locator(".secret-santa-remove-repair").click()
            expect(page.locator(".secret-santa-participant", has_text="Cid")).to_have_count(0)
            assert "gives to" not in page.content()
            assert ExchangeParticipant.objects.get(
                name=cid_santa, exchange=exchange
            ).last_emailed_at

            # Add and repair: a latecomer, two Santas and the latecomer get a new assignment
            page.locator(".secret-santa-latecomer > summary").click()
            page.fill("#latecomer-name", "Fay")
            page.fill("#latecomer-email", "fay@example.com")
            page.locator(".secret-santa-add-repair").click()
            expect(page.locator(".secret-santa-participant", has_text="Fay")).to_be_visible()
            fay = exchange.participants.get(name="Fay")
            assert fay.gives_to_id is not None
            assert ExchangeParticipant.objects.filter(gives_to=fay).count() == 1
            screenshot(page, "organizer-after-repairs")

            # Close, revealing the pairings to everyone
            page.locator(".secret-santa-close-button").click()
            page.check("#close-reveal")
            page.locator(".secret-santa-close-confirm").click()
            expect(page.locator(".secret-santa-closed-text")).to_be_visible()
            guest = guest_context.new_page()
            ann = exchange.participants.get(name="Ann")
            guest.goto(
                f"{live_server.url}{reverse('gift_manager:secret_santa_participant', args=[ann.token])}",
                wait_until="domcontentloaded",
            )
            expect(guest.locator(".secret-santa-revealed-pairing")).to_have_count(5)
            screenshot(guest, "participant-closed-revealed")

            # Start next year's exchange from this one: no pair is repeated
            page.locator(".secret-santa-copy").click()
            page.fill('input[name="name"]', "Office 2027")
            page.wait_for_function("document.getElementById('id_exchange_date')._flatpickr")
            page.evaluate(
                "(value) => document.getElementById('id_exchange_date')._flatpickr"
                ".setDate(value, true)",
                (timezone.localdate() + timedelta(days=365)).isoformat(),
            )
            expect(page.locator('input[name="no_repeat_draw"]')).to_be_checked()
            page.get_by_role("button", name="Create").click()
            page.wait_for_url("**/secret-santa/*-*/")
            copy = Exchange.objects.get(name="Office 2027")
            assert copy.participants.count() == 5
            page.locator(".secret-santa-draw-button").click()
            expect(page.locator(".secret-santa-drawn-text")).to_be_visible()
            before = set(exchange.participants.values_list("name", "gives_to__name"))
            after = set(copy.participants.values_list("name", "gives_to__name"))
            assert not before & after
        finally:
            guest_context.close()
            context.close()
