"""Card appearance parity between the dashboard and Grid.js card view."""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory

pytestmark = [pytest.mark.frontend, pytest.mark.django_db(transaction=True)]

CARD_STYLE_JS = """card => {
    const s = getComputedStyle(card);
    return {
        borderRadius: s.borderTopLeftRadius,
        borderTopWidth: s.borderTopWidth,
        borderLeftWidth: s.borderLeftWidth,
        borderLeftColor: s.borderLeftColor,
        backgroundColor: s.backgroundColor,
        paddingTop: s.paddingTop,
        paddingLeft: s.paddingLeft,
        boxShadow: s.boxShadow,
        rowGap: s.rowGap,
    };
}"""


@pytest.fixture
def logged_in_page(page: Page, client, live_server, seed_data_e2e, settings):
    client.force_login(seed_data_e2e.alice)
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    return page


def _set_theme(page: Page, theme: str):
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_grid_card_matches_gift_plan_card(logged_in_page: Page, live_server, seed_data_e2e, theme):
    """The Grid.js card view and the gift plan card share container styling."""
    page = logged_in_page
    RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name="Card parity gift"),
        event=None,
        status=seed_data_e2e.statuses["planned"],
        shared_with=[seed_data_e2e.alice],
    )

    page.goto(f"{live_server.url}/", wait_until="networkidle")
    _set_theme(page, theme)
    plan_card = page.locator(".gift-plan-card").first
    expect(plan_card).to_be_visible()
    page.wait_for_timeout(400)  # let theme transitions settle
    plan_style = plan_card.evaluate(CARD_STYLE_JS)

    page.goto(f"{live_server.url}/en/gifts/", wait_until="networkidle")
    _set_theme(page, theme)
    page.wait_for_selector(".gridjs-tbody .gridjs-tr")
    page.evaluate(
        "document.querySelectorAll('[data-view]:not(.view-toggle-btn)')"
        ".forEach(el => el.setAttribute('data-view', 'card'))"
    )
    grid_card = page.locator('[data-view="card"] .gridjs-tbody .gridjs-tr').first
    expect(grid_card).to_be_visible()
    page.wait_for_timeout(400)  # let the box-shadow/transform transitions settle
    grid_style = grid_card.evaluate(CARD_STYLE_JS)

    for key in (
        "borderRadius",
        "borderTopWidth",
        "borderLeftWidth",
        "backgroundColor",
        "paddingTop",
        "paddingLeft",
        "boxShadow",
        "rowGap",
    ):
        assert grid_style[key] == plan_style[key], f"{key} differs in {theme} theme"


def test_grid_card_view_has_no_horizontal_overflow_on_mobile(
    logged_in_page: Page, live_server, seed_data_e2e
):
    page = logged_in_page
    page.set_viewport_size({"width": 360, "height": 800})
    for route in ("gifts", "events", "persons"):
        page.goto(f"{live_server.url}/en/{route}/", wait_until="networkidle")
        page.wait_for_selector('[data-view="card"] .gridjs-tbody .gridjs-tr')
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
