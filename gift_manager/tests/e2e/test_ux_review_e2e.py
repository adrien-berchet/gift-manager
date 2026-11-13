"""Browser checks for the 2026-11-13 UX review fixes (A4, A5, A6)."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.test_received_gift_e2e import login_as
from gift_manager.tests.e2e.test_received_gift_e2e import open_page


@pytest.mark.frontend
@pytest.mark.e2e
def test_filter_panel_is_translated_and_hides_the_selection_column(
    page: Page, live_server, seed_data_e2e
):
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}/fr/gifts/")
    page.locator(".advanced-list-tools-summary").first.click()
    panel = page.locator(".advanced-list-tools-body").first
    expect(panel.locator(".sort-option").first).to_be_visible()
    expect(panel.locator(".column-filter").first).to_be_visible()

    text = panel.inner_text().lower()  # labels are upper-cased by CSS
    for english in ("filters", "clear", "all ", "filter ", "checkbox"):
        assert english not in text, english
    assert "filtres" in text
    assert "effacer" in text
    assert "affichage" in text
    placeholders = panel.locator("input.column-filter[type=text]").evaluate_all(
        "inputs => inputs.map(input => input.placeholder)"
    )
    options = panel.locator("select.column-filter option[value='']").all_inner_texts()
    assert placeholders or options
    assert set(placeholders) <= {"Filtrer…"}
    assert set(options) <= {"Tous"}


@pytest.mark.frontend
@pytest.mark.e2e
def test_global_search_keeps_the_keys_typed_right_after_opening(
    page: Page, live_server, seed_data_e2e
):
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")

    # No pause: the keys are typed while the modal is still fading in
    page.keyboard.press("Control+k")
    page.keyboard.type("nov")

    search_input = page.locator("#globalSearchInput")
    expect(search_input).to_be_focused()
    expect(search_input).to_have_value("nov")
    expect(page.locator("#searchModal")).to_contain_text("Novel")


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 1401, 1679, 1920])
def test_small_grids_do_not_scroll_sideways(page: Page, live_server, seed_data_e2e, width):
    page.set_viewport_size({"width": width, "height": 900})
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:relation_statuses')}")
    page.wait_for_selector(".gridjs-wrapper .gridjs-tr")
    overflow = page.locator(".gridjs-wrapper").first.evaluate(
        "wrapper => wrapper.scrollWidth - wrapper.clientWidth"
    )
    assert overflow <= 0
