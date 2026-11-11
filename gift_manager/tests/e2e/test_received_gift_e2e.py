"""End-to-end browser test for received gifts recording and viewing flow."""

import re
from datetime import date

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import ReceivedGift
from gift_manager.models import Wish


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


@pytest.mark.frontend
@pytest.mark.e2e
def test_received_gift_record_and_view_journey(page: Page, live_server, seed_data_e2e):
    alice = seed_data_e2e.alice
    login_as(page, live_server.url, "alice")

    # 1. Navigate to received gifts list
    list_url = f"{live_server.url}{reverse('gift_manager:received_gift_list')}"
    open_page(page, list_url)

    # Verify header and initial empty state
    expect(page.locator("h1")).to_contain_text("Received Gifts")
    expect(page.get_by_text("No received gifts found")).to_be_visible()

    # 2. Click record button to open offcanvas
    page.locator('[data-action="create"]:visible').first.click()

    panel = page.locator("#editPanel")
    expect(panel).to_be_visible()
    expect(panel.locator("form")).to_be_visible()

    # 3. Fill in form
    panel.locator('input[name="title"]').fill("Noise Cancelling Headphones")
    panel.locator("label", has_text="Someone else").click()
    panel.locator('input[name="giver_label"]').fill("Aunt Marie")
    panel.locator("label", has_text="Other occasion").click()
    panel.locator('input[name="occasion_text"]').fill("30th Birthday")
    panel.locator('textarea[name="description"]').fill(
        "Over-ear wireless headphones with great sound."
    )

    # Select rating 5
    panel.locator("label.rating-input-star[for$='reaction_rating_5']").click()
    panel.locator('textarea[name="reaction_note"]').fill("Incredible sound quality!")

    # Submit form and wait for panel to close
    with page.expect_response(
        lambda r: "/profile/received-gifts/add/" in r.url and r.status in (200, 204)
    ):
        panel.locator('button[type="submit"].btn-primary').click()

    expect(panel).not_to_be_visible()

    # 4. Verify item rendered on timeline
    item = page.locator(".received-gift-item")
    expect(item).to_be_visible()
    expect(item).to_contain_text("Noise Cancelling Headphones")
    expect(item).to_contain_text("Aunt Marie")
    expect(item).to_contain_text("30th Birthday")
    expect(item).to_contain_text("Over-ear wireless headphones")

    # 5. Toggle thank-you status
    thank_you_btn = item.locator('button[title*="thank-you as sent"]')
    expect(thank_you_btn).to_be_visible()

    with page.expect_response(lambda r: "toggle-thank-you" in r.url and r.status in (200, 204)):
        thank_you_btn.click()

    # Verify status changed to thanked
    thanked_btn = item.locator('button[title*="thank-you as pending"]')
    expect(thanked_btn).to_be_visible()
    expect(thanked_btn).to_contain_text("Thanked")

    # Verify database state
    gift = ReceivedGift.objects.get(recipient_user=alice)
    assert gift.title == "Noise Cancelling Headphones"
    assert gift.giver_label == "Aunt Marie"
    assert gift.reaction_rating == 5
    assert gift.thank_you_sent is True


FILTER_FORM = "#received-gifts-container > .card form"
FILTER_BUTTONS = f"{FILTER_FORM} .btn-group[role='group'] .btn"


def filter_button_boxes(page: Page) -> list[dict]:
    """Bounding boxes of the thank-you status filter buttons, left to right."""
    return page.eval_on_selector_all(
        FILTER_BUTTONS,
        """buttons => buttons.map(b => {
            const r = b.getBoundingClientRect();
            return {x: r.x, width: r.width};
        })""",
    )


def rounded_box(locator) -> dict:
    """Bounding box rounded to the pixel (hover transforms leave sub-pixel noise)."""
    return {key: round(value) for key, value in locator.bounding_box().items()}


def hold_list_requests(page: Page, query: str) -> list:
    """Intercept list refreshes whose URL contains ``query`` and keep them pending."""
    held_routes = []

    def hold_request(route):
        held_routes.append(route)

    page.route(lambda url: "/profile/received-gifts/" in url and query in url, hold_request)
    return held_routes


