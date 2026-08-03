"""Pytest configuration and fixtures for end-to-end tests.

This module provides specialized fixtures for Playwright-based end-to-end testing,
including browser configuration, test data setup, and utility functions for
interacting with the modern UX interface components.
"""

import pytest
from allauth.account.models import EmailAddress
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

# =============================================================================
# Seed Data Fixtures
# =============================================================================


@pytest.fixture
def seed_data_e2e(transactional_db):
    """Deterministic seed dataset for Playwright E2E tests.

    Returns a :class:`~gift_manager.seed_data.SeedData` frozen dataclass.
    Uses ``transactional_db`` which is required by the live-server fixture.
    """
    from gift_manager.seed_data import create_seed_data

    return create_seed_data()


# =============================================================================
# Browser Configuration
# =============================================================================


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for e2e tests with modern UX requirements."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
        "permissions": ["clipboard-read", "clipboard-write"],
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
        },
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, browser_name):
    """Configure browser launch arguments for different browsers."""
    base_args = {
        **browser_type_launch_args,
        "headless": True,  # Override with --headed for debugging
    }

    # Browser-specific configurations
    if browser_name == "chromium":
        base_args["args"] = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",  # For AJAX testing
            "--disable-features=VizDisplayCompositor",
        ]
    elif browser_name == "firefox":
        base_args["firefox_user_prefs"] = {
            "dom.webnotifications.enabled": False,
            "media.navigator.permission.disabled": True,
        }

    return base_args


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def test_user(transactional_db):
    """Create a test user for authentication in e2e tests."""
    user = UserFactory(
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
    )
    EmailAddress.objects.create(
        user=user,
        email="test@example.com",
        primary=True,
        verified=True,
    )
    return user


@pytest.fixture
def test_admin_user(transactional_db):
    """Create an admin user for testing admin-specific functionality."""
    user = UserFactory(
        username="admin",
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
    )
    EmailAddress.objects.create(
        user=user,
        email="admin@example.com",
        primary=True,
        verified=True,
    )
    return user


@pytest.fixture
def sample_persons(transactional_db, test_user):
    """Create sample persons for testing list operations."""
    return [
        PersonFactory(first_name="Alice", family_name="Johnson", user_link=test_user),
        PersonFactory(first_name="Bob", family_name="Smith", user_link=test_user),
        PersonFactory(first_name="Carol", family_name="Williams", user_link=test_user),
        PersonFactory(first_name="David", family_name="Brown", user_link=test_user),
        PersonFactory(first_name="Eve", family_name="Davis", user_link=test_user),
    ]


@pytest.fixture
def sample_groups(transactional_db):
    """Create sample person groups with hierarchy."""
    family = PersonGroupFactory(name="Family")
    friends = PersonGroupFactory(name="Friends")
    work = PersonGroupFactory(name="Work Colleagues")
    close_friends = PersonGroupFactory(name="Close Friends", parent_groups=[friends])
    return {
        "family": family,
        "friends": friends,
        "work": work,
        "close_friends": close_friends,
    }


@pytest.fixture
def sample_gifts(transactional_db):
    """Create sample gifts for testing."""
    return [
        GiftFactory(name="Smartphone", comment="Latest model"),
        GiftFactory(name="Book", comment="Programming guide"),
        GiftFactory(name="Coffee Mug", comment="Personalized"),
        GiftFactory(name="Headphones", comment="Noise cancelling"),
    ]


@pytest.fixture
def sample_events(transactional_db):
    """Create sample events for testing."""
    return [
        EventFactory(name="Birthday", recurrence="yearly"),
        EventFactory(name="Anniversary", recurrence="yearly"),
        EventFactory(name="Christmas", recurrence="yearly"),
        EventFactory(name="Graduation", schedule_type="one_time", recurrence=None),
    ]


