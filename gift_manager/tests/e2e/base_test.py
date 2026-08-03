"""Base test class and utilities for end-to-end tests.

This module provides a base test class with common functionality for all e2e tests,
including setup, teardown, and utility methods for interacting with the modern UX interface.
"""

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page
from playwright.sync_api import expect


class BaseE2ETest:
    """Base class for all end-to-end tests.

    Provides common functionality and utilities for testing the modern UX interface,
    including authentication, navigation, and interaction with modals and panels.
    """

    # Test configuration
    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.frontend,
        pytest.mark.e2e,
    ]

    def setup_method(self):
        """Set up each test method."""
        self.page_load_timeout = 10000
        self.ajax_timeout = 5000
        self.animation_timeout = 1000

    def login_as_user(self, page: Page, live_server, user: User, password: str = "testpass123"):
        """Log in as the specified user."""
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="login"]', user.username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        # Wait for successful login (redirect away from login page)
        # Don't assume specific redirect URL, just wait for navigation
        page.wait_for_load_state("networkidle", timeout=self.page_load_timeout)

        # Verify we're no longer on the login page
        current_url = page.url
        assert "/accounts/login/" not in current_url, f"Still on login page: {current_url}"

        # Verify successful login by checking we don't see login form
        expect(page.locator("body")).not_to_contain_text("Sign In")

    def navigate_to_entity_list(self, page: Page, live_server, entity_type: str):
        """Navigate to an entity list page."""
        valid_entities = ["persons", "gifts", "events", "relations", "groups", "tags"]
        if entity_type not in valid_entities:
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of {valid_entities}")

        page.goto(f"{live_server.url}/{entity_type}/")
        page.wait_for_load_state("networkidle")

        # Verify we're on the correct page
        expect(page.locator("h1, .page-title")).to_be_visible()

    def wait_for_modal(self, page: Page, modal_id: str = "confirmModal") -> None:
        """Wait for a modal to appear and be fully visible."""
        modal = page.locator(f"#{modal_id}")
        expect(modal).to_be_visible(timeout=self.ajax_timeout)
        expect(modal).to_have_class("show")

        # Wait for modal animation to complete
        page.wait_for_timeout(self.animation_timeout)

    def wait_for_panel(self, page: Page, panel_id: str = "editPanel") -> None:
        """Wait for a slide panel to appear and be fully visible."""
        panel = page.locator(f"#{panel_id}")
        expect(panel).to_be_visible(timeout=self.ajax_timeout)
        expect(panel).to_have_class("show")

        # Wait for panel animation to complete
        page.wait_for_timeout(self.animation_timeout)

    def close_modal(self, page: Page, modal_id: str = "confirmModal") -> None:
        """Close a modal dialog."""
        modal = page.locator(f"#{modal_id}")
        close_btn = modal.locator(".btn-close, [data-bs-dismiss='modal']").first
        close_btn.click()

        # Wait for modal to be hidden
        expect(modal).not_to_be_visible(timeout=self.animation_timeout)

    def close_panel(self, page: Page, panel_id: str = "editPanel") -> None:
        """Close a slide panel."""
        panel = page.locator(f"#{panel_id}")
        close_btn = panel.locator(".btn-close, [data-bs-dismiss='offcanvas']").first
        close_btn.click()

        # Wait for panel to be hidden
        expect(panel).not_to_be_visible(timeout=self.animation_timeout)

    def confirm_modal_action(self, page: Page, modal_id: str = "confirmModal") -> None:
        """Click the confirm/primary action button in a modal."""
        modal = page.locator(f"#{modal_id}")
        confirm_btn = modal.locator(".btn-danger, .btn-primary").first
        confirm_btn.click()

    def submit_panel_form(self, page: Page, panel_id: str = "editPanel") -> None:
        """Submit the form within a slide panel."""
        panel = page.locator(f"#{panel_id}")
        submit_btn = panel.locator("button[type='submit'], .btn-primary").first
        submit_btn.click()

    def wait_for_ajax_complete(self, page: Page) -> None:
        """Wait for all AJAX requests to complete."""
        # Wait for HTMX requests to complete
        page.wait_for_function(
            "typeof htmx !== 'undefined' && !htmx.config.requestClass", timeout=self.ajax_timeout
        )

        # Wait for any loading indicators to disappear
        loading_indicators = page.locator(".loading, .spinner, [data-loading]")
        if loading_indicators.count() > 0:
            expect(loading_indicators.first).not_to_be_visible(timeout=self.ajax_timeout)

    def wait_for_list_update(self, page: Page, list_selector: str = ".list-container") -> None:
        """Wait for a list to update after an operation."""
        self.wait_for_ajax_complete(page)

        # Ensure the list container is visible and stable
        list_container = page.locator(list_selector)
        expect(list_container).to_be_visible(timeout=self.ajax_timeout)

    def get_list_item_count(self, page: Page, list_selector: str = ".list-container") -> int:
        """Get the number of items in a list."""
        items = page.locator(f"{list_selector} .list-item, {list_selector} tr[data-entity-id]")
        return items.count()

    def click_quick_action(
        self, page: Page, item_index: int, action: str, list_selector: str = ".list-container"
    ) -> None:
        """Click a quick action button for a specific list item."""
        item = page.locator(f"{list_selector} .list-item, {list_selector} tr").nth(item_index)
        action_btn = item.locator(f"[data-action='{action}'], .btn-{action}").first
        action_btn.click()

    def select_bulk_items(
        self, page: Page, indices: list, list_selector: str = ".list-container"
    ) -> None:
        """Select multiple items in a list for bulk operations."""
        for index in indices:
            checkbox = page.locator(f"{list_selector} input[type='checkbox']").nth(index)
            checkbox.check()

    def verify_notification(
        self, page: Page, message: str, notification_type: str = "success"
    ) -> None:
        """Verify that a notification message appears."""
        notification = page.locator(f".alert-{notification_type}, .toast-{notification_type}")
        expect(notification).to_be_visible(timeout=self.ajax_timeout)
        expect(notification).to_contain_text(message)

    def verify_form_validation_error(self, page: Page, field_name: str, error_message: str) -> None:
        """Verify that a form validation error is displayed."""
        field = page.locator(f"[name='{field_name}']")
        error_element = field.locator(
            "xpath=following-sibling::*[contains(@class, 'invalid-feedback') or contains(@class, 'error')]"
        ).first
        expect(error_element).to_be_visible()
        expect(error_element).to_contain_text(error_message)

    def check_keyboard_accessibility(self, page: Page, component_selector: str) -> None:
        """Test basic keyboard accessibility for a component."""
        component = page.locator(component_selector)
        expect(component).to_be_visible()

        # Test Escape key closes the component (if applicable)
        if "modal" in component_selector or "offcanvas" in component_selector:
            page.keyboard.press("Escape")
            expect(component).not_to_be_visible()

    def check_mobile_responsiveness(self, page: Page, component_selector: str) -> None:
        """Test that a component is responsive on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        component = page.locator(component_selector)
        expect(component).to_be_visible()

        # Verify component adapts to mobile size
        bounding_box = component.bounding_box()
        assert bounding_box["width"] <= 375, (
            f"Component width {bounding_box['width']} exceeds mobile viewport"
        )

    def measure_performance(self, page: Page, operation_name: str, operation_func) -> dict:
        """Measure the performance of an operation."""
        start_time = page.evaluate("performance.now()")

        # Execute the operation
        operation_func()

        end_time = page.evaluate("performance.now()")
        duration = end_time - start_time

        # Get additional performance metrics
        metrics = page.evaluate("""
            () => {
                const entries = performance.getEntriesByType('measure');
                const navigation = performance.getEntriesByType('navigation')[0];
                return {
                    domContentLoaded: navigation
                        ? navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart
                        : 0,
                    loadComplete: navigation ? navigation.loadEventEnd - navigation.loadEventStart : 0,
                };
            }
        """)

        return {
            "operation": operation_name,
            "duration_ms": duration,
            **metrics,
        }


class BaseCRUDTest(BaseE2ETest):
    """Base class for testing CRUD operations with the modern UX interface."""

    def test_create_workflow(
        self, page: Page, live_server, test_user, entity_type: str, form_data: dict
    ):
        """Test the complete create workflow for an entity."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, entity_type)

        # Click create button
        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()

        # Wait for create panel to open
        self.wait_for_panel(page)

        # Fill form
        for field_name, value in form_data.items():
            self.fill_form_field(page, field_name, value)

        # Submit form
        self.submit_panel_form(page)

        # Wait for success and panel to close
        self.wait_for_ajax_complete(page)
        expect(page.locator("#editPanel")).not_to_be_visible()

        # Verify entity was created (appears in list)
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text(str(list(form_data.values())[0]))

    def test_edit_workflow(
        self, page: Page, live_server, test_user, entity_type: str, item_index: int, form_data: dict
    ):
        """Test the complete edit workflow for an entity."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, entity_type)

        # Click edit button for first item
        self.click_quick_action(page, item_index, "edit")

        # Wait for edit panel to open
        self.wait_for_panel(page)

        # Verify form is populated with existing data
        for field_name, value in form_data.items():
            self.expect_form_field_populated(page, field_name, value)

        # Update form
        for field_name, value in form_data.items():
            self.fill_form_field(page, field_name, value)

        # Submit form
        self.submit_panel_form(page)

        # Wait for success and panel to close
        self.wait_for_ajax_complete(page)
        expect(page.locator("#editPanel")).not_to_be_visible()

        # Verify entity was updated
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text(str(list(form_data.values())[0]))

    def fill_form_field(self, page: Page, field_name: str, value):
        """Fill a form field using the appropriate browser interaction."""
        field = page.locator(f"[name='{field_name}']").first
        field_type = field.get_attribute("type")
        tag_name = field.evaluate("element => element.tagName.toLowerCase()")

        if field_type == "checkbox":
            if value:
                field.check()
            else:
                field.uncheck()
            return

        if field_type == "radio":
            page.locator(f"[name='{field_name}'][value='{value}']").check()
            return

        if tag_name == "select":
            field.select_option(str(value))
            return

        field.fill(str(value))

    def expect_form_field_populated(self, page: Page, field_name: str, value):
        """Assert an edit form field is populated using field-specific checks."""
        field = page.locator(f"[name='{field_name}']").first
        field_type = field.get_attribute("type")
        tag_name = field.evaluate("element => element.tagName.toLowerCase()")

        if field_type == "radio":
            expect(page.locator(f"[name='{field_name}'][value='{value}']")).to_be_checked()
            return

        if field_type == "checkbox":
            return

        if tag_name == "select":
            expect(field).not_to_have_value("")
            return

        expect(field).not_to_have_value("")

    def test_delete_workflow(
        self, page: Page, live_server, test_user, entity_type: str, item_index: int
    ):
        """Test the complete delete workflow for an entity."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, entity_type)

        # Get initial item count
        initial_count = self.get_list_item_count(page)

        # Click delete button for specified item
        self.click_quick_action(page, item_index, "delete")

        # Wait for delete confirmation modal
        self.wait_for_modal(page)

        # Confirm deletion
        self.confirm_modal_action(page)

        # Wait for success and modal to close
        self.wait_for_ajax_complete(page)
        expect(page.locator("#confirmModal")).not_to_be_visible()

        # Verify entity was deleted (item count decreased)
        self.wait_for_list_update(page)
        final_count = self.get_list_item_count(page)
        assert final_count == initial_count - 1, (
            f"Expected {initial_count - 1} items, got {final_count}"
        )
