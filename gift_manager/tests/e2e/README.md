# End-to-End Testing with Playwright

This directory contains comprehensive end-to-end tests for the Gift Manager application's modern UX interface. These tests verify complete user workflows using real browsers and complement the existing unit and integration tests.

## Overview

The e2e tests validate:
- Complete CRUD workflows with modals and slide panels
- Cross-browser compatibility (Chromium, Firefox, WebKit)
- Mobile responsiveness and touch interactions
- Keyboard navigation and accessibility features
- Performance characteristics and loading states
- Real-time search and filtering functionality
- Bulk operations and inline editing

## Test Organization

```
gift_manager/tests/e2e/
├── __init__.py                     # Package initialization and documentation
├── conftest.py                     # Shared fixtures and configuration
├── base_test.py                    # Base test classes and utilities
├── test_crud_workflows.py          # Complete CRUD operation tests
├── test_modal_panel_interactions.py # Modal and panel behavior tests
├── test_accessibility.py           # Keyboard navigation and a11y tests
├── test_mobile_responsive.py       # Mobile device and responsive tests
├── test_performance.py             # Performance and loading time tests
└── README.md                       # This documentation file
```

## Prerequisites

### 1. Install Dependencies

```bash
# Install Python dependencies including Playwright
pip install -e .[test]

# Or install specific packages
pip install pytest pytest-playwright playwright pytest-django
```

### 2. Install Browser Binaries

```bash
# Install all browsers
python -m playwright install

# Or install specific browsers
python -m playwright install chromium firefox webkit

# Install system dependencies (Linux/macOS)
python -m playwright install-deps
```

### 3. Database Setup

The tests use the same testing database configuration as unit tests. Ensure your `GiftManager/settings/testing.py` is properly configured:

```python
# For PostgreSQL (recommended for full compatibility)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "gift_manager_test",
        "USER": "gift_manager",
        "PASSWORD": "gift_manager",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# For SQLite (quick local testing, some features may not work)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "test_db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA cache=shared;",  # Required for live_server
        },
    }
}
```

## Running Tests

### Basic Usage

```bash
# Run all e2e tests with default browser (Chromium)
pytest gift_manager/tests/e2e/ -v

# Run with specific browser
pytest gift_manager/tests/e2e/ --browser firefox -v

# Run with multiple browsers
pytest gift_manager/tests/e2e/ --browser chromium --browser firefox --browser webkit -v
```

### Advanced Options

```bash
# Run in headed mode (show browser window)
pytest gift_manager/tests/e2e/ --headed -v

# Run with video recording
pytest gift_manager/tests/e2e/ --video on -v

# Run with screenshots on failure
pytest gift_manager/tests/e2e/ --screenshot only-on-failure -v

# Run specific test file
pytest gift_manager/tests/e2e/test_crud_workflows.py -v

# Run specific test class
pytest gift_manager/tests/e2e/test_crud_workflows.py::TestPersonCRUDWorkflow -v

# Run specific test method
pytest gift_manager/tests/e2e/test_crud_workflows.py::TestPersonCRUDWorkflow::test_person_create_workflow -v
```

### Test Filtering

```bash
# Run only mobile tests
pytest gift_manager/tests/e2e/ -m "mobile" -v

# Run only accessibility tests
pytest gift_manager/tests/e2e/ -m "accessibility" -v

# Run only fast tests (exclude slow performance tests)
pytest gift_manager/tests/e2e/ -m "not slow" -v

# Run integration tests
pytest gift_manager/tests/e2e/ -m "integration" -v
```

### Using Tox for E2E Testing

```bash
# Run e2e tests with single browser (convenient for development)
tox -e e2e

# Run e2e tests in debug mode (headed, verbose output)
tox -e e2e-debug

# Run mobile-specific tests
tox -e e2e-mobile

# Run full cross-browser testing
tox -e py311-playwright
```

## Test Configuration

### Tox Integration

The e2e tests are integrated with tox for consistent testing environments:

```bash
# Run e2e tests with tox
tox -e py311-playwright

# Run with specific browser
tox -e py311-playwright -- --browser firefox

# Run with multiple Python versions
tox -e py310-playwright,py311-playwright,py312-playwright
```

### Environment Variables

Key environment variables for configuration:

```bash
# Django settings
export DJANGO_SETTINGS_MODULE="GiftManager.settings.testing"
export DJANGO_ENV="testing"

# Database configuration (if using PostgreSQL)
export DB_NAME="gift_manager_test"
export DB_USER="gift_manager"
export DB_PASSWORD="gift_manager"
export DB_HOST="localhost"
export DB_PORT="5432"

# Playwright configuration
export PLAYWRIGHT_BROWSERS_PATH="/path/to/browsers"  # Optional
export HEADED="true"  # Run in headed mode
export SLOW_MO="1000"  # Slow down actions by 1 second
```

## Writing Tests

### Base Test Classes

Use the provided base classes for consistent test structure:

