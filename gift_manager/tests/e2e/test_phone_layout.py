"""Regression coverage for clipped cards and controls on narrow phone screens."""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.frontend, pytest.mark.mobile, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def phone_page(page, client, live_server, seed_data_e2e, settings):
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


def assert_cards_fit(page):
    """Check the cards themselves: hidden overflow can mask a broken document width."""
    cards = page.locator('[data-view="card"] .gridjs-tbody .gridjs-tr')
    expect(cards.first).to_be_visible()
    assert cards.evaluate_all("""cards => cards.every(card => {
        const bounds = card.getBoundingClientRect();
        return bounds.left >= 0 && bounds.right <= innerWidth &&
            [...card.querySelectorAll('.gridjs-td')].every(cell =>
                cell.scrollWidth <= cell.clientWidth + 1);
    })""")


@pytest.mark.parametrize("width", [320, 375, 390])
def test_phone_cards_fit_with_long_content(phone_page, live_server, seed_data_e2e, width):
    person = next(iter(seed_data_e2e.persons.values()))
    person.first_name = "Alexandria" * 8
    person.save(update_fields=["first_name"])
    page = phone_page
    page.set_viewport_size({"width": width, "height": 812})

    for route in ["persons", "gifts", "events"]:
        page.goto(f"{live_server.url}/en/{route}/")
        assert_cards_fit(page)
        expect(page.locator(".gridjs-tbody .gridjs-td[data-label]").first).to_be_visible()


def test_phone_form_controls_fit_and_remain_readable(phone_page, live_server):
    page = phone_page
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(f"{live_server.url}/en/persons/")
    page.locator('[data-action="create"]:visible').first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("form")).to_be_visible()
    expect(panel).to_have_css("transform", "none")
    controls = panel.locator(
        ".form-control:visible, .form-select:visible, "
        ".form-input-text:visible, .form-date-input:visible, .form-textarea:visible"
    )
    assert controls.count() > 0
    assert controls.evaluate_all("""controls => controls.every(control => {
        const bounds = control.getBoundingClientRect();
        return parseFloat(getComputedStyle(control).fontSize) >= 16 &&
            bounds.height >= 44 && bounds.left >= 0 && bounds.right <= innerWidth;
    })""")
    save = panel.locator('button[type="submit"]')
    save.scroll_into_view_if_needed()
    expect(save).to_be_in_viewport()
    page.set_viewport_size({"width": 568, "height": 320})
    save.scroll_into_view_if_needed()
    expect(save).to_be_in_viewport()
    panel.locator('.btn-close[data-bs-dismiss="offcanvas"]').click()
    expect(panel).not_to_be_visible()


def test_phone_navigation_fits_short_viewport(phone_page, live_server):
    page = phone_page
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(f"{live_server.url}/en/")
    # Skip links must stay offscreen until keyboard focus, including on phones.
    assert page.locator(".skip-link").first.evaluate(
        "link => link.getBoundingClientRect().bottom <= 0"
    )
    page.locator(".navbar-toggler").click()
    menu = page.locator(".navbar-collapse.show")
    expect(menu).to_be_visible()
    assert menu.evaluate("element => element.getBoundingClientRect().bottom <= innerHeight")
    logout = menu.locator('a[href$="/logout/"]')
    logout.scroll_into_view_if_needed()
    expect(logout).to_be_in_viewport()
    page.locator("#navbarMoreDropdown").click()
    expect(menu.locator(".dropdown-menu.show")).to_be_visible()
    menu.locator('a.dropdown-item[href$="/events/"]').click()
    expect(page).to_have_url(f"{live_server.url}/en/events/")


