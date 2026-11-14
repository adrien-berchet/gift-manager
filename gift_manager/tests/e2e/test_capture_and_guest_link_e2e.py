"""Browser tests for the bookmarklet capture flow and the read-only wishlist share link."""

from urllib.parse import unquote

import pytest
from django.urls import reverse
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Wish

SHOP_URL = "https://shop.example/products/red-scarf?utm=tracking"

SHOP_PAGE = """<!DOCTYPE html>
<html><head>
<title>Red scarf | Shop</title>
<link rel="canonical" href="https://shop.example/products/red-scarf">
<meta property="og:title" content="Red &quot;wool&quot; scarf">
<meta property="og:description" content="A warm scarf.">
<script type="application/ld+json">{"@graph": [{"@type": "Product",
 "offers": [{"@type": "Offer", "price": "24.50", "priceCurrency": "EUR"}]}]}</script>
</head><body><h1>Red scarf</h1></body></html>"""


def login_as(page: Page, base_url: str, username: str) -> None:
    password = "testpass123" if username == "testuser" else f"{username}_password"
    page.goto(f"{base_url}/accounts/login/", wait_until="domcontentloaded")
    page.fill('input[name="login"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=30_000)


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestBookmarkletCapture:
    def test_bookmarklet_captures_a_product_and_prefills_a_wish_and_a_plan(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        context = browser.new_context(**browser_context_args)
        page = context.new_page()
        try:
            login_as(page, live_server.url, "alice")
            page.goto(f"{live_server.url}{reverse('gift_manager:profile_detail')}")
            href = page.locator("a.bookmarklet-link").get_attribute("href")
            assert href.startswith("javascript:")

            # Run the bookmarklet on a shop page, as a click in the bookmarks bar would
            page.route(
                "https://shop.example/**",
                lambda route: route.fulfill(content_type="text/html", body=SHOP_PAGE),
            )
            page.goto(SHOP_URL)
            with context.expect_page() as opened:
                page.evaluate(unquote(href.removeprefix("javascript:")))
            capture = opened.value
            capture.wait_for_load_state("domcontentloaded")

            capture_url = capture.url
            assert "/capture/" in capture_url
            preview = capture.locator(".capture-preview")
            expect(preview).to_contain_text('Red "wool" scarf')
            expect(preview).to_contain_text("24.50")
            expect(preview.locator("a")).to_have_attribute(
                "href", "https://shop.example/products/red-scarf"
            )
            # The shop page itself is left alone
            assert page.url == SHOP_URL

            # Plan for someone: the gift survives the recipient step
            capture.click('[data-capture-target="plan"]')
            capture.wait_for_selector(
                'input[name="new_gift-name"][type="hidden"]', state="attached"
            )
            capture.locator('select[name="recipient"]').select_option(index=1)
            capture.click('button.btn-primary[name="nav"][value="next"]')
            expect(capture.locator('input[name="new_gift-name"]')).to_have_value('Red "wool" scarf')
            expect(capture.locator('input[name="new_gift-name"]')).to_be_visible()
            expect(capture.locator('input[name="new_gift-price"]')).to_have_value("24.50")

            # Add to my wishlist
            capture.goto(capture_url)
            capture.click('[data-capture-target="wish"]')
            expect(capture.locator('input[name="title"]')).to_have_value('Red "wool" scarf')
            expect(capture.locator('input[name="price_hint"]')).to_have_value("24.50")
            capture.click('#main-form button[type="submit"]')
            capture.wait_for_url(lambda url: url.endswith(reverse("gift_manager:wishlist_list")))

            wish = Wish.objects.get(wisher=alice, title='Red "wool" scarf')
            assert wish.url == "https://shop.example/products/red-scarf"
            assert str(wish.price_hint) == "24.50"
        finally:
            context.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGuestWishlistLink:
    def test_owner_shares_the_wishlist_and_a_visitor_reads_it(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        Wish.objects.create(
            wisher=alice, title="Shared scarf", url="https://shop.example/scarf", price_hint="19.90"
        )
        owner_context = browser.new_context(**browser_context_args)
        guest_context = browser.new_context(
            **{**browser_context_args, "viewport": {"width": 390, "height": 844}}
        )
        owner = owner_context.new_page()
        guest = guest_context.new_page()
        try:
            login_as(owner, live_server.url, "alice")
            owner.goto(f"{live_server.url}{reverse('gift_manager:wishlist_list')}")
            owner.click(".wishlist-share button[type='submit']")
            link = owner.locator("#wishlist-share-url").input_value()
            assert "/wishes/share/" in link

            response = guest.goto(link)
            assert response.status == 200
            expect(guest.locator("h1")).to_contain_text("Alice Seed")
            card = guest.locator(".guest-wishes-list article", has_text="Shared scarf")
            expect(card).to_be_visible()
            expect(card.locator("a")).to_have_attribute("rel", "noopener noreferrer")
            expect(guest.locator("nav")).to_have_count(0)
            expect(guest.locator("form")).to_have_count(0)
            # No sideways scrolling on a phone
            assert guest.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )

            owner.click(".wishlist-share .btn-outline-danger")
            owner.wait_for_selector("#wishlist-share-url", state="detached")
            assert guest.goto(link).status == 404
        finally:
            owner_context.close()
            guest_context.close()