@pytest.fixture
def complete_test_data(
    transactional_db, sample_persons, sample_groups, sample_gifts, sample_events
):
    """Create a complete set of test data with relations."""
    status = RelationStatusFactory(status="Idea")

    # Create some relations
    relations = []
    for i, person in enumerate(sample_persons[:3]):
        gift = sample_gifts[i % len(sample_gifts)]
        event = sample_events[i % len(sample_events)]
        relation = RelationFactory(
            person=person,
            gift=gift,
            event=event,
            status=status,
        )
        relations.append(relation)

    return {
        "persons": sample_persons,
        "groups": sample_groups,
        "gifts": sample_gifts,
        "events": sample_events,
        "relations": relations,
        "status": status,
    }


# =============================================================================
# Page Interaction Utilities
# =============================================================================


@pytest.fixture
def login_user():
    """Utility function to log in a user via the web interface."""

    def _login(page: Page, live_server, user, password="testpass123"):
        """Log in the specified user."""
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="login"]', user.username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        # Wait for successful login (redirect to dashboard or home)
        page.wait_for_url(f"{live_server.url}/", timeout=5000)

        # Verify login was successful
        expect(page.locator("body")).not_to_contain_text("Sign In")

    return _login


@pytest.fixture
def modal_helpers():
    """Utility functions for interacting with modal dialogs."""

    def _wait_for_modal(page: Page, modal_id="confirmModal", timeout=5000):
        """Wait for a modal to appear and be visible."""
        modal = page.locator(f"#{modal_id}")
        expect(modal).to_be_visible(timeout=timeout)
        return modal

    def _close_modal(page: Page, modal_id="confirmModal"):
        """Close a modal dialog."""
        modal = page.locator(f"#{modal_id}")
        close_btn = modal.locator(".btn-close, [data-bs-dismiss='modal']").first
        close_btn.click()
        expect(modal).not_to_be_visible()

    def _confirm_modal_action(page: Page, modal_id="confirmModal"):
        """Click the confirm/primary action button in a modal."""
        modal = page.locator(f"#{modal_id}")
        confirm_btn = modal.locator(".btn-danger, .btn-primary").first
        confirm_btn.click()

    return {
        "wait_for_modal": _wait_for_modal,
        "close_modal": _close_modal,
        "confirm_action": _confirm_modal_action,
    }


@pytest.fixture
def panel_helpers():
    """Utility functions for interacting with slide panels (offcanvas)."""

    def _wait_for_panel(page: Page, panel_id="editPanel", timeout=5000):
        """Wait for a slide panel to appear and be visible."""
        panel = page.locator(f"#{panel_id}")
        expect(panel).to_be_visible(timeout=timeout)
        expect(panel).to_have_class("show")
        return panel

    def _close_panel(page: Page, panel_id="editPanel"):
        """Close a slide panel."""
        panel = page.locator(f"#{panel_id}")
        close_btn = panel.locator(".btn-close, [data-bs-dismiss='offcanvas']").first
        close_btn.click()
        expect(panel).not_to_be_visible()

    def _submit_panel_form(page: Page, panel_id="editPanel"):
        """Submit the form within a slide panel."""
        panel = page.locator(f"#{panel_id}")
        submit_btn = panel.locator("button[type='submit'], .btn-primary").first
        submit_btn.click()

    return {
        "wait_for_panel": _wait_for_panel,
        "close_panel": _close_panel,
        "submit_form": _submit_panel_form,
    }


