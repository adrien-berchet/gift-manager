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

    # borderLeftColor is intentionally not compared: gift plan cards color the accent by
    # urgency, while list-page cards use a neutral primary accent.
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


@pytest.mark.parametrize("route", ["gifts", "persons", "events"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_grid_card_rows_and_actions_are_compact(
    logged_in_page: Page, live_server, seed_data_e2e, theme, route
):
    """Card rows ignore list-view striping and action buttons use the compact style."""
    page = logged_in_page
    page.goto(f"{live_server.url}/en/{route}/", wait_until="networkidle")
    _set_theme(page, theme)
    page.wait_for_selector(".gridjs-tbody .gridjs-tr")
    page.evaluate(
        "document.querySelectorAll('[data-view]:not(.view-toggle-btn)')"
        ".forEach(el => el.setAttribute('data-view', 'card'))"
    )
    page.wait_for_timeout(400)
    cards = page.locator('[data-view="card"] .gridjs-tbody .gridjs-tr')
    assert cards.count() >= 2

    # Even and odd cards: no zebra background on any cell.
    backgrounds = cards.evaluate_all(
        """cards => cards.flatMap(card => [...card.querySelectorAll('.gridjs-td')]
            .map(td => getComputedStyle(td).backgroundColor))"""
    )
    assert set(backgrounds) == {"rgba(0, 0, 0, 0)"}

    buttons = cards.first.locator(".quick-action-btn")
    assert buttons.count() >= 2
    sizes = buttons.evaluate_all(
        """btns => btns.map(b => ({
            action: b.dataset.action,
            ariaLabel: b.getAttribute('aria-label'),
            height: b.getBoundingClientRect().height,
            width: b.getBoundingClientRect().width,
            label: getComputedStyle(b.querySelector('.btn-text')).display,
        }))"""
    )
    # Give keeps its label; on pages without Give the Details action is the labeled one.
    has_give = any(size["action"] == "create" for size in sizes)
    labeled_action = "create" if has_give else "detail"
    for size in sizes:
        assert size["ariaLabel"], "icon-only actions need an accessible name"
        assert size["height"] <= 32
        if size["action"] == labeled_action:
            assert size["label"] != "none"
        else:
            assert size["label"] == "none"
            assert size["width"] <= 32
    # All actions fit on a single row.
    tops = buttons.evaluate_all(
        "btns => new Set(btns.map(b => Math.round(b.getBoundingClientRect().top))).size"
    )
    assert tops == 1


def test_grid_card_fields_stack_tightly_with_touch_sized_actions_on_phone(
    logged_in_page: Page, live_server, seed_data_e2e
):
    """On phones each value sits right under its label and actions are tap-sized."""
    page = logged_in_page
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto(f"{live_server.url}/en/gifts/", wait_until="networkidle")
    page.wait_for_selector('[data-view="card"] .gridjs-tbody .gridjs-td[data-label]')
    page.wait_for_timeout(400)

    heights = page.evaluate(
        """() => [...document.querySelectorAll(
            '[data-view="card"] .gridjs-tr .gridjs-td[data-label]:not(:last-child)')]
            .filter(td => td.offsetParent !== null)
            .map(td => td.getBoundingClientRect().height)"""
    )
    assert heights
    # Label (~15px) + value (<=2 lines): a stretched label would push this well beyond.
    assert max(heights) < 90, heights

    buttons = page.locator('[data-view="card"] .gridjs-tbody .gridjs-tr').first.locator(
        ".quick-action-btn"
    )
    expect(buttons.first).to_be_visible()
    sizes = buttons.evaluate_all(
        """btns => btns.map(b => {
            const r = b.getBoundingClientRect();
            return {width: r.width, height: r.height};
        })"""
    )
    assert sizes
    for size in sizes:
        assert size["height"] >= 44
        assert size["width"] >= 44


def test_gift_cards_share_one_layout_even_when_fields_are_empty(
    logged_in_page: Page, live_server, seed_data_e2e
):
    """Every gift card lists all fields in the same order, empty ones show a placeholder."""
    from decimal import Decimal

    GiftFactory(
        name="Full gift",
        comment="Hand-knitted",
        url="https://shop.example.com/scarf",
        price=Decimal("12.50"),
        shared_with=[seed_data_e2e.alice],
    )
    GiftFactory(name="Bare gift", comment="", url="", price=None, shared_with=[seed_data_e2e.alice])

    page = logged_in_page
    page.goto(f"{live_server.url}/en/gifts/", wait_until="networkidle")
    page.wait_for_selector(".gridjs-tbody .gridjs-tr")
    # Use the real view toggle so the card labels are attached like for a user.
    page.evaluate("document.querySelector('button[data-view=\"card\"]').click()")
    page.wait_for_selector('[data-view="card"] .gridjs-td[data-label]')
    page.wait_for_timeout(400)

    layouts = page.evaluate(
        """() => [...document.querySelectorAll('[data-view="card"] .gridjs-tbody .gridjs-tr')]
            .map(card => [...card.querySelectorAll('.gridjs-td[data-label]')].map(td => ({
                label: td.dataset.label,
                alignItems: getComputedStyle(td).alignItems,
                displayed: getComputedStyle(td).display !== 'none',
                empty: td.textContent.trim() === '',
                placeholder: getComputedStyle(td, '::after').content,
            })))"""
    )
    assert len(layouts) >= 2
    labels = [[cell["label"] for cell in card] for card in layouts]
    assert labels[0] == ["Gift name", "Comment", "Link", "Price", "Tags", "Actions"]
    assert all(card_labels == labels[0] for card_labels in labels)
    for card in layouts:
        for cell in card:
            assert cell["displayed"], f"{cell['label']} is hidden"
            assert cell["alignItems"] == "baseline"  # label and value share a baseline
            if cell["empty"]:
                assert cell["placeholder"] == '"—"'


@pytest.mark.parametrize(
    ("viewport", "extra_lines"),
    [({"width": 1280, "height": 900}, 0), ({"width": 360, "height": 800}, 1)],
    ids=["desktop", "phone"],
)
def test_card_comment_is_clamped_to_three_lines(
    logged_in_page: Page, live_server, seed_data_e2e, viewport, extra_lines
):
    """A very long comment is cut after three lines instead of growing the card."""
    long_comment = " ".join(["Wordy wool scarf in a very long description"] * 40)
    GiftFactory(name="Wordy gift", comment=long_comment, shared_with=[seed_data_e2e.alice])

    page = logged_in_page
    page.set_viewport_size(viewport)
    page.goto(f"{live_server.url}/en/gifts/", wait_until="networkidle")
    page.wait_for_selector(".gridjs-tbody .gridjs-tr")
    if viewport["width"] > 768:  # phones already default to the card view
        page.evaluate("document.querySelector('button[data-view=\"card\"]').click()")
    page.wait_for_selector('[data-view="card"] .gridjs-td[data-label]')
    page.wait_for_timeout(400)

    metrics = page.evaluate(
        """() => {
            const cell = [...document.querySelectorAll(
                '[data-view="card"] .gridjs-td[data-label="Comment"]')]
                .find(td => td.textContent.includes('Wordy'));
            const style = getComputedStyle(cell);
            const height = cell.getBoundingClientRect().height;
            cell.style.webkitLineClamp = 'none';
            const unclampedHeight = cell.getBoundingClientRect().height;
            cell.style.webkitLineClamp = '';
            return {
                height,
                unclampedHeight,
                lineHeight: parseFloat(style.lineHeight),
                padding: parseFloat(style.paddingTop) + parseFloat(style.paddingBottom),
            };
        }"""
    )
    max_height = metrics["lineHeight"] * (3 + extra_lines) + metrics["padding"] + 1
    assert metrics["height"] <= max_height, metrics
    assert metrics["unclampedHeight"] > metrics["height"] * 2, "the long comment should be cut"
