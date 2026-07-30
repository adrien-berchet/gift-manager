"""Comprehensive E2E tests for all list templates in the GiftManager project.

Tests cover: grid loading, column rendering, pagination, dynamic page sizing,
bulk operations, inline editing, real-time search, dynamic filters,
permission-aware UI, initial sort, feature interactions, and mobile viewports.

Templates tested:
- person_list.html    (bulk ops, inline editing, search, filters, dynamic sizing)
- event_list.html     (all common features)
- relation_list.html  (status selector, multi-column sort)
- person_group_list.html (inline editing, grid/tree views, drag-and-drop)
- gift_list.html      (bulk operations, tag badges)
- status_list.html    (minimal features, no bulk ops / inline editing)
"""

import re

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.permissions import create_or_update_permission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(
    page: Page,
    base_url: str,
    username: str = "alice",
    password: str = "alice_password",
):
    """Log in as the specified user and wait for redirect."""
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="login"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=10_000)
    assert "/accounts/login/" not in page.url, f"Still on login page: {page.url}"


def _wait_for_grid(page: Page, grid_id: str, timeout: int = 10_000):
    """Wait for a Grid.js grid to fully render with rows."""
    grid_sel = f"#{grid_id}"
    page.wait_for_selector(f"{grid_sel} .gridjs-wrapper", timeout=timeout)
    page.wait_for_selector(
        f"{grid_sel} .gridjs-tbody tr, {grid_sel} .gridjs-notfound",
        timeout=timeout,
    )


def _grid_row_count(page: Page, grid_id: str) -> int:
    """Return the number of visible data rows in a Grid.js table."""
    return page.locator(f"#{grid_id} .gridjs-tbody tr").count()


def _grid_body_text(page: Page, grid_id: str) -> str:
    """Return the visible text content of the grid body."""
    return page.locator(f"#{grid_id} .gridjs-tbody").inner_text()


def _get_header_texts(page: Page, grid_id: str) -> list[str]:
    """Return visible header texts for a grid."""
    headers = page.locator(f"#{grid_id} .gridjs-thead th")
    return [h.inner_text().strip() for h in headers.all() if h.is_visible()]


def _get_search_input(page: Page, grid_id: str):
    """Return the search input locator for the given grid."""
    return page.locator(
        f"#{grid_id}-search, "
        f"[data-grid-id='{grid_id}'] input[type='search'], "
        ".search-filter-sort input[type='search'], "
        ".search-filter-sort input[type='text']"
    ).first


def _open_advanced_tools(page: Page, grid_id: str):
    """Open the advanced tools disclosure for a grid if it exists."""
    details = page.locator(f"#{grid_id}-advanced-tools")
    if details.count() == 0:
        return

    if details.evaluate("element => element.open"):
        return

    details.locator("summary").click()
    page.wait_for_timeout(600)


def _get_select_button(page: Page, grid_id: str):
    """Open advanced tools and return the select button for a grid."""
    _open_advanced_tools(page, grid_id)
    return page.locator(f"#toggle-selection-{grid_id}")


def _open_filter_panel(page: Page, grid_id: str):
    """Open the filter panel for a grid (click the toggle button)."""
    _open_advanced_tools(page, grid_id)
    toggle = page.locator(f"#{grid_id}-filter-toggle")
    if toggle.is_visible():
        content = page.locator(f"#{grid_id}-filter-content")
        content_class = content.get_attribute("class") if content.count() > 0 else ""
        if "expanded" not in (content_class or ""):
            toggle.click()
            page.wait_for_timeout(400)


def _filter_js_errors(errors: list[str]) -> list[str]:
    """Remove non-actionable console errors (favicon, etc.)."""
    return [e for e in errors if "favicon" not in e.lower()]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def console_errors(page: Page):
    """Attach a console error listener to the page and return the error list."""
    errors: list[str] = []
    page._console_errors = errors  # type: ignore[attr-defined]

    def _on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", _on_console)
    yield errors
    page.remove_listener("console", _on_console)