@pytest.mark.parametrize("language", ["en", "fr"])
def test_phone_edit_actions_stay_visible_while_fields_scroll(phone_page, live_server, language):
    page = phone_page
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(f"{live_server.url}/{language}/persons/")
    page.locator('[data-action="edit"]:visible').first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("form")).to_be_visible()
    expect(panel).to_have_css("transform", "none")
    fields = panel.locator(".form-fields")
    actions = panel.locator(".panel-form-actions")
    cancel = actions.locator('[data-bs-dismiss="offcanvas"]')
    save = actions.locator('button[type="submit"].btn-primary')
    delete = actions.locator('[data-action="delete"]')

    for viewport in [{"width": 320, "height": 568}, {"width": 568, "height": 320}]:
        page.set_viewport_size(viewport)
        for scroll_position in [0, 100_000]:
            fields.evaluate("(element, top) => element.scrollTop = top", scroll_position)
            for button in [delete, cancel, save]:
                expect(button).to_be_in_viewport(ratio=1)
            bounds = actions.bounding_box()
            assert abs(bounds["y"] + bounds["height"] - viewport["height"]) <= 1
            assert abs(cancel.bounding_box()["y"] - save.bounding_box()["y"]) <= 2
            assert fields.bounding_box()["y"] + fields.bounding_box()["height"] <= bounds["y"] + 1
        assert fields.evaluate("element => element.scrollTop > 0")

    # A soft keyboard can shrink the visual viewport without resizing the layout viewport.
    page.set_viewport_size({"width": 320, "height": 568})
    page.evaluate("""() => {
        Object.defineProperty(visualViewport, 'height', {configurable: true, value: 320});
        Object.defineProperty(visualViewport, 'offsetTop', {configurable: true, value: 20});
        visualViewport.dispatchEvent(new Event('resize'));
    }""")
    assert panel.bounding_box()["height"] == pytest.approx(320, abs=1)
    assert actions.bounding_box()["y"] + actions.bounding_box()["height"] <= 341
    for button in [delete, cancel, save]:
        expect(button).to_be_in_viewport(ratio=1)
    page.evaluate("""() => {
        delete visualViewport.height;
        delete visualViewport.offsetTop;
        visualViewport.dispatchEvent(new Event('resize'));
    }""")
    cancel.click()
    expect(panel).not_to_be_visible()


def test_phone_edit_save_cancel_and_delete_confirmation(phone_page, live_server):
    page = phone_page
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{live_server.url}/en/gifts/")
    page.locator('[data-action="edit"]:visible').first.click()
    panel = page.locator("#editPanel")
    name = panel.locator('[name="name"]')
    expect(name).to_be_visible()
    edit_url = panel.locator("form").get_attribute("action")
    name.fill("Saved on a phone")
    panel.locator('.panel-form-actions button[type="submit"].btn-primary').click()
    expect(panel).not_to_be_visible()
    edit = page.locator(f'a[data-action="edit"][href="{edit_url}"]:visible')
    edit.click()
    expect(name).to_have_value("Saved on a phone")
    name.fill("Discarded phone edit")
    panel.locator('.panel-form-actions [data-bs-dismiss="offcanvas"]').click()
    page.locator("#discard-changes-btn").click()
    expect(panel).not_to_be_visible()
    edit.click()
    expect(name).to_have_value("Saved on a phone")
    panel.locator('.panel-form-actions [data-action="delete"]').click()
    confirmation = page.locator("#confirmModal")
    expect(confirmation).to_be_visible()
    confirmation.locator('.modal-footer [data-bs-dismiss="modal"]').click()
    expect(confirmation).not_to_be_visible()
    expect(panel).to_be_visible()
    expect(name).to_have_value("Saved on a phone")
    panel.locator('.panel-form-actions [data-bs-dismiss="offcanvas"]').click()
    expect(panel).not_to_be_visible()


@pytest.mark.parametrize("width", [375, 1280])
@pytest.mark.parametrize("action", ["create", "edit"])
def test_edit_panel_opens_without_automatic_field_scroll(phone_page, live_server, width, action):
    page = phone_page
    page.set_viewport_size({"width": width, "height": 667})
    page.add_init_script("""(() => {
        window.panelScrollCalls = [];
        const original = Element.prototype.scrollIntoView;
        Element.prototype.scrollIntoView = function(options) {
            if (this.closest('#editPanel')) window.panelScrollCalls.push(options);
            return original.call(this, options);
        };
    })()""")
    page.goto(f"{live_server.url}/en/relations/")
    page.locator(f'[data-action="{action}"]:visible').first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("form")).to_be_visible()
    expect(panel).to_have_css("transform", "none")
    # Observe past the former 300ms autofocus + 300ms keyboard + 100ms scroll timers.
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 1200))")
    assert page.evaluate("window.panelScrollCalls") == []
    assert panel.locator(".form-fields").evaluate("element => element.scrollTop") == 0
    expect(panel.locator(".btn-close")).to_be_focused()

    page.keyboard.press("Tab")
    first_field = (
        panel.locator(".form-fields").locator('input:not([type="hidden"]), select, textarea').first
    )
    expect(first_field).to_be_focused()


def test_edit_panel_validation_errors_still_receive_focus(phone_page, live_server):
    page = phone_page
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{live_server.url}/en/gifts/")
    page.locator('[data-action="edit"]:visible').first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("form")).to_be_visible()
    # Let the invalid value reach Django rather than stop at client-side validation.
    name = panel.locator('[name="name"]')
    name.evaluate("field => field.removeAttribute('required')")
    name.fill("")
    panel.locator('.panel-form-actions button[type="submit"].btn-primary').click()
    errors = panel.locator(".form-error-summary")
    expect(errors).to_be_visible()
    expect(errors).to_be_in_viewport()
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 1200))")
    expect(errors).to_be_focused()
