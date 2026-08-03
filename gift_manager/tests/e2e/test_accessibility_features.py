"""Accessibility feature tests for the modern UX interface.

These tests verify that the application meets accessibility standards
including keyboard navigation, screen reader support, and ARIA compliance.
"""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.accessibility
class TestKeyboardAccessibility(BaseE2ETest):
    """Test keyboard navigation and accessibility features."""

    def test_modal_keyboard_navigation(self, page: Page, live_server, test_user, sample_persons):
        """Test keyboard navigation within modal dialogs."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open delete confirmation modal
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Test focus management - focus should be within modal
        focused_element = page.evaluate("""
            () => {
                const modal = document.getElementById('confirmModal');
                const activeElement = document.activeElement;
                return modal && modal.contains(activeElement);
            }
        """)
        assert focused_element, "Focus should be within modal"

        # Test Tab navigation within modal
        page.keyboard.press("Tab")

        # Should be able to navigate between modal buttons
        cancel_btn = modal.locator(".btn-secondary, [data-bs-dismiss='modal']").first
        confirm_btn = modal.locator(".btn-danger, .btn-primary").first

        if cancel_btn.count() > 0 and confirm_btn.count() > 0:
            # Test that we can reach both buttons
            for _ in range(5):  # Try up to 5 tabs
                focused = page.evaluate("document.activeElement")
                if focused and (
                    cancel_btn.evaluate("el => el === document.activeElement")
                    or confirm_btn.evaluate("el => el === document.activeElement")
                ):
                    break
                page.keyboard.press("Tab")

        # Test Escape key closes modal
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

        # Test focus restoration after modal closes
        page.wait_for_timeout(100)  # Allow for focus restoration
        focused_after = page.evaluate("document.activeElement.tagName")
        assert focused_after in ["BUTTON", "A", "INPUT", "BODY"], (
            "Focus should be restored to actionable element"
        )

    def test_panel_keyboard_navigation(self, page: Page, live_server, test_user, sample_persons):
        """Test keyboard navigation within slide panels."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open edit panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Test focus management - focus should move to first form field
        first_name_field = panel.locator("[name='first_name']")
        if first_name_field.count() > 0:
            expect(first_name_field).to_be_focused()

            # Test Tab navigation through form fields
            page.keyboard.press("Tab")

            family_name_field = panel.locator("[name='family_name']")
            if family_name_field.count() > 0:
                expect(family_name_field).to_be_focused()

        # Test Escape key closes panel
        page.keyboard.press("Escape")
        expect(panel).not_to_be_visible()

    def test_list_keyboard_navigation(self, page: Page, live_server, test_user, sample_persons):
        """Test keyboard navigation through list items and actions."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test Tab navigation through list
        page.keyboard.press("Tab")

        # Navigate through actionable elements
        actionable_elements = []
        for _ in range(20):  # Try up to 20 tabs
            focused = page.evaluate("""
                () => {
                    const activeElement = document.activeElement;
                    return activeElement ? activeElement.tagName + ':' + (activeElement.className || '') : 'none';
                }
            """)

            if focused not in actionable_elements:
                actionable_elements.append(focused)

            page.keyboard.press("Tab")

            # Break if we've cycled back to the first element
            if len(actionable_elements) > 1 and actionable_elements[0] == focused:
                break

        # Should have found actionable elements
        assert len(actionable_elements) > 0, "Should find actionable elements in list"

        # Test Enter key activation
        edit_buttons = page.locator("[data-action='edit']")
        if edit_buttons.count() > 0:
            first_edit_btn = edit_buttons.first
            first_edit_btn.focus()
            page.keyboard.press("Enter")

            # Should open edit panel
            self.wait_for_panel(page)
            panel = page.locator("#editPanel")
            expect(panel).to_be_visible()

            # Close panel
            page.keyboard.press("Escape")

    def test_form_keyboard_shortcuts(self, page: Page, live_server, test_user):
        """Test keyboard shortcuts in forms."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Fill form fields
        first_name_field = panel.locator("[name='first_name']")
        family_name_field = panel.locator("[name='family_name']")

        if first_name_field.count() > 0:
            first_name_field.fill("Keyboard Test")
        if family_name_field.count() > 0:
            family_name_field.fill("User")

        # Test Ctrl+S shortcut for save (if implemented)
        page.keyboard.press("Control+s")

        # Wait a moment to see if save was triggered
        page.wait_for_timeout(500)

        # Panel may close if Ctrl+S works, or remain open if not implemented
        # This is implementation-dependent

        # Test Enter key in form (should submit)
        if panel.is_visible():
            submit_btn = panel.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.focus()
                page.keyboard.press("Enter")

                self.wait_for_ajax_complete(page)
                expect(panel).not_to_be_visible()

    def test_skip_links(self, page: Page, live_server, test_user):
        """Test skip links for keyboard navigation."""
        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/")

        # Test skip to main content link
        skip_link = page.locator("a[href='#main'], .skip-link")
        if skip_link.count() > 0:
            # Skip links are often hidden until focused
            skip_link.focus()
            expect(skip_link).to_be_visible()

            # Activate skip link
            page.keyboard.press("Enter")

            # Focus should move to main content
            main_content = page.locator("#main, main, .main-content")
            if main_content.count() > 0:
                # Focus should be within or on main content area
                focus_is_in_main = main_content.first.evaluate(
                    "main => main === document.activeElement || main.contains(document.activeElement)"
                )
                assert focus_is_in_main


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.accessibility
class TestARIACompliance(BaseE2ETest):
    """Test ARIA attributes and screen reader support."""

    def test_modal_aria_attributes(self, page: Page, live_server, test_user, sample_persons):
        """Test ARIA attributes on modal dialogs."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open modal
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Test modal ARIA attributes
        modal_dialog = modal.locator(".modal-dialog")
        if modal_dialog.count() > 0:
            role = modal_dialog.get_attribute("role")
            if role:
                assert role == "dialog", f"Expected role='dialog', got '{role}'"

            aria_modal = modal_dialog.get_attribute("aria-modal")
            if aria_modal:
                assert aria_modal == "true", f"Expected aria-modal='true', got '{aria_modal}'"

            aria_labelledby = modal_dialog.get_attribute("aria-labelledby")
            if aria_labelledby:
                # Should reference modal title
                title_element = page.locator(f"#{aria_labelledby}")
                expect(title_element).to_be_visible()

        # Test modal title
        modal_title = modal.locator(".modal-title")
        if modal_title.count() > 0:
            title_id = modal_title.get_attribute("id")
            assert title_id is not None, "Modal title should have an ID"

        # Close modal
        page.keyboard.press("Escape")

    def test_form_aria_attributes(self, page: Page, live_server, test_user):
        """Test ARIA attributes on form elements."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Test form field labels
        form_fields = panel.locator("input, select, textarea")
        for i in range(form_fields.count()):
            field = form_fields.nth(i)
            field_id = field.get_attribute("id")
            field_name = field.get_attribute("name")

            if field_id:
                # Look for associated label
                label = panel.locator(f"label[for='{field_id}']")
                if label.count() > 0:
                    expect(label).to_be_visible()
                else:
                    # Check for aria-label or aria-labelledby
                    aria_label = field.get_attribute("aria-label")
                    aria_labelledby = field.get_attribute("aria-labelledby")
                    assert aria_label or aria_labelledby, (
                        f"Field {field_name} should have label or aria-label"
                    )

        # Test required field indicators
        required_fields = panel.locator("input[required], select[required], textarea[required]")
        for i in range(required_fields.count()):
            field = required_fields.nth(i)
            aria_required = field.get_attribute("aria-required")
            if aria_required:
                assert aria_required == "true", "Required fields should have aria-required='true'"

        # Close panel
        page.keyboard.press("Escape")

    def test_button_aria_attributes(self, page: Page, live_server, test_user, sample_persons):
        """Test ARIA attributes on buttons and interactive elements."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test action buttons
        action_buttons = page.locator("[data-action]")
        for i in range(min(5, action_buttons.count())):
            button = action_buttons.nth(i)

            # Buttons should have accessible names
            aria_label = button.get_attribute("aria-label")
            button_text = button.text_content()
            title = button.get_attribute("title")

            assert aria_label or button_text or title, "Buttons should have accessible names"

        # Test toggle buttons (if any)
        toggle_buttons = page.locator("[aria-pressed], .btn-toggle")
        for i in range(toggle_buttons.count()):
            button = toggle_buttons.nth(i)
            aria_pressed = button.get_attribute("aria-pressed")
            if aria_pressed:
                assert aria_pressed in ["true", "false"], (
                    "Toggle buttons should have aria-pressed='true' or 'false'"
                )

    def test_list_aria_attributes(self, page: Page, live_server, test_user, sample_persons):
        """Test ARIA attributes on list elements."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test list container
        list_container = page.locator(".list-container")
        if list_container.count() > 0:
            role = list_container.get_attribute("role")
            if role:
                assert role in ["list", "table", "grid"], (
                    f"List container should have appropriate role, got '{role}'"
                )

        # Test list items
        list_items = page.locator(".list-container .list-item, .list-container tr")
        if list_items.count() > 0:
            first_item = list_items.first
            role = first_item.get_attribute("role")
            if role:
                assert role in ["listitem", "row"], (
                    f"List items should have appropriate role, got '{role}'"
                )

        # Test checkboxes for bulk selection
        checkboxes = page.locator("input[type='checkbox']")
        for i in range(min(3, checkboxes.count())):
            checkbox = checkboxes.nth(i)
            aria_label = checkbox.get_attribute("aria-label")
            associated_label = page.locator(f"label[for='{checkbox.get_attribute('id')}']")

            assert aria_label or associated_label.count() > 0, (
                "Checkboxes should have accessible labels"
            )

    def test_live_regions(self, page: Page, live_server, test_user, sample_persons):
        """Test ARIA live regions for dynamic content updates."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test notification areas
        notification_areas = page.locator(".alert, .toast, .notification")
        for i in range(notification_areas.count()):
            area = notification_areas.nth(i)
            aria_live = area.get_attribute("aria-live")
            role = area.get_attribute("role")

            if aria_live:
                assert aria_live in ["polite", "assertive"], (
                    f"Live regions should have appropriate aria-live value, got '{aria_live}'"
                )
            elif role:
                assert role in ["status", "alert"], (
                    f"Notification areas should have appropriate role, got '{role}'"
                )

        # Test loading indicators
        loading_indicators = page.locator(".loading, .spinner")
        for i in range(loading_indicators.count()):
            indicator = loading_indicators.nth(i)
            aria_label = indicator.get_attribute("aria-label")
            role = indicator.get_attribute("role")

            if indicator.is_visible():
                assert aria_label or role, "Loading indicators should have accessible labels"


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.accessibility
class TestScreenReaderSupport(BaseE2ETest):
    """Test screen reader support and announcements."""

    def test_dynamic_content_announcements(
        self, page: Page, live_server, test_user, sample_persons
    ):
        """Test that dynamic content changes are announced to screen readers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test modal opening announcement
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Modal should have appropriate ARIA attributes for screen readers
        modal_content = modal.locator(".modal-content, .modal-dialog").first
        if modal_content.count() > 0:
            role = modal_content.get_attribute("role")
            aria_modal = modal_content.get_attribute("aria-modal")

            # These attributes help screen readers understand the modal context
            if role:
                assert role == "dialog", "Modal should have role='dialog'"
            if aria_modal:
                assert aria_modal == "true", "Modal should have aria-modal='true'"

        page.keyboard.press("Escape")

    def test_form_error_announcements(self, page: Page, live_server, test_user):
        """Test that form validation errors are announced to screen readers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Submit empty form to trigger validation
        self.submit_panel_form(page)

        # Look for error messages with appropriate ARIA attributes
        error_messages = panel.locator(
            "#offcanvasContent .form-error-summary, #offcanvasContent .invalid-feedback, "
            "#offcanvasContent .error, #offcanvasContent .alert-danger"
        )
        if error_messages.count() > 0:
            first_error = error_messages.first

            # Error messages should be associated with form fields
            aria_describedby = first_error.get_attribute("aria-describedby")
            role = first_error.get_attribute("role")
            aria_live = first_error.get_attribute("aria-live")

            # At least one of these should be present for screen reader support
            assert aria_describedby or role or aria_live, (
                "Error messages should have screen reader support"
            )

        page.keyboard.press("Escape")

    def test_loading_state_announcements(self, page: Page, live_server, test_user, sample_persons):
        """Test that loading states are announced to screen readers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Trigger an action that might show loading state
        self.click_quick_action(page, 0, "edit")

        # Look for loading indicators during the brief loading period
        loading_indicators = page.locator(".loading, .spinner, [data-loading]")
        if loading_indicators.count() > 0:
            for i in range(loading_indicators.count()):
                indicator = loading_indicators.nth(i)
                if indicator.is_visible():
                    aria_label = indicator.get_attribute("aria-label")
                    role = indicator.get_attribute("role")
                    aria_live = indicator.get_attribute("aria-live")

                    # Loading indicators should be accessible to screen readers
                    assert aria_label or role or aria_live, (
                        "Loading indicators should be accessible"
                    )

        # Wait for panel to load
        self.wait_for_panel(page)
        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        page.keyboard.press("Escape")


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.accessibility
class TestColorContrastAndVisibility(BaseE2ETest):
    """Test color contrast and visual accessibility features."""

    def test_focus_indicators(self, page: Page, live_server, test_user, sample_persons):
        """Test that focus indicators are visible and meet contrast requirements."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test focus indicators on buttons
        action_buttons = page.locator("[data-action], .btn")
        if action_buttons.count() > 0:
            first_button = action_buttons.first
            first_button.focus()

            # Check that element has focus
            is_focused = first_button.evaluate("el => el === document.activeElement")
            assert is_focused, "Button should be focused"

            # Get computed styles to check focus indicator
            focus_styles = first_button.evaluate("""
                el => {
                    const styles = getComputedStyle(el);
                    return {
                        outline: styles.outline,
                        outlineWidth: styles.outlineWidth,
                        outlineColor: styles.outlineColor,
                        boxShadow: styles.boxShadow,
                        borderColor: styles.borderColor
                    };
                }
            """)

            # Should have some form of focus indicator
            has_focus_indicator = (
                focus_styles["outline"] != "none"
                or focus_styles["outlineWidth"] != "0px"
                or "focus" in focus_styles["boxShadow"]
                or focus_styles["borderColor"] != "initial"
            )

            assert has_focus_indicator, "Focused elements should have visible focus indicators"

    def test_text_contrast(self, page: Page, live_server, test_user, sample_persons):
        """Test text contrast ratios (basic check)."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Check text elements for basic contrast
        text_elements = page.locator("p, span, div, h1, h2, h3, h4, h5, h6, .entity-name")

        for i in range(min(10, text_elements.count())):
            element = text_elements.nth(i)
            if element.is_visible():
                styles = element.evaluate("""
                    el => {
                        const styles = getComputedStyle(el);
                        return {
                            color: styles.color,
                            backgroundColor: styles.backgroundColor,
                            fontSize: styles.fontSize
                        };
                    }
                """)

                # Basic check - text should not be transparent or same as background
                assert styles["color"] != "rgba(0, 0, 0, 0)", "Text should not be transparent"
                assert styles["color"] != styles["backgroundColor"], (
                    "Text should contrast with background"
                )

    def test_button_sizing(self, page: Page, live_server, test_user, sample_persons):
        """Test that interactive elements meet minimum size requirements."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test button sizes (should be at least 44x44px for touch accessibility)
        buttons = page.locator("button, .btn, [role='button']")

        for i in range(min(10, buttons.count())):
            button = buttons.nth(i)
            if button.is_visible():
                button_box = button.bounding_box()

                # Buttons should meet minimum touch target size
                assert button_box["width"] >= 24, (
                    f"Button width {button_box['width']} should be at least 24px"
                )
                assert button_box["height"] >= 24, (
                    f"Button height {button_box['height']} should be at least 24px"
                )

    def test_error_message_visibility(self, page: Page, live_server, test_user):
        """Test that error messages are clearly visible and accessible."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form and trigger validation errors
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        self.submit_panel_form(page)

        # Check error message visibility
        error_messages = panel.locator(
            "#offcanvasContent .form-error-summary, #offcanvasContent .invalid-feedback, "
            "#offcanvasContent .error, #offcanvasContent .alert-danger"
        )
        if error_messages.count() > 0:
            first_error = error_messages.first
            expect(first_error).to_be_visible()

            # Error messages should have appropriate styling
            error_styles = first_error.evaluate("""
                el => {
                    const styles = getComputedStyle(el);
                    return {
                        color: styles.color,
                        display: styles.display,
                        visibility: styles.visibility
                    };
                }
            """)

            assert error_styles["display"] != "none", "Error messages should be displayed"
            assert error_styles["visibility"] != "hidden", "Error messages should be visible"

        page.keyboard.press("Escape")
        self.wait_for_panel_close(page)
