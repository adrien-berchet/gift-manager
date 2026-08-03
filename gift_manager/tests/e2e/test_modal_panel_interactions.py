"""End-to-end tests for modal and panel interactions.

These tests verify that modals and slide panels work correctly with proper
animations, keyboard navigation, and accessibility features.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


class TestModalInteractions(BaseE2ETest):
    """Test modal dialog interactions and behaviors."""

    def test_delete_confirmation_modal_display(
        self, page: Page, live_server, test_user, sample_persons
    ):
        """Test that delete confirmation modal displays correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Click delete button for first person
        self.click_quick_action(page, 0, "delete")

        # Wait for modal to appear
        self.wait_for_modal(page)

        # Verify modal structure and content
        modal = page.locator("#confirmModal")
        expect(modal).to_have_class("modal")
        expect(modal).to_have_class("show")

        # Check modal header
        modal_title = modal.locator(".modal-title")
        expect(modal_title).to_be_visible()
        expect(modal_title).to_contain_text("Confirm")

        # Check modal body contains entity information
        modal_body = modal.locator(".modal-body")
        expect(modal_body).to_be_visible()
        expect(modal_body).to_contain_text("delete")

        # Check modal footer has correct buttons
        cancel_btn = modal.locator(".btn-secondary")
        expect(cancel_btn).to_be_visible()
        expect(cancel_btn).to_contain_text("Cancel")

        confirm_btn = modal.locator(".btn-danger")
        expect(confirm_btn).to_be_visible()
        expect(confirm_btn).to_contain_text("Delete")

    def test_modal_cancel_behavior(self, page: Page, live_server, test_user, sample_persons):
        """Test that canceling a modal works correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Get initial count
        initial_count = self.get_list_item_count(page)

        # Click delete button
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        # Click cancel button
        modal = page.locator("#confirmModal")
        cancel_btn = modal.locator(".btn-secondary")
        cancel_btn.click()

        # Verify modal closes
        expect(modal).not_to_be_visible()

        # Verify no deletion occurred
        final_count = self.get_list_item_count(page)
        assert final_count == initial_count, "Item was deleted despite canceling"

    def test_modal_escape_key_closes(self, page: Page, live_server, test_user, sample_persons):
        """Test that Escape key closes modal."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open modal
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        # Press Escape key
        page.keyboard.press("Escape")

        # Verify modal closes
        modal = page.locator("#confirmModal")
        expect(modal).not_to_be_visible()

    def test_modal_backdrop_click_closes(self, page: Page, live_server, test_user, sample_persons):
        """Test that clicking modal backdrop closes modal."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open modal
        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)

        # Click on backdrop (outside modal content)
        modal = page.locator("#confirmModal")
        modal_backdrop = modal.locator(".modal-backdrop")
        if modal_backdrop.count() > 0:
            modal_backdrop.click()
        else:
            # Click on modal itself but outside the content area
            modal.click(position={"x": 10, "y": 10})

        # Verify modal closes
        expect(modal).not_to_be_visible()


class TestPanelInteractions(BaseE2ETest):
    """Test slide panel (offcanvas) interactions and behaviors."""

    def test_edit_panel_display(self, page: Page, live_server, test_user, sample_persons):
        """Test that edit panel displays correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Click edit button for first person
        self.click_quick_action(page, 0, "edit")

        # Wait for panel to appear
        self.wait_for_panel(page)

        # Verify panel structure and content
        panel = page.locator("#editPanel")
        expect(panel).to_have_class("offcanvas")
        expect(panel).to_have_class("show")

        # Check panel header
        panel_title = panel.locator(".offcanvas-title")
        expect(panel_title).to_be_visible()
        expect(panel_title).to_contain_text("Edit")

        # Check panel body contains form
        panel_body = panel.locator(".offcanvas-body")
        expect(panel_body).to_be_visible()

        form = panel_body.locator("form")
        expect(form).to_be_visible()

        # Check form has required fields
        first_name_field = form.locator("[name='first_name']")
        expect(first_name_field).to_be_visible()
        expect(first_name_field).not_to_have_value("")

        family_name_field = form.locator("[name='family_name']")
        expect(family_name_field).to_be_visible()
        expect(family_name_field).not_to_have_value("")

    def test_panel_form_submission(self, page: Page, live_server, test_user, sample_persons):
        """Test that panel form submission works correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Click edit button
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Update form fields
        panel = page.locator("#editPanel")
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Updated Name")

        # Submit form
        self.submit_panel_form(page)

        # Wait for panel to close and list to update
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Verify update was successful
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text("Updated Name")

    def test_panel_cancel_behavior(self, page: Page, live_server, test_user, sample_persons):
        """Test that canceling panel form works correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Get original name
        original_name = page.locator(".list-container .entity-name").first.text_content()

        # Click edit button
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Make changes to form
        panel = page.locator("#editPanel")
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Changed Name")

        # Close panel without saving
        self.close_panel(page)

        # Verify changes were not saved
        current_name = page.locator(".list-container .entity-name").first.text_content()
        assert current_name == original_name, "Changes were saved despite canceling"

    def test_panel_escape_key_closes(self, page: Page, live_server, test_user, sample_persons):
        """Test that Escape key closes panel."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Press Escape key
        page.keyboard.press("Escape")

        # Verify panel closes
        panel = page.locator("#editPanel")
        expect(panel).not_to_be_visible()

    def test_create_panel_display(self, page: Page, live_server, test_user):
        """Test that create panel displays correctly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Click create button
        create_btn = self.get_create_button(page)
        create_btn.click()

        # Wait for panel to appear
        self.wait_for_panel(page)

        # Verify panel structure
        panel = page.locator("#editPanel")
        expect(panel).to_have_class("offcanvas")
        expect(panel).to_have_class("show")

        # Check panel title indicates creation
        panel_title = panel.locator(".offcanvas-title")
        expect(panel_title).to_contain_text("Create", case_sensitive=False)

        # Check form fields are empty
        form = panel.locator("form")
        first_name_field = form.locator("[name='first_name']")
        expect(first_name_field).to_have_value("")

        family_name_field = form.locator("[name='family_name']")
        expect(family_name_field).to_have_value("")