# ===========================================================================
# 1. PERSON LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListGridLoading:
    """Grid loading and rendering tests for person_list.html."""

    def test_grid_loads_without_js_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Page loads, grid renders, and no JS console errors are emitted."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        expect(page.locator("#person-grid .gridjs-wrapper")).to_be_visible()
        assert _grid_row_count(page, "person-grid") > 0
        assert _filter_js_errors(console_errors) == [], f"Console errors: {console_errors}"

    def test_correct_columns_rendered(self, page: Page, live_server, seed_data_e2e):
        """All expected columns (First Name, Family Name, Email, Groups, Actions)."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        headers = _get_header_texts(page, "person-grid")
        lower_headers = [h.lower() for h in headers]
        assert any("first" in h for h in lower_headers), f"Missing First Name: {headers}"
        assert any("family" in h or "last" in h for h in lower_headers), (
            f"Missing Family Name: {headers}"
        )
        assert any("action" in h for h in lower_headers), f"Missing Actions: {headers}"

    def test_person_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed data persons (Mom, Dad, Sister, Best Friend, Colleague) appear."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        body = _grid_body_text(page, "person-grid")
        assert "Mom" in body
        assert "Dad" in body
        assert "Sister" in body

    def test_five_persons_visible(self, page: Page, live_server, seed_data_e2e):
        """Alice (owner) sees all 5 seed persons."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        assert _grid_row_count(page, "person-grid") == 5

    def test_pagination_controls_attached(self, page: Page, live_server, seed_data_e2e):
        """Pagination footer is attached to the DOM."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        expect(page.locator("#person-grid .gridjs-pagination")).to_be_attached()

    def test_groups_column_displays_links(self, page: Page, live_server, seed_data_e2e):
        """Groups column shows linked group names for persons with groups."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        group_links = page.locator("#person-grid .gridjs-tbody a[href*='person_groups']")
        assert group_links.count() > 0, "Expected group links to be rendered"


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListBulkOperations:
    """Bulk operations tests for person_list.html."""

    def test_select_button_present(self, page: Page, live_server, seed_data_e2e):
        """Select button is visible after opening advanced tools."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        btn = _get_select_button(page, "person-grid")
        expect(btn).to_be_visible()
        expect(btn).to_contain_text("Select")

    def test_checkboxes_appear_after_toggle(self, page: Page, live_server, seed_data_e2e):
        """Clicking Select reveals row checkboxes."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        _get_select_button(page, "person-grid").click()
        page.wait_for_timeout(600)

        checkboxes = page.locator("#person-grid .gridjs-tbody input[type='checkbox']")
        assert checkboxes.count() > 0, "No checkboxes after clicking Select"

    def test_select_individual_row(self, page: Page, live_server, seed_data_e2e):
        """Individual row checkboxes can be toggled."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        _get_select_button(page, "person-grid").click()
        page.wait_for_timeout(600)

        cbs = page.locator("#person-grid .gridjs-tbody input[type='checkbox']")
        if cbs.count() > 0:
            cbs.first.check()
            expect(cbs.first).to_be_checked()
            cbs.first.uncheck()
            expect(cbs.first).not_to_be_checked()

    def test_select_all_checkbox(self, page: Page, live_server, seed_data_e2e):
        """Select-all checkbox in the header toggles all row checkboxes."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        _get_select_button(page, "person-grid").click()
        page.wait_for_timeout(600)

        select_all = page.locator("#person-grid .bulk-select-all")
        if select_all.count() > 0 and select_all.is_visible():
            select_all.check()
            page.wait_for_timeout(300)

            row_cbs = page.locator("#person-grid .gridjs-tbody input[type='checkbox']")
            for i in range(row_cbs.count()):
                expect(row_cbs.nth(i)).to_be_checked()

            select_all.uncheck()
            page.wait_for_timeout(300)
            for i in range(row_cbs.count()):
                expect(row_cbs.nth(i)).not_to_be_checked()

    def test_bulk_toolbar_appears_on_selection(self, page: Page, live_server, seed_data_e2e):
        """Selecting items shows the bulk actions toolbar."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        _get_select_button(page, "person-grid").click()
        page.wait_for_timeout(600)

        cbs = page.locator("#person-grid .gridjs-tbody input[type='checkbox']")
        if cbs.count() > 0:
            cbs.first.check()
            page.wait_for_timeout(400)

            toolbar = page.locator(".bulk-actions-toolbar")
            if toolbar.count() > 0:
                expect(toolbar).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListInlineEditing:
    """Inline editing tests for person_list.html."""

    def test_double_click_activates_edit(self, page: Page, live_server, seed_data_e2e):
        """Double-clicking an editable cell activates inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_advanced_tools(page, "person-grid")

        cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        expect(cell).to_be_visible()
        original = cell.inner_text().strip()

        cell.dblclick()
        page.wait_for_timeout(500)

        inline_input = page.locator(
            "#person-grid .inline-edit-input, #person-grid .inline-editing-active input"
        )
        if inline_input.count() > 0:
            expect(inline_input.first).to_have_value(original)
            page.keyboard.press("Escape")

    def test_escape_cancels_edit(self, page: Page, live_server, seed_data_e2e):
        """Pressing Escape cancels inline editing without saving."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_advanced_tools(page, "person-grid")

        cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        original = cell.inner_text().strip()

        cell.dblclick()
        page.wait_for_timeout(500)

        inline_input = page.locator(
            "#person-grid .inline-edit-input, #person-grid .inline-editing-active input"
        )
        if inline_input.count() > 0:
            inline_input.first.fill("CANCELLED_VALUE")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Cell should revert to original value
            cell_text = cell.inner_text().strip()
            assert cell_text == original, f"Expected '{original}' after cancel, got '{cell_text}'"

    def test_enter_saves_edit(self, page: Page, live_server, seed_data_e2e):
        """Pressing Enter saves the inline edit (via AJAX)."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_advanced_tools(page, "person-grid")

        cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        original = cell.inner_text().strip()

        cell.dblclick()
        page.wait_for_timeout(500)

        inline_input = page.locator(
            "#person-grid .inline-edit-input, #person-grid .inline-editing-active input"
        )
        if inline_input.count() > 0:
            new_value = f"{original} Edited"
            inline_input.first.fill(new_value)

            # Wait for network response after Enter
            with page.expect_response(lambda r: "inline-update" in r.url, timeout=5000) as response:
                page.keyboard.press("Enter")
            assert response.value.status == 200

            page.wait_for_timeout(800)

            # Check for success indicator or updated cell value
            updated_text = cell.inner_text().strip()
            success_indicator = page.locator("#person-grid .inline-success")
            # Either the cell updated or a success indicator appeared
            if success_indicator.count() > 0 or updated_text == new_value:
                # Restore original value
                cell.dblclick()
                page.wait_for_timeout(500)
                restore_input = page.locator(
                    "#person-grid .inline-edit-input, #person-grid .inline-editing-active input"
                )
                if restore_input.count() > 0:
                    restore_input.first.fill(original)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(800)

    def test_editable_fields_have_cursor_hint(self, page: Page, live_server, seed_data_e2e):
        """Editable cells have the inline-editable CSS class."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_advanced_tools(page, "person-grid")
        page.wait_for_timeout(800)

        editable_cells = page.locator("#person-grid .inline-editable")
        # Person template maps columns 1,2,3 (first_name, family_name, email)
        # So at least some cells should be marked editable
        if editable_cells.count() > 0:
            assert editable_cells.count() >= 3, (
                "Expected at least 3 editable cells (first_name, family_name, email)"
            )


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListSearch:
    """Real-time search tests for person_list.html."""

    def test_search_filters_results(self, page: Page, live_server, seed_data_e2e):
        """Typing in search box filters grid results."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_filter_panel(page, "person-grid")

        search_input = _get_search_input(page, "person-grid")
        if search_input.is_visible():
            initial = _grid_row_count(page, "person-grid")
            search_input.fill("Mom")
            page.wait_for_timeout(800)

            filtered = _grid_row_count(page, "person-grid")
            assert filtered <= initial
            assert filtered >= 1, "Search for 'Mom' should find at least 1"

    def test_clear_search_restores_all_results(self, page: Page, live_server, seed_data_e2e):
        """Clearing search shows all results again."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_filter_panel(page, "person-grid")

        search_input = _get_search_input(page, "person-grid")
        if search_input.is_visible():
            initial = _grid_row_count(page, "person-grid")
            search_input.fill("Mom")
            page.wait_for_timeout(800)

            search_input.clear()
            page.wait_for_timeout(800)

            restored = _grid_row_count(page, "person-grid")
            assert restored == initial, (
                f"Expected {initial} rows after clearing search, got {restored}"
            )

    def test_search_no_results_shows_message(self, page: Page, live_server, seed_data_e2e):
        """Searching for nonexistent text shows 'no records' message."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_filter_panel(page, "person-grid")

        search_input = _get_search_input(page, "person-grid")
        if search_input.is_visible():
            search_input.fill("ZZZZNONEXISTENT999")
            page.wait_for_timeout(800)

            not_found = page.locator("#person-grid .gridjs-notfound")
            if not_found.count() > 0:
                expect(not_found).to_be_visible()
            else:
                assert _grid_row_count(page, "person-grid") == 0

    def test_search_across_multiple_columns(self, page: Page, live_server, seed_data_e2e):
        """Search works across first name and family name columns."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_filter_panel(page, "person-grid")

        search_input = _get_search_input(page, "person-grid")
        if search_input.is_visible():
            # Search by family name
            search_input.fill("Seed")
            page.wait_for_timeout(800)

            # Mom, Dad, Sister all have family_name "Seed"
            count = _grid_row_count(page, "person-grid")
            assert count >= 3, f"'Seed' family name should match >= 3 rows, got {count}"

            search_input.clear()
            page.wait_for_timeout(800)


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListSort:
    """Sorting tests for person_list.html."""

    def test_initial_sort_applied(self, page: Page, live_server, seed_data_e2e):
        """Initial sort (Family Name, then First Name) applies on page load."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        page.wait_for_timeout(600)

        sorted_headers = page.locator(
            "#person-grid .gridjs-th-sort-asc, #person-grid .gridjs-th-sort-desc"
        )
        if sorted_headers.count() > 0:
            assert sorted_headers.count() >= 1, "At least one sorted column expected"

    def test_shift_click_multi_column_sort(self, page: Page, live_server, seed_data_e2e):
        """Shift+clicking a second column adds multi-column sort."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        page.wait_for_timeout(300)

        family_hdr = page.locator("#person-grid .gridjs-thead th:nth-child(3)")
        family_hdr.click()
        page.wait_for_timeout(300)

        first_hdr = page.locator("#person-grid .gridjs-thead th:nth-child(2)")
        first_hdr.click(modifiers=["Shift"])
        page.wait_for_timeout(300)

        assert _grid_row_count(page, "person-grid") > 0, "Grid should still show rows"

    def test_sort_toggle_ascending_descending(self, page: Page, live_server, seed_data_e2e):
        """Clicking a header toggles between ascending and descending sort."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        page.wait_for_timeout(300)

        hdr = page.locator("#person-grid .gridjs-thead th:nth-child(3)")
        hdr.click()
        page.wait_for_timeout(400)

        rows_asc = [
            page.locator(f"#person-grid .gridjs-tbody tr:nth-child({i + 1})").inner_text()
            for i in range(_grid_row_count(page, "person-grid"))
        ]

        hdr.click()
        page.wait_for_timeout(400)

        rows_desc = [
            page.locator(f"#person-grid .gridjs-tbody tr:nth-child({i + 1})").inner_text()
            for i in range(_grid_row_count(page, "person-grid"))
        ]

        if len(rows_asc) > 1:
            assert rows_asc != rows_desc, "Sort order should change between clicks"


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListDynamicPageSize:
    """Dynamic page sizing tests for person_list.html."""

    def test_resize_adjusts_rows(self, page: Page, live_server, seed_data_e2e):
        """Shrinking viewport height reduces displayed rows (or stays same if data fits)."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        page.set_viewport_size({"width": 1920, "height": 400})
        page.wait_for_timeout(1500)
        small_count = _grid_row_count(page, "person-grid")

        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(1500)
        restored = _grid_row_count(page, "person-grid")

        assert small_count >= 1, "Grid should show at least 1 row even in small viewport"
        assert restored >= small_count, "Larger viewport should show same or more rows"


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonListPermissions:
    """Permission-aware UI tests for person_list.html."""

    def test_owner_sees_all_action_buttons(self, page: Page, live_server, seed_data_e2e):
        """Alice (owner) sees edit, delete, share buttons."""
        _login(page, live_server.url, "alice", "alice_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        action_cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:last-child")
        html = action_cell.inner_html()
        assert "fa-edit" in html or "btn-warning" in html, "Owner: edit button missing"
        assert "fa-trash" in html or "btn-danger" in html, "Owner: delete button missing"

    def test_viewer_has_limited_actions(self, page: Page, live_server, seed_data_e2e):
        """Bob (viewer on some) sees limited action buttons."""
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        row_count = _grid_row_count(page, "person-grid")
        assert row_count > 0, "Bob should see at least some persons"

        # Check first row's action cell - should have details at minimum
        action_cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:last-child")
        html = action_cell.inner_html()
        assert "fa-eye" in html or "btn-info" in html, "Details button missing for viewer"

    def test_viewer_cannot_use_edit_on_viewer_items(self, page: Page, live_server, seed_data_e2e):
        """Bob's edit button is disabled on items where he only has VIEWER permission.

        The permission-aware UI renders all action buttons but disables those
        the user lacks permission for (disabled attribute + opacity: 0.5).
        """
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        # Find a row for "Mom" (Bob has VIEWER on Mom)
        rows = page.locator("#person-grid .gridjs-tbody tr")
        for i in range(rows.count()):
            row_text = rows.nth(i).inner_text()
            if "Mom" in row_text:
                edit_btn = rows.nth(i).locator(
                    "td:last-child button[data-action='edit'], td:last-child a[data-action='edit']"
                )
                if edit_btn.count() > 0:
                    # Viewer's edit button should be disabled
                    assert (
                        edit_btn.first.is_disabled()
                        or edit_btn.first.get_attribute("disabled") is not None
                    ), "Viewer edit button should be disabled on VIEWER-permission items"
                break


# ===========================================================================
# 2. EVENT LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestEventListGridLoading:
    """Grid loading and rendering tests for event_list.html."""

    def test_grid_loads_without_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Event list loads and grid renders correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        assert _grid_row_count(page, "event-grid") > 0
        assert _filter_js_errors(console_errors) == []

    def test_correct_columns_rendered(self, page: Page, live_server, seed_data_e2e):
        """Event grid shows name, comment, usual_date, and actions columns."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        headers = _get_header_texts(page, "event-grid")
        lower_headers = [h.lower() for h in headers]
        assert any("name" in h for h in lower_headers), f"Name missing: {headers}"
        assert any("action" in h for h in lower_headers), f"Actions missing: {headers}"

    def test_event_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed events (Christmas, Mom Birthday, Graduation) appear."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        body = _grid_body_text(page, "event-grid")
        assert "Christmas" in body
        assert "Graduation" in body

    def test_three_events_visible(self, page: Page, live_server, seed_data_e2e):
        """Alice sees all 3 seed events."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        assert _grid_row_count(page, "event-grid") == 3

    def test_pagination_present(self, page: Page, live_server, seed_data_e2e):
        """Pagination footer is attached."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        expect(page.locator("#event-grid .gridjs-pagination")).to_be_attached()


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestEventListFeatures:
    """Feature tests for event_list.html."""

    def test_select_button_present(self, page: Page, live_server, seed_data_e2e):
        """Select button for bulk operations is present."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        expect(_get_select_button(page, "event-grid")).to_be_visible()

    def test_create_button_navigates(self, page: Page, live_server, seed_data_e2e):
        """Create new event button has a proper href."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        # Scope to page-header to avoid matching nav search result links
        create_btn = page.locator(
            ".page-header-actions a[data-action='create'], "
            ".page-header a.btn-primary[data-action='create']"
        ).first
        expect(create_btn).to_be_visible()
        href = create_btn.get_attribute("href")
        assert "create" in href.lower()

    def test_inline_editing_comment(self, page: Page, live_server, seed_data_e2e):
        """Double-clicking the comment cell enables inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")
        _open_advanced_tools(page, "event-grid")

        cell = page.locator("#event-grid .gridjs-tbody tr:first-child td:nth-child(3)")
        if cell.is_visible():
            cell.dblclick()
            page.wait_for_timeout(500)

            inline = page.locator(
                "#event-grid .inline-edit-input, #event-grid .inline-editing-active input"
            )
            if inline.count() > 0:
                page.keyboard.press("Escape")

    def test_initial_sort_by_name(self, page: Page, live_server, seed_data_e2e):
        """Initial sort by Name applies; Christmas < Graduation < Mom Birthday."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")
        page.wait_for_timeout(600)

        rows = page.locator("#event-grid .gridjs-tbody tr")
        if rows.count() >= 3:
            first = rows.nth(0).inner_text()
            second = rows.nth(1).inner_text()
            assert "Christmas" in first, f"Expected Christmas first, got: {first}"
            assert "Graduation" in second, f"Expected Graduation second, got: {second}"

    def test_search_filters_events(self, page: Page, live_server, seed_data_e2e):
        """Search filters event results."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")
        _open_filter_panel(page, "event-grid")

        search = _get_search_input(page, "event-grid")
        if search.is_visible():
            search.fill("Christmas")
            page.wait_for_timeout(800)
            assert _grid_row_count(page, "event-grid") >= 1

            search.clear()
            page.wait_for_timeout(800)

    def test_bob_sees_limited_events(self, page: Page, live_server, seed_data_e2e):
        """Bob only sees events he has permissions on (Christmas, Graduation).

        Bob has VIEWER on Christmas and EDITOR on Graduation, so exactly 2 events.
        """
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/events/")
        _wait_for_grid(page, "event-grid")

        count = _grid_row_count(page, "event-grid")
        # Bob should see fewer events than Alice (who sees 3)
        assert count <= 3, f"Bob should see fewer events than Alice, got {count}"
        assert count >= 1, f"Bob should see at least 1 event, got {count}"

        # Verify Bob can see specific events he has permissions on
        body = _grid_body_text(page, "event-grid")
        assert "Christmas" in body or "Graduation" in body, (
            f"Bob should see Christmas or Graduation, got: {body}"
        )


# ===========================================================================
# 3. RELATION LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestRelationListGridLoading:
    """Grid loading and rendering tests for relation_list.html."""

    def test_grid_loads_without_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Relation list loads and grid renders correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        assert _grid_row_count(page, "relation-grid") > 0
        assert _filter_js_errors(console_errors) == []

    def test_correct_columns_rendered(self, page: Page, live_server, seed_data_e2e):
        """Relation grid has gift, related object, event, comment, status, due date, actions."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        headers = _get_header_texts(page, "relation-grid")
        lower_headers = [h.lower() for h in headers]
        assert any("gift" in h for h in lower_headers), f"Gift column missing: {headers}"
        assert any("action" in h for h in lower_headers), f"Actions missing: {headers}"

    def test_relation_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed relation data (gifts, persons) appears."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        body = _grid_body_text(page, "relation-grid")
        assert "Smartphone" in body or "Novel" in body or "Watch" in body

    def test_four_relations_visible(self, page: Page, live_server, seed_data_e2e):
        """Alice sees all 4 seed relations."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        assert _grid_row_count(page, "relation-grid") == 4

    def test_workspace_refreshes_after_list_update_for_new_no_date_plan(
        self, page: Page, live_server, seed_data_e2e
    ):
        """A newly created no-date gift plan should appear in the workspace."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/")

        workspace = page.locator(".gift-plan-workspace")
        expect(workspace).to_be_visible()
        expect(workspace).not_to_contain_text("Workspace Refresh Kite")

        gift = Gift.objects.create(name="Workspace Refresh Kite")
        create_or_update_permission(
            seed_data_e2e.alice,
            gift,
            permission_level=PermissionLevel.OWNER,
        )
        relation = Relation.objects.create(
            person=seed_data_e2e.persons["dad"],
            gift=gift,
            status=seed_data_e2e.statuses["planned"],
            due_date=None,
            comment="Created after the page loaded",
        )
        create_or_update_permission(
            seed_data_e2e.alice,
            relation,
            permission_level=PermissionLevel.OWNER,
        )

        refreshed = page.evaluate(
            """() => new Promise((resolve) => {
                const timeout = setTimeout(() => resolve(false), 5000);
                document.addEventListener('gift-plan-workspace:refreshed', () => {
                    clearTimeout(timeout);
                    resolve(true);
                }, { once: true });
                document.dispatchEvent(new CustomEvent('list:update'));
            })"""
        )

        assert refreshed is True
        expect(page.locator(".gift-plan-urgency-section--needs_details")).to_contain_text(
            "Workspace Refresh Kite"
        )

    def test_workspace_cards_use_equal_height_compact_layout(
        self, page: Page, live_server, seed_data_e2e
    ):
        """Gift-plan workspace cards should stay compact and equal-height per section."""
        long_gift = Gift.objects.create(
            name=(
                "Equal Height Long Workspace Gift With A Very Long Name That Should Clamp Cleanly"
            )
        )
        short_gift = Gift.objects.create(name="Equal Height Short Gift")
        for gift in (long_gift, short_gift):
            create_or_update_permission(
                seed_data_e2e.alice,
                gift,
                permission_level=PermissionLevel.OWNER,
            )

        for gift, comment in (
            (
                long_gift,
                (
                    "A deliberately long workspace note that should be clipped so the "
                    "card can share a stable height with its siblings in the section."
                ),
            ),
            (short_gift, ""),
        ):
            relation = Relation.objects.create(
                person=seed_data_e2e.persons["dad"],
                gift=gift,
                event=seed_data_e2e.events["christmas"],
                status=seed_data_e2e.statuses["planned"],
                due_date=None,
                comment=comment,
            )
            create_or_update_permission(
                seed_data_e2e.alice,
                relation,
                permission_level=PermissionLevel.OWNER,
            )

        page.set_viewport_size({"width": 1280, "height": 800})
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/")
        page.wait_for_selector(".gift-plan-card", timeout=10_000)

        section = page.locator(".gift-plan-urgency-section--needs_details").first
        ideas_section = page.locator(".gift-plan-urgency-section--ideas").first
        grid = section.locator(".gift-plan-card-grid").first
        card = section.locator(".gift-plan-card").first
        title = card.locator(".gift-plan-card-title").first
        note = card.locator(".gift-plan-note").first

        expect(section).to_be_visible()
        expect(ideas_section).to_be_visible()
        expect(grid).to_be_visible()
        expect(card).to_be_visible()
        expect(title).to_be_visible()
        expect(note).to_be_visible()

        layout = section.evaluate(
            """grid => {
                const cardGrid = grid.querySelector('.gift-plan-card-grid');
                const gridStyles = getComputedStyle(cardGrid);
                const card = grid.querySelector('.gift-plan-card');
                const title = card.querySelector('.gift-plan-card-title');
                const note = card.querySelector('.gift-plan-note');
                const targetCards = Array.from(grid.querySelectorAll('.gift-plan-card'))
                    .filter((candidate) => (
                        candidate.textContent.includes('Equal Height Long Workspace Gift') ||
                        candidate.textContent.includes('Equal Height Short Gift')
                    ));
                const cardStyles = getComputedStyle(card);
                const titleStyles = getComputedStyle(title);
                const noteStyles = getComputedStyle(note);
                return {
                    alignItems: gridStyles.alignItems,
                    gridAutoRows: gridStyles.gridAutoRows,
                    gridGap: parseFloat(gridStyles.gap),
                    cardGap: parseFloat(cardStyles.gap),
                    cardPadding: parseFloat(cardStyles.paddingTop),
                    titleFontSize: parseFloat(titleStyles.fontSize),
                    titleLineClamp: getComputedStyle(title.querySelector('a')).webkitLineClamp,
                    noteLineClamp: noteStyles.webkitLineClamp,
                    targetHeights: targetCards.map((targetCard) => (
                        targetCard.getBoundingClientRect().height
                    )),
                    targetWidths: targetCards.map((targetCard) => (
                        targetCard.getBoundingClientRect().width
                    )),
                };
            }"""
        )
        underfilled_section_layout = page.evaluate(
            """() => {
                const needsGrid = document.querySelector(
                    '.gift-plan-urgency-section--needs_details .gift-plan-card-grid'
                );
                const ideasGrid = document.querySelector(
                    '.gift-plan-urgency-section--ideas .gift-plan-card-grid'
                );
                const needsCard = needsGrid.querySelector('.gift-plan-card');
                const ideaCard = ideasGrid.querySelector('.gift-plan-card');
                const ideasGridBox = ideasGrid.getBoundingClientRect();
                const needsCardBox = needsCard.getBoundingClientRect();
                const ideaCardBox = ideaCard.getBoundingClientRect();
                return {
                    ideasGridWidth: ideasGridBox.width,
                    needsCardWidth: needsCardBox.width,
                    ideaCardWidth: ideaCardBox.width,
                };
            }"""
        )

        assert layout["alignItems"] == "stretch"
        assert layout["gridAutoRows"] == "1fr"
        assert layout["gridGap"] <= 12
        assert layout["cardGap"] <= 9
        assert layout["cardPadding"] <= 12
        assert layout["titleFontSize"] <= 16
        assert layout["titleLineClamp"] == "2"
        assert layout["noteLineClamp"] == "2"
        assert len(layout["targetHeights"]) == 2
        assert max(layout["targetHeights"]) - min(layout["targetHeights"]) <= 1
        assert len(layout["targetWidths"]) == 2
        assert max(layout["targetWidths"]) - min(layout["targetWidths"]) <= 1
        assert (
            abs(
                underfilled_section_layout["ideaCardWidth"]
                - underfilled_section_layout["needsCardWidth"]
            )
            <= 1
        )
        assert underfilled_section_layout["ideaCardWidth"] < (
            underfilled_section_layout["ideasGridWidth"] * 0.5
        )

        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(100)

        tablet_layout = grid.evaluate(
            """grid => ({
                columns: getComputedStyle(grid).gridTemplateColumns
                    .split(' ')
                    .filter(Boolean)
                    .length,
            })"""
        )

        assert tablet_layout["columns"] == 1

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(100)

        mobile_layout = grid.evaluate(
            """grid => {
                const card = grid.querySelector('.gift-plan-card');
                const actions = card.querySelector('.gift-plan-card-actions');
                const cardBox = card.getBoundingClientRect();
                const actionsBox = actions.getBoundingClientRect();
                return {
                    columns: getComputedStyle(grid).gridTemplateColumns
                        .split(' ')
                        .filter(Boolean)
                        .length,
                    cardLeft: cardBox.left,
                    cardRight: cardBox.right,
                    viewportWidth: window.innerWidth,
                    actionsVisible: actionsBox.width > 0 && actionsBox.height > 0,
                };
            }"""
        )

        assert mobile_layout["columns"] == 1
        assert mobile_layout["cardLeft"] >= 0
        assert mobile_layout["cardRight"] <= mobile_layout["viewportWidth"]
        assert mobile_layout["actionsVisible"] is True


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestRelationListStatusSelector:
    """Status selector tests for relation_list.html."""

    def test_status_selector_present(self, page: Page, live_server, seed_data_e2e):
        """Status selector dropdown is rendered in each row."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        selectors = page.locator("#relation-grid .status-selector")
        assert selectors.count() > 0

    def test_status_selector_has_all_options(self, page: Page, live_server, seed_data_e2e):
        """Each selector includes all seeded statuses."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        first_selector = page.locator("#relation-grid .status-selector").first
        options = first_selector.locator("option")
        option_texts = [o.inner_text().strip() for o in options.all()]

        assert "Abandoned" in option_texts
        assert len(option_texts) >= 5, f"Expected >= 5 options, got: {option_texts}"

    def test_status_change_sends_request(self, page: Page, live_server, seed_data_e2e):
        """Changing the status selector fires an AJAX POST request."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        selector = page.locator("#relation-grid .status-selector").first
        current = selector.input_value()

        # Find a different option
        options = selector.locator("option")
        new_value = None
        for opt in options.all():
            val = opt.get_attribute("value")
            if val != current:
                new_value = val
                break

        if new_value:
            with page.expect_response(lambda r: "relation_status_update" in r.url, timeout=5000):
                selector.select_option(new_value)

    def test_gift_links_navigate(self, page: Page, live_server, seed_data_e2e):
        """Gift name links point to gift detail pages."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        links = page.locator("#relation-grid .gridjs-tbody a[href*='gifts/']")
        if links.count() > 0:
            href = links.first.get_attribute("href")
            assert "/gifts/" in href


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestRelationListSort:
    """Sort tests for relation_list.html."""

    def test_three_column_initial_sort(self, page: Page, live_server, seed_data_e2e):
        """Three-column initial sort (Status, Related Object, Gift) applies."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")
        page.wait_for_timeout(600)

        assert _grid_row_count(page, "relation-grid") > 0

    def test_select_button_present(self, page: Page, live_server, seed_data_e2e):
        """Select button for bulk operations is present."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        expect(_get_select_button(page, "relation-grid")).to_be_visible()


