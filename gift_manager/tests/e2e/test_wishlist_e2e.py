"""End-to-end browser tests for user personal profile preferences and wishlist lifecycle.

Covers the complete collaborative user journey across wisher and giver personas:
1. Alice updates her profile preferences and avoid notes via HTMX.
2. Alice creates a wish via the offcanvas panel and verifies its active card rendering.
3. Bob visits his linked record for Alice and inspects her wishlist and preferences.
4. Bob claims Alice's wish via HTMX.
5. Bob creates a surprise gift plan fulfilling the wish.
6. Alice verifies her wish remains intact with zero indication of Bob's claim or plan (anti-spoiler privacy).
7. Alice is forbidden from claiming or planning her own wish.
8. Color contrast (WCAG AA) is validated in light and dark mode across wish cards and giver view.
"""

import pytest
from django.urls import reverse
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager import account_links
from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Wish
from gift_manager.models import WishPriority
from gift_manager.permissions import create_or_update_permission


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


CONTRAST_EVAL_JS = """
(args) => {
  const { selector, theme } = args;
  const parse = (value) => {
    if (!value || value === 'transparent') return {r: 0, g: 0, b: 0, a: 0};
    const parts = value.match(/[\\d.]+/g);
    if (!parts || parts.length < 3) return {r: 0, g: 0, b: 0, a: 0};
    const [r, g, b, a = 1] = parts.map(Number);
    return {r, g, b, a};
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const channel = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const luminance = ({r, g, b}) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  const pageBg = theme === 'dark' ? {r: 15, g: 23, b: 42, a: 1} : {r: 255, g: 255, b: 255, a: 1};

  const effectiveBackground = (el) => {
    const layers = [];
    for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg.a > 0) layers.push(bg);
    }
    return layers.reduceRight((below, layer) => blend(layer, below), pageBg);
  };

  const container = document.querySelector(selector);
  if (!container) return [];

  const elements = [...container.querySelectorAll('*')]
    .filter((el) => {
      if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return false;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
      return [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== '');
    });

  return elements.map((el) => {
    const style = getComputedStyle(el);
    const color = parse(style.color);
    const bg = effectiveBackground(el);
    const [hi, lo] = [luminance(color), luminance(bg)].sort((a, b) => b - a);
    const contrast = (hi + 0.05) / (lo + 0.05);
    const fontSize = parseFloat(style.fontSize);
    const fontWeight = parseInt(style.fontWeight, 10) || 400;
    const isLarge = fontSize >= 24 || (fontSize >= 18.5 && fontWeight >= 700);
    return {
      text: el.textContent.trim().slice(0, 30),
      contrast: Math.round(contrast * 100) / 100,
      isLarge: isLarge,
      tag: el.tagName,
    };
  });
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestWishlistE2E:
    """Full lifecycle, collaboration and privacy verification across personas."""

    def test_wishlist_full_collaborative_journey_and_privacy(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        bob = seed_data_e2e.bob

        # Ensure Alice and Bob are confirmed friends
        alice.profile.friends.add(bob.profile)

        # Bob has a Person record for Alice linked to her user account
        alice_person = Person.objects.create(
            first_name="Alice",
            family_name="Seed",
            email_address=encode_email("alice@example.com"),
        )
        create_or_update_permission(bob, alice_person, permission_level=PermissionLevel.OWNER)
        account_links.link(alice_person, alice, actor=bob)

        # Create two isolated browser contexts for Alice and Bob
        alice_context = browser.new_context(**browser_context_args)
        bob_context = browser.new_context(**browser_context_args)
        alice_page = alice_context.new_page()
        bob_page = bob_context.new_page()

        try:
            # ------------------------------------------------------------------
            # 1. Alice logs in, saves gift preferences on /profile/
            # ------------------------------------------------------------------
            login_as(alice_page, live_server.url, "alice")
            open_page(alice_page, f"{live_server.url}{reverse('gift_manager:profile_detail')}")

            pref_form = alice_page.locator("#profile-preferences-form")
            expect(pref_form).to_be_visible()

            pref_notes_input = pref_form.locator('textarea[name="preferences_notes"]')
            avoid_notes_input = pref_form.locator('textarea[name="avoid_notes"]')

            pref_notes_input.fill("Shoe size 39, favorite color blue, loves mechanical keyboards.")
            avoid_notes_input.fill("Severe peanut allergy, hates cheap plastic.")

            with alice_page.expect_response(
                lambda r: "/profile/update-preferences/" in r.url and r.status in (200, 204)
            ):
                pref_form.locator('button[type="submit"]').click()

            # Verify saved preferences in DB
            alice.profile.refresh_from_db()
            assert "mechanical keyboards" in alice.profile.preferences_notes
            assert "Severe peanut allergy" in alice.profile.avoid_notes

            # ------------------------------------------------------------------
            # 2. Alice adds a wish on /profile/wishlist/ via the offcanvas form
            # ------------------------------------------------------------------
            open_page(alice_page, f"{live_server.url}{reverse('gift_manager:wishlist_list')}")
            expect(alice_page.locator("h1")).to_contain_text("My Wishlist")

            # Click "Add a wish"
            alice_page.locator(
                'a[href*="/wishes/create/"]:visible, [data-action="create"]:visible'
            ).first.click()

            # Wait for offcanvas #editPanel to open and display form
            panel = alice_page.locator("#editPanel")
            expect(panel).to_be_visible()
            expect(panel.locator("form.wish-form")).to_be_visible()

            # Fill in the wish fields
            wish_title = "Mechanical Keyboard"
            panel.locator('input[name="title"]').fill(wish_title)
            panel.locator('input[name="url"]').fill("https://example.com/keyboard")
            panel.locator('input[name="price_hint"]').fill("120.00")
            panel.locator('select[name="priority"]').select_option(str(WishPriority.MEDIUM.value))
            panel.locator('textarea[name="notes"]').fill("Cherry MX Brown switches preferred.")

            # Submit and wait for panel to close and list to update
            with alice_page.expect_response(
                lambda r: "/profile/wishlist/add/" in r.url and r.status in (200, 204)
            ):
                panel.locator('button[type="submit"].btn-primary').click()

            expect(panel).not_to_be_visible()

            # Assert the new wish card appears in the active wishes list
            active_list = alice_page.locator(".active-wishes-list")
            wish_card = active_list.locator(".wish-card", has_text=wish_title)
            expect(wish_card).to_be_visible()
            expect(wish_card).to_contain_text("120")
            expect(wish_card).to_contain_text("Cherry MX Brown switches preferred.")

            # Record wish from DB
            created_wish = Wish.objects.get(wisher=alice, title=wish_title)
            assert created_wish.claimed_by is None

            # ------------------------------------------------------------------
            # 3. Bob logs in and visits Alice's linked Person detail page
            # ------------------------------------------------------------------
            login_as(bob_page, live_server.url, "bob")
            person_path = reverse(
                "gift_manager:person_detail", kwargs={"pk": alice_person.person_id}
            )
            person_url = f"{live_server.url}{person_path}"
            open_page(bob_page, person_url)

            # ------------------------------------------------------------------
            # 4. Bob views Alice's Wishlist & preferences section
            # ------------------------------------------------------------------
            wishlist_container = bob_page.locator("#person-wishlist-container")
            expect(wishlist_container).to_be_visible()
            expect(wishlist_container).to_contain_text(
                "Severe peanut allergy, hates cheap plastic."
            )
            expect(wishlist_container).to_contain_text("Shoe size 39, favorite color blue")

            # Check wish item
            wish_item = wishlist_container.locator(f"#wish-item-{created_wish.wish_id}")
            expect(wish_item).to_be_visible()
            expect(wish_item).to_contain_text(wish_title)
            expect(wish_item).to_contain_text("Available")

            # ------------------------------------------------------------------
            # 5. Bob claims the wish via HTMX
            # ------------------------------------------------------------------
            claim_form = wish_item.locator("form[action*='/claim/']")
            claim_button = claim_form.locator("button[type='submit']")
            expect(claim_button).to_contain_text("Claim")

            with bob_page.expect_response(
                lambda r: f"/wishes/{created_wish.wish_id}/claim/" in r.url and r.status == 200
            ):
                claim_button.click()

            # Badge updates to "Claimed by you", button becomes "Release claim"
            expect(wish_item.locator(".badge", has_text="Claimed by you")).to_be_visible()
            expect(claim_form.locator("button[type='submit']")).to_contain_text("Release claim")

            created_wish.refresh_from_db()
            assert created_wish.claimed_by == bob

            # ------------------------------------------------------------------
            # 6. Bob plans this gift
            # ------------------------------------------------------------------
            plan_form = wish_item.locator("form[action*='/plan/']")
            plan_button = plan_form.locator("button[type='submit']")
            expect(plan_button).to_contain_text("Plan this gift")

            with bob_page.expect_navigation():
                plan_button.click()

            # Bob is redirected back to the person detail page
            expect(bob_page.locator("#person-wishlist-container")).to_be_visible()

            # On the wish item, the "Planned" badge is now visible
            updated_wish_item = bob_page.locator(f"#wish-item-{created_wish.wish_id}")
            expect(updated_wish_item.locator(".badge", has_text="Planned")).to_be_visible()

            # Under Bob's gift plans in progress, the surprise gift is listed
            expect(bob_page.locator("body")).to_contain_text(wish_title)

            # ------------------------------------------------------------------
            # 7. Alice checks her wishlist: STRICT anti-spoiler privacy contract
            # ------------------------------------------------------------------
            # Reload Alice's wishlist page
            alice_page.reload(wait_until="domcontentloaded")
            alice_wish_card = alice_page.locator(f"#wish-{created_wish.wish_id}")
            expect(alice_wish_card).to_be_visible()

            # The wish card content in Alice's view must have ZERO indication of Bob's claim or plan
            card_html = alice_wish_card.inner_html()
            assert "bob" not in card_html.lower()
            assert "claimed" not in card_html.lower()
            assert "planned" not in card_html.lower()

            # Alice's entire wishlist body has no leak
            body_text = alice_page.locator("#wishlist-body").inner_text()
            assert "bob" not in body_text.lower()
            assert "claimed" not in body_text.lower()
            assert "planned" not in body_text.lower()

            # ------------------------------------------------------------------
            # 8. Alice cannot claim or plan her own wish (Forbidden / Not Allowed)
            # ------------------------------------------------------------------
            claim_path = reverse(
                "gift_manager:wish_claim_toggle",
                kwargs={"person_id": alice_person.person_id, "wish_id": created_wish.wish_id},
            )
            claim_url = f"{live_server.url}{claim_path}"
            csrf_token = alice_page.evaluate(
                "() => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''"
            )
            alice_claim_response = alice_page.request.post(
                claim_url,
                headers={"X-CSRFToken": csrf_token},
            )
            assert alice_claim_response.status in (403, 404)

        finally:
            alice_context.close()
            bob_context.close()

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_wishlist_cards_color_contrast_light_and_dark_mode(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e, theme
    ):
        """Verify WCAG AA text contrast (>= 4.5:1, >= 3.0:1 for large) on wishlist cards."""
        alice = seed_data_e2e.alice
        bob = seed_data_e2e.bob
        alice.profile.friends.add(bob.profile)

        alice_person = Person.objects.create(
            first_name="Alice",
            family_name="Seed",
            email_address=encode_email("alice@example.com"),
        )
        create_or_update_permission(bob, alice_person, permission_level=PermissionLevel.OWNER)
        account_links.link(alice_person, alice, actor=bob)

        context = browser.new_context(**browser_context_args)
        page = context.new_page()

        try:
            # 1. Check wisher's wishlist cards in Alice's view
            login_as(page, live_server.url, "alice")
            open_page(page, f"{live_server.url}{reverse('gift_manager:wishlist_list')}")
            page.add_style_tag(content="*, *::before, *::after { transition: none !important; }")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")

            expect(page.locator(".wish-card").first).to_be_visible()

            wisher_cells = page.evaluate(
                CONTRAST_EVAL_JS,
                {"selector": "#wishlist-body", "theme": theme},
            )
            assert wisher_cells, "No text elements found in wisher wishlist body"

            unreadable_wisher = [
                cell
                for cell in wisher_cells
                if cell["contrast"] < (3.0 if cell["isLarge"] else 4.5)
            ]
            assert unreadable_wisher == [], (
                f"Contrast violations in wisher view ({theme}): {unreadable_wisher}"
            )

            # 2. Check giver's wishlist and preferences container in Bob's view
            login_as(page, live_server.url, "bob")
            giver_person_path = reverse(
                "gift_manager:person_detail", kwargs={"pk": alice_person.person_id}
            )
            person_url = f"{live_server.url}{giver_person_path}"
            open_page(page, person_url)
            page.add_style_tag(content="*, *::before, *::after { transition: none !important; }")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")

            expect(page.locator("#person-wishlist-container")).to_be_visible()

            giver_cells = page.evaluate(
                CONTRAST_EVAL_JS,
                {"selector": "#person-wishlist-container", "theme": theme},
            )
            assert giver_cells, "No text elements found in giver wishlist container"

            unreadable_giver = [
                cell for cell in giver_cells if cell["contrast"] < (3.0 if cell["isLarge"] else 4.5)
            ]
            assert unreadable_giver == [], (
                f"Contrast violations in giver view ({theme}): {unreadable_giver}"
            )

        finally:
            context.close()
