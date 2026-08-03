"""Base test class and utilities for end-to-end tests.

This module provides a base test class with common functionality for all e2e tests,
including setup, teardown, and utility methods for interacting with the modern UX interface.
"""

import re

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
        expect(modal).to_have_class(re.compile(r"\bshow\b"))

        # Wait for modal animation to complete
        page.wait_for_timeout(self.animation_timeout)

    def wait_for_bulk_delete_modal(self, page: Page) -> str:
        """Wait for the bulk delete confirmation modal and return its id."""
        modal = page.locator(
            "#bulk-delete-modal:visible, #bulkConfirmModal:visible, #confirmModal:visible"
        ).first
        expect(modal).to_be_visible(timeout=self.ajax_timeout)
        expect(modal).to_have_class(re.compile(r"\bshow\b"))

        # Wait for modal animation to complete
        page.wait_for_timeout(self.animation_timeout)
        return modal.get_attribute("id") or "confirmModal"

    def wait_for_panel(
        self, page: Page, panel_id: str = "editPanel", timeout: int | None = None
    ) -> None:
        """Wait for a slide panel to appear and be fully visible."""
        panel = page.locator(f"#{panel_id}")
        expect(panel).to_be_visible(timeout=timeout or self.ajax_timeout)
        expect(panel).to_have_class(re.compile(r"\bshow\b"))

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

        def accept_dialog(dialog):
            dialog.accept()

        page.on("dialog", accept_dialog)
        try:
            close_btn.click()
        finally:
            page.remove_listener("dialog", accept_dialog)
        page.wait_for_timeout(400)
        unsaved_modal = page.locator("#unsaved-changes-modal")
        if unsaved_modal.count() > 0 and unsaved_modal.is_visible():
            unsaved_modal.locator("#discard-changes-btn").click()
            page.wait_for_timeout(400)
        if panel.is_visible():
            panel.evaluate("""
                element => {
                    const offcanvas = window.bootstrap?.Offcanvas?.getInstance(element)
                        || window.bootstrap?.Offcanvas?.getOrCreateInstance(element);
                    if (offcanvas) {
                        offcanvas.hide();
                    }
                }
            """)
            page.wait_for_timeout(400)
        self.wait_for_panel_close(page, panel_id)

    def wait_for_panel_close(self, page: Page, panel_id: str = "editPanel") -> None:
        """Wait for a slide panel to be hidden."""
        panel = page.locator(f"#{panel_id}")
        expect(panel).not_to_be_visible(timeout=self.ajax_timeout)

    def confirm_modal_action(self, page: Page, modal_id: str = "confirmModal") -> None:
        """Click the confirm/primary action button in a modal."""
        modal = page.locator(f"#{modal_id}")
        confirm_btn = modal.locator("#confirm-bulk-delete, .btn-danger, .btn-primary").first
        confirm_btn.click()

    def submit_panel_form(self, page: Page, panel_id: str = "editPanel") -> None:
        """Submit the form within a slide panel."""
        panel = page.locator(f"#{panel_id}")
        submit_btn = panel.locator("button[type='submit'].btn-primary").first
        expect(submit_btn).to_be_visible(timeout=self.ajax_timeout)
        page.evaluate("""
            () => {
                document.activeElement?.blur?.();
                document.querySelectorAll(".flatpickr-input").forEach((input) => {
                    input._flatpickr?.close();
                });
            }
        """)
        submit_btn.click()

    def wait_for_ajax_complete(self, page: Page) -> None:
        """Wait for all AJAX requests to complete."""
        # Wait for HTMX requests to complete
        page.wait_for_function(
            """
            () => {
                if (typeof window.htmx === 'undefined') return true;
                const requestClass = window.htmx.config?.requestClass || 'htmx-request';
                return document.querySelectorAll(`.${requestClass}`).length === 0;
            }
            """,
            timeout=self.ajax_timeout,
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
        items = self.get_list_items(page, list_selector)
        return items.count()

    def get_list_items(self, page: Page, list_selector: str = ".list-container"):
        """Return list item rows across legacy list markup and Grid.js tables."""
        return page.locator(
            f"{list_selector} .list-item, "
            f"{list_selector} tr[data-entity-id], "
            f"{list_selector} tbody tr.gridjs-tr"
        )

    def wait_for_list_item_count(
        self, page: Page, expected_count: int, list_selector: str = ".list-container"
    ) -> None:
        """Wait until the visible list has the expected number of items."""
        expect(self.get_list_items(page, list_selector)).to_have_count(
            expected_count, timeout=self.ajax_timeout
        )

    def click_quick_action(
        self, page: Page, item_index: int, action: str, list_selector: str = ".list-container"
    ) -> None:
        """Click a quick action button for a specific list item."""
        item = self.get_list_items(page, list_selector).nth(item_index)
        action_btn = item.locator(f"[data-action='{action}'], .btn-{action}").first
        expect(action_btn).to_be_visible(timeout=self.ajax_timeout)
        expect(action_btn).to_be_enabled(timeout=self.ajax_timeout)
        action_btn.click()

    def get_create_button(self, page: Page):
        """Return the visible page-level create button, not hidden global-search shortcuts."""
        return page.locator(
            ".page-header-actions [data-action='create'], "
            ".page-header [data-action='create'], "
            "[data-action='create'].btn-primary:visible, "
            ".btn-create:visible"
        ).first

    def get_bulk_toolbar(self, page: Page):
        """Return the bulk actions toolbar without matching its nested controls twice."""
        return page.locator(".bulk-actions-toolbar, .bulk-actions").first

    def show_bulk_selection_checkboxes(self, page: Page, list_selector: str = ".list-container"):
        """Enter bulk-selection mode and return row checkbox locators."""
        checkboxes = page.locator(
            f"{list_selector} .bulk-select-item, "
            f"{list_selector} input[type='checkbox']:not(.bulk-select-all)"
        )
        if checkboxes.count() > 0 and not checkboxes.first.is_visible():
            toggle_btn = page.locator("[id^='toggle-selection-']").first
            if toggle_btn.count() > 0:
                advanced_tools = page.locator("details.advanced-list-tools").first
                if advanced_tools.count() > 0 and not toggle_btn.is_visible():
                    advanced_tools.evaluate("element => { element.open = true; }")
                    expect(toggle_btn).to_be_visible(timeout=self.ajax_timeout)
                toggle_btn.click()
                page.evaluate("""
                    () => new Promise(resolve => {
                        requestAnimationFrame(() => requestAnimationFrame(resolve));
                    })
                """)
                expect(checkboxes.first).to_be_visible(timeout=self.ajax_timeout)

        expect(checkboxes.first).to_be_visible(timeout=self.ajax_timeout)
        return checkboxes

    def click_bulk_checkbox(self, checkbox) -> None:
        """Click a bulk checkbox and verify its checked state."""
        checkbox.click(timeout=self.ajax_timeout)
        expect(checkbox).to_be_checked(timeout=self.ajax_timeout)

    def select_bulk_items(
        self, page: Page, indices: list, list_selector: str = ".list-container"
    ) -> None:
        """Select multiple items in a list for bulk operations."""
        checkboxes = self.show_bulk_selection_checkboxes(page, list_selector)

        for index in indices:
            checkbox = checkboxes.nth(index)
            self.click_bulk_checkbox(checkbox)

        selected_count = self.get_bulk_toolbar(page).locator(".selected-count").first
        expect(selected_count).to_have_text(str(len(indices)), timeout=self.ajax_timeout)

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

    def run_create_workflow(
        self, page: Page, live_server, test_user, entity_type: str, form_data: dict
    ):
        """Test the complete create workflow for an entity."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, entity_type)

        # Click create button
        create_btn = self.get_create_button(page)
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

    def run_edit_workflow(
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
        field.evaluate("element => element.blur()")

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

    def run_delete_workflow(
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