def wait_for_held(page: Page, held_routes: list) -> None:
    for _ in range(50):
        if held_routes:
            return
        page.wait_for_timeout(100)
    msg = "the filter request was not intercepted"
    raise AssertionError(msg)


def assert_filter_bar_stable_while_loading(page: Page, boxes_before: list[dict]) -> None:
    """While a filter request runs, no button changes size and the results dim."""
    filter_bar = page.locator(FILTER_FORM)
    expect(filter_bar.locator(".spinner-border, .loading-spinner, .btn.loading")).to_have_count(0)
    assert filter_button_boxes(page) == boxes_before
    # Client-side validation must not mark the filters valid (its icon widens a select)
    expect(filter_bar.locator(".is-valid, .is-invalid")).to_have_count(0)
    expect(page.locator(FILTER_BUTTONS).first).to_have_text("All")
    # Slow requests get feedback on the results instead of on the buttons
    page.wait_for_function(
        """() => {
            const results = document.querySelector('#received-gifts-results');
            return results && parseFloat(getComputedStyle(results).opacity) < 1;
        }""",
        timeout=5_000,
    )


def assert_filter_bar_settled(page: Page, boxes_before: list[dict]) -> None:
    """After the swap, buttons keep their labels and never flash "Saved"."""
    filter_bar = page.locator(FILTER_FORM)
    expect(filter_bar).not_to_contain_text("Saved")
    expect(filter_bar.locator(".spinner-border, .btn.loading")).to_have_count(0)
    expect(page.locator(FILTER_BUTTONS).first).to_have_text("All")
    expect(page.locator("#received-gifts-results")).to_have_css("opacity", "1")
    page.wait_for_timeout(500)
    expect(filter_bar).not_to_contain_text("Saved")
    assert [round(b["width"]) for b in filter_button_boxes(page)] == [
        round(b["width"]) for b in boxes_before
    ]


@pytest.mark.frontend
@pytest.mark.e2e
def test_received_gift_filters_do_not_shift_status_buttons(page: Page, live_server, seed_data_e2e):
    """Changing a filter must not swap a status button for a wider spinner."""
    alice = seed_data_e2e.alice
    ReceivedGift.objects.create(
        recipient_user=alice,
        title="Old Scarf",
        giver_label="Aunt Marie",
        received_on=date(2024, 5, 1),
    )
    ReceivedGift.objects.create(
        recipient_user=alice,
        title="New Lamp",
        giver_label="Uncle Paul",
        received_on=date(2025, 5, 1),
        thank_you_sent=True,
    )
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_list')}")
    boxes_before = filter_button_boxes(page)
    assert len(boxes_before) == 3

    # 1. Year select: submits the form without a submitter
    held_routes = hold_list_requests(page, "year=2024")
    page.select_option("select[name='year']", "2024")
    wait_for_held(page, held_routes)
    assert_filter_bar_stable_while_loading(page, boxes_before)
    with page.expect_response(lambda r: "year=2024" in r.url):
        held_routes[0].continue_()
    expect(page.locator(".received-gifts-timeline")).to_contain_text("Old Scarf")
    expect(page.locator(".received-gifts-timeline")).not_to_contain_text("New Lamp")
    assert_filter_bar_settled(page, boxes_before)

    # 2. Status button: the clicked button must not grow either
    boxes_before = filter_button_boxes(page)
    held_routes = hold_list_requests(page, "thank_you=sent")
    page.locator(FILTER_BUTTONS).nth(2).click()
    wait_for_held(page, held_routes)
    assert_filter_bar_stable_while_loading(page, boxes_before)
    with page.expect_response(lambda r: "thank_you=sent" in r.url):
        held_routes[0].continue_()
    expect(page.get_by_text("No received gifts found")).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
