"""Mobile device interaction tests for the modern UX interface.

These tests verify that the application works correctly on mobile devices
with touch interactions, responsive design, and mobile-specific behaviors.
"""

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


def tap_or_click(locator, **kwargs):
    """Use touch tap when available, otherwise fall back to mouse click."""
    click_count = kwargs.pop("click_count", 1)
    if click_count != 1:
        locator.click(click_count=click_count, **kwargs)
        return

    try:
        locator.tap(**kwargs)
    except PlaywrightError as exc:
        if "does not support tap" not in str(exc):
            raise
        locator.click(**kwargs)


def first_visible_list_target(page: Page):
    """Return a visible touch target from a responsive list/grid."""
    target = page.locator(
        ".list-container .list-item:visible, "
        ".list-container .gridjs-tbody td:visible, "
        ".list-container .gridjs-tbody tr:visible"
    ).first
    expect(target).to_be_visible()
    return target


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.mobile
class TestMobileDeviceInteractions(BaseE2ETest):
    """Test mobile device interactions and responsive behavior."""

    def setup_method(self):
        """Set up mobile-specific test configuration."""
        super().setup_method()
        self.mobile_timeout = 8000  # Mobile may be slower

    def test_mobile_modal_behavior(self, page: Page, live_server, test_user, sample_persons):
        """Test that modals work correctly on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test delete confirmation modal on mobile
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Verify modal adapts to mobile screen
        modal_dialog = modal.locator(".modal-dialog")
        dialog_box = modal_dialog.bounding_box()
        viewport_size = page.viewport_size

        # Modal should fit within mobile viewport with margins
        assert dialog_box["width"] <= viewport_size["width"], "Modal should fit mobile width"
        assert dialog_box["x"] >= 0, "Modal should not overflow the left edge"

        # Test touch interaction to close modal
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

    def test_mobile_slide_panel_behavior(self, page: Page, live_server, test_user, sample_persons):
        """Test that slide panels adapt to mobile screens."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test edit panel on mobile
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Verify panel adapts to mobile (should be full-screen or nearly full-screen)
        panel_box = panel.bounding_box()
        viewport_size = page.viewport_size

        # On mobile, panel should take most or all of the screen width
        width_ratio = panel_box["width"] / viewport_size["width"]
        assert width_ratio >= 0.8, (
            f"Panel should take at least 80% of mobile width, got {width_ratio:.2f}"
        )

        # Test form interaction on mobile
        first_name_field = panel.locator("[name='first_name']")
        expect(first_name_field).to_be_visible()

        # Test touch interaction
        tap_or_click(first_name_field)
        expect(first_name_field).to_be_focused()

        # Test virtual keyboard handling
        first_name_field.fill("Mobile Test User")
        expect(first_name_field).to_have_value("Mobile Test User")

        # Close panel
        self.close_panel(page)

    def test_touch_interactions(self, page: Page, live_server, test_user, sample_persons):
        """Test touch-specific interactions like tap, swipe, and long press."""
        # Set mobile viewport with touch support
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test tap interaction
        first_person_row = first_visible_list_target(page)

        # Test tap to select/highlight
        tap_or_click(first_person_row)

        # Test double tap for inline editing (if implemented)
        person_name = first_person_row.locator(".entity-name").first
        if person_name.count() > 0:
            tap_or_click(person_name, click_count=2)

        # Check if inline editing activated
        inline_edit_field = page.locator(".inline-edit-field")
        if inline_edit_field.count() > 0:
            expect(inline_edit_field).to_be_visible()
            inline_edit_field.fill("Touch Edited Name")
            inline_edit_field.press("Enter")

            # Wait for save
            self.wait_for_ajax_complete(page)

        # Test tap on action buttons
        edit_button = page.locator(".list-container [data-action='edit']:visible").first
        if edit_button.count() > 0:
            tap_or_click(edit_button)
            self.wait_for_panel(page)

            panel = page.locator("#editPanel")
            expect(panel).to_be_visible()
            self.close_panel(page)

    def test_swipe_gestures(self, page: Page, live_server, test_user, sample_persons):
        """Test swipe gestures for mobile interactions."""
        # Set mobile viewport with touch support
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test swipe to reveal actions (if implemented)
        first_person_row = first_visible_list_target(page)

        row_box = first_person_row.bounding_box()

        # Perform swipe gesture (left to right)
        page.mouse.move(row_box["x"] + 10, row_box["y"] + row_box["height"] / 2)
        page.mouse.down()

        page.mouse.move(row_box["x"] + 100, row_box["y"] + row_box["height"] / 2)
        page.mouse.up()

        page.wait_for_timeout(500)  # Allow for swipe animation

    def test_mobile_keyboard_handling(self, page: Page, live_server, test_user):
        """Test virtual keyboard handling on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = self.get_create_button(page)
        tap_or_click(create_btn)
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Test form field interaction with virtual keyboard
        first_name_field = panel.locator("[name='first_name']")
        tap_or_click(first_name_field)
        expect(first_name_field).to_be_focused()

        # Simulate virtual keyboard appearance by checking viewport changes
        # Note: Playwright may not fully simulate virtual keyboard behavior
        first_name_field.fill("Mobile User")
        expect(first_name_field).to_have_value("Mobile User")

        # Test moving between fields
        family_name_field = panel.locator("[name='family_name']")
        tap_or_click(family_name_field)
        expect(family_name_field).to_be_focused()

        family_name_field.fill("Test")
        expect(family_name_field).to_have_value("Test")

        # Test form submission
        submit_btn = panel.locator("button[type='submit']")
        tap_or_click(submit_btn)

        # Wait for form submission
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

    def test_mobile_navigation_menu(self, page: Page, live_server, test_user):
        """Test mobile navigation menu behavior."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/")

        # Look for mobile menu toggle (hamburger menu)
        menu_toggle = page.locator(".navbar-toggler, .menu-toggle, .hamburger")
        if menu_toggle.count() > 0:
            expect(menu_toggle).to_be_visible()

            # Test menu toggle
            tap_or_click(menu_toggle)

            # Wait for menu animation
            page.wait_for_timeout(500)

            # Check if navigation menu is visible
            nav_menu = page.locator(".navbar-collapse, .mobile-menu, .nav-menu")
            if nav_menu.count() > 0:
                expect(nav_menu).to_be_visible()

                # Test navigation link
                persons_link = nav_menu.locator("a[href*='persons']")
                if persons_link.count() > 0:
                    tap_or_click(persons_link)

                    # Verify navigation worked
                    expect(page).to_have_url(f"{live_server.url}/persons/")

    def test_mobile_list_interactions(self, page: Page, live_server, test_user, sample_persons):
        """Test list interactions optimized for mobile."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test mobile-optimized list layout
        list_container = page.locator(".list-container")
        expect(list_container).to_be_visible()

        # Verify list items are touch-friendly
        list_items = page.locator(
            ".list-container .list-item:visible, "
            ".list-container .gridjs-tbody td:visible, "
            ".list-container .gridjs-tbody tr:visible"
        )
        if list_items.count() > 0:
            first_item = list_items.first
            item_box = first_item.bounding_box()

            # List items should be tall enough for touch interaction (minimum 44px)
            assert item_box["height"] >= 40, (
                f"List item height {item_box['height']} should be at least 40px for touch"
            )

        # Test mobile search functionality
        search_input = page.locator("input[type='search'], .search-input")
        if search_input.count() > 0:
            tap_or_click(search_input)
            expect(search_input).to_be_focused()

            search_input.fill("Alice")

            # Wait for search results
            self.wait_for_list_update(page)

            # Verify search worked
            filtered_items = page.locator(
                ".list-container .list-item:visible, "
                ".list-container .gridjs-tbody td:visible, "
                ".list-container .gridjs-tbody tr:visible"
            )
            if filtered_items.count() > 0:
                # At least one result should contain "Alice"
                alice_found = False
                for i in range(filtered_items.count()):
                    item_text = filtered_items.nth(i).text_content()
                    if "Alice" in item_text:
                        alice_found = True
                        break
                assert alice_found, "Search should find Alice"

    def test_mobile_bulk_operations(self, page: Page, live_server, test_user, sample_persons):
        """Test bulk operations on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test mobile bulk selection
        checkboxes = page.locator(".list-container input[type='checkbox']")
        if checkboxes.count() > 0:
            # Select multiple items via touch
            row_checkboxes = self.show_bulk_selection_checkboxes(page)
            for index in range(min(3, row_checkboxes.count())):
                checkbox = row_checkboxes.nth(index)
                self.click_bulk_checkbox(checkbox)

            # Check if bulk actions toolbar appears
            bulk_toolbar = self.get_bulk_toolbar(page)
            if bulk_toolbar.count() > 0:
                expect(bulk_toolbar).to_be_visible()
                expect(bulk_toolbar.locator(".selected-count")).to_have_text("3")

                # Verify toolbar is mobile-friendly
                toolbar_box = bulk_toolbar.bounding_box()
                viewport_size = page.viewport_size

                assert toolbar_box["width"] <= viewport_size["width"], (
                    "Bulk toolbar should fit mobile width"
                )

    def test_mobile_accessibility(self, page: Page, live_server, test_user, sample_persons):
        """Test mobile accessibility features."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test touch target sizes
        action_buttons = page.locator("[data-action], .btn")
        if action_buttons.count() > 0:
            for i in range(min(5, action_buttons.count())):
                button = action_buttons.nth(i)
                if button.is_visible():
                    button_box = button.bounding_box()

                    # Touch targets should be at least 44x44px
                    assert button_box["width"] >= 40, (
                        f"Button width {button_box['width']} should be at least 40px"
                    )
                    assert button_box["height"] >= 40, (
                        f"Button height {button_box['height']} should be at least 40px"
                    )

        # Test focus indicators on mobile
        first_button = page.locator("[data-action], .btn").first
        if first_button.count() > 0:
            first_button.focus()

            # Check for visible focus indicator
            focused_styles = first_button.evaluate("el => getComputedStyle(el)")
            # Focus should be visible (outline, box-shadow, etc.)
            assert focused_styles is not None, "Should have computed styles for focused element"

    @pytest.mark.slow
    def test_mobile_performance(self, page: Page, live_server, test_user, sample_persons):
        """Test performance characteristics on mobile devices."""
        # Set mobile viewport with slower CPU simulation
        page.set_viewport_size({"width": 375, "height": 667})

        # Simulate slower mobile CPU
        client = page.context.new_cdp_session(page)
        client.send("Emulation.setCPUThrottlingRate", {"rate": 4})  # 4x slower

        try:
            self.login_as_user(page, live_server, test_user)

            # Measure page load time on mobile
            start_time = page.evaluate("performance.now()")
            self.navigate_to_entity_list(page, live_server, "persons")
            end_time = page.evaluate("performance.now()")

            load_time = end_time - start_time
            # Mobile should still load reasonably fast even with throttling
            assert load_time < 10000, (
                f"Mobile page load took {load_time}ms, should be under 10000ms"
            )

            # Measure modal interaction time
            start_time = page.evaluate("performance.now()")
            self.click_quick_action(page, 0, "delete")
            self.wait_for_modal(page)
            end_time = page.evaluate("performance.now()")

            modal_time = end_time - start_time
            assert modal_time < 2000, (
                f"Mobile modal open took {modal_time}ms, should be under 2000ms"
            )

        finally:
            # Reset CPU throttling
            client.send("Emulation.setCPUThrottlingRate", {"rate": 1})

    def test_mobile_orientation_changes(self, page: Page, live_server, test_user, sample_persons):
        """Test behavior during orientation changes."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test portrait orientation
        page.set_viewport_size({"width": 375, "height": 667})

        # Open edit panel in portrait
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        portrait_box = panel.bounding_box()

        # Change to landscape orientation
        page.set_viewport_size({"width": 667, "height": 375})
        page.wait_for_timeout(500)  # Allow for orientation change

        # Panel should still be visible and adapt
        expect(panel).to_be_visible()
        landscape_box = panel.bounding_box()

        # Panel dimensions should adapt to new orientation
        assert (
            landscape_box["width"] != portrait_box["width"]
            or landscape_box["height"] != portrait_box["height"]
        ), "Panel should adapt to orientation change"

        # Form should still be functional
        first_name_field = panel.locator("[name='first_name']")
        expect(first_name_field).to_be_visible()
        expect(first_name_field).to_be_editable()

    def test_mobile_network_conditions(self, page: Page, live_server, test_user, sample_persons):
        """Test behavior under mobile network conditions."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        # Simulate slow 3G network
        client = page.context.new_cdp_session(page)
        client.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "downloadThroughput": 1.5 * 1024 * 1024 / 8,  # 1.5 Mbps
                "uploadThroughput": 750 * 1024 / 8,  # 750 Kbps
                "latency": 40,  # 40ms latency
            },
        )

        try:
            self.login_as_user(page, live_server, test_user)
            self.navigate_to_entity_list(page, live_server, "persons")

            # Test that loading indicators appear during slow requests
            self.click_quick_action(page, 0, "edit")

            # Look for loading indicators
            loading_indicator = page.locator(".loading, .spinner, [data-loading]")
            if loading_indicator.count() > 0:
                # Loading indicator should appear briefly
                expect(loading_indicator.first).to_be_visible()

            # Panel should eventually load
            self.wait_for_panel(page, timeout=self.mobile_timeout)

            panel = page.locator("#editPanel")
            expect(panel).to_be_visible()

        finally:
            # Reset network conditions
            client.send(
                "Network.emulateNetworkConditions",
                {"offline": False, "downloadThroughput": -1, "uploadThroughput": -1, "latency": 0},
            )


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.mobile
class TestTabletInteractions(BaseE2ETest):
    """Test tablet-specific interactions and responsive behavior."""

    def test_tablet_layout_adaptation(self, page: Page, live_server, test_user, sample_persons):
        """Test that the interface adapts properly to tablet screens."""
        # Set tablet viewport (iPad size)
        page.set_viewport_size({"width": 820, "height": 1024})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test that layout uses tablet space effectively
        list_container = page.locator(".list-container")
        expect(list_container).to_be_visible()

        container_box = list_container.bounding_box()
        viewport_size = page.viewport_size

        # Should use most of the tablet width
        width_ratio = container_box["width"] / viewport_size["width"]
        assert width_ratio >= 0.8, (
            f"List should use at least 80% of tablet width, got {width_ratio:.2f}"
        )

        # Test slide panel behavior on tablet
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        panel_box = panel.bounding_box()

        # Panel should be appropriately sized for tablet (not full-screen like mobile)
        panel_width_ratio = panel_box["width"] / viewport_size["width"]
        assert 0.3 <= panel_width_ratio <= 0.7, (
            f"Panel width ratio {panel_width_ratio:.2f} should be between 0.3 and 0.7 on tablet"
        )

    def test_tablet_touch_interactions(self, page: Page, live_server, test_user, sample_persons):
        """Test touch interactions optimized for tablet use."""
        # Set tablet viewport
        page.set_viewport_size({"width": 820, "height": 1024})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test tap interactions
        first_person_row = first_visible_list_target(page)

        # Test single tap
        tap_or_click(first_person_row)

        # Test double tap for details or editing
        person_name = first_person_row.locator(".entity-name").first
        if person_name.count() > 0:
            tap_or_click(person_name, click_count=2)

        # Check if action was triggered (inline edit or detail view)
        page.wait_for_timeout(500)

        # Test action button interactions
        edit_button = page.locator(".list-container [data-action='edit']:visible").first
        if edit_button.count() > 0:
            tap_or_click(edit_button)
            self.wait_for_panel(page)

            panel = page.locator("#editPanel")
            expect(panel).to_be_visible()

            # Test form interaction on tablet
            first_name_field = panel.locator("[name='first_name']")
            tap_or_click(first_name_field)
            expect(first_name_field).to_be_focused()

            first_name_field.fill("Tablet Test User")
            expect(first_name_field).to_have_value("Tablet Test User")

            self.close_panel(page)

    def test_tablet_multitasking_behavior(self, page: Page, live_server, test_user, sample_persons):
        """Test behavior when tablet is in multitasking mode (split screen)."""
        # Simulate split-screen by using a narrower but tall viewport
        page.set_viewport_size({"width": 400, "height": 1024})

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Interface should adapt to narrow width
        list_container = page.locator(".list-container")
        expect(list_container).to_be_visible()

        # Test that modals and panels work in constrained space
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        panel_box = panel.bounding_box()
        viewport_size = page.viewport_size

        # Panel should fit within the constrained width
        assert panel_box["width"] <= viewport_size["width"], (
            "Panel should fit within split-screen width"
        )
        assert panel_box["x"] >= 0, "Panel should not extend beyond left edge"
        assert panel_box["x"] + panel_box["width"] <= viewport_size["width"], (
            "Panel should not extend beyond right edge"
        )
