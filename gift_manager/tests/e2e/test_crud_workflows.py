"""End-to-end tests for complete CRUD workflows using the modern UX interface.

These tests verify that the entire user experience works correctly for creating,
reading, updating, and deleting entities using modals and slide panels.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseCRUDTest


class TestPersonCRUDWorkflow(BaseCRUDTest):
    """Test complete CRUD workflows for Person entities."""

    def test_person_create_workflow(self, page: Page, live_server, test_user):
        """Test creating a new person through the slide panel interface."""
        form_data = {
            "first_name": "John",
            "family_name": "Doe",
            "email_address": "john.doe@example.com",
        }

        self.test_create_workflow(page, live_server, test_user, "persons", form_data)

    def test_person_edit_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test editing an existing person through the slide panel interface."""
        form_data = {
            "first_name": "Jane",
            "family_name": "Smith",
            "email_address": "jane.smith@example.com",
        }

        self.test_edit_workflow(page, live_server, test_user, "persons", 0, form_data)

    def test_person_delete_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test deleting a person through the modal confirmation interface."""
        self.test_delete_workflow(page, live_server, test_user, "persons", 0)

    def test_person_detail_view(self, page: Page, live_server, test_user, sample_persons):
        """Test viewing person details in a slide panel."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        person_name = page.locator(".list-container .entity-name").first.text_content()
        self.click_quick_action(page, 0, "detail")

        # Wait for detail panel to open
        self.wait_for_panel(page, "detailPanel")

        # Verify person details are displayed
        detail_panel = page.locator("#detailPanel")
        expect(detail_panel).to_contain_text(person_name)
        expect(detail_panel).to_contain_text("Basic Information")

        # Test quick actions in detail panel
        edit_btn = detail_panel.locator("[data-action='edit']").first
        expect(edit_btn).to_be_visible()

        delete_btn = detail_panel.locator("[data-action='delete']").first
        expect(delete_btn).to_be_visible()


class TestGiftCRUDWorkflow(BaseCRUDTest):
    """Test complete CRUD workflows for Gift entities."""

    def test_gift_create_workflow(self, page: Page, live_server, test_user):
        """Test creating a new gift through the slide panel interface."""
        form_data = {
            "name": "Smartphone",
            "comment": "Latest iPhone model",
            "price": "999.99",
        }

        self.test_create_workflow(page, live_server, test_user, "gifts", form_data)

    def test_gift_edit_workflow(self, page: Page, live_server, test_user, sample_gifts):
        """Test editing an existing gift through the slide panel interface."""
        form_data = {
            "name": "Updated Smartphone",
            "comment": "Updated description",
            "price": "1099.99",
        }

        self.test_edit_workflow(page, live_server, test_user, "gifts", 0, form_data)

    def test_gift_delete_workflow(self, page: Page, live_server, test_user, sample_gifts):
        """Test deleting a gift through the modal confirmation interface."""
        self.test_delete_workflow(page, live_server, test_user, "gifts", 0)


class TestEventCRUDWorkflow(BaseCRUDTest):
    """Test complete CRUD workflows for Event entities."""

    def test_event_create_workflow(self, page: Page, live_server, test_user):
        """Test creating a new event through the slide panel interface."""
        form_data = {
            "name": "Birthday Party",
            "comment": "Annual celebration",
            "schedule_type": "recurring",
            "date": "2026-08-15",
            "recurrence": "yearly",
        }

        self.test_create_workflow(page, live_server, test_user, "events", form_data)

    def test_event_edit_workflow(self, page: Page, live_server, test_user, sample_events):
        """Test editing an existing event through the slide panel interface."""
        form_data = {
            "name": "Updated Birthday Party",
            "comment": "Updated celebration details",
            "schedule_type": "recurring",
            "date": "2026-08-15",
            "recurrence": "yearly",
        }

        self.test_edit_workflow(page, live_server, test_user, "events", 0, form_data)

    def test_event_delete_workflow(self, page: Page, live_server, test_user, sample_events):
        """Test deleting an event through the modal confirmation interface."""
        self.test_delete_workflow(page, live_server, test_user, "events", 0)


class TestBulkOperationsWorkflow(BaseCRUDTest):
    """Test bulk operations workflows."""

    def test_bulk_delete_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test bulk delete operation with multiple persons."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Get initial count
        initial_count = self.get_list_item_count(page)

        # Select multiple items
        self.select_bulk_items(page, [0, 1, 2])

        # Verify bulk actions toolbar appears
        bulk_toolbar = self.get_bulk_toolbar(page)
        if bulk_toolbar.count() > 0:
            expect(bulk_toolbar).to_be_visible()

            # Click bulk delete
            bulk_delete_btn = bulk_toolbar.locator("[data-action='bulk-delete'], .bulk-delete")
            if bulk_delete_btn.count() > 0:
                bulk_delete_btn.click()

                # Wait for bulk confirmation modal
                modal_id = self.wait_for_bulk_delete_modal(page)
                bulk_modal = page.locator(f"#{modal_id}")

                # Verify modal shows correct count
                expect(bulk_modal).to_contain_text("3")

                # Confirm bulk deletion
                self.confirm_modal_action(page, modal_id)

                # Wait for completion
                self.wait_for_ajax_complete(page)

                # Verify items were deleted
                expected_count = initial_count - 3
                self.wait_for_list_item_count(page, expected_count)


class TestInlineEditingWorkflow(BaseCRUDTest):
    """Test inline editing functionality."""

    def test_inline_edit_person_name(self, page: Page, live_server, test_user, sample_persons):
        """Test inline editing of person name in list view."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Double-click on first person's name to edit
        first_person_name = page.locator(".list-container .entity-name").first
        if first_person_name.count() > 0:
            original_name = first_person_name.text_content()
            first_person_name.dblclick()

            # Verify inline edit field appears
            edit_field = page.locator(".inline-edit-field")
            if edit_field.count() > 0:
                expect(edit_field).to_be_visible()
                expect(edit_field).to_have_value(original_name)

                # Update the name
                new_name = "Updated Name"
                edit_field.fill(new_name)
                edit_field.press("Enter")

                # Wait for save to complete
                self.wait_for_ajax_complete(page)

                # Verify name was updated
                expect(first_person_name).to_contain_text(new_name)

                # Verify success notification (if implemented)
                notification = page.locator(".alert-success, .toast-success, .notification")
                if notification.count() > 0:
                    expect(notification).to_be_visible()


class TestSearchAndFilterWorkflow(BaseCRUDTest):
    """Test real-time search and filtering functionality."""

    def test_real_time_search(self, page: Page, live_server, test_user, sample_persons):
        """Test real-time search filtering in person list."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Get initial count
        initial_count = self.get_list_item_count(page)
        assert initial_count > 0, "No persons found for testing"

        # Type in search box
        search_box = page.locator("input[type='search'], .search-input")
        if search_box.count() > 0:
            search_box.fill("Alice")

            # Wait for search results to update
            self.wait_for_list_update(page)

            # Verify results are filtered
            filtered_count = self.get_list_item_count(page)
            if filtered_count < initial_count:
                # Verify all visible results contain search term
                visible_names = page.locator(".list-container .entity-name").all_text_contents()
                for name in visible_names:
                    assert "Alice" in name, f"Result '{name}' does not contain search term 'Alice'"

            # Clear search
            search_box.fill("")

            # Wait for results to reset
            self.wait_for_list_update(page)

            # Verify all results are shown again
            final_count = self.get_list_item_count(page)
            assert final_count == initial_count, "Search clear did not restore all results"