def test_received_gift_card_toggle_does_not_dim_results(page: Page, live_server, seed_data_e2e):
    """A card action refreshes the list in the background: the cards must not dim."""
    ReceivedGift.objects.create(
        recipient_user=seed_data_e2e.alice,
        title="Warm Socks",
        giver_label="Aunt Marie",
        received_on=date(2025, 5, 1),
    )
    login_as(page, live_server.url, "alice")
    list_url = f"{live_server.url}{reverse('gift_manager:received_gift_list')}"
    open_page(page, list_url)
    held_routes = []

    def hold_request(route):
        held_routes.append(route)

    card = page.locator(".received-gift-item")
    toggle = card.locator("form.gift-plan-quick-action-form button")
    # Measure while hovered: the card lifts on hover, which is not a layout shift
    toggle.hover()
    page.wait_for_timeout(300)
    toggle_box = rounded_box(toggle)
    held_toggles = []

    def hold_toggle(route):
        held_toggles.append(route)

    page.route("**/toggle-thank-you/", hold_toggle)
    page.route(lambda url: url.split("?")[0] == list_url, hold_request)
    toggle.click()
    wait_for_held(page, held_toggles)

    # While saving, the toggle keeps its label and size (no "Submitting..." spinner)
    assert card.locator(".spinner-border, .btn.loading, .fa-pulse").count() == 0
    assert toggle.inner_text().strip() == "Thank-you pending"
    assert rounded_box(toggle) == toggle_box

    held_toggles[0].continue_()
    wait_for_held(page, held_routes)
    assert card.locator(".spinner-border, .btn.loading, .fa-pulse").count() == 0
    assert rounded_box(toggle) == toggle_box

    # Longer than the filter dimming delay: a background refresh must not trigger it
    page.wait_for_timeout(500)
    expect(page.locator("#received-gifts-results")).to_have_css("opacity", "1")

    with page.expect_response(lambda r: r.url.split("?")[0] == list_url):
        held_routes[0].continue_()
    expect(
        page.locator(".received-gift-item").get_by_role("button", name="Thanked")
    ).to_be_visible()
    # The new button state is the feedback: no toast in the corner
    page.wait_for_timeout(500)
    expect(page.locator(".toast", has_text="Thank-you marked")).to_have_count(0)
    expect(page.locator("#received-gifts-results")).to_have_css("opacity", "1")


@pytest.mark.frontend
@pytest.mark.e2e
def test_received_gift_panel_switches_giver_and_occasion_modes(
    page: Page, live_server, seed_data_e2e
):
    """Radios swap the giver selector / occasion event for free text; only one side is saved."""
    alice = seed_data_e2e.alice
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_list')}")
    page.locator('[data-action="create"]:visible').first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("form")).to_be_visible()

    # Givers: people and groups are two sections of one selector, shown by default
    picker = panel.locator(".giver-picker")
    giver_name = panel.locator('input[name="giver_label"]')
    expect(picker).to_be_visible()
    expect(giver_name).to_be_hidden()
    expect(picker.locator(".giver-picker-title")).to_have_text(["People", "Groups"])

    # "Someone else" replaces the selector with the free-text name, and back
    panel.locator("label", has_text="Someone else").click()
    expect(giver_name).to_be_visible()
    expect(picker).to_be_hidden()
    giver_name.fill("Neighbour")
    panel.locator("label", has_text="People or groups").click()
    expect(picker).to_be_visible()
    expect(giver_name).to_be_hidden()

    # Occasion: a known event by default, or a free-text occasion
    event_select = panel.locator('select[name="event"]')
    occasion = panel.locator('input[name="occasion_text"]')
    expect(event_select).to_be_visible()
    expect(occasion).to_be_hidden()
    panel.locator("label", has_text="Other occasion").click()
    expect(occasion).to_be_visible()
    expect(event_select).to_be_hidden()
    occasion.fill("Housewarming")
    panel.locator("label[for='id_occasion_mode_0']").click()
    expect(event_select).to_be_visible()

    # Gift: a new gift (title and link) by default, or a fulfilled wish
    title = panel.locator('input[name="title"]')
    link = panel.locator('input[name="url"]')
    wish = panel.locator('select[name="wish"]')
    expect(title).to_be_visible()
    expect(link).to_be_visible()
    expect(wish).to_be_hidden()
    panel.locator("label.btn", has_text="Fulfilled wish").click()
    expect(wish).to_be_visible()
    expect(title).to_be_hidden()
    expect(link).to_be_hidden()
    panel.locator("label.btn", has_text="New gift").click()
    expect(title).to_be_visible()

    panel.locator('input[name="title"]').fill("Photo Album")
    picker.get_by_label("Mom Seed").check()
    picker.get_by_label("Family", exact=True).check()
    event_value = event_select.locator("option").nth(1).get_attribute("value")
    event_select.select_option(event_value)
    with page.expect_response(
        lambda r: "/profile/received-gifts/add/" in r.url and r.status in (200, 204)
    ):
        panel.locator('button[type="submit"].btn-primary').click()
    expect(panel).not_to_be_visible()

    # Only the chosen side of each choice is saved
    gift = ReceivedGift.objects.get(recipient_user=alice, title="Photo Album")
    assert [str(p) for p in gift.giver_persons.all()] == ["Mom Seed"]
    assert [g.name for g in gift.giver_groups.all()] == ["Family"]
    assert gift.giver_label == ""
    assert str(gift.event_id) == event_value
    assert gift.occasion_text == gift.event.name[:100]

    card = page.locator(".received-gift-item", has_text="Photo Album")
    expect(card).to_contain_text("Mom Seed")
    expect(card).to_contain_text("Family")