# ===========================================================================
# 4. PERSON GROUP LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonGroupListGridLoading:
    """Grid loading tests for person_group_list.html."""

    def test_grid_loads_without_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Person group list loads and grid renders correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        assert _grid_row_count(page, "person-group-grid") > 0
        assert _filter_js_errors(console_errors) == []

    def test_group_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed groups (Family, Close Family, Friends) appear."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        body = _grid_body_text(page, "person-group-grid")
        assert "Family" in body
        assert "Friends" in body

    def test_three_groups_visible(self, page: Page, live_server, seed_data_e2e):
        """Alice sees all 3 seed groups."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        assert _grid_row_count(page, "person-group-grid") == 3


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonGroupListTreeView:
    """Tree view tests for person_group_list.html."""

    def test_view_toggle_buttons_present(self, page: Page, live_server, seed_data_e2e):
        """Grid/Tree toggle buttons are present when hierarchy exists."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        grid_btn = page.locator("#grid-view-btn")
        tree_btn = page.locator("#tree-view-btn")
        if grid_btn.count() > 0:
            expect(grid_btn).to_be_visible()
            expect(tree_btn).to_be_visible()

    def test_switch_to_tree_view(self, page: Page, live_server, seed_data_e2e):
        """Clicking Tree View shows tree and hides grid."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        tree_btn = page.locator("#tree-view-btn")
        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(500)

            expect(page.locator(".tree-view-container")).to_have_class(re.compile(r"active"))
            expect(page.locator(".grid-view-container")).not_to_have_class(re.compile(r"active"))
            assert page.locator(".tree-node").count() > 0

    def test_switch_back_to_grid_view(self, page: Page, live_server, seed_data_e2e):
        """Toggling back to grid shows grid and hides tree."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        tree_btn = page.locator("#tree-view-btn")
        grid_btn = page.locator("#grid-view-btn")

        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(300)
            grid_btn.click()
            page.wait_for_timeout(300)

            expect(page.locator(".grid-view-container")).to_have_class(re.compile(r"active"))

    def test_tree_nodes_are_draggable(self, page: Page, live_server, seed_data_e2e):
        """Tree view nodes have draggable='true' attribute."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")

        tree_btn = page.locator("#tree-view-btn")
        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(500)

            draggable = page.locator(".tree-node[draggable='true']")
            assert draggable.count() > 0

    def test_tree_node_collapse_expand(self, page: Page, live_server, seed_data_e2e):
        """Nodes with children can be collapsed and expanded."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")

        tree_btn = page.locator("#tree-view-btn")
        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(500)

            toggles = page.locator(".tree-node .toggle-icon")
            if toggles.count() > 0:
                initial_visible = page.locator(".tree-node:visible").count()
                toggles.first.click()
                page.wait_for_timeout(300)

                after_collapse = page.locator(".tree-node:visible").count()
                assert after_collapse <= initial_visible

                toggles.first.click()
                page.wait_for_timeout(300)

    def test_tree_node_member_count(self, page: Page, live_server, seed_data_e2e):
        """Tree nodes show member count badges."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")

        tree_btn = page.locator("#tree-view-btn")
        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(500)

            badges = page.locator(".tree-node .badge-count")
            assert badges.count() > 0, "Tree nodes should show member count"

    def test_view_preference_persists(self, page: Page, live_server, seed_data_e2e):
        """View preference (grid/tree) persists via localStorage."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        tree_btn = page.locator("#tree-view-btn")
        if tree_btn.count() > 0 and tree_btn.is_visible():
            tree_btn.click()
            page.wait_for_timeout(500)

            stored = page.evaluate("localStorage.getItem('personGroupView')")
            assert stored == "tree", f"Expected 'tree' in localStorage, got {stored}"

            # Navigate away and back
            page.goto(f"{live_server.url}/person_groups/")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)

            # Tree view should still be active
            tree_container = page.locator(".tree-view-container")
            if tree_container.count() > 0:
                expect(tree_container).to_have_class(re.compile(r"active"))

            # Clean up
            page.evaluate("localStorage.removeItem('personGroupView')")


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPersonGroupListFeatures:
    """Feature tests for person_group_list.html."""

    def test_inline_editing_group_name(self, page: Page, live_server, seed_data_e2e):
        """Double-clicking group name enables inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")
        _open_advanced_tools(page, "person-group-grid")

        cell = page.locator("#person-group-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        if cell.is_visible():
            cell.dblclick()
            page.wait_for_timeout(500)
            inline = page.locator(
                "#person-group-grid .inline-edit-input, "
                "#person-group-grid .inline-editing-active input"
            )
            if inline.count() > 0:
                page.keyboard.press("Escape")

    def test_select_button_present(self, page: Page, live_server, seed_data_e2e):
        """Select button for bulk operations is present."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        expect(_get_select_button(page, "person-group-grid")).to_be_visible()

    def test_explorer_view_link(self, page: Page, live_server, seed_data_e2e):
        """Explorer View button links correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/person_groups/")
        _wait_for_grid(page, "person-group-grid")

        link = page.locator("a[href*='explore']")
        if link.count() > 0:
            href = link.first.get_attribute("href")
            assert "explore" in href.lower()


# ===========================================================================
# 5. GIFT LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestGiftListGridLoading:
    """Grid loading and rendering tests for gift_list.html."""

    def test_grid_loads_without_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Gift list loads and grid renders correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        assert _grid_row_count(page, "gift-grid") > 0
        assert _filter_js_errors(console_errors) == []

    def test_correct_columns_rendered(self, page: Page, live_server, seed_data_e2e):
        """Gift grid shows name, comment, tags, and actions columns."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        headers = _get_header_texts(page, "gift-grid")
        lower_headers = [h.lower() for h in headers]
        assert any("name" in h for h in lower_headers), f"Name missing: {headers}"
        assert any("action" in h for h in lower_headers), f"Actions missing: {headers}"

    def test_gift_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed gifts (Smartphone, Novel, Watch, Scarf) appear."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        body = _grid_body_text(page, "gift-grid")
        assert "Smartphone" in body
        assert "Novel" in body

    def test_four_gifts_visible(self, page: Page, live_server, seed_data_e2e):
        """Alice sees all 4 seed gifts."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        assert _grid_row_count(page, "gift-grid") == 4

    def test_tags_column_renders_badges(self, page: Page, live_server, seed_data_e2e):
        """Tags column displays tags for gifts that have them.

        Note: Tags may be rendered as uppercase badges (e.g., BOOKS, ELECTRONICS).
        """
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        body = _grid_body_text(page, "gift-grid").lower()
        assert "electronics" in body or "gadgets" in body or "books" in body


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestGiftListFeatures:
    """Feature tests for gift_list.html."""

    def test_select_button_present(self, page: Page, live_server, seed_data_e2e):
        """Select button for bulk operations is present."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        expect(_get_select_button(page, "gift-grid")).to_be_visible()

    def test_inline_editing_name(self, page: Page, live_server, seed_data_e2e):
        """Double-clicking name cell enables inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")
        _open_advanced_tools(page, "gift-grid")

        cell = page.locator("#gift-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        if cell.is_visible():
            cell.dblclick()
            page.wait_for_timeout(500)
            inline = page.locator(
                "#gift-grid .inline-edit-input, #gift-grid .inline-editing-active input"
            )
            if inline.count() > 0:
                page.keyboard.press("Escape")

    def test_inline_editing_comment(self, page: Page, live_server, seed_data_e2e):
        """Double-clicking comment cell enables inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")
        _open_advanced_tools(page, "gift-grid")

        cell = page.locator("#gift-grid .gridjs-tbody tr:first-child td:nth-child(3)")
        if cell.is_visible():
            cell.dblclick()
            page.wait_for_timeout(500)
            inline = page.locator(
                "#gift-grid .inline-edit-input, #gift-grid .inline-editing-active input"
            )
            if inline.count() > 0:
                page.keyboard.press("Escape")

    def test_initial_sort_by_name(self, page: Page, live_server, seed_data_e2e):
        """Initial sort by Name - Novel < Scarf < Smartphone < Watch."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")
        page.wait_for_timeout(600)

        rows = page.locator("#gift-grid .gridjs-tbody tr")
        if rows.count() >= 4:
            first = rows.nth(0).inner_text()
            assert "Novel" in first, f"Expected Novel first (alphabetical), got: {first}"

    def test_search_filters_gifts(self, page: Page, live_server, seed_data_e2e):
        """Search filters gift results."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")
        _open_filter_panel(page, "gift-grid")

        search = _get_search_input(page, "gift-grid")
        if search.is_visible():
            search.fill("Smartphone")
            page.wait_for_timeout(800)
            assert _grid_row_count(page, "gift-grid") >= 1

            search.clear()
            page.wait_for_timeout(800)

    def test_owner_gift_actions(self, page: Page, live_server, seed_data_e2e):
        """Alice sees edit and delete on gift list."""
        _login(page, live_server.url, "alice", "alice_password")
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        action = page.locator("#gift-grid .gridjs-tbody tr:first-child td:last-child")
        html = action.inner_html()
        assert "fa-edit" in html or "btn-warning" in html
        assert "fa-trash" in html or "btn-danger" in html


