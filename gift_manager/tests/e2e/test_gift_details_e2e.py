"""Browser tests for the link and price of gifts and gift plans."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import RelationFactory


def login(page: Page, base_url: str):
    """Log in as Alice, waiting for the redirect rather than for an idle network."""
    page.goto(f"{base_url}/accounts/login/", wait_until="domcontentloaded")
    page.fill('input[name="login"]', "alice")
    page.fill('input[name="password"]', "alice_password")
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=30_000)


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGiftDetailsWorkflow:
    def test_plan_card_shows_link_and_price(self, page: Page, live_server, seed_data_e2e):
        relation = RelationFactory(
            person=seed_data_e2e.persons["dad"],
            gift=GiftFactory(
                name="Priced Gift",
                shared_with=[seed_data_e2e.alice],
                price=Decimal(42),
                url="https://shop.example/gift",
            ),
            event=seed_data_e2e.events["christmas"],
            status=seed_data_e2e.statuses["planned"],
            due_date=timezone.localdate() + timedelta(days=1),
            comment="",
        )
        create_or_update_permission(
            seed_data_e2e.alice, relation, permission_level=PermissionLevel.OWNER
        )
        login(page, live_server.url)
        page.goto(f"{live_server.url}/", wait_until="domcontentloaded")

        card = page.locator(".gift-plan-card", has_text="Priced Gift").first
        expect(card.locator(".link-price-display__price")).to_contain_text("42")
        link = card.locator(".link-price-display__link")
        expect(link).to_have_attribute("href", "https://shop.example/gift")
        expect(link).to_have_attribute("rel", "noopener noreferrer nofollow")

    def test_gift_form_section_is_collapsed_and_saves_values(
        self, page: Page, live_server, seed_data_e2e
    ):
        login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/create/", wait_until="domcontentloaded")

        section = page.locator("details", has_text="Link and price")
        expect(section).not_to_have_attribute("open", "")
        expect(page.locator("input[name='url']")).not_to_be_visible()

        section.locator("summary").click()
        page.fill("input[name='name']", "Form Gift")
        page.fill("input[name='url']", "https://shop.example/form")
        page.fill("input[name='price']", "19.90")
        page.locator("form button[type='submit']").first.click()
        expect(page).not_to_have_url(f"{live_server.url}/gifts/create/")

        gift = Gift.objects.get(name="Form Gift")
        assert gift.url == "https://shop.example/form"
        assert gift.price == Decimal("19.90")


CONTRAST_JS = """
() => {
  const parse = (value) => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
  const channel = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const luminance = ([r, g, b]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  const addon = document.querySelector('.input-group-text');
  const input = document.querySelector("input[name='price']");
  const addonStyle = getComputedStyle(addon);
  const inputStyle = getComputedStyle(input);
  const [hi, lo] = [luminance(parse(addonStyle.color)), luminance(parse(addonStyle.backgroundColor))]
    .sort((a, b) => b - a);
  return {
    addonHeight: addon.getBoundingClientRect().height,
    inputHeight: input.getBoundingClientRect().height,
    contrast: (hi + 0.05) / (lo + 0.05),
    addonBackground: addonStyle.backgroundColor,
    inputBackground: inputStyle.backgroundColor,
  };
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestCurrencyAddonAppearance:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_currency_addon_matches_the_price_input(
        self, page: Page, live_server, seed_data_e2e, theme
    ):
        login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/create/", wait_until="domcontentloaded")
        page.locator("details", has_text="Link and price").locator("summary").click()
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        expect(page.locator(".input-group-text")).to_be_visible()

        metrics = page.evaluate(CONTRAST_JS)

        assert abs(metrics["addonHeight"] - metrics["inputHeight"]) < 0.5, metrics
        assert metrics["contrast"] >= 4.5, metrics
        if theme == "dark":
            assert metrics["addonBackground"] != "rgb(233, 236, 239)", metrics


CARD_LAYOUT_JS = """
(title) => {
  const card = [...document.querySelectorAll('.gift-plan-card')]
    .find((el) => el.textContent.includes(title));
  const squashed = [...card.children]
    .filter((child) => child.getBoundingClientRect().height > 0)
    .filter((child) => child.scrollHeight > child.clientHeight + 1)
    .map((child) => child.className);
  const note = card.querySelector('.gift-plan-note');
  return {
    clipped: card.scrollHeight > card.clientHeight + 1,
    squashed,
    noteHeight: note ? note.getBoundingClientRect().height : 0,
    noteVisible: note ? note.getBoundingClientRect().bottom <= card.getBoundingClientRect().bottom : false,
  };
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestDashboardCardWithDetails:
    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "phone"])
    def test_card_with_link_price_tags_and_comment_is_not_squashed(
        self, page: Page, live_server, seed_data_e2e, width
    ):
        page.set_viewport_size({"width": width, "height": 900})
        alice = seed_data_e2e.alice
        tags = [GiftTagFactory(name=f"Tag {i}", shared_with=[alice]) for i in range(2)]
        relation = RelationFactory(
            person=seed_data_e2e.persons["dad"],
            gift=GiftFactory(
                name="Detailed Novel",
                shared_with=[alice],
                price=Decimal(15),
                url="https://www.linkedin.com/in/someone",
                tags=tags,
            ),
            event=seed_data_e2e.events["christmas"],
            status=seed_data_e2e.statuses["planned"],
            due_date=timezone.localdate() + timedelta(days=1),
            comment="A comment that should stay readable on the card",
        )
        create_or_update_permission(alice, relation, permission_level=PermissionLevel.OWNER)
        login(page, live_server.url)
        page.goto(f"{live_server.url}/", wait_until="domcontentloaded")
        card = page.locator(".gift-plan-card", has_text="Detailed Novel").first
        expect(card).to_be_visible()

        layout = page.evaluate(CARD_LAYOUT_JS, "Detailed Novel")

        assert layout["clipped"] is False, layout
        assert layout["squashed"] == [], layout
        assert layout["noteHeight"] > 0 and layout["noteVisible"], layout