@pytest.mark.frontend
@pytest.mark.e2e
def test_received_gift_giver_section_stays_put(page: Page, live_server, seed_data_e2e):
    """Ticking a giver is not highlighted, and switching to free text does not move anything."""
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_list')}")
    page.locator('[data-action="create"]:visible').first.click()
    panel = page.locator("#editPanel")
    picker = panel.locator(".giver-picker")
    expect(picker).to_be_visible()
    section = panel.locator(".card", has=page.locator(".giver-picker"))
    options = section.locator(".guided-choice-options")
    giver_name = panel.locator('input[name="giver_label"]')
    # Measure once the panel has finished sliding in
    expect(panel).to_have_class(re.compile(r"\bshow\b"))
    expect(panel).not_to_have_class(re.compile(r"\bshowing\b"))
    section_box = rounded_box(section)
    options_box = rounded_box(options)
    picker_box = rounded_box(picker)

    # The tick is the feedback: no unsaved-change border, but the change is still tracked
    picker.get_by_label("Mom Seed").check()
    page.wait_for_timeout(400)
    expect(section.locator(".field-group-unsaved, .field-unsaved")).to_have_count(0)
    expect(panel.locator(".panel-form-actions.has-unsaved-changes")).to_have_count(1)
    assert rounded_box(section) == section_box

    # Switching to free text swaps the content in place: same section box, nothing shifted
    panel.locator("label", has_text="Someone else").click()
    expect(giver_name).to_be_visible()
    page.wait_for_timeout(400)
    expect(section).not_to_have_class(re.compile(r"field-group-unsaved"))
    assert rounded_box(section) == section_box
    assert rounded_box(options) == options_box
    assert rounded_box(giver_name)["x"] == picker_box["x"]

    panel.locator("label", has_text="People or groups").click()
    expect(picker).to_be_visible()
    page.wait_for_timeout(400)
    assert rounded_box(section) == section_box
    assert rounded_box(picker) == picker_box


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("mark_received", [True, False], ids=["marked", "kept-open"])
def test_received_gift_records_a_fulfilled_wish(
    page: Page, live_server, seed_data_e2e, mark_received
):
    """Choosing "Fulfilled wish" takes the title and link from the wish, in place.

    The wish is marked as received unless the (ticked by default) checkbox is unticked.
    """
    alice = seed_data_e2e.alice
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_list')}")
    page.locator('[data-action="create"]:visible').first.click()
    panel = page.locator("#editPanel")
    wish_select = panel.locator('select[name="wish"]')
    section = panel.locator(".card", has=page.locator('select[name="wish"]'))
    expect(panel.locator('input[name="title"]')).to_be_visible()
    expect(panel).not_to_have_class(re.compile(r"\bshowing\b"))
    section_box = rounded_box(section)

    panel.locator('input[name="title"]').fill("Typed title, ignored")
    panel.locator("label.btn", has_text="Fulfilled wish").click()
    expect(wish_select).to_be_visible()
    # The content is swapped in place: the section keeps its size and position
    assert rounded_box(section) == section_box

    wish_value = wish_select.locator("option").nth(1).get_attribute("value")
    wish_select.select_option(wish_value)
    mark_checkbox = panel.get_by_label("Mark the wish as received")
    expect(mark_checkbox).to_be_checked()
    if not mark_received:
        mark_checkbox.uncheck()
        # The tick is the feedback: no unsaved-change border shifting the checkbox
        page.wait_for_timeout(400)
        expect(section.locator(".form-check.field-group-unsaved")).to_have_count(0)
    panel.locator(".giver-picker").get_by_label("Mom Seed").check()
    with page.expect_response(
        lambda r: "/profile/received-gifts/add/" in r.url and r.status in (200, 204)
    ):
        panel.locator('button[type="submit"].btn-primary').click()
    expect(panel).not_to_be_visible()

    gift = ReceivedGift.objects.select_related("wish").get(recipient_user=alice)
    assert str(gift.wish_id) == wish_value
    assert gift.title == gift.wish.title
    assert gift.url == gift.wish.url
    assert gift.fulfills_wish is mark_received
    assert gift.wish.is_fulfilled is mark_received
    expect(page.locator(".received-gift-item", has_text=gift.wish.title)).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
