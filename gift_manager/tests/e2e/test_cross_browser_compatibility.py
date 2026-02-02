"""Cross-browser compatibility tests for the modern UX interface.

These tests verify that all functionality works consistently across different
browsers (Chromium, Firefox, WebKit) and handle browser-specific behaviors.
"""

import pytest
from playwright.sync_api import Page, expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


@pytest.mark.frontend
@pytest.mark.e2e
class TestCrossBrowserCompatibility(BaseE2ETest):
    """Test functionality across different browsers."""

    def test_modal_behavior_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that modal dialogs work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test delete confirmation modal
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        # Verify modal structure is consistent
        modal = page.locator("#confirmModal")
        expect(modal).to_have_class("modal")
        expect(modal).to_have_class("show")

        # Test modal animations complete properly
        page.wait_for_timeout(500)  # Allow for animation
        expect(modal).to_be_visible()

        # Test Escape key behavior
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

        # Test modal reopening
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)
        expect(modal).to_be_visible()

        # Test backdrop click (browser-specific behavior)
        modal_dialog = modal.locator(".modal-dialog")
        modal_backdrop_area = modal.bounding_box()
        dialog_box = modal_dialog.bounding_box()

        # Click outside dialog area but within modal
        click_x = modal_backdrop_area["x"] + 10
        click_y = modal_backdrop_area["y"] + 10
        if click_x < dialog_box["x"] or click_y < dialog_box["y"]:
            page.mouse.click(click_x, click_y)
            expect(modal).not_to_be_visible()

    def test_slide_panel_behavior_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that slide panels work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test edit panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_have_class("offcanvas")
        expect(panel).to_have_class("show")

        # Test panel positioning and size
        panel_box = panel.bounding_box()
        viewport_size = page.viewport_size

        # Panel should be positioned correctly
        assert panel_box["width"] > 0, "Panel should have width"
        assert panel_box["height"] > 0, "Panel should have height"
        assert panel_box["x"] + panel_box["width"] <= viewport_size["width"], "Panel should fit in viewport"

        # Test form interaction
        first_name_field = panel.locator("[name='first_name']")
        expect(first_name_field).to_be_visible()
        expect(first_name_field).to_be_editable()

        # Test form submission
        first_name_field.fill("Cross Browser Test")
        self.submit_panel_form(page)

        # Wait for panel to close
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

    def test_ajax_requests_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that AJAX requests work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Monitor network requests
        requests = []
        responses = []

        def handle_request(request):
            if "persons" in request.url:
                requests.append(request)

        def handle_response(response):
            if "persons" in response.url:
                responses.append(response)

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Trigger AJAX request via edit action
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Verify AJAX request was made
        assert len(requests) > 0, "Should have made AJAX requests"
        assert len(responses) > 0, "Should have received AJAX responses"

        # Verify response was successful
        successful_responses = [r for r in responses if r.status < 400]
        assert len(successful_responses) > 0, "Should have successful AJAX responses"

    def test_css_animations_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that CSS animations work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test modal fade-in animation
        self.click_quick_action(page, 0, "delete")

        modal = page.locator("#confirmModal")
        # Modal should start invisible or with opacity 0
        expect(modal).to_be_visible()

        # Wait for animation to complete
        page.wait_for_timeout(300)

        # Modal should be fully visible
        expect(modal).to_have_class("show")

        # Test modal fade-out animation
        page.keyboard.press("Escape")

        # Wait for animation to complete
        page.wait_for_timeout(300)
        expect(modal).not_to_be_visible()

    def test_javascript_events_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that JavaScript events work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test click events
        edit_button = page.locator("[data-action='edit']").first
        expect(edit_button).to_be_visible()

        edit_button.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Test keyboard events
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.focus()

        # Test key press events
        first_name_field.press("Control+a")
        first_name_field.type("Keyboard Test")

        expect(first_name_field).to_have_value("Keyboard Test")

        # Test form submission via Enter key
        first_name_field.press("Tab")  # Move to next field
        submit_button = panel.locator("button[type='submit']")
        submit_button.press("Enter")

        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

    def test_responsive_behavior_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that responsive design works consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test desktop view
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.reload()

        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        panel_box = panel.bounding_box()

        # Panel should be side panel on desktop
        assert panel_box["width"] < 800, "Panel should be side panel on desktop"

        self.close_panel(page)

        # Test tablet view
        page.set_viewport_size({"width": 768, "height": 1024})
        page.reload()

        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel_box = panel.bounding_box()
        # Panel behavior may change on tablet
        assert panel_box["width"] > 0, "Panel should be visible on tablet"

        self.close_panel(page)

        # Test mobile view
        page.set_viewport_size({"width": 375, "height": 667})
        page.reload()

        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel_box = panel.bounding_box()
        viewport_size = page.viewport_size

        # Panel should adapt to mobile (possibly full-screen)
        assert panel_box["width"] <= viewport_size["width"], "Panel should fit mobile viewport"

    def test_form_validation_cross_browser(self, page: Page, live_server, test_user):
        """Test that form validation works consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")

        # Try to submit empty form
        self.submit_panel_form(page)

        # Panel should remain open due to validation errors
        expect(panel).to_be_visible()

        # Check for validation error indicators
        error_indicators = panel.locator(".invalid-feedback, .error, .is-invalid")
        if error_indicators.count() > 0:
            expect(error_indicators.first).to_be_visible()

        # Fill required fields and resubmit
        first_name_field = panel.locator("[name='first_name']")
        family_name_field = panel.locator("[name='family_name']")

        first_name_field.fill("Browser Test")
        family_name_field.fill("User")

        self.submit_panel_form(page)

        # Panel should close on successful submission
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

    def test_accessibility_features_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that accessibility features work consistently across browsers."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Test keyboard navigation
        page.keyboard.press("Tab")

        # Find first focusable element
        focused_element = page.evaluate("document.activeElement")
        assert focused_element is not None, "Should have focused element"

        # Test modal accessibility
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")

        # Check ARIA attributes
        modal_dialog = modal.locator(".modal-dialog")
        role = modal_dialog.get_attribute("role")
        if role:
            assert role == "dialog", f"Expected role='dialog', got '{role}'"

        # Test focus management
        focused_in_modal = page.evaluate("""
            () => {
                const modal = document.getElementById('confirmModal');
                const activeElement = document.activeElement;
                return modal && modal.contains(activeElement);
            }
        """)
        assert focused_in_modal, "Focus should be within modal"

        # Test Escape key
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

    @pytest.mark.slow
    def test_performance_cross_browser(self, page: Page, live_server, test_user, sample_persons):
        """Test that performance is acceptable across browsers."""
        self.login_as_user(page, live_server, test_user)

        # Measure page load time
        start_time = page.evaluate("performance.now()")
        self.navigate_to_entity_list(page, live_server, "persons")
        end_time = page.evaluate("performance.now()")

        load_time = end_time - start_time
        assert load_time < 5000, f"Page load took {load_time}ms, should be under 5000ms"

        # Measure modal open time
        start_time = page.evaluate("performance.now()")
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)
        end_time = page.evaluate("performance.now()")

        modal_time = end_time - start_time
        assert modal_time < 1000, f"Modal open took {modal_time}ms, should be under 1000ms"

        # Close modal
        page.keyboard.press("Escape")

        # Measure panel open time
        start_time = page.evaluate("performance.now()")
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)
        end_time = page.evaluate("performance.now()")

        panel_time = end_time - start_time
        assert panel_time < 1000, f"Panel open took {panel_time}ms, should be under 1000ms"


@pytest.mark.frontend
@pytest.mark.e2e
class TestBrowserSpecificFeatures(BaseE2ETest):
    """Test browser-specific features and workarounds."""

    def test_webkit_specific_behaviors(self, page: Page, live_server, test_user, sample_persons):
        """Test WebKit-specific behaviors and workarounds."""
        browser_name = page.context.browser.browser_type.name
        if browser_name != "webkit":
            pytest.skip("WebKit-specific test")

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # WebKit may handle animations differently
        self.click_quick_action(page, 0, "edit")

        # Give WebKit extra time for animations
        page.wait_for_timeout(500)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()
        expect(panel).to_have_class("show")

    def test_firefox_specific_behaviors(self, page: Page, live_server, test_user, sample_persons):
        """Test Firefox-specific behaviors and workarounds."""
        browser_name = page.context.browser.browser_type.name
        if browser_name != "firefox":
            pytest.skip("Firefox-specific test")

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Firefox may handle form validation differently
        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")

        # Test Firefox form validation
        self.submit_panel_form(page)

        # Firefox may show native validation messages
        expect(panel).to_be_visible()

    def test_chromium_specific_behaviors(self, page: Page, live_server, test_user, sample_persons):
        """Test Chromium-specific behaviors and workarounds."""
        browser_name = page.context.browser.browser_type.name
        if browser_name != "chromium":
            pytest.skip("Chromium-specific test")

        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Chromium may have specific DevTools integration
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Test Chromium-specific features like autofill
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.focus()

        # Chromium may trigger autofill suggestions
        expect(first_name_field).to_be_focused()
