"""Complete user workflow integration tests.

These tests verify end-to-end user workflows that span multiple operations
and demonstrate the full functionality of the modern UX interface.
"""

import re

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.integration
class TestCompleteUserWorkflows(BaseE2ETest):
    """Test complete user workflows from start to finish."""

    def get_row_by_compact_text(self, page: Page, *text_parts: str):
        """Return a list row whose Grid/table text may omit cell-boundary spaces."""
        pattern = re.compile(r"\s*".join(re.escape(part) for part in text_parts))
        row = self.get_list_items(page).filter(has_text=pattern).first
        expect(row).to_be_visible(timeout=self.ajax_timeout)
        return row

    def test_complete_person_management_workflow(self, page: Page, live_server, test_user):
        """Test complete workflow: create person, edit details, view relations, delete."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Create a new person
        create_btn = self.get_create_button(page)
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
        self.wait_for_panel_close(page)

        # Verify person was created
        self.wait_for_list_update(page)
        john_row = self.get_row_by_compact_text(page, "John", "Workflow")

        # Step 2: Edit the person's details
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
        self.wait_for_panel_close(page)

        # Verify update
        self.wait_for_list_update(page)
        jonathan_row = self.get_row_by_compact_text(page, "Jonathan", "Workflow")

        # Step 3: View person details
        detail_button = jonathan_row.locator("[data-action='detail']").first
        detail_button.click()

        # Wait for detail view (could be panel or modal)
        detail_panel = page.locator("#detailPanel")
        if detail_panel.count() > 0:
            self.wait_for_panel(page, "detailPanel")
            expect(detail_panel).to_contain_text(re.compile(r"Jonathan\s*Workflow"))
            self.close_panel(page, "detailPanel")

        # Step 4: Delete the person
        delete_btn = jonathan_row.locator("[data-action='delete']")
        delete_btn.click()
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_contain_text(re.compile(r"Jonathan\s*Workflow"))

        # Confirm deletion
        self.confirm_modal_action(page)
        self.wait_for_ajax_complete(page)
        expect(modal).not_to_be_visible()

        # Verify deletion
        self.wait_for_list_update(page)
        expect(
            self.get_list_items(page).filter(has_text=re.compile(r"Jonathan\s*Workflow"))
        ).to_have_count(0)

    def test_gift_planning_workflow(
        self, page: Page, live_server, test_user, sample_persons, sample_events
    ):
        """Test complete gift planning workflow: create gift, assign to person/event, manage relations."""
        self.login_as_user(page, live_server, test_user)

        # Step 1: Create a new gift
        self.navigate_to_entity_list(page, live_server, "gifts")

        create_btn = self.get_create_button(page)
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
        self.wait_for_panel_close(page)

        # Verify gift was created
        self.wait_for_list_update(page)
        expect(page.locator(".list-container")).to_contain_text("Workflow Test Gift")

        # Step 2: Create a relation between person and gift
        self.navigate_to_entity_list(page, live_server, "relations")

        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        expect(panel).to_be_visible()

        # Select recipient, gift, and event (if selectors are available)
        recipient_select = panel.locator("[name='recipient']")
        person_select = panel.locator("[name='person']")
        gift_select = panel.locator("[name='gift']")
        event_select = panel.locator("[name='event']")

        if recipient_select.count() > 0:
            recipient_select.select_option(index=1)  # Select first available recipient
        elif person_select.count() > 0:
            person_select.select_option(index=1)  # Select first available person

        if gift_select.count() > 0:
            # Try to select our created gift
            gift_options = gift_select.locator("option")
            selected_gift = False
            for i in range(gift_options.count()):
                option_text = gift_options.nth(i).text_content()
                if "Workflow Test Gift" in option_text:
                    gift_select.select_option(index=i)
                    selected_gift = True
                    break
            assert selected_gift, "Created gift should be available in relation gift options"

        if event_select.count() > 0 and event_select.locator("option").count() > 1:
            event_select.select_option(index=1)  # Select first available event

        # Submit relation creation
        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        self.wait_for_panel_close(page)

        # Verify relation was created
        gift_plan_card = page.locator(".gift-plan-card", has_text="Workflow Test Gift").first
        expect(gift_plan_card).to_be_visible(timeout=self.ajax_timeout)

        # Step 3: Update relation status
        if gift_plan_card.count() > 0:
            edit_btn = gift_plan_card.locator("[data-action='edit']").first
            edit_btn.click()
            self.wait_for_panel(page)

            expect(panel).to_be_visible()

            # Update status if available
            status_select = panel.locator("[name='status']")
            if status_select.count() > 0 and status_select.locator("option").count() > 1:
                status_select.select_option(index=1)  # Change to different status

            # Submit update
            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            self.wait_for_panel_close(page)

        # Step 4: Clean up - delete the gift
        self.navigate_to_entity_list(page, live_server, "gifts")

        # Find and delete our test gift
        gift_row = self.get_list_items(page).filter(has_text="Workflow Test Gift").first
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

        initial_count = self.get_list_item_count(page)

        # Step 1: Create multiple test persons for bulk operations
        test_persons = ["Bulk User 1", "Bulk User 2", "Bulk User 3"]

        for index, person_name in enumerate(test_persons, start=1):
            create_btn = self.get_create_button(page)
            create_btn.click()
            self.wait_for_panel(page)

            panel = page.locator("#editPanel")
            first_name_field = panel.locator("[name='first_name']")
            family_name_field = panel.locator("[name='family_name']")

            first_name_field.fill(person_name)
            family_name_field.fill("Test")

            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            self.wait_for_panel_close(page)
            self.wait_for_list_item_count(page, initial_count + index)

        # Refresh to see all created persons
        after_create_count = initial_count + len(test_persons)
        self.wait_for_list_item_count(page, after_create_count)

        # Step 2: Select multiple persons for bulk operations
        self.select_bulk_items(page, [0, 1, 2])

        # Step 3: Verify bulk actions toolbar appears
        bulk_toolbar = self.get_bulk_toolbar(page)
        if bulk_toolbar.count() > 0:
            expect(bulk_toolbar).to_be_visible()

            # Step 4: Perform bulk delete
            bulk_delete_btn = bulk_toolbar.locator("[data-action='bulk-delete'], .bulk-delete")
            if bulk_delete_btn.count() > 0:
                bulk_delete_btn.click()

                # Wait for bulk confirmation modal
                modal_id = self.wait_for_bulk_delete_modal(page)

                # Confirm bulk deletion
                self.confirm_modal_action(page, modal_id)
                self.wait_for_ajax_complete(page)

                # Verify bulk deletion completed
                self.wait_for_list_item_count(page, after_create_count - 3)

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
        navigation = page.locator("#navigation")
        gifts_link = navigation.locator(".nav-link[href$='/gifts/']")
        if gifts_link.count() > 0:
            gifts_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(re.compile(r"/gifts/$"))

        # Step 3: Navigate to events
        more_menu = navigation.locator("#navbarMoreDropdown")
        events_link = navigation.locator(".dropdown-item[href$='/events/']")
        if events_link.count() > 0:
            more_menu.click()
            events_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(re.compile(r"/events/$"))

        # Step 4: Navigate to Gift Plans
        relations_link = navigation.locator(".nav-link[href$='/relations/']")
        if relations_link.count() > 0:
            relations_link.click()
            page.wait_for_load_state("networkidle")
            expect(page).to_have_url(re.compile(r"/relations/$"))

        # Step 5: Test browser back/forward navigation
        page.go_back()
        page.wait_for_load_state("networkidle")

        page.go_forward()
        page.wait_for_load_state("networkidle")

        # Verify we're back at relations
        expect(page).to_have_url(re.compile(r"/relations/$"))

    def test_error_handling_workflow(self, page: Page, live_server, test_user):
        """Test error handling workflow: trigger errors, verify recovery."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Step 1: Test form validation errors
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()

        # Submit empty form to trigger client-side validation
        self.submit_panel_form(page)

        # Panel should remain open with errors
        expect(panel).to_be_visible()

        # Check for browser/client-side validation state
        first_name_field = panel.locator("[name='first_name']")
        assert first_name_field.evaluate("field => field.validity.valueMissing"), (
            "Required first name should be marked missing"
        )
        assert first_name_field.evaluate("field => field.matches(':invalid')"), (
            "Required first name should be invalid"
        )

        # Step 2: Fix errors and resubmit
        family_name_field = panel.locator("[name='family_name']")

        first_name_field.fill("Error Test")
        family_name_field.fill("User")

        self.submit_panel_form(page)
        self.wait_for_ajax_complete(page)
        self.wait_for_panel_close(page)

        # Step 3: Test network error handling (if possible)
        # This is difficult to test without mocking, but we can test timeout scenarios

        # Step 4: Clean up test data
        error_test_row = (
            self.get_list_items(page).filter(has_text=re.compile(r"Error Test\s*User")).first
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
    @pytest.mark.performance
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
        panel = page.locator("#editPanel")
        expect(panel).to_be_visible(timeout=self.ajax_timeout)
        expect(panel).to_have_class(re.compile(r"\bshow\b"))
        panel_open_time = page.evaluate("performance.now()")

        # Step 3: Submit form
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
        assert panel_open_duration < 2000, (
            f"Panel open took {panel_open_duration}ms, should be under 2000ms"
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

        # Step 1: Test keyboard activation of a row action
        edit_button = self.get_list_items(page).first.locator("[data-action='edit']").first
        expect(edit_button).to_be_visible(timeout=self.ajax_timeout)
        edit_button.focus()
        expect(edit_button).to_be_focused()

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
        self.wait_for_panel_close(page)

        # Step 4: Test modal accessibility
        delete_button = self.get_list_items(page).first.locator("[data-action='delete']").first
        expect(delete_button).to_be_visible(timeout=self.ajax_timeout)
        delete_button.focus()
        expect(delete_button).to_be_focused()

        # Activate delete with keyboard
        page.keyboard.press("Enter")
        self.wait_for_modal(page)

        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()

        # Test Escape key closes modal
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()

        # Verify focus management
        page.wait_for_function(
            "() => ['BUTTON', 'A', 'INPUT'].includes(document.activeElement?.tagName)",
            timeout=self.ajax_timeout,
        )
        focused_after_modal = page.evaluate("document.activeElement.tagName")
        assert focused_after_modal in ["BUTTON", "A", "INPUT"], (
            "Focus should return to actionable element"
        )
