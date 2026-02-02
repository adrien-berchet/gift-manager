"""End-to-end tests for Gift Manager using Playwright.

This package contains comprehensive end-to-end tests that verify complete user workflows
using real browsers. These tests complement the existing unit and integration tests by
validating the full user experience including JavaScript interactions, AJAX operations,
and cross-browser compatibility.

Test Organization:
- conftest.py: Shared fixtures and configuration for e2e tests
- test_crud_workflows.py: Complete CRUD operation workflows
- test_modal_interactions.py: Modal dialog interactions and behaviors
- test_panel_interactions.py: Slide panel interactions and behaviors
- test_accessibility.py: Keyboard navigation and screen reader support
- test_mobile_responsive.py: Mobile device and responsive design tests
- test_performance.py: Performance and loading time tests

Usage:
    # Run all e2e tests
    pytest gift_manager/tests/e2e/ -v

    # Run with specific browser
    pytest gift_manager/tests/e2e/ --browser firefox

    # Run with multiple browsers
    pytest gift_manager/tests/e2e/ --browser chromium --browser firefox --browser webkit

    # Run in headed mode for debugging
    pytest gift_manager/tests/e2e/ --headed

    # Run with video recording
    pytest gift_manager/tests/e2e/ --video on
"""
