"""Performance benchmark tests for the modern UX interface.

These tests measure and validate performance characteristics of the application
including page load times, AJAX response times, and user interaction latency.
"""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.performance
class TestPerformanceBenchmarks(BaseE2ETest):
    """Test performance characteristics and benchmarks."""

    def setup_method(self):
        """Set up performance testing configuration."""
        super().setup_method()
        self.performance_thresholds = {
            "page_load": 5000,  # 5 seconds max
            "modal_open": 1000,  # 1 second max
            "panel_open": 1000,  # 1 second max
            "form_submit": 3000,  # 3 seconds max
            "ajax_request": 2000,  # 2 seconds max
            "search_response": 1000,  # 1 second max
        }

    def measure_operation(self, page: Page, operation_name: str, operation_func):
        """Measure the performance of an operation."""
        # Clear performance marks
        page.evaluate("performance.clearMarks(); performance.clearMeasures();")

        start_time = page.evaluate("performance.now()")

        # Execute the operation
        result = operation_func()

        end_time = page.evaluate("performance.now()")
        duration = end_time - start_time

        # Get additional performance metrics
        metrics = page.evaluate("""
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                const resources = performance.getEntriesByType('resource');

                return {
                    domContentLoaded: navigation
                        ? navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart
                        : 0,
                    loadComplete: navigation ? navigation.loadEventEnd - navigation.loadEventStart : 0,
                    resourceCount: resources.length,
                    totalResourceSize: resources.reduce((sum, r) => sum + (r.transferSize || 0), 0)
                };
            }
        """)

        return {
            "operation": operation_name,
            "duration_ms": duration,
            "result": result,
            **metrics,
        }

    def test_page_load_performance(self, page: Page, live_server, test_user):
        """Test page load performance for different entity lists."""
        self.login_as_user(page, live_server, test_user)

        entity_types = ["persons", "gifts", "events", "relations"]

        for entity_type in entity_types:

            def load_page():
                page.goto(f"{live_server.url}/{entity_type}/")
                page.wait_for_load_state("networkidle")
                return page.url

            metrics = self.measure_operation(page, f"load_{entity_type}_page", load_page)

            # Assert performance threshold
            assert metrics["duration_ms"] < self.performance_thresholds["page_load"], (
                f"{entity_type} page load took {metrics['duration_ms']:.0f}ms, "
                f"should be under {self.performance_thresholds['page_load']}ms"
            )

            # Log metrics for analysis
            print(f"{entity_type.title()} Page Load Metrics:")
            print(f"  Total Time: {metrics['duration_ms']:.0f}ms")
            print(f"  DOM Content Loaded: {metrics['domContentLoaded']:.0f}ms")
            print(f"  Resources: {metrics['resourceCount']}")
            print(f"  Total Size: {metrics['totalResourceSize'] / 1024:.1f}KB")

    def test_modal_performance(self, page: Page, live_server, test_user, sample_persons):
        """Test modal dialog performance."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        def open_modal():
            self.click_quick_action(page, 0, "delete")
            self.wait_for_modal(page)
            return page.locator("#confirmModal").is_visible()

        metrics = self.measure_operation(page, "open_delete_modal", open_modal)

        assert metrics["duration_ms"] < self.performance_thresholds["modal_open"], (
            f"Modal open took {metrics['duration_ms']:.0f}ms, "
            f"should be under {self.performance_thresholds['modal_open']}ms"
        )

        assert metrics["result"], "Modal should be visible after opening"

        # Test modal close performance
        def close_modal():
            page.keyboard.press("Escape")
            modal = page.locator("#confirmModal")
            expect(modal).not_to_be_visible()
            return not modal.is_visible()

    def test_slide_panel_performance(self, page, live_server, test_user):
        """Test slide panel performance."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        def open_panel():
            self.click_quick_action(page, 0, "edit")
            self.wait_for_panel(page)
            return page.locator("#editPanel").is_visible()

        metrics = self.measure_operation(page, "open_edit_panel", open_panel)

        assert metrics["duration_ms"] < self.performance_thresholds["panel_open"], (
            f"Panel open took {metrics['duration_ms']:.0f}ms, "
            f"should be under {self.performance_thresholds['panel_open']}ms"
        )

        assert metrics["result"], "Panel should be visible after opening"

        # Test panel close performance
        def close_panel():
            page.keyboard.press("Escape")
            panel = page.locator("#editPanel")
            expect(panel).not_to_be_visible()
            return not panel.is_visible()

        close_metrics = self.measure_operation(page, "close_edit_panel", close_panel)

        assert close_metrics["duration_ms"] < 500, (
            f"Panel close took {close_metrics['duration_ms']:.0f}ms, should be under 500ms"
        )

        print("Panel Performance:")
        print(f"  Open Time: {metrics['duration_ms']:.0f}ms")
        print(f"  Close Time: {close_metrics['duration_ms']:.0f}ms")

    def test_form_submission_performance(self, page: Page, live_server, test_user):
        """Test form submission performance."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Open create form
        create_btn = self.get_create_button(page)
        create_btn.click()
        self.wait_for_panel(page)

        panel = page.locator("#editPanel")

        # Fill form
        first_name_field = panel.locator("[name='first_name']")
        family_name_field = panel.locator("[name='family_name']")

        first_name_field.fill("Performance Test")
        family_name_field.fill("User")

        def submit_form():
            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            expect(panel).not_to_be_visible()
            return not panel.is_visible()

        metrics = self.measure_operation(page, "submit_create_form", submit_form)

        assert metrics["duration_ms"] < self.performance_thresholds["form_submit"], (
            f"Form submission took {metrics['duration_ms']:.0f}ms, "
            f"should be under {self.performance_thresholds['form_submit']}ms"
        )

        assert metrics["result"], "Form should be submitted successfully"

        print(f"Form Submission Performance: {metrics['duration_ms']:.0f}ms")

        # Clean up - delete the created person
        self.wait_for_list_update(page)
        perf_test_row = (
            page.locator(".list-container").locator("text=Performance Test").locator("..").first
        )
        if perf_test_row.count() > 0:
            delete_btn = perf_test_row.locator("[data-action='delete']")
            delete_btn.click()
            self.wait_for_modal(page)
            self.confirm_modal_action(page)
            self.wait_for_ajax_complete(page)

    def test_search_performance(self, page: Page, live_server, test_user, sample_persons):
        """Test search functionality performance."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        search_input = page.locator("input[type='search'], .search-input")
        if search_input.count() > 0:

            def perform_search():
                search_input.fill("Alice")
                self.wait_for_list_update(page)
                return self.get_list_item_count(page)

            metrics = self.measure_operation(page, "search_persons", perform_search)

            assert metrics["duration_ms"] < self.performance_thresholds["search_response"], (
                f"Search took {metrics['duration_ms']:.0f}ms, "
                f"should be under {self.performance_thresholds['search_response']}ms"
            )

            print(f"Search Performance: {metrics['duration_ms']:.0f}ms")
            print(f"Results Found: {metrics['result']}")

            # Clear search
            search_input.fill("")
            self.wait_for_list_update(page)

    def test_bulk_operations_performance(self, page: Page, live_server, test_user, sample_persons):
        """Test bulk operations performance."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Create test data for bulk operations
        test_persons = []
        for i in range(5):
            create_btn = self.get_create_button(page)
            create_btn.click()
            self.wait_for_panel(page)

            panel = page.locator("#editPanel")
            first_name_field = panel.locator("[name='first_name']")
            family_name_field = panel.locator("[name='family_name']")

            first_name_field.fill(f"Bulk Test {i}")
            family_name_field.fill("User")

            self.submit_panel_form(page)
            self.wait_for_ajax_complete(page)
            test_persons.append(f"Bulk Test {i}")

        self.wait_for_list_update(page)

        # Test bulk selection performance
        checkboxes = page.locator(".list-container input[type='checkbox']")
        if checkboxes.count() >= 3:

            def select_bulk_items():
                self.select_bulk_items(page, [0, 1, 2])
                return 3

            select_metrics = self.measure_operation(page, "bulk_select", select_bulk_items)

            assert select_metrics["duration_ms"] < 1000, (
                f"Bulk selection took {select_metrics['duration_ms']:.0f}ms, should be under 1000ms"
            )

            # Test bulk delete performance (if available)
            bulk_toolbar = self.get_bulk_toolbar(page)
            if bulk_toolbar.count() > 0:
                bulk_delete_btn = bulk_toolbar.locator("[data-action='bulk-delete'], .bulk-delete")
                if bulk_delete_btn.count() > 0:

                    def perform_bulk_delete():
                        bulk_delete_btn.click()
                        modal_id = self.wait_for_bulk_delete_modal(page)
                        self.confirm_modal_action(page, modal_id)
                        self.wait_for_ajax_complete(page)
                        return True

                    bulk_metrics = self.measure_operation(page, "bulk_delete", perform_bulk_delete)

                    assert bulk_metrics["duration_ms"] < 5000, (
                        f"Bulk delete took {bulk_metrics['duration_ms']:.0f}ms, should be under 5000ms"
                    )

                    print("Bulk Operations Performance:")
                    print(f"  Selection: {select_metrics['duration_ms']:.0f}ms")
                    print(f"  Bulk Delete: {bulk_metrics['duration_ms']:.0f}ms")

    def test_memory_usage(self, page: Page, live_server, test_user, sample_persons):
        """Test memory usage during operations."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        # Get initial memory usage
        initial_memory = page.evaluate("""
            () => {
                if (performance.memory) {
                    return {
                        used: performance.memory.usedJSHeapSize,
                        total: performance.memory.totalJSHeapSize,
                        limit: performance.memory.jsHeapSizeLimit
                    };
                }
                return null;
            }
        """)

        if initial_memory:
            # Perform several operations
            for i in range(5):
                self.click_quick_action(page, 0, "edit")
                self.wait_for_panel(page)
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)

            # Get final memory usage
            final_memory = page.evaluate("""
                () => {
                    if (performance.memory) {
                        return {
                            used: performance.memory.usedJSHeapSize,
                            total: performance.memory.totalJSHeapSize,
                            limit: performance.memory.jsHeapSizeLimit
                        };
                    }
                    return null;
                }
            """)

            if final_memory:
                memory_increase = final_memory["used"] - initial_memory["used"]
                memory_increase_mb = memory_increase / (1024 * 1024)

                print("Memory Usage:")
                print(f"  Initial: {initial_memory['used'] / (1024 * 1024):.1f}MB")
                print(f"  Final: {final_memory['used'] / (1024 * 1024):.1f}MB")
                print(f"  Increase: {memory_increase_mb:.1f}MB")

                # Memory increase should be reasonable (less than 10MB for basic operations)
                assert memory_increase_mb < 10, (
                    f"Memory increase {memory_increase_mb:.1f}MB should be under 10MB"
                )

    def test_network_efficiency(self, page: Page, live_server, test_user, sample_persons):
        """Test network request efficiency."""
        self.login_as_user(page, live_server, test_user)

        # Monitor network requests
        requests = []
        responses = []

        def handle_request(request):
            requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "size": len(request.post_data or ""),
                    "timestamp": page.evaluate("performance.now()"),
                }
            )

        def handle_response(response):
            responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "size": len(response.body()) if response.body() else 0,
                    "timestamp": page.evaluate("performance.now()"),
                }
            )

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Perform operations that trigger AJAX requests
        self.navigate_to_entity_list(page, live_server, "persons")

        self.click_quick_action(page, 0, "edit")
        self.wait_for_panel(page)
        page.keyboard.press("Escape")

        self.click_quick_action(page, 0, "delete")
        self.wait_for_modal(page)
        page.keyboard.press("Escape")

        # Analyze network efficiency
        ajax_requests = [
            r
            for r in requests
            if "persons" in r["url"] and r["method"] in ["GET", "POST", "PUT", "DELETE"]
        ]
        ajax_responses = [r for r in responses if "persons" in r["url"] and r["status"] < 400]

        print("Network Efficiency:")
        print(f"  Total Requests: {len(requests)}")
        print(f"  AJAX Requests: {len(ajax_requests)}")
        print(f"  Successful Responses: {len(ajax_responses)}")

        if ajax_requests:
            total_request_size = sum(r["size"] for r in ajax_requests)
            total_response_size = sum(r["size"] for r in ajax_responses)

            print(f"  Request Size: {total_request_size / 1024:.1f}KB")
            print(f"  Response Size: {total_response_size / 1024:.1f}KB")

            # Requests should be reasonably sized
            assert total_request_size < 100 * 1024, (
                f"Total request size {total_request_size / 1024:.1f}KB should be under 100KB"
            )
            assert total_response_size < 500 * 1024, (
                f"Total response size {total_response_size / 1024:.1f}KB should be under 500KB"
            )

    @pytest.mark.parametrize(
        "viewport_size",
        [
            {"width": 1920, "height": 1080},  # Desktop
            {"width": 768, "height": 1024},  # Tablet
            {"width": 375, "height": 667},  # Mobile
        ],
    )
    def test_responsive_performance(
        self, page: Page, live_server, test_user, sample_persons, viewport_size
    ):
        """Test performance across different viewport sizes."""
        page.set_viewport_size(viewport_size)

        self.login_as_user(page, live_server, test_user)

        def load_and_interact():
            self.navigate_to_entity_list(page, live_server, "persons")
            self.click_quick_action(page, 0, "edit")
            self.wait_for_panel(page)
            page.keyboard.press("Escape")
            return True

        metrics = self.measure_operation(
            page,
            f"responsive_{viewport_size['width']}x{viewport_size['height']}",
            load_and_interact,
        )

        # Performance should be reasonable across all viewport sizes
        max_time = 8000 if viewport_size["width"] < 500 else 6000  # Allow more time for mobile
        assert metrics["duration_ms"] < max_time, (
            f"Responsive performance at {viewport_size['width']}x{viewport_size['height']} "
            f"took {metrics['duration_ms']:.0f}ms, should be under {max_time}ms"
        )

        print(
            f"Responsive Performance ({viewport_size['width']}x{viewport_size['height']}): "
            f"{metrics['duration_ms']:.0f}ms"
        )

    def test_concurrent_operations_performance(
        self, page: Page, live_server, test_user, sample_persons
    ):
        """Test performance when multiple operations are triggered rapidly."""
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")

        def rapid_operations():
            # Rapidly open and close panels
            for i in range(3):
                self.click_quick_action(page, 0, "edit")
                self.wait_for_panel(page)
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)  # Brief pause between operations
            return True

        metrics = self.measure_operation(page, "rapid_panel_operations", rapid_operations)

        # Rapid operations should complete within reasonable time
        assert metrics["duration_ms"] < 5000, (
            f"Rapid operations took {metrics['duration_ms']:.0f}ms, should be under 5000ms"
        )

        print(f"Concurrent Operations Performance: {metrics['duration_ms']:.0f}ms")

    def teardown_method(self):
        """Clean up after performance tests."""
        # Performance tests may create test data that needs cleanup
        # This is handled by the transactional database in conftest.py