class TestPanelFormValidation(BaseE2ETest):
    """Test form validation within panels."""

    def test_required_field_validation(self, page: Page, live_server, test_user):
        """Test that required field validation works in panels."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create panel
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        # Try to submit empty form
        self.submit_panel_form(page)

        # Verify validation errors appear
        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()  # Panel should remain open

        # Check for validation error messages
        error_messages = panel.locator(".invalid-feedback, .error")
        expect(error_messages.first).to_be_visible()

    def test_form_validation_clears_on_correction(self, page: Page, live_server, test_user):
        """Test that validation errors clear when fields are corrected."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create panel
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        # Submit empty form to trigger validation
        self.submit_panel_form(page)

        # Verify error appears
        panel = page.locator("#editPanel")
        error_message = panel.locator(".invalid-feedback, .error").first
        expect(error_message).to_be_visible()

        # Fill required field
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("John")

        # Verify error clears (may need to trigger validation)
        first_name_field.blur()
        expect(error_message).not_to_be_visible()


class TestUnsavedChangesProtection(BaseE2ETest):
    """Test unsaved changes protection in panels."""

    def test_unsaved_changes_warning(self, page: Page, live_server, test_user, sample_persons):
        """Test that unsaved changes trigger warning when closing panel."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open edit panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Make changes to form
        panel = page.locator("#editPanel")
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Modified Name")

        # Try to close panel
        close_btn = panel.locator(".btn-close")
        close_btn.click()

        # Verify warning dialog appears
        warning_dialog = page.locator(".unsaved-changes-warning, .confirm-dialog")
        expect(warning_dialog).to_be_visible()

        # Verify warning message
        expect(warning_dialog).to_contain_text("unsaved changes")

    def test_unsaved_changes_visual_indicators(
        self, page: Page, live_server, test_user, sample_persons
    ):
        """Test that modified fields show visual indicators."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open edit panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)

        # Make changes to form
        panel = page.locator("#editPanel")
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Modified Name")

        # Verify field shows modified indicator
        expect(first_name_field).to_have_class("modified")

        # Or check for other visual indicators
        modified_indicator = panel.locator(".field-modified, .unsaved-indicator")
        if modified_indicator.count() > 0:
            expect(modified_indicator).to_be_visible()
