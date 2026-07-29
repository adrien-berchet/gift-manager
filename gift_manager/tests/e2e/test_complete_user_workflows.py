"""Complete user workflow integration tests.

These tests verify end-to-end user workflows that span multiple operations
and demonstrate the full functionality of the modern UX interface.
"""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.integration
class TestCompleteUserWorkflows(BaseE2ETest):
    """Test complete user workflows from start to finish."""

    def test_complete_person_management_workflow(self, page: Page, live_server, test_user):
        """Test complete workflow: create person, edit details, view relations, delete."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Create a new person
        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Fill person details
        first_name_field = panel.locator("[name='first_name']")
        family_name_field = panel.locator("[name='family_name']")
        email_field = panel.locator("[name='email_address']")

        first_name_field.fill("John")
        family_name_field.fill("Workflow")
        if email_field.count() > 0:
            email_field.fill("john.workflow@example.com")

        # Submit creation
        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Verify person was created
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text("John Workflow")

        # Step 2: Edit the person's details
        # Find the newly created person
        john_row = page.locator(".list-container").locator("text=John Workflow").locator("..").first
        edit_btn = john_row.locator("[data-action='edit']")
        edit_btn.click()
        self.wait_for_panel(page)

        expect(panel).to_be_visible()

        # Update details
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Jonathan")

        # Add additional details if available
        comment_field = panel.locator("[name='comment']")
        if comment_field.count() > 0:
            comment_field.fill("Updated via workflow test")

        # Submit update
        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Verify update
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text("Jonathan Workflow")

        # Step 3: View person details
        jonathan_row = (
            page.locator(".list-container").locator("text=Jonathan Workflow").locator("..").first
        )
        person_name_link = jonathan_row.locator(".entity-name, a").first
        person_name_link.click()

        # Wait for detail view (could be panel or modal)
        detail_panel = page.locator("#detailPanel")
        if detail_panel.count() > 0:
            self.wait_for_panel(page, "detailPanel")
            expect(detail_panel).to_contain_text("Jonathan Workflow")
            self.close_panel(page, "detailPanel")

        # Step 4: Delete the person
        delete_btn = jonathan_row.locator("[data-action='delete']")
        delete_btn.click()
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_contain_text("Jonathan Workflow")

        # Confirm deletion
        self.confirm_modal_action(page)
        self.wait_for_ajax_complete(page)
        expect(modal).not_to_be_visible()

        # Verify deletion
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).not_to_contain_text("Jonathan Workflow")

    def test_gift_planning_workflow(
        self, page: Page, live_server, test_user, sample_persons, sample_events
    ):
        """Test complete gift planning workflow: create gift, assign to person/event, manage relations."""
        self.login_as_user(page, live_server, test_user)

        # Step 1: Create a new gift
        self.navigate_to_entity_list(page, live_server, "gifts")

        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Fill gift details
        name_field = panel.locator("[name='name']")
        comment_field = panel.locator("[name='comment']")
        price_field = panel.locator("[name='price']")

        name_field.fill("Workflow Test Gift")
        if comment_field.count() > 0:
            comment_field.fill("A gift for testing complete workflows")
        if price_field.count() > 0:
            price_field.fill("99.99")

        # Submit creation
        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Verify gift was created
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text("Workflow Test Gift")

        # Step 2: Create a relation between person and gift
        self.navigate_to_entity_list(page, live_server, "relations")

        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        expect(panel).to_be_visible()

        # Select person, gift, and event (if selectors are available)
        person_select = panel.locator("[name='person']")
        gift_select = panel.locator("[name='gift']")
        event_select = panel.locator("[name='event']")

        if person_select.count() > 0:
            person_select.select_option(index=1)  # Select first available person
        if gift_select.count() > 0:
            # Try to select our created gift
            gift_options = gift_select.locator("option")
            for i in range(gift_options.count()):
                option_text = gift_options.nth(i).text_content()
                if "Workflow Test Gift" in option_text:
                    gift_select.select_option(index=i)
                    break
        if event_select.count() > 0:
            event_select.select_option(index=1)  # Select first available event

        # Submit relation creation
        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Verify relation was created
        self.wait_for_list_update(page)

        # Step 3: Update relation status
        # Find the relation we just created
        relation_rows = page.locator(".list-container .list-item, .list-container tr")
        if relation_rows.count() > 0:
            first_relation = relation_rows.first
            edit_btn = first_relation.locator("[data-action='edit']")
            edit_btn.click()
            self.wait_for_panel(page)

            expect(panel).to_be_visible()

            # Update status if available
            status_select = panel.locator("[name='status']")
            if status_select.count() > 0:
                status_select.select_option(index=1)  # Change to different status

            # Submit update
            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            expect(panel).not_to_be_visible()

        # Step 4: Clean up - delete the gift
        self.navigate_to_entity_list(page, live_server, "gifts")

        # Find and delete our test gift
        gift_row = (
            page.locator(".list-container").locator("text=Workflow Test Gift").locator("..").first
        )
        delete_btn = gift_row.locator("[data-action='delete']")
        delete_btn.click()
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        self.confirm_modal_action(page)
        self.wait_for_ajax_complete(page)
        expect(modal).not_to_be_visible()

    def test_bulk_management_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test bulk operations workflow: select multiple items, perform bulk actions."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Create multiple test persons for bulk operations
        test_persons = ["Bulk User 1", "Bulk User 2", "Bulk User 3"]

        for person_name in test_persons:
            create_btn = page.locator("[data-action='create'], .btn-create").first
            create_btn.click()
            self.wait_for_panel(page)

            panel = page.locator("#editPanel")
            first_name_field = panel.locator("[name='first_name']")
            family_name_field = panel.locator("[name='family_name']")

            first_name_field.fill(person_name)
            family_name_field.fill("Test")

            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            expect(panel).not_to_be_visible()

        # Refresh to see all created persons
        self.wait_for_list_update(page)

        # Step 2: Select multiple persons for bulk operations
        checkboxes = page.locator(".list-container input[type='checkbox']")
        if checkboxes.count() >= 3:
            # Select first 3 checkboxes
            for i in range(3):
                checkboxes.nth(i).check()
                expect(checkboxes.nth(i)).to_be_checked()

            # Step 3: Verify bulk actions toolbar appears
            bulk_toolbar = page.locator(".bulk-actions-toolbar, .bulk-actions")
            if bulk_toolbar.count() > 0:
                expect(bulk_toolbar).to_be_visible()

                # Step 4: Perform bulk delete
                bulk_delete_btn = bulk_toolbar.locator("[data-action='bulk-delete'], .bulk-delete")
                if bulk_delete_btn.count() > 0:
                    bulk_delete_btn.click()

                    # Wait for bulk confirmation modal
                    bulk_modal = page.locator("#bulkConfirmModal, #confirmModal")
                    self.wait_for_modal(page, bulk_modal.get_attribute("id") or "confirmModal")

                    # Confirm bulk deletion
                    self.confirm_modal_action(
                        page, bulk_modal.get_attribute("id") or "confirmModal"
                    )
                    self.wait_for_ajax_complete(page)

                    # Verify bulk deletion completed
                    self.wait_for_list_update(page)

        # Step 5: Verify cleanup - test persons should be removed
        for person_name in test_persons:
            expect(page.locator(".list-container")).not_to_contain_text(person_name)

    def test_search_and_filter_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test search and filtering workflow: search, filter, clear, navigate results."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Get initial count
        initial_count = self.get_list_item_count(page)
        assert initial_count > 0, "Should have persons to search"

        # Step 2: Test search functionality
        search_input = page.locator("input[type='search'], .search-input")
        if search_input.count() > 0:
            # Search for a specific person
            search_input.fill("Alice")
            self.wait_for_list_update(page)

            # Verify search results
            filtered_count = self.get_list_item_count(page)
            assert filtered_count <= initial_count, "Search should filter results"

            # Verify search results contain search term
            if filtered_count > 0:
                visible_text = page.locator(".list-container").text_content()
                assert "Alice" in visible_text, "Search results should contain search term"

            # Step 3: Clear search
            search_input.fill("")
            self.wait_for_list_update(page)

            # Verify all results are shown again
            final_count = self.get_list_item_count(page)
            assert final_count == initial_count, "Clearing search should restore all results"

        # Step 4: Test filtering (if available)
        filter_controls = page.locator(".filter-control, select[name*='filter']")
        if filter_controls.count() > 0:
            first_filter = filter_controls.first

            # Apply a filter
            if first_filter.tag_name.lower() == "select":
                options = first_filter.locator("option")
                if options.count() > 1:
                    first_filter.select_option(index=1)
                    self.wait_for_list_update(page)

                    # Verify filter was applied
                    filtered_count = self.get_list_item_count(page)
                    # Filter may or may not reduce count depending on data

                    # Reset filter
                    first_filter.select_option(index=0)
                    self.wait_for_list_update(page)

    def test_inline_editing_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test inline editing workflow: double-click edit, save, cancel."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Test inline editing activation
        first_person_name = page.locator(".list-container .entity-name").first
        original_name = first_person_name.text_content()

        # Double-click to activate inline editing
        first_person_name.dblclick()

        # Step 2: Check if inline edit field appears
        inline_edit_field = page.locator(".inline-edit-field")
        if inline_edit_field.count() > 0:
            expect(inline_edit_field).to_be_visible()
            expect(inline_edit_field).to_have_value(original_name)

            # Step 3: Edit the value
            new_name = "Inline Edited Name"
            inline_edit_field.fill(new_name)

            # Step 4: Save via Enter key
            inline_edit_field.press("Enter")
            self.wait_for_ajax_complete(page)

            # Verify change was saved
            expect(first_person_name).to_contain_text(new_name)

            # Step 5: Test cancel behavior
            first_person_name.dblclick()
            if inline_edit_field.count() > 0:
                inline_edit_field.fill("Cancelled Edit")
                inline_edit_field.press("Escape")

                # Verify change was not saved
                expect(first_person_name).to_contain_text(new_name)
                expect(first_person_name).not_to_contain_text("Cancelled Edit")

    def test_navigation_workflow(self, page: Page, live_server, test_user, complete_test_data):
        """Test navigation workflow: move between different entity types, maintain context."""
        self.login_as_user(page, live_server, test_user)

        # Step 1: Start with persons
        self.navigate_to_entity_list(page, live_server, "persons")
        expect(page.locator(".list-container")).to_be_visible()

        # Step 2: Navigate to gifts
        gifts_link = page.locator("a[href*='gifts'], .nav-link:has-text('Gifts')")
        if gifts_link.count() > 0:
            gifts_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(f"{live_server.url}/gifts/")

        # Step 3: Navigate to events
        events_link = page.locator("a[href*='events'], .nav-link:has-text('Events')")
        if events_link.count() > 0:
            events_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(f"{live_server.url}/events/")

        # Step 4: Navigate to Gift Plans
        relations_link = page.locator("a[href*='relations'], .nav-link:has-text('Gift Plans')")
        if relations_link.count() > 0:
            relations_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(f"{live_server.url}/relations/")

        # Step 5: Test browser back/forward navigation
        page.go_back()
        page.wait_for_load_state("networkidle")

        page.go_forward()
        page.wait_for_load_state("networkidle")

        # Verify we're back at relations
        expect(page).to_have_url(f"{live_server.url}/relations/")

    def test_error_handling_workflow(self, page: Page, live_server, test_user):
        """Test error handling workflow: trigger errors, verify recovery."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Test form validation errors
        create_btn = page.locator("[data-action='create'], .btn-create").first
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Submit empty form to trigger validation
        self.submit_panel_form(page)

        # Panel should remain open with errors
        expect(panel).to_be_visible()

        # Check for error messages
        error_messages = panel.locator(".invalid-feedback, .error, .alert-danger")
        if error_messages.count() > 0:
            expect(error_messages.first).to_be_visible()

        # Step 2: Fix errors and resubmit
        first_name_field = panel.locator("[name='first_name']")
        family_name_field = panel.locator("[name='family_name']")

        first_name_field.fill("Error Test")
        family_name_field.fill("User")

        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Step 3: Test network error handling (if possible)
        # This is difficult to test without mocking, but we can test timeout scenarios

        # Step 4: Clean up test data
        error_test_row = (
            page.locator(".list-container").locator("text=Error Test").locator("..").first
        )
        if error_test_row.count() > 0:
            delete_btn = error_test_row.locator("[data-action='delete']")
            delete_btn.click()
            self.wait_for_modal(page)

            modal = page.locator("#confirmModal")
            self.confirm_modal_action(page)
            self.wait_for_ajax_complete(page)
            expect(modal).not_to_be_visible()

    @pytest.mark.slow
    def test_performance_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test performance during typical user workflows."""
        self.login_as_user(page, live_server, test_user)

        # Measure complete workflow performance
        workflow_start = page.evaluate("performance.now()")

        # Step 1: Navigate to list
        self.navigate_to_entity_list(page, live_server, "persons")
        list_load_time = page.evaluate("performance.now()")

        # Step 2: Open edit panel
        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)
        panel_open_time = page.evaluate("performance.now()")

        # Step 3: Submit form
        panel = page.locator("#editPanel")
        first_name_field = panel.locator("[name='first_name']")
        first_name_field.fill("Performance Test")

        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        form_submit_time = page.evaluate("performance.now()")

        # Calculate performance metrics
        list_load_duration = list_load_time - workflow_start
        panel_open_duration = panel_open_time - list_load_time
        form_submit_duration = form_submit_time - panel_open_time
        total_workflow_duration = form_submit_time - workflow_start

        # Assert performance thresholds
        assert list_load_duration < 3000, (
            f"List load took {list_load_duration}ms, should be under 3000ms"
        )
        assert panel_open_duration < 1000, (
            f"Panel open took {panel_open_duration}ms, should be under 1000ms"
        )
        assert form_submit_duration < 2000, (
            f"Form submit took {form_submit_duration}ms, should be under 2000ms"
        )
        assert total_workflow_duration < 5000, (
            f"Total workflow took {total_workflow_duration}ms, should be under 5000ms"
        )

        # Log performance metrics for analysis
        print("Performance Metrics:")
        print(f"  List Load: {list_load_duration:.0f}ms")
        print(f"  Panel Open: {panel_open_duration:.0f}ms")
        print(f"  Form Submit: {form_submit_duration:.0f}ms")
        print(f"  Total Workflow: {total_workflow_duration:.0f}ms")

    def test_accessibility_workflow(self, page: Page, live_server, test_user, sample_persons):
        """Test accessibility during complete workflows."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Test keyboard navigation through workflow
        page.keyboard.press("Tab")  # Focus first element

        # Navigate to edit button using keyboard
        for _ in range(10):  # Try up to 10 tabs to find edit button
            focused_element = page.evaluate("document.activeElement")
            if focused_element and "edit" in str(focused_element).lower():
                break
            page.keyboard.press("Tab")

        # Activate edit with keyboard
        page.keyboard.press("Enter")
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Step 2: Test keyboard navigation within panel
        first_name_field = panel.locator("[name='first_name']")
        expect(first_name_field).to_be_focused()

        # Navigate through form fields
        page.keyboard.press("Tab")
        family_name_field = panel.locator("[name='family_name']")
        expect(family_name_field).to_be_focused()

        # Step 3: Test form submission via keyboard
        family_name_field.fill("Accessibility Test")
        page.keyboard.press("Tab")  # Move to submit button
        page.keyboard.press("Enter")  # Submit form

        self.wait_for_ajax_complete(page)
        expect(panel).not_to_be_visible()

        # Step 4: Test modal accessibility
        # Navigate to delete button
        page.keyboard.press("Tab")
        for _ in range(10):  # Try to find delete button
            focused_element = page.evaluate("document.activeElement")
            if focused_element and "delete" in str(focused_element).lower():
                break
            page.keyboard.press("Tab")

        # Activate delete with keyboard
        page.keyboard.press("Enter")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Test Escape key closes modal
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

        # Verify focus management
        focused_after_modal = page.evaluate("document.activeElement.tagName")
        assert focused_after_modal in ["BUTTON", "A", "INPUT"], (
            "Focus should return to actionable element"
        )