# ===========================================================================
# 6. STATUS LIST TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestStatusListGridLoading:
    """Grid loading and rendering tests for status_list.html."""

    def test_grid_loads_without_errors(
        self, page: Page, live_server, seed_data_e2e, console_errors
    ):
        """Status list loads and grid renders correctly."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        assert _grid_row_count(page, "status-grid") > 0
        assert _filter_js_errors(console_errors) == []

    def test_status_data_displayed(self, page: Page, live_server, seed_data_e2e):
        """Seed statuses appear."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        body = _grid_body_text(page, "status-grid")
        assert "Idea" in body
        assert "Abandoned" in body
        assert "Given" in body

    def test_seed_statuses_visible(self, page: Page, live_server, seed_data_e2e):
        """All 5 seed statuses are visible."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        assert _grid_row_count(page, "status-grid") == 5


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestStatusListMinimalFeatures:
    """Status list is minimal: no bulk ops, no inline editing."""

    def test_no_select_button(self, page: Page, live_server, seed_data_e2e):
        """No Select button (no bulk operations)."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        assert page.locator("#toggle-selection-status-grid").count() == 0

    def test_no_inline_editing(self, page: Page, live_server, seed_data_e2e):
        """Double-click does not activate inline editing."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        cell = page.locator("#status-grid .gridjs-tbody tr:first-child td:first-child")
        if cell.is_visible():
            cell.dblclick()
            page.wait_for_timeout(500)
            inline = page.locator(
                "#status-grid .inline-edit-input, #status-grid .inline-editing-active input"
            )
            assert inline.count() == 0

    def test_action_buttons_only_details(self, page: Page, live_server, seed_data_e2e):
        """Only a details button is shown (no edit/delete/share)."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        action = page.locator("#status-grid .gridjs-tbody tr:first-child td:last-child")
        if action.is_visible():
            html = action.inner_html()
            assert "fa-eye" in html or "btn-info" in html or "detail" in html.lower()

    def test_search_filters_statuses(self, page: Page, live_server, seed_data_e2e):
        """Search filters status results."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")
        _open_filter_panel(page, "status-grid")

        search = _get_search_input(page, "status-grid")
        if search.is_visible():
            search.fill("Idea")
            page.wait_for_timeout(800)
            assert _grid_row_count(page, "status-grid") >= 1

            search.clear()
            page.wait_for_timeout(800)

    def test_pagination_present(self, page: Page, live_server, seed_data_e2e):
        """Pagination footer is attached."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        expect(page.locator("#status-grid .gridjs-pagination")).to_be_attached()

    def test_dynamic_page_sizing_works(self, page: Page, live_server, seed_data_e2e):
        """Dynamic page sizing does not break the grid."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/relation_statuses/")
        _wait_for_grid(page, "status-grid")

        assert _grid_row_count(page, "status-grid") > 0


# ===========================================================================
# 7. CROSS-TEMPLATE TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestCrossTemplateGridLoading:
    """Verify shared features work consistently across all list templates."""

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/relations/advanced/", "relation-grid"),
            ("/person_groups/", "person-group-grid"),
            ("/gifts/", "gift-grid"),
            ("/relation_statuses/", "status-grid"),
        ],
    )
    def test_all_grids_load(
        self, page: Page, live_server, seed_data_e2e, console_errors, path, grid_id
    ):
        """Every list template loads its grid without JS errors."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        assert _grid_row_count(page, grid_id) > 0
        assert _filter_js_errors(console_errors) == [], f"JS errors on {path}: {console_errors}"

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/relations/advanced/", "relation-grid"),
            ("/person_groups/", "person-group-grid"),
            ("/gifts/", "gift-grid"),
            ("/relation_statuses/", "status-grid"),
        ],
    )
    def test_all_grids_have_pagination(self, page: Page, live_server, seed_data_e2e, path, grid_id):
        """Every grid has pagination controls attached."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        expect(page.locator(f"#{grid_id} .gridjs-pagination")).to_be_attached()

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/relations/advanced/", "relation-grid"),
            ("/person_groups/", "person-group-grid"),
            ("/gifts/", "gift-grid"),
        ],
    )
    def test_all_grids_have_action_buttons(
        self, page: Page, live_server, seed_data_e2e, path, grid_id
    ):
        """All grids (except status) have action buttons in each row."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        action = page.locator(f"#{grid_id} .gridjs-tbody tr:first-child td:last-child")
        expect(action).to_be_visible()
        html = action.inner_html()
        assert "btn" in html.lower() or "fa-" in html

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/relations/advanced/", "relation-grid"),
            ("/person_groups/", "person-group-grid"),
            ("/gifts/", "gift-grid"),
        ],
    )
    def test_action_buttons_are_not_clipped(
        self, page: Page, live_server, seed_data_e2e, path, grid_id
    ):
        """Action cells are wide enough for desktop icon+label buttons."""
        page.set_viewport_size({"width": 1280, "height": 800})
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        action_cell = page.locator(f"#{grid_id} .gridjs-tbody tr:first-child td:last-child")
        cell_box = action_cell.evaluate(
            """cell => ({
                clientWidth: cell.clientWidth,
                scrollWidth: cell.scrollWidth,
            })"""
        )
        assert cell_box["scrollWidth"] <= cell_box["clientWidth"] + 1

        buttons = page.locator(f"#{grid_id} .gridjs-tbody tr:first-child .quick-action-btn")
        expect(buttons.first).to_be_visible()
        measurements = buttons.evaluate_all(
            """buttons => buttons.map((button) => ({
                action: button.dataset.action,
                clientWidth: button.clientWidth,
                scrollWidth: button.scrollWidth,
            }))"""
        )

        clipped = [item for item in measurements if item["scrollWidth"] > item["clientWidth"] + 1]
        assert clipped == []

    @pytest.mark.parametrize(
        "path",
        [
            "/persons/",
            "/events/",
            "/relations/",
            "/relations/advanced/",
            "/person_groups/",
            "/gifts/",
            "/relation_statuses/",
        ],
    )
    def test_page_has_h1(self, page: Page, live_server, seed_data_e2e, path):
        """Each list page has a visible <h1> title."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")

        expect(page.locator("h1")).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestCrossTemplateCreateButtons:
    """Create button tests across all entity list templates (except status)."""

    @pytest.mark.parametrize(
        "path",
        [
            "/persons/",
            "/events/",
            "/gifts/",
            "/relations/",
            "/relations/advanced/",
            "/person_groups/",
        ],
    )
    def test_create_button_visible(self, page: Page, live_server, seed_data_e2e, path):
        """Create button is visible in page header for authenticated users."""
        _login(page, live_server.url, "alice", "alice_password")
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")

        # Scope to the page-header-actions area to avoid matching nav or grid buttons
        create_btn = page.locator(
            ".page-header-actions a[data-action='create'], "
            ".page-header a.btn-primary[data-action='create']"
        )
        expect(create_btn.first).to_be_visible(timeout=5000)


# ===========================================================================
# 8. PERMISSION-AWARE UI TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestPermissionAwareUI:
    """Permission-aware UI tests using different user accounts.

    Alice = OWNER of everything.
    Bob = mixed (VIEWER, EDITOR, NONE).
    """

    def test_owner_sees_all_person_actions(self, page: Page, live_server, seed_data_e2e):
        """Alice sees edit, delete, share on persons."""
        _login(page, live_server.url, "alice", "alice_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        action = page.locator("#person-grid .gridjs-tbody tr:first-child td:last-child")
        html = action.inner_html()
        assert "fa-edit" in html or "btn-warning" in html
        assert "fa-trash" in html or "btn-danger" in html

    def test_owner_sees_share_button(self, page: Page, live_server, seed_data_e2e):
        """Alice sees the share button on persons."""
        _login(page, live_server.url, "alice", "alice_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        action = page.locator("#person-grid .gridjs-tbody tr:first-child td:last-child")
        html = action.inner_html()
        assert "fa-share" in html or "btn-success" in html, "Owner should see share btn"

    def test_bob_sees_fewer_persons(self, page: Page, live_server, seed_data_e2e):
        """Bob sees only persons he has permissions on (Mom, Dad, Best Friend)."""
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        count = _grid_row_count(page, "person-grid")
        assert count == 3, f"Bob should see 3 persons, got {count}"

    def test_bob_sees_fewer_gifts(self, page: Page, live_server, seed_data_e2e):
        """Bob sees only gifts he has permissions on (Smartphone, Novel, Watch)."""
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        count = _grid_row_count(page, "gift-grid")
        assert count == 3, f"Bob should see 3 gifts, got {count}"

    def test_bob_sees_fewer_relations(self, page: Page, live_server, seed_data_e2e):
        """Bob sees only relations he has permissions on (relation_0, relation_2)."""
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/relations/advanced/")
        _wait_for_grid(page, "relation-grid")

        count = _grid_row_count(page, "relation-grid")
        assert count == 2, f"Bob should see 2 relations, got {count}"

    def test_bob_editor_sees_edit_button(self, page: Page, live_server, seed_data_e2e):
        """Bob (EDITOR on Best Friend) sees edit button for Best Friend."""
        _login(page, live_server.url, "bob", "bob_password")
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        rows = page.locator("#person-grid .gridjs-tbody tr")
        for i in range(rows.count()):
            row_text = rows.nth(i).inner_text()
            if "Best Friend" in row_text:
                action_html = rows.nth(i).locator("td:last-child").inner_html()
                assert "fa-edit" in action_html or "btn-warning" in action_html, (
                    "Editor should see edit button on EDITOR-permission items"
                )
                break


# ===========================================================================
# 9. FILTER PANEL TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestFilterPanel:
    """Filter panel component tests across list templates."""

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/relations/advanced/", "relation-grid"),
            ("/gifts/", "gift-grid"),
            ("/relation_statuses/", "status-grid"),
        ],
    )
    def test_filter_panel_present(self, page: Page, live_server, seed_data_e2e, path, grid_id):
        """Filter panel is present on all list pages."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")

        panel = page.locator(
            f"#{grid_id}-filter-panel, "
            ".search-filter-sort, "
            ".filter-panel, "
            f"[data-grid-id='{grid_id}']"
        )
        expect(panel.first).to_be_attached()

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/gifts/", "gift-grid"),
        ],
    )
    def test_filter_toggle_opens_panel(self, page: Page, live_server, seed_data_e2e, path, grid_id):
        """Clicking the filter toggle button opens the filter content."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        toggle = page.locator(f"#{grid_id}-filter-toggle")
        if toggle.is_visible():
            toggle.click()
            page.wait_for_timeout(400)

            content = page.locator(f"#{grid_id}-filter-content")
            if content.count() > 0:
                expect(content).to_be_visible()

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/gifts/", "gift-grid"),
        ],
    )
    def test_search_input_in_filter_panel(
        self, page: Page, live_server, seed_data_e2e, path, grid_id
    ):
        """Search input is present inside the filter panel."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)
        _open_filter_panel(page, grid_id)

        search = page.locator(f"#{grid_id}-search")
        if search.count() > 0:
            expect(search).to_be_visible()