```python
from gift_manager.tests.e2e.base_test import BaseE2ETest, BaseCRUDTest

class TestMyFeature(BaseE2ETest):
    """Test my feature with common utilities."""

    def test_my_workflow(self, page, live_server, test_user):
        self.login_as_user(page, live_server, test_user)
        self.navigate_to_entity_list(page, live_server, "persons")
        # ... test implementation
```

### Test Fixtures

Common fixtures available in `conftest.py`:

- `test_user`: Basic test user for authentication
- `test_admin_user`: Admin user with elevated permissions
- `sample_persons`: List of sample Person objects
- `sample_groups`: Dictionary of sample PersonGroup objects
- `sample_gifts`: List of sample Gift objects
- `sample_events`: List of sample Event objects
- `complete_test_data`: Complete set of related test data

### Helper Functions

Utility functions for common interactions:

```python
def test_modal_interaction(self, page, live_server, test_user):
    # Login and navigate
    self.login_as_user(page, live_server, test_user)
    self.navigate_to_entity_list(page, live_server, "persons")

    # Trigger modal
    self.click_quick_action(page, 0, "delete")
    self.wait_for_modal(page)

    # Interact with modal
    self.confirm_modal_action(page)
    self.wait_for_ajax_complete(page)
```

### Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.slow
class TestPerformance(BaseE2ETest):
    """Performance tests that take longer to run."""

    @pytest.mark.mobile
    def test_mobile_performance(self, page, live_server):
        """Test performance on mobile devices."""
        pass
```

## Debugging Tests

### Visual Debugging

```bash
# Run in headed mode to see browser
pytest gift_manager/tests/e2e/ --headed -v

# Slow down actions for observation
SLOW_MO=1000 pytest gift_manager/tests/e2e/ --headed -v

# Enable Playwright debug mode
PLAYWRIGHT_DEBUG=1 pytest gift_manager/tests/e2e/ --headed -v
```

### Screenshots and Videos

```bash
# Take screenshots on failure
pytest gift_manager/tests/e2e/ --screenshot only-on-failure -v

# Record videos of all tests
pytest gift_manager/tests/e2e/ --video on -v

# Record videos only on failure
pytest gift_manager/tests/e2e/ --video retain-on-failure -v
```

### Traces and Debugging

```bash
# Enable trace recording
pytest gift_manager/tests/e2e/ --tracing on -v

# View traces in Playwright trace viewer
playwright show-trace test-results/trace.zip
```

### Adding Debug Points

```python
def test_with_debugging(self, page, live_server, test_user):
    self.login_as_user(page, live_server, test_user)

    # Pause execution for manual inspection
    page.pause()

    # Take screenshot for debugging
    page.screenshot(path="debug_screenshot.png")

    # Print page content
    print(page.content())
```

## Performance Considerations

### Test Execution Time

- **Unit tests**: ~10-50ms per test
- **E2E tests**: ~2-5 seconds per test
- **Full e2e suite**: ~5-15 minutes depending on browser count

### Optimization Tips

1. **Use appropriate test markers** to run only necessary tests during development
2. **Run single browser** for development, all browsers for CI
3. **Use headless mode** for faster execution
4. **Limit parallel execution** if system resources are constrained
5. **Use test data fixtures** efficiently to minimize setup time

### CI/CD Integration

The tests are configured for GitHub Actions with:
- Parallel execution across browsers
- Artifact collection for test results
- Trace collection on failures
- PostgreSQL service for full database compatibility

## Troubleshooting

### Common Issues

1. **Browser installation fails**
   ```bash
   # Try manual installation
   python -m playwright install chromium
   python -m playwright install-deps
   ```

2. **Database connection errors**
   ```bash
   # Check database configuration in testing.py
   # Ensure PostgreSQL is running (if using PostgreSQL)
   # Verify SQLite shared cache configuration (if using SQLite)
   ```

3. **Tests timeout**
   ```bash
   # Increase timeout in conftest.py or test methods
   # Check for slow network or system performance
   # Verify Django server starts correctly
   ```

4. **Element not found errors**
   ```bash
   # Check selectors in test code
   # Verify page loads completely before interaction
   # Use page.wait_for_selector() for dynamic content
   ```

### Getting Help

1. Check the [Playwright documentation](https://playwright.dev/python/)
2. Review existing test examples in this directory
3. Use `page.pause()` to inspect page state during test execution
4. Enable debug mode with `PLAYWRIGHT_DEBUG=1`
5. Check test output and screenshots in `test-results/` directory

## Best Practices

1. **Keep tests focused**: One workflow per test method
2. **Use meaningful test names**: Describe what is being tested
3. **Leverage fixtures**: Reuse test data and setup code
4. **Wait for elements**: Use explicit waits instead of sleep
5. **Test real user workflows**: Focus on complete user journeys
6. **Maintain test independence**: Each test should be able to run in isolation
7. **Use appropriate assertions**: Prefer Playwright's expect() for better error messages
8. **Document complex tests**: Add comments for non-obvious test logic

## Contributing

When adding new e2e tests:

1. Follow the existing test structure and naming conventions
2. Use the base test classes and helper functions
3. Add appropriate test markers for categorization
4. Include both positive and negative test cases
5. Test across different browsers when relevant
6. Update this documentation if adding new patterns or utilities
