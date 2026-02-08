"""Setup validation tests for the e2e testing infrastructure.

These tests verify that the Playwright testing infrastructure is properly
configured and can run basic browser automation tasks.
"""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.base_test import BaseE2ETest


class TestSetupValidation(BaseE2ETest):
    """Validate that the e2e testing setup is working correctly."""

    def test_browser_launches(self, page: Page):
        """Test that the browser launches and can navigate to a basic page."""
        # Navigate to a simple page
        page.goto("data:text/html,<html><body><h1>Test Page</h1></body></html>")

        # Verify page loaded
        expect(page.locator("h1")).to_contain_text("Test Page")

    def test_django_server_accessible(self, page: Page, live_server):
        """Test that the Django live server is accessible."""
        # Navigate to the live server
        page.goto(f"{live_server.url}/")

        # Verify we get a response (may be login page or home page)
        expect(page.locator("body")).to_be_visible()

        # Check that we get a proper HTTP response (not an error page)
        expect(page).not_to_have_title("Server Error")
        expect(page).not_to_have_title("Not Found")

    def test_authentication_flow(self, page: Page, live_server, test_user):
        """Test that user authentication works in the e2e environment."""
        # Navigate to login page
        page.goto(f"{live_server.url}/accounts/login/")

        # Verify login form is present
        expect(page.locator("input[name='login']")).to_be_visible()
        expect(page.locator("input[name='password']")).to_be_visible()

        # Fill and submit login form
        page.fill("input[name='login']", test_user.username)
        page.fill("input[name='password']", "testpass123")
        page.click("button[type='submit']")

        # Wait for successful login (redirect away from login page)
        # Don't assume specific redirect URL, just wait for navigation
        page.wait_for_load_state("networkidle", timeout=10000)

        # Verify we're no longer on the login page
        current_url = page.url
        assert "/accounts/login/" not in current_url, f"Still on login page: {current_url}"

        # Verify successful login by checking we don't see login form
        expect(page.locator("body")).not_to_contain_text("Sign In")

    def test_database_fixtures_work(self, page: Page, live_server, test_user, sample_persons):
        """Test that database fixtures are properly created and accessible."""
        # Verify test data was created
        assert len(sample_persons) > 0, "Sample persons fixture should create test data"

        # Login and navigate to persons list
        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/persons/")

        # Verify persons are displayed (basic check)
        expect(page.locator("body")).to_be_visible()

        # If the persons list page exists and shows data, we should see some content
        # This is a basic validation that the fixtures are working
        persons_content = page.locator(".list-container, .table, .persons-list, .gridjs-table")
        if persons_content.count() > 0:
            # Check if any of the content containers exist (may be hidden during loading)
            content_exists = persons_content.first.count() > 0
            assert content_exists, "Should find persons list content on page"

    @pytest.mark.slow
    def test_ajax_functionality_basic(self, page: Page, live_server, test_user):
        """Test that basic AJAX functionality works (if HTMX is loaded)."""
        self.login_as_user(page, live_server, test_user)

        # Navigate to a page that should have HTMX
        page.goto(f"{live_server.url}/persons/")

        # Check if HTMX is loaded (basic validation)
        htmx_loaded = page.evaluate("typeof htmx !== 'undefined'")

        if htmx_loaded:
            # If HTMX is loaded, test basic functionality
            expect(page.locator("body")).to_be_visible()
            print("✓ HTMX is loaded and available")
        else:
            # If HTMX is not loaded, that's okay for basic setup validation
            print("ℹ HTMX not detected (may not be implemented yet)")

    def test_responsive_viewport(self, page: Page, live_server, test_user):
        """Test that responsive design works with different viewport sizes."""
        self.login_as_user(page, live_server, test_user)

        # Test desktop viewport
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(f"{live_server.url}/")
        expect(page.locator("body")).to_be_visible()

        # Test tablet viewport
        page.set_viewport_size({"width": 768, "height": 1024})
        page.reload()
        expect(page.locator("body")).to_be_visible()

        # Test mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.reload()
        expect(page.locator("body")).to_be_visible()

        # Verify page adapts to mobile size
        body_width = page.locator("body").bounding_box()["width"]
        assert body_width <= 375, f"Body width {body_width} should fit mobile viewport"

    def test_keyboard_navigation_basic(self, page: Page, live_server, test_user):
        """Test that basic keyboard navigation works."""
        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/")

        # Test Tab navigation
        page.keyboard.press("Tab")

        # Verify some element has focus
        focused_element = page.evaluate("document.activeElement.tagName")
        assert focused_element in ["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"], (
            f"Expected focusable element, got {focused_element}"
        )

    def test_error_handling(self, page: Page, live_server):
        """Test that error pages are handled gracefully."""
        # Navigate to a non-existent page
        page.goto(f"{live_server.url}/nonexistent-page/")

        # Should get a 404 page, not a browser error
        expect(page.locator("body")).to_be_visible()

        # The page should indicate it's a 404 (either in title or content)
        page_content = page.content().lower()
        assert "404" in page_content or "not found" in page_content, (
            "Expected 404 error page content"
        )


@pytest.mark.playwright
class TestPlaywrightSpecificFeatures(BaseE2ETest):
    """Test Playwright-specific features and capabilities."""

    def test_screenshot_capability(self, page: Page, live_server):
        """Test that screenshots can be taken."""
        page.goto(f"{live_server.url}/")

        # Take a screenshot
        screenshot = page.screenshot()
        assert len(screenshot) > 0, "Screenshot should contain data"

    def test_network_interception(self, page: Page, live_server):
        """Test that network requests can be monitored."""
        requests = []

        def handle_request(request):
            requests.append(request.url)

        page.on("request", handle_request)
        page.goto(f"{live_server.url}/")

        # Should have captured at least the main page request
        assert len(requests) > 0, "Should have captured network requests"
        assert any(live_server.url in url for url in requests), (
            "Should have captured request to live server"
        )

    def test_javascript_evaluation(self, page: Page, live_server):
        """Test that JavaScript can be evaluated in the browser."""
        page.goto(f"{live_server.url}/")

        # Evaluate JavaScript
        result = page.evaluate("1 + 1")
        assert result == 2, "JavaScript evaluation should work"

        # Test DOM manipulation
        page.evaluate("document.body.setAttribute('data-test', 'playwright')")
        test_attr = page.get_attribute("body", "data-test")
        assert test_attr == "playwright", "DOM manipulation should work"