def test_wishlist_shows_and_undoes_received_wishes(page: Page, live_server, seed_data_e2e):
    """Receiving a wish moves it to "Received wishes"; the wish panel can stop counting it."""
    alice = seed_data_e2e.alice
    wish = Wish.objects.create(wisher=alice, title="Espresso Machine")
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:wishlist_list')}")
    card = page.locator(f"#wish-{wish.wish_id}")
    received_section = page.locator(".received-wishes-section")
    expect(received_section).to_have_count(0)

    # 1. Record it from the card: the panel starts on "Fulfilled wish"
    card.get_by_role("link", name="Mark as received").click()
    panel = page.locator("#editPanel")
    expect(panel.locator('select[name="wish"]')).to_be_visible()
    panel.locator(".giver-picker").get_by_label("Mom Seed").check()
    with page.expect_response(
        lambda r: "/profile/received-gifts/add/" in r.url and r.status in (200, 204)
    ):
        panel.locator('button[type="submit"].btn-primary').click()
    expect(panel).not_to_be_visible()

    # 2. It moved to the "Received wishes" section, with a badge
    expect(received_section.locator("summary")).to_contain_text("Received wishes (1)")
    expect(page.locator(".active-wishes-list").get_by_text("Espresso Machine")).to_have_count(0)
    received_section.locator("summary").click()
    expect(card.locator(".wish-received-badge")).to_contain_text("Received on")

    # 3. The wish panel lists the gift; stop counting it: the wish goes back to the open list
    card.locator(".gift-plan-card-title a").click()
    expect(panel).to_be_visible()
    block = panel.locator(".wish-received")
    expect(block).to_contain_text("Mom Seed")
    with page.expect_response(lambda r: "toggle-fulfills-wish" in r.url):
        block.get_by_role("button", name="Don't count as received").click()
    expect(block.get_by_role("button", name="Count as received")).to_be_visible()
    expect(panel).to_be_visible()

    expect(received_section).to_have_count(0)
    active_card = page.locator(".active-wishes-list").locator(f"#wish-{wish.wish_id}")
    expect(active_card.locator(".wish-last-received")).to_contain_text("Last received on")
    wish.refresh_from_db()
    assert wish.is_fulfilled is False
