"""End-to-end browser tests for collaborative group gifts and contribution tally.

Covers:
1. Scenario 1 (Surprise plan):
   - Alice creates a surprise plan for Bob (price 90.00 EUR), claims it as buyer.
   - Alice enables group gift via HTMX.
   - Alice adds Carol (collaborator) and Dave (external contributor name).
   - Equal split computes 30.00 EUR each.
   - Alice marks Carol as paid.
   - Progress bar shows 60.00 / 90.00 EUR collected, Dave owes 30.00 EUR.
   - Bob (recipient w/ VIEWER permission) logs in:
     - Surprise plan is hidden on /relations/.
     - Direct plan URL and HTMX partial return HTTP 404 (anti-spoiler).
     - Direct POSTs to all group gift endpoints return HTTP 404.
     - Control check: Alice's identical POST returns HTTP 200.
2. Scenario 2 (Non-surprise shared plan):
   - Alice creates a non-surprise plan for Bob, shared with Bob (VIEWER) and Carol (EDITOR).
   - Alice enables group gift and adds Carol.
   - Bob logs in and visits the plan detail page:
     - Bob sees gift name and details (HTTP 200).
     - #relation-group-gift is strictly absent.
     - Page body contains zero mention of group gifts, contributor names or tallies.
     - Bob's POSTs to group gift endpoints return HTTP 403 PermissionDenied.
3. Contrast & Accessibility:
   - Evaluates WCAG AA text contrast in light and dark mode.
   - Verifies progress bar ARIA attributes (role, valuenow, valuemax, valuetext, label).
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager import account_links
from gift_manager import group_gifts
from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory


def login_as(page: Page, base_url: str, username: str) -> None:
    """Log in as a user (testuser uses testpass123; others <username>_password)."""
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


def share(relation: Relation, user: User, level: int) -> None:
    """Grant explicit object permission on a relation."""
    create_or_update_permission(user, relation, permission_level=level)


def get_csrf_token(page: Page) -> str:
    """Retrieve CSRF token from page cookie or input."""
    return page.evaluate(
        "() => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "
        "document.querySelector('input[name=\"csrfmiddlewaretoken\"]')?.value || ''"
    )


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
      if (el.getAttribute('aria-hidden') === 'true') return false;
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
class TestGroupGiftE2E:
    """Full lifecycle, collaboration and privacy verification for group gifts."""

    def test_group_gift_surprise_plan_collaborative_workflow(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        """Scenario 1: Collaborative group gift workflow on a surprise plan with strict anti-spoiler."""
        alice = seed_data_e2e.alice
        bob = seed_data_e2e.bob

        # Create Carol as a collaborator
        carol = User.objects.create_user(
            username="carol",
            email="carol@example.com",
            password="carol_password",
        )

        # Ensure Alice and Bob are confirmed friends so account link succeeds
        alice.profile.friends.add(bob.profile)

        # Bob is linked to a Person record created by Alice
        bob_person = Person.objects.create(
            first_name="Bob",
            family_name="Seed",
            email_address=encode_email("bob_recipient@example.com"),
        )
        create_or_update_permission(alice, bob_person, permission_level=PermissionLevel.OWNER)
        account_links.link(bob_person, bob, actor=alice)

        # Alice creates a surprise plan for Bob, price 90.00 EUR, claimed by Alice (buyer)
        gift = GiftFactory(
            name="Astronomical Telescope",
            price=Decimal("90.00"),
            shared_with=[alice, bob, carol],
        )
        surprise_plan = Relation.objects.create(
            person=bob_person,
            gift=gift,
            event=None,
            is_surprise=True,
            price=Decimal("90.00"),
            claimed_by=alice,
            claimed_at=timezone.now(),
        )
        share(surprise_plan, alice, PermissionLevel.OWNER)
        share(surprise_plan, bob, PermissionLevel.VIEWER)
        share(surprise_plan, carol, PermissionLevel.EDITOR)

        alice_context = browser.new_context(**browser_context_args)
        bob_context = browser.new_context(**browser_context_args)
        alice_page = alice_context.new_page()
        bob_page = bob_context.new_page()

        try:
            # ------------------------------------------------------------------
            # 1. Alice logs in and opens the relation detail page
            # ------------------------------------------------------------------
            login_as(alice_page, live_server.url, "alice")
            detail_url = f"{live_server.url}{surprise_plan.get_absolute_url()}"
            open_page(alice_page, detail_url)

            # Inactive group gift card is visible with CTA
            group_gift_section = alice_page.locator("#relation-group-gift")
            expect(group_gift_section).to_be_visible()
            expect(group_gift_section).to_contain_text("Group Gift & Contributions")

            enable_btn = group_gift_section.locator('button:has-text("Organize as a group gift")')
            expect(enable_btn).to_be_visible()

            # ------------------------------------------------------------------
            # 2. Alice enables group gift via HTMX
            # ------------------------------------------------------------------
            with alice_page.expect_response(
                lambda r: "/group-gift/toggle/" in r.url and r.status == 200
            ):
                enable_btn.click()

            # Section updates: progress bar and contributor form appear
            expect(alice_page.locator("#relation-group-gift .progress-bar")).to_be_visible()
            # Alice is automatically present as Buyer
            expect(alice_page.locator("#relation-group-gift")).to_contain_text("Buyer")
            expect(alice_page.locator("#relation-group-gift")).to_contain_text("alice")

            # ------------------------------------------------------------------
            # 3. Verify user dropdown: Carol is selectable, Bob is absent (recipient)
            # ------------------------------------------------------------------
            user_select = alice_page.locator("#gg-contributor-user")
            expect(user_select).to_be_visible()
            user_options = user_select.locator("option").all_inner_texts()
            assert not any("bob" in opt.lower() for opt in user_options), (
                "Bob (recipient) must not be selectable as contributor!"
            )
            assert any("carol" in opt.lower() for opt in user_options), (
                "Carol (collaborator) must be in the contributor dropdown."
            )

            # ------------------------------------------------------------------
            # 4. Add Carol as contributor via HTMX
            # ------------------------------------------------------------------
            user_select.select_option(value=str(carol.pk))
            add_form = alice_page.locator("#relation-group-gift form[action*='contributors/add']")
            with alice_page.expect_response(
                lambda r: "/group-gift/contributors/add/" in r.url and r.status == 200
            ):
                add_form.locator('button[type="submit"]').click()

            expect(alice_page.locator("#relation-group-gift")).to_contain_text("carol")

            # ------------------------------------------------------------------
            # 5. Add Dave as external contributor via HTMX
            # ------------------------------------------------------------------
            alice_page.locator("#gg-contributor-name").fill("Dave")
            with alice_page.expect_response(
                lambda r: "/group-gift/contributors/add/" in r.url and r.status == 200
            ):
                alice_page.locator(
                    "#relation-group-gift form[action*='contributors/add'] button[type='submit']"
                ).click()

            expect(alice_page.locator("#relation-group-gift")).to_contain_text("Dave")

            # Verify equal split of 90.00 EUR across 3 people = 30.00 EUR each
            surprise_plan.refresh_from_db()
            summary = group_gifts.get_group_gift_summary(surprise_plan, alice)
            currency = summary.currency
            expect(alice_page.locator("#relation-group-gift")).to_contain_text(f"30.00 {currency}")

            # ------------------------------------------------------------------
            # 6. Alice marks Carol as paid via HTMX
            # ------------------------------------------------------------------
            carol_contrib = surprise_plan.contributions.get(user=carol)
            paid_btn = alice_page.locator(f"#gg-paid-{carol_contrib.pk}")
            expect(paid_btn).to_be_visible()
            expect(paid_btn).to_contain_text("Mark paid")

            with alice_page.expect_response(
                lambda r: (
                    f"/contributors/{carol_contrib.pk}/toggle-paid/" in r.url and r.status == 200
                )
            ):
                paid_btn.click()

            # Carol now shows "Mark unpaid" and Paid badge
            expect(alice_page.locator(f"#gg-paid-{carol_contrib.pk}")).to_contain_text(
                "Mark unpaid"
            )

            # ------------------------------------------------------------------
            # 7. Check financial tally and progress bar
            # ------------------------------------------------------------------
            # Alice (buyer, 30.00 paid) + Carol (30.00 paid) = 60.00 paid of 90.00
            # Dave owes 30.00 to Alice
            section_text = alice_page.locator("#relation-group-gift").inner_text()
            assert f"60.00 {currency}" in section_text
            assert f"90.00 {currency}" in section_text
            assert f"30.00 {currency}" in section_text
            assert "alice" in section_text

            progress_bar = alice_page.locator("#relation-group-gift .progress-bar")
            expect(progress_bar).to_have_attribute("role", "progressbar")
            expect(progress_bar).to_have_attribute("aria-label", "Contribution progress")
            expect(progress_bar).to_have_attribute("aria-valuemin", "0")
            assert float(progress_bar.get_attribute("aria-valuenow")) == pytest.approx(
                60.00, abs=0.1
            )
            assert float(progress_bar.get_attribute("aria-valuemax")) == pytest.approx(
                90.00, abs=0.1
            )

            # ------------------------------------------------------------------
            # 8. Bob logs in: STRICT Anti-spoiler & Privacy Verification
            # ------------------------------------------------------------------
            login_as(bob_page, live_server.url, "bob")

            # A. Plan is hidden from /relations/
            open_page(bob_page, f"{live_server.url}/relations/")
            expect(bob_page.get_by_text("Astronomical Telescope")).to_have_count(0)

            # B. Direct URL to surprise plan returns 404
            plan_response = bob_page.goto(detail_url, wait_until="domcontentloaded")
            assert plan_response.status == 404

            # C. Direct URL to HTMX partial returns 404
            partial_response = bob_page.goto(
                f"{detail_url}?partial=true", wait_until="domcontentloaded"
            )
            assert partial_response.status == 404

            # D. Direct POSTs to group gift endpoints return 404
            bob_csrf = get_csrf_token(bob_page)
            dave_contrib = surprise_plan.contributions.get(name="Dave")

            test_endpoints = [
                reverse(
                    "gift_manager:relation_group_gift_toggle",
                    kwargs={"pk": surprise_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_mode",
                    kwargs={"pk": surprise_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_add",
                    kwargs={"pk": surprise_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_toggle_paid",
                    kwargs={
                        "pk": surprise_plan.relation_id,
                        "contribution_id": carol_contrib.pk,
                    },
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_amount",
                    kwargs={
                        "pk": surprise_plan.relation_id,
                        "contribution_id": dave_contrib.pk,
                    },
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_remove",
                    kwargs={
                        "pk": surprise_plan.relation_id,
                        "contribution_id": dave_contrib.pk,
                    },
                ),
            ]

            for endpoint in test_endpoints:
                res = bob_page.request.post(
                    f"{live_server.url}{endpoint}",
                    headers={"X-CSRFToken": bob_csrf},
                    data={"action": "disable", "split_mode": "equal", "name": "Eve"},
                )
                assert res.status == 404, f"Endpoint {endpoint} must return 404 for recipient!"

            # E. Control check: Alice doing identical POST gets 200 (valid harness)
            alice_csrf = get_csrf_token(alice_page)
            control_url = reverse(
                "gift_manager:relation_group_gift_contributor_toggle_paid",
                kwargs={
                    "pk": surprise_plan.relation_id,
                    "contribution_id": carol_contrib.pk,
                },
            )
            alice_control = alice_page.request.post(
                f"{live_server.url}{control_url}",
                headers={"X-CSRFToken": alice_csrf},
            )
            assert alice_control.status == 200, "Alice control POST must succeed with 200"

        finally:
            alice_context.close()
            bob_context.close()

    def test_group_gift_non_surprise_shared_plan_privacy(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e
    ):
        """Scenario 2: Non-surprise shared plan displays gift info but strictly conceals group gift."""
        alice = seed_data_e2e.alice
        bob = seed_data_e2e.bob

        carol = User.objects.create_user(
            username="carol_scenario2",
            email="carol2@example.com",
            password="carol_scenario2_password",
        )

        # Ensure Alice and Bob are confirmed friends
        alice.profile.friends.add(bob.profile)

        bob_person = Person.objects.create(
            first_name="Bob",
            family_name="Shared",
            email_address=encode_email("bob_shared@example.com"),
        )
        create_or_update_permission(alice, bob_person, permission_level=PermissionLevel.OWNER)
        account_links.link(bob_person, bob, actor=alice)

        # Alice creates a non-surprise plan for Bob, shared with Bob and Carol
        gift = GiftFactory(
            name="Shared Espresso Machine",
            price=Decimal("120.00"),
            shared_with=[alice, bob, carol],
        )
        shared_plan = Relation.objects.create(
            person=bob_person,
            gift=gift,
            event=None,
            is_surprise=False,
            price=Decimal("120.00"),
            claimed_by=alice,
            claimed_at=timezone.now(),
        )
        share(shared_plan, alice, PermissionLevel.OWNER)
        share(shared_plan, bob, PermissionLevel.VIEWER)
        share(shared_plan, carol, PermissionLevel.EDITOR)

        # Alice organizes group gift with Carol
        group_gifts.enable_group_gift(shared_plan, actor=alice)
        carol_contrib = group_gifts.add_contributor(shared_plan, actor=alice, user=carol)
        group_gifts.add_contributor(shared_plan, actor=alice, name="Dave")
        group_gifts.toggle_contribution_paid(carol_contrib, actor=alice)

        bob_context = browser.new_context(**browser_context_args)
        bob_page = bob_context.new_page()

        try:
            login_as(bob_page, live_server.url, "bob")
            detail_url = f"{live_server.url}{shared_plan.get_absolute_url()}"
            response = open_page(bob_page, detail_url)
            assert response.status == 200

            # 1. Bob sees the gift name and details
            expect(bob_page.locator("body")).to_contain_text("Shared Espresso Machine")

            # 2. #relation-group-gift section is STRICTLY ABSENT
            expect(bob_page.locator("#relation-group-gift")).to_have_count(0)

            # 3. Bob's page text contains zero mention of group gift, external contributors or tallies
            page_text = bob_page.locator("body").inner_text()
            assert "group gift" not in page_text.lower()
            assert "dave" not in page_text.lower()
            assert "total collected" not in page_text.lower()
            assert "owed to" not in page_text.lower()

            # 4. Bob POSTing to group gift endpoints gets HTTP 403 Forbidden
            bob_csrf = get_csrf_token(bob_page)
            dave_contrib = shared_plan.contributions.get(name="Dave")

            test_endpoints = [
                reverse(
                    "gift_manager:relation_group_gift_toggle",
                    kwargs={"pk": shared_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_mode",
                    kwargs={"pk": shared_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_add",
                    kwargs={"pk": shared_plan.relation_id},
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_toggle_paid",
                    kwargs={
                        "pk": shared_plan.relation_id,
                        "contribution_id": carol_contrib.pk,
                    },
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_amount",
                    kwargs={
                        "pk": shared_plan.relation_id,
                        "contribution_id": dave_contrib.pk,
                    },
                ),
                reverse(
                    "gift_manager:relation_group_gift_contributor_remove",
                    kwargs={
                        "pk": shared_plan.relation_id,
                        "contribution_id": dave_contrib.pk,
                    },
                ),
            ]

            for endpoint in test_endpoints:
                res = bob_page.request.post(
                    f"{live_server.url}{endpoint}",
                    headers={"X-CSRFToken": bob_csrf},
                    data={"action": "disable", "split_mode": "equal", "name": "Eve"},
                )
                assert res.status == 403, (
                    f"Recipient must receive HTTP 403 on group gift endpoint {endpoint}!"
                )

        finally:
            bob_context.close()

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_group_gift_contrast_and_accessibility(
        self, browser: Browser, browser_context_args, live_server, seed_data_e2e, theme
    ):
        """Verify WCAG AA text contrast (>= 4.5:1, >= 3.0:1 large) and ARIA attributes."""
        # Use relation_2 which is already seeded with graduation group gift
        relation = seed_data_e2e.relations[2]

        context = browser.new_context(**browser_context_args)
        page = context.new_page()

        try:
            login_as(page, live_server.url, "alice")
            detail_url = f"{live_server.url}{relation.get_absolute_url()}"
            open_page(page, detail_url)

            # Disable animations & set theme
            page.add_style_tag(content="*, *::before, *::after { transition: none !important; }")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            expect(page.locator("html")).to_have_attribute("data-theme", theme)

            # 1. Verify Progress Bar ARIA attributes
            progress_bar = page.locator("#relation-group-gift .progress-bar")
            expect(progress_bar).to_be_visible()
            expect(progress_bar).to_have_attribute("role", "progressbar")
            expect(progress_bar).to_have_attribute("aria-label", "Contribution progress")
            expect(progress_bar).to_have_attribute("aria-valuemin", "0")
            assert float(progress_bar.get_attribute("aria-valuenow")) == pytest.approx(
                100.00, abs=0.1
            )
            assert float(progress_bar.get_attribute("aria-valuemax")) == pytest.approx(
                150.00, abs=0.1
            )
            assert "100" in progress_bar.get_attribute("aria-valuetext")

            # 2. Check Contrast across all elements in #relation-group-gift
            cells = page.evaluate(
                CONTRAST_EVAL_JS,
                {"selector": "#relation-group-gift", "theme": theme},
            )
            assert cells, "No text elements found in #relation-group-gift"

            unreadable = [
                cell for cell in cells if cell["contrast"] < (3.0 if cell["isLarge"] else 4.5)
            ]
            assert unreadable == [], (
                f"WCAG AA contrast violations in #relation-group-gift ({theme}): {unreadable}"
            )

        finally:
            context.close()