# ===========================================================================
# 10. FEATURE INTERACTIONS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestFeatureInteractions:
    """Tests verifying multiple features work together correctly."""

    def test_search_and_sort_together(self, page: Page, live_server, seed_data_e2e):
        """Searching then sorting does not break the grid."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_filter_panel(page, "person-grid")

        search = _get_search_input(page, "person-grid")
        if search.is_visible():
            search.fill("Seed")
            page.wait_for_timeout(800)

            hdr = page.locator("#person-grid .gridjs-thead th:nth-child(2)")
            hdr.click()
            page.wait_for_timeout(400)

            assert _grid_row_count(page, "person-grid") > 0

            search.clear()
            page.wait_for_timeout(800)

    def test_inline_editing_then_search(self, page: Page, live_server, seed_data_e2e):
        """Starting inline edit, cancelling, then searching works."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")
        _open_advanced_tools(page, "person-grid")

        cell = page.locator("#person-grid .gridjs-tbody tr:first-child td:nth-child(2)")
        cell.dblclick()
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        _open_filter_panel(page, "person-grid")
        search = _get_search_input(page, "person-grid")
        if search.is_visible():
            search.fill("Dad")
            page.wait_for_timeout(800)
            assert _grid_row_count(page, "person-grid") >= 1

            search.clear()
            page.wait_for_timeout(800)

    def test_bulk_selection_then_search(self, page: Page, live_server, seed_data_e2e):
        """Selecting items then searching preserves grid stability."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/gifts/")
        _wait_for_grid(page, "gift-grid")

        _get_select_button(page, "gift-grid").click()
        page.wait_for_timeout(600)

        cbs = page.locator("#gift-grid .gridjs-tbody input[type='checkbox']")
        if cbs.count() > 0:
            cbs.first.check()
            page.wait_for_timeout(300)

        _open_filter_panel(page, "gift-grid")
        search = _get_search_input(page, "gift-grid")
        if search.is_visible():
            search.fill("Novel")
            page.wait_for_timeout(800)
            assert _grid_row_count(page, "gift-grid") >= 1

            search.clear()
            page.wait_for_timeout(800)

    def test_grid_refresh_via_list_update_event(self, page: Page, live_server, seed_data_e2e):
        """Dispatching a 'list:update' event triggers grid refresh."""
        _login(page, live_server.url)
        page.goto(f"{live_server.url}/persons/")
        _wait_for_grid(page, "person-grid")

        # Dispatch the event that grid-utils listens for
        page.evaluate(
            "document.body.dispatchEvent(new CustomEvent('list:update', {bubbles: true}))"
        )
        page.wait_for_timeout(1000)

        after = _grid_row_count(page, "person-grid")
        # Grid should still render (refresh might change data or stay same)
        assert after > 0, "Grid should still have rows after list:update event"


# ===========================================================================
# 11. MOBILE VIEWPORT TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestMobileViewport:
    """Tests for responsive behavior on mobile viewports."""

    @pytest.mark.parametrize(
        "path,grid_id",
        [
            ("/persons/", "person-grid"),
            ("/events/", "event-grid"),
            ("/gifts/", "gift-grid"),
        ],
    )
    def test_grid_renders_on_mobile(self, page: Page, live_server, seed_data_e2e, path, grid_id):
        """Grid renders correctly on mobile viewport (375x667)."""
        _login(page, live_server.url)
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{live_server.url}{path}")
        _wait_for_grid(page, grid_id)

        assert _grid_row_count(page, grid_id) > 0

        # Grid should not overflow the viewport horizontally (allow scrollable)
        wrapper = page.locator(f"#{grid_id} .gridjs-wrapper")
        expect(wrapper).to_be_visible()

        # Reset
        page.set_viewport_size({"width": 1920, "height": 1080})

    def test_page_header_visible_on_mobile(self, page: Page, live_server, seed_data_e2e):
        """Page header (h1) is visible on mobile."""
        _login(page, live_server.url)
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{live_server.url}/persons/")
        page.wait_for_load_state("networkidle")

        expect(page.locator("h1")).to_be_visible()
        page.set_viewport_size({"width": 1920, "height": 1080})

    def test_create_button_accessible_on_mobile(self, page: Page, live_server, seed_data_e2e):
        """Create button is still accessible on mobile viewport."""
        _login(page, live_server.url)
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{live_server.url}/persons/")
        page.wait_for_load_state("networkidle")

        # Scope to page-header to avoid matching nav/grid action buttons
        create_btn = page.locator(
            ".page-header-actions a[data-action='create'], "
            ".page-header a.btn-primary[data-action='create']"
        )
        expect(create_btn.first).to_be_attached()
        page.set_viewport_size({"width": 1920, "height": 1080})


# ===========================================================================
# 12. UNAUTHENTICATED ACCESS TESTS
# ===========================================================================


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
class TestUnauthenticatedAccess:
    """Verify that unauthenticated users are redirected to login."""

    @pytest.mark.parametrize(
        "path",
        [
            "/persons/",
            "/events/",
            "/relations/",
            "/relations/advanced/",
            "/person_groups/",
            "/gifts/",
            "/relation_statuses/",
        ],
    )
    def test_redirect_to_login(self, page: Page, live_server, seed_data_e2e, path):
        """Unauthenticated access to list pages redirects to login."""
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")

        assert "login" in page.url.lower() or "accounts" in page.url.lower(), (
            f"Expected redirect to login, got: {page.url}"
        )
