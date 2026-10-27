"""Swipe gestures on Grid.js rows (gift plan cards) of a touch device."""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory

pytestmark = [
    pytest.mark.frontend,
    pytest.mark.e2e,
    pytest.mark.mobile,
    pytest.mark.django_db(transaction=True),
    # Touch sequences are dispatched through the Chrome DevTools Protocol
    pytest.mark.only_browser("chromium"),
]

GRID = "relation-grid"
TOUCHMOVE_INTERVENTION = "Ignored attempt to cancel a touchmove"

# Page size updates and the initial sort re-render the rows after the first paint
WAIT_FOR_QUIET_GRID_JS = """grid => new Promise(resolve => {
    const done = () => { observer.disconnect(); resolve(); };
    let timer = setTimeout(done, 500);
    const observer = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, 500); });
    observer.observe(document.getElementById(grid), { childList: true, subtree: true });
})"""


@pytest.fixture
def touch_page(browser, browser_context_args, client, live_server, seed_data_e2e, settings):
    context = browser.new_context(
        **{
            **browser_context_args,
            "viewport": {"width": 390, "height": 844},
            "has_touch": True,
            "is_mobile": True,
        }
    )
    client.force_login(seed_data_e2e.alice)
    context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    page = context.new_page()
    page.console_messages = []
    page.on("console", lambda message: page.console_messages.append(message.text))
    yield page
    context.close()


def _plan(seed_data_e2e, name, permission_level):
    relation = RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name=name),
        event=None,
        status=seed_data_e2e.statuses["planned"],
    )
    for obj in (relation, relation.gift):
        create_or_update_permission(seed_data_e2e.alice, obj, permission_level=permission_level)
    return relation


def _open_card(page: Page, live_server, relation):
    page.goto(f"{live_server.url}/en/relations/advanced/")
    card = page.locator(f'#{GRID} .gridjs-tr[data-entity-id="{relation.relation_id}"]')
    card.and_(page.locator("[data-touch-enhanced]")).wait_for()
    page.evaluate(WAIT_FOR_QUIET_GRID_JS, GRID)
    card.scroll_into_view_if_needed()
    return card


def _swipe(page: Page, card, delta_x, delta_y=0, steps=4):
    """Drag one finger across the card the way a phone reports it: fast, in small moves."""
    box = card.bounding_box()
    start_x = box["x"] + box["width"] / 2 - delta_x / 2
    start_y = box["y"] + min(box["height"] / 2, 40)
    cdp = page.context.new_cdp_session(page)
    cdp.send(
        "Input.dispatchTouchEvent",
        {"type": "touchStart", "touchPoints": [{"x": start_x, "y": start_y}]},
    )
    for step in range(1, steps + 1):
        point = {"x": start_x + delta_x * step / steps, "y": start_y + delta_y * step / steps}
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    cdp.detach()


def _transform(card):
    return card.evaluate("el => el.style.transform")


def test_swiping_an_editable_card_reveals_its_actions(touch_page: Page, live_server, seed_data_e2e):
    relation = _plan(seed_data_e2e, "Swipe editable gift", PermissionLevel.OWNER)
    card = _open_card(touch_page, live_server, relation)

    _swipe(touch_page, card, 100)

    assert "swipe-actions-visible" in card.get_attribute("class")
    actions = card.locator(".swipe-actions-left .swipe-action-btn")
    assert actions.evaluate_all("buttons => buttons.map(b => b.dataset.action)") == [
        "edit",
        "share",
    ]
    assert not [text for text in touch_page.console_messages if TOUCHMOVE_INTERVENTION in text]

    actions.first.tap()

    expect(touch_page.locator("#editPanel")).to_be_visible()
    expect(touch_page.locator("#editPanel")).to_contain_text("Swipe editable gift")


def test_swiping_a_card_without_actions_snaps_back(touch_page: Page, live_server, seed_data_e2e):
    relation = _plan(seed_data_e2e, "Swipe read-only gift", PermissionLevel.VIEWER)
    card = _open_card(touch_page, live_server, relation)

    _swipe(touch_page, card, 100)

    assert card.locator(".swipe-actions").count() == 0
    assert "swipe-actions-visible" not in card.get_attribute("class")
    assert _transform(card) == ""


def test_vertical_drag_scrolls_without_sliding_the_card(
    touch_page: Page, live_server, seed_data_e2e
):
    relation = _plan(seed_data_e2e, "Swipe scroll gift", PermissionLevel.OWNER)
    card = _open_card(touch_page, live_server, relation)

    # Mostly vertical, with the sideways drift of a real thumb
    _swipe(touch_page, card, 30, delta_y=-120)

    assert "swipe-actions-visible" not in card.get_attribute("class")
    assert _transform(card) == ""
    assert not [text for text in touch_page.console_messages if TOUCHMOVE_INTERVENTION in text]
