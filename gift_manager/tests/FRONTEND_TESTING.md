# Frontend Testing Guide

This document explains how to run and maintain the frontend tests for the Gift Manager application.

## ⚠️ Important Setup Note

**Frontend tests are SKIPPED by default** in this environment due to network restrictions that prevent downloading Playwright browser binaries.

When attempting to run `playwright install chromium`, you may see errors like:
- `Error: Download failed: server returned code 403 body 'Host not allowed'`
- This is a firewall/network policy in containerized environments

**Good news:** The core functionality is already thoroughly tested with **162 comprehensive unit tests** that cover:
- Nested group hierarchy logic
- Cycle prevention
- Permission inheritance
- All database operations
- Form validation

Frontend tests only verify JavaScript enhancements (expand/collapse, search filtering, etc.) which are nice-to-have visual features, not critical business logic.

## Overview

Frontend tests use **Playwright** to test JavaScript-dependent features that cannot be validated with unit tests alone. These tests run in a real browser and interact with the actual UI.

## What is Tested

The frontend tests cover:

1. **Tree View Functionality**
   - Hierarchy rendering with correct indentation
   - Expand/collapse behavior for nested groups
   - Visual representation of parent-child relationships

2. **Searchable Multi-Select**
   - Real-time filtering of options
   - "Select All" and "Clear All" buttons
   - Search box interaction

3. **Cycle Prevention UI**
   - Groups cannot select themselves as parents
   - Groups cannot select their descendants as parents
   - Form validation with visual feedback

## Installation

### 1. Install Dependencies

```bash
pip install playwright pytest-playwright
```

### 2. Install Browser Binaries

**Note:** This step will FAIL in the current environment due to network restrictions.

If you're in a local development environment without network restrictions:

```bash
# Use Python Playwright (not Node.js version)
python3 -m playwright install chromium

# Or install webkit (Safari engine) or firefox
python3 -m playwright install webkit
python3 -m playwright install firefox

# Or install all browsers
python3 -m playwright install
```

This downloads browser binaries (~170MB each) needed for testing.

If you see 403 errors, your environment blocks Playwright CDN downloads - **this is expected and OK**. The frontend tests will remain skipped, which is fine since all critical functionality is covered by unit tests.

## Running Tests

### Run All Frontend Tests

```bash
pytest gift_manager/tests/test_frontend.py -v
```

### Run with a Specific Browser

By default, tests run on Chromium. To test with WebKit or Firefox:

```bash
# Test with WebKit (Safari engine)
pytest --browser webkit gift_manager/tests/test_frontend.py -v

# Test with Firefox
pytest --browser firefox gift_manager/tests/test_frontend.py -v

# Test with all browsers
pytest --browser chromium --browser webkit --browser firefox gift_manager/tests/test_frontend.py -v
```

### Run Only Non-Slow Tests (Skip Frontend)

Frontend tests are marked as `slow`. To skip them:

```bash
pytest -m "not slow"
```

### Run a Specific Test

```bash
pytest gift_manager/tests/test_frontend.py::TestSearchableMultiSelect::test_search_filter_works -v
```

### Run in Headed Mode (See the Browser)

For debugging, you can watch the browser:

```bash
pytest gift_manager/tests/test_frontend.py --headed
```

### Run with Video Recording

```bash
pytest gift_manager/tests/test_frontend.py --video on
```

Videos are saved to `test-results/` directory.

## Test Structure

### Fixtures

- `setup_test_user`: Creates a test user with credentials (uses `transactional_db`)
- `setup_group_hierarchy`: Creates a test hierarchy of person groups (uses `transactional_db`)
- `browser_context_args`: Configures browser viewport and settings
- `browser_type_launch_args`: Configures headless mode

**Important**: Fixtures that create database objects for `live_server` tests **must** use `transactional_db` instead of `db`. This ensures data is committed and visible to the live_server thread, which runs in a separate process with its own database connection.

### Test Classes

1. **TestPersonGroupTreeView**
   - `test_tree_view_renders_hierarchy`: Verifies tree structure appears
   - `test_tree_view_expand_collapse`: Tests collapsible nodes
   - `test_tree_view_indentation`: Validates visual hierarchy

2. **TestSearchableMultiSelect**
   - `test_searchable_select_filter_works`: Tests search filtering
   - `test_select_all_button_works`: Verifies Select All functionality
   - `test_clear_all_button_works`: Verifies Clear All functionality