@pytest.fixture
def list_helpers():
    """Utility functions for interacting with enhanced list views."""

    def _wait_for_list_update(page: Page, list_selector=".list-container", timeout=5000):
        """Wait for a list to update after an operation."""
        # Wait for any loading indicators to disappear
        page.wait_for_selector(".loading-indicator", state="hidden", timeout=1000)

        # Wait for the list container to be stable
        list_container = page.locator(list_selector)
        expect(list_container).to_be_visible(timeout=timeout)

        return list_container

    def _select_list_items(page: Page, indices, list_selector=".list-container"):
        """Select multiple items in a list by their indices."""
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
                    expect(toggle_btn).to_be_visible()
                toggle_btn.click()
                page.evaluate("""
                    () => new Promise(resolve => {
                        requestAnimationFrame(() => requestAnimationFrame(resolve));
                    })
                """)
                expect(checkboxes.first).to_be_visible()

        expect(checkboxes.first).to_be_visible()
        for index in indices:
            checkbox = checkboxes.nth(index)
            checkbox.click()
            expect(checkbox).to_be_checked()

        selected_count = page.locator(".bulk-actions-toolbar, .bulk-actions").first.locator(
            ".selected-count"
        )
        expect(selected_count).to_have_text(str(len(indices)))

    def _get_quick_action_button(page: Page, item_index, action, list_selector=".list-container"):
        """Get a quick action button for a specific list item."""
        item = page.locator(
            f"{list_selector} .list-item, "
            f"{list_selector} tr[data-entity-id], "
            f"{list_selector} tbody tr.gridjs-tr"
        ).nth(item_index)
        return item.locator(f"[data-action='{action}']")

    return {
        "wait_for_update": _wait_for_list_update,
        "select_items": _select_list_items,
        "get_action_button": _get_quick_action_button,
    }


@pytest.fixture
def accessibility_helpers():
    """Utility functions for testing accessibility features."""

    def _test_keyboard_navigation(page: Page, start_selector, expected_stops):
        """Test keyboard navigation through a sequence of elements."""
        page.locator(start_selector).focus()

        for expected_selector in expected_stops:
            page.keyboard.press("Tab")
            expected_element = page.locator(expected_selector)
            expect(expected_element).to_be_focused()

    def _test_escape_key_closes(page: Page, component_selector):
        """Test that Escape key closes a component."""
        component = page.locator(component_selector)
        expect(component).to_be_visible()

        page.keyboard.press("Escape")
        expect(component).not_to_be_visible()

    def _check_aria_attributes(page: Page, selector, expected_attributes):
        """Check that an element has the expected ARIA attributes."""
        element = page.locator(selector)
        for attr, expected_value in expected_attributes.items():
            actual_value = element.get_attribute(f"aria-{attr}")
            assert actual_value == expected_value, (
                f"Expected aria-{attr}='{expected_value}', got '{actual_value}'"
            )

    return {
        "test_keyboard_nav": _test_keyboard_navigation,
        "test_escape_closes": _test_escape_key_closes,
        "check_aria": _check_aria_attributes,
    }


# =============================================================================
# Performance Testing Utilities
# =============================================================================


@pytest.fixture
def performance_helpers():
    """Utility functions for performance testing."""

    def _measure_page_load_time(page: Page, url):
        """Measure page load time and return metrics."""
        start_time = page.evaluate("performance.now()")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        end_time = page.evaluate("performance.now()")

        load_time = end_time - start_time

        # Get additional performance metrics
        metrics = page.evaluate("""
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                return {
                    domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                    loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                    firstPaint: performance.getEntriesByName('first-paint')[0]?.startTime || 0,
                    firstContentfulPaint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0,
                };
            }
        """)

        return {
            "total_load_time": load_time,
            **metrics,
        }

    def _measure_ajax_response_time(page: Page, trigger_selector, expected_response_selector):
        """Measure AJAX operation response time."""
        start_time = page.evaluate("performance.now()")

        page.click(trigger_selector)
        page.wait_for_selector(expected_response_selector, state="visible")

        end_time = page.evaluate("performance.now()")
        return end_time - start_time

    return {
        "measure_page_load": _measure_page_load_time,
        "measure_ajax": _measure_ajax_response_time,
    }


# =============================================================================
# Mobile Testing Configuration
# =============================================================================


@pytest.fixture
def mobile_context_args():
    """Browser context configuration for mobile testing."""
    return {
        "viewport": {"width": 375, "height": 667},  # iPhone SE size
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
    }


@pytest.fixture
def tablet_context_args():
    """Browser context configuration for tablet testing."""
    return {
        "viewport": {"width": 768, "height": 1024},  # iPad size
        "user_agent": (
            "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
    }