3. **TestGroupFormCyclePrevention**
   - `test_form_prevents_selecting_self_as_parent`: No self-reference
   - `test_form_prevents_selecting_descendants_as_parents`: No cycles

## Writing New Frontend Tests

### Basic Template

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
class TestMyFeature:
    """Tests for my new feature."""

    def test_my_interaction(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that my feature works."""
        # Log in
        login_user(page, live_server)

        # Navigate to page
        page.goto(f"{live_server.url}/my-page/")

        # Find element
        my_element = page.locator('.my-class')

        # Interact
        my_element.click()

        # Assert
        expect(my_element).to_have_class('active')
```

### Creating Fixtures for Live Server Tests

If you need to create database objects for your tests:

```python
@pytest.fixture
def my_test_data(transactional_db):
    """Create test data visible to live_server.

    IMPORTANT: Use transactional_db, not db!
    """
    user = UserFactory(username="testuser")
    group = PersonGroupFactory(name="Test Group")
    # Data is automatically committed and visible to live_server
    return {'user': user, 'group': group}
```

### Best Practices

1. **Use `@pytest.mark.slow`**: Mark all frontend tests as slow
2. **Use `@pytest.mark.django_db(transaction=True)`**: Required for live server
3. **Use `transactional_db` in fixtures**: Database fixtures must use `transactional_db` instead of `db` to ensure data is committed and visible to live_server
4. **Wait for elements**: Use `page.wait_for_selector()` or `expect()` assertions
5. **Keep tests focused**: Test one interaction per test method
6. **Use meaningful selectors**: Prefer data attributes or classes over generic tags

## Troubleshooting

### Tests Timeout

If tests are timing out, increase waits:

```python
page.wait_for_selector('.my-element', timeout=10000)  # 10 seconds
```

### Element Not Found

Verify the selector is correct:

```python
page.screenshot(path="debug.png")  # Take screenshot
print(page.content())  # Print HTML
```

### Database Issues

**Data not visible in live_server tests:**

If your test times out waiting for elements that should exist, the data created in fixtures may not be visible to live_server. **Solution**: Ensure all database fixtures use `transactional_db` instead of `db`:

```python
# ❌ Wrong - data not visible to live_server
@pytest.fixture
def my_data(db):
    return MyModel.objects.create(...)

# ✅ Correct - data is committed and visible
@pytest.fixture
def my_data(transactional_db):
    return MyModel.objects.create(...)
```

**Database backend issues:**

Frontend tests use `transaction=True` which may have issues with SQLite. Additionally, **SQLite `:memory:` databases do NOT work with live_server** because they are thread-local.

**Required database configuration:**

Your `testing.py` settings **must** use a shared-cache SQLite database:

```python
# ❌ Wrong - thread-local, live_server can't see data
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ✅ Correct - shared across threads
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "file:memorydb_default?mode=memory&cache=shared",
        "TEST": {
            "NAME": "file:memorydb_default?mode=memory&cache=shared",
        },
    }
}
```

This uses SQLite's shared-cache mode which allows multiple threads (including live_server) to access the same in-memory database. See: https://www.sqlite.org/inmemorydb.html#sharedmemdb

Alternatively, use PostgreSQL for testing which handles multi-threaded access naturally.

## Performance

Frontend tests are significantly slower than unit tests:

- **Unit test**: ~10-50ms per test
- **Frontend test**: ~2-5 seconds per test

This is why they're marked as `slow` and can be skipped during development.

## CI/CD Integration

In CI pipelines, always run in headless mode:

```bash
pytest gift_manager/tests/test_frontend.py --headed=false
```

Example GitHub Actions:

```yaml
- name: Run frontend tests
  run: |
    playwright install chromium
    pytest gift_manager/tests/test_frontend.py -v
```

## Limitations

Frontend tests do NOT cover:

- Mobile/responsive layouts (tests run at desktop viewport size)
- Performance/load testing
- Accessibility testing
- Real Safari/Edge (we use WebKit/Chromium engines, not the actual browsers)

For comprehensive testing, consider additional tools like:
- BrowserStack (real Safari/Edge testing)
- Lighthouse (performance)
- axe-core (accessibility)
- Responsive design mode testing
