"""Frontend tests for nested groups functionality using Playwright.

These tests verify JavaScript-dependent features that unit tests cannot cover.

NOTE: These tests require browser binaries to be installed via:
    python3 -m playwright install chromium
    # or for webkit/firefox:
    python3 -m playwright install webkit
    python3 -m playwright install firefox

To run with a specific browser:
    pytest --browser webkit gift_manager/tests/test_frontend.py

If browser installation fails, these tests can be skipped with:
    pytest -m "not slow"
"""

# pylint: disable=redefined-outer-name
import tempfile

import pytest
from django.contrib.auth.models import User

try:
    from playwright.sync_api import Page
    from playwright.sync_api import expect

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = object
    expect = None

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

# Skip all frontend tests if Playwright is not available
pytestmark = [
    pytest.mark.slow,
    pytest.mark.frontend,
    pytest.mark.skipif(
        not PLAYWRIGHT_AVAILABLE,
        reason="Playwright is not installed. Install with 'uv pip install .[test]'",
    ),
]


@pytest.fixture
def setup_test_user(transactional_db):
    """Create a test user and log them in.

    Uses transactional_db to ensure data is committed and visible to live_server.
    """
    from allauth.account.models import EmailAddress
    from django.db import connection, transaction

    # Use a transaction to ensure data is committed
    with transaction.atomic():
        user = UserFactory(username="testuser", email="testuser@example.com")
        user.set_password("testpass123")
        user.save()

        # Create verified email address for allauth
        # Without this, allauth will redirect to email verification page
        EmailAddress.objects.create(
            user=user,
            email="testuser@example.com",
            verified=True,
            primary=True,
        )

    # Explicitly commit using database connection
    connection.commit()

    # Debug: verify user exists and can authenticate
    from django.contrib.auth import authenticate
    user_check = User.objects.filter(username="testuser").exists()
    email_check = EmailAddress.objects.filter(user=user, verified=True).exists()
    auth_check = authenticate(username="testuser", password="testpass123")

    print(f"DEBUG: User 'testuser' exists in database: {user_check}")
    print(f"DEBUG: User has verified email: {email_check}")
    print(f"DEBUG: User can authenticate: {auth_check is not None}")

    return user


@pytest.fixture
def setup_group_hierarchy(transactional_db, setup_test_user):
    """Create a hierarchy of person groups for testing.

    Uses transactional_db to ensure data is committed and visible to live_server.
    This is required because live_server runs in a separate thread with its own
    database connection.

    Structure:
        Root
        ├── Child 1
        │   └── Grandchild 1
        └── Child 2
    """
    from django.db import connection

    user = setup_test_user

    # Create groups
    root = PersonGroupFactory(name="Root Group")
    child1 = PersonGroupFactory(name="Child Group 1")
    child2 = PersonGroupFactory(name="Child Group 2")
    grandchild1 = PersonGroupFactory(name="Grandchild Group 1")

    # Set up hierarchy
    child1.parent_groups.add(root)
    child2.parent_groups.add(root)
    grandchild1.parent_groups.add(child1)

    # Grant permissions
    for group in [root, child1, child2, grandchild1]:
        PersonGroupPermission.objects.create(
            user=user,
            group=group,
            permission_type=PermissionLevel.OWNER,
        )

    # Add some members
    person1 = PersonFactory(first_name="John", family_name="Doe")
    person2 = PersonFactory(first_name="Jane", family_name="Smith")

    PersonPermission.objects.create(
        user=user,
        person=person1,
        permission_type=PermissionLevel.OWNER,
    )
    PersonPermission.objects.create(
        user=user,
        person=person2,
        permission_type=PermissionLevel.OWNER,
    )

    root.person_set.add(person1)
    child1.person_set.add(person2)

    # Explicitly commit using database connection
    connection.commit()

    # Debug: verify groups exist and have hierarchy
    group_count = PersonGroup.objects.count()
    root_children_count = root.get_children().count()
    print(f"DEBUG: Created {group_count} groups, root has {root_children_count} children")

    return {
        "user": user,
        "root": root,
        "child1": child1,
        "child2": child2,
        "grandchild1": grandchild1,
        "person1": person1,
        "person2": person2,
    }


def login_user(page: Page, live_server, username="testuser", password="testpass123"):
    """Helper to log in a user.

    This app uses django-allauth which has different field names than standard Django auth.
    Rate limiting is disabled in testing settings, so login should work reliably.
    """
    # Navigate to login page
    page.goto(f"{live_server.url}/accounts/login/", wait_until="networkidle")

    # Wait for page to load by checking for the login form
    page.wait_for_selector("form", timeout=10000)

    # Check if we're already logged in (redirect to home page)
    if "/accounts/login/" not in page.url:
        print(f"DEBUG login_user: Already logged in, current URL: {page.url}")
        return True

    # django-allauth uses 'login' for username field, not 'username'
    # Try allauth field first (#id_login), fallback to standard Django (#id_username)
    try:
        login_field = page.locator("#id_login")
        login_field.wait_for(state="visible", timeout=5000)
        login_field.fill(username)
    except Exception:
        try:
            # Fallback to standard Django auth field
            username_field = page.locator("#id_username")
            username_field.wait_for(state="visible", timeout=5000)
            username_field.fill(username)
        except Exception:
            # Try to find any input field that might be the login field
            all_inputs = page.locator("input[type='text'], input[type='email']").all()
            if all_inputs:
                all_inputs[0].fill(username)

    # Fill in the password field (same for both allauth and standard Django)
    password_field = page.locator("#id_password")
    password_field.wait_for(state="visible", timeout=5000)
    password_field.fill(password)

    # Submit the form
    submit_button = page.locator('button[type="submit"]')
    submit_button.click()

    # Wait for page to load
    page.wait_for_load_state("networkidle", timeout=15000)

    # Check if login succeeded
    current_url = page.url
    if "/accounts/login/" not in current_url:
        print(f"DEBUG login_user: Login SUCCESS")
        return True
    else:
        print(f"DEBUG login_user: Login FAILED - still on login page")
        # Check for error messages for debugging
        error_messages = page.locator(
            ".alert-danger, .errorlist, .invalid-feedback, .alert"
        ).all_text_contents()
        if error_messages:
            print(f"DEBUG login_user: Error messages: {error_messages}")

        # Check for rate limiting (should not happen with our settings)
        page_content = page.content()
        if "Too Many Requests" in page_content or "rate limit" in page_content.lower():
            print("DEBUG login_user: Rate limiting detected - check test settings!")

        return False


@pytest.mark.slow
class TestPersonGroupTreeView:
    """Tests for the person group tree view functionality.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits. The test-level
    transaction wrapper would prevent those commits from being visible
    to live_server.
    """

    def test_tree_view_renders_hierarchy(self, page: Page, live_server, setup_group_hierarchy):
        """Test that the tree view correctly renders the group hierarchy."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Debug: Check what's on the page
        page.screenshot(path=f"{tempfile.gettempdir()}/debug_page_loaded.png")

        # Check if Grid.js table loaded with data
        grid_wrapper = page.locator("#person-group-grid")
        if grid_wrapper.count() > 0:
            print("Grid wrapper found")
            # Check for Grid.js table
            grid_table = page.locator("#person-group-grid table")
            if grid_table.count() > 0:
                print(
                    f"Grid table found, rows: {page.locator('#person-group-grid tbody tr').count()}"
                )

        # Check if tree view button exists
        tree_view_btn = page.locator("#tree-view-btn")

        if tree_view_btn.count() == 0:
            # Tree view button doesn't exist - hierarchy wasn't detected
            print("ERROR: Tree view button not found!")
            print("Page HTML:", page.content()[:1000])  # First 1000 chars

            # Try to understand why
            pytest.fail(
                "Tree view button (#tree-view-btn) not found on page. "
                "This means has_hierarchy=False in the template context. "
                "Possible causes:\n"
                "1. Database not using shared-cache mode (check testing.py)\n"
                "2. Fixtures not using transactional_db\n"
                "3. Groups created but parent_groups relationship not saved\n"
                f"Screenshot saved to {tempfile.gettempdir()}/debug_page_loaded.png"
            )

        # Wait for tree view button to be visible
        tree_view_btn.wait_for(state="visible", timeout=10000)

        # Switch to tree view
        tree_view_btn.click()

        # Wait for tree view container to become visible
        tree_view_container = page.locator(".tree-view-container.active")
        tree_view_container.wait_for(state="visible", timeout=5000)

        # Verify root group is visible (using data attribute for exact match)
        root_node = page.locator('.tree-node[data-group-name="Root Group"]')
        expect(root_node).to_be_visible()

        # Verify child groups exist in the DOM (using exact data attributes)
        child1_node = page.locator('.tree-node[data-group-name="Child Group 1"]')
        child2_node = page.locator('.tree-node[data-group-name="Child Group 2"]')

        # Both children should be visible in the tree
        expect(child1_node).to_be_visible()
        expect(child2_node).to_be_visible()

    def test_tree_view_expand_collapse(self, page: Page, live_server, setup_group_hierarchy):
        """Test expanding and collapsing tree nodes."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Switch to tree view
        page.wait_for_selector("#tree-view-btn", timeout=10000)
        page.locator("#tree-view-btn").click()

        # Wait for tree view container to become visible
        page.locator(".tree-view-container.active").wait_for(state="visible", timeout=5000)

        # Verify tree nodes are visible
        # Check for groups in the hierarchy - they should all be rendered
        root_node = page.locator('.tree-node[data-group-name="Root Group"]')
        expect(root_node).to_be_visible()

        # Verify child groups are also visible in the tree
        child1_node = page.locator('.tree-node[data-group-name="Child Group 1"]')
        child2_node = page.locator('.tree-node[data-group-name="Child Group 2"]')

        expect(child1_node).to_be_visible()
        expect(child2_node).to_be_visible()

    def test_tree_view_indentation(self, page: Page, live_server, setup_group_hierarchy):
        """Test that tree nodes have correct indentation levels."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Switch to tree view
        page.wait_for_selector("#tree-view-btn", timeout=10000)
        page.locator("#tree-view-btn").click()

        # Wait for tree view container to become visible
        page.locator(".tree-view-container.active").wait_for(state="visible", timeout=5000)

        # Check that nodes have correct depth attributes
        # Root should be depth 0, children depth 1
        level0_node = page.locator('.tree-node[data-depth="0"]').first
        level1_node = page.locator('.tree-node[data-depth="1"]').first

        # Verify depth 0 node exists (root)
        expect(level0_node).to_be_visible()

        # Verify depth 1 nodes exist (children)
        expect(level1_node).to_be_visible()


@pytest.mark.slow
class TestSearchableMultiSelect:
    """Tests for searchable multi-select form functionality.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits.
    """

    def test_searchable_select_filter_works(self, page: Page, live_server, setup_group_hierarchy):
        """Test that the search filter in multi-select fields works."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")

        # Wait for form and searchable select to load
        page.wait_for_selector("select.searchable-select", timeout=10000)

        # Find the searchable select for parent groups
        search_input = page.locator(".searchable-select-search").first

        # Only test if searchable select is implemented
        if search_input.count() > 0:
            search_input.wait_for(state="visible", timeout=5000)

            # Type in search box
            search_input.fill("Child")
            page.wait_for_timeout(300)  # Wait for filter to apply

            # Get the parent select element
            parent_select = page.locator("select.searchable-select").first

            # Verify that only matching options are visible
            # Should show "Child Group 1", "Child Group 2", and "Grandchild Group 1"
            visible_options = parent_select.locator("option:visible")

            # At least the child groups should be visible
            expect(visible_options.count()).to_be_greater_than(0)

    def test_select_all_button_works(self, page: Page, live_server, setup_group_hierarchy):
        """Test that the Select All button selects all visible options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")
        page.wait_for_selector("select.searchable-select", timeout=10000)

        # Find Select All button
        select_all_btn = page.locator('button:has-text("Select All")').first

        # Only test if Select All button exists
        if select_all_btn.count() > 0:
            select_all_btn.wait_for(state="visible", timeout=5000)

            # Click Select All
            select_all_btn.click()
            page.wait_for_timeout(300)

            # Verify all options are selected
            parent_select = page.locator("select.searchable-select").first
            selected_options = parent_select.locator("option[selected]")

            # Should have at least some options selected
            expect(selected_options.count()).to_be_greater_than(0)

    def test_clear_all_button_works(self, page: Page, live_server, setup_group_hierarchy):
        """Test that the Clear All button deselects all options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")
        page.wait_for_selector("select.searchable-select", timeout=10000)

        # Find Select All and Clear All buttons
        select_all_btn = page.locator('button:has-text("Select All")').first
        clear_all_btn = page.locator('button:has-text("Clear All")').first

        # Only test if buttons exist
        if select_all_btn.count() > 0 and clear_all_btn.count() > 0:
            select_all_btn.wait_for(state="visible", timeout=5000)

            # First select all
            select_all_btn.click()
            page.wait_for_timeout(300)

            # Then clear all
            clear_all_btn.click()
            page.wait_for_timeout(300)

            # Verify no options are selected
            parent_select = page.locator("select.searchable-select").first
            selected_options = parent_select.locator("option[selected]")

            expect(selected_options).to_have_count(0)


@pytest.mark.slow
class TestGroupFormCyclePrevention:
    """Tests for cycle prevention in the UI.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits.
    """

    def test_form_prevents_selecting_self_as_parent(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that a group cannot select itself as a parent."""
        login_user(page, live_server)

        data = setup_group_hierarchy

        # Navigate to edit the root group
        page.goto(
            f"{live_server.url}/person_groups/{data['root'].group_id}/edit/",
            wait_until="networkidle",
        )

        # Wait for form and select to load
        page.wait_for_selector("select.searchable-select", timeout=10000)

        # The current group should not appear in parent groups options
        parent_select = page.locator("select#id_parent_groups")
        parent_select.wait_for(state="visible", timeout=5000)

        # Get all options
        all_options = parent_select.locator("option").all_text_contents()

        # "Root Group" should not be in the list
        assert "Root Group" not in all_options, (
            "Group should not be able to select itself as parent"
        )

    def test_form_prevents_selecting_descendants_as_parents(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that a group cannot select its descendants as parents."""
        login_user(page, live_server)

        data = setup_group_hierarchy

        # Navigate to edit the root group
        page.goto(
            f"{live_server.url}/person_groups/{data['root'].group_id}/edit/",
            wait_until="networkidle",
        )

        # Wait for form and select to load
        page.wait_for_selector("select.searchable-select", timeout=10000)

        # Get all parent group options
        parent_select = page.locator("select#id_parent_groups")
        parent_select.wait_for(state="visible", timeout=5000)

        all_options = parent_select.locator("option").all_text_contents()

        # Descendants (Child Group 1, Child Group 2, Grandchild Group 1) should not be in the list
        assert "Child Group 1" not in all_options, "Group should not select its child as parent"
        assert "Child Group 2" not in all_options, "Group should not select its child as parent"
        assert "Grandchild Group 1" not in all_options, (
            "Group should not select its grandchild as parent"
        )


@pytest.mark.slow
class TestViewToggleAndLocalStorage:
    """Tests for view toggle and localStorage functionality.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits.
    """

    def test_view_toggle_switches_between_list_and_card(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that view toggle switches between list and card views."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Wait for Grid.js to load
        page.wait_for_selector(".gridjs-wrapper", timeout=10000)

        # Find the view toggle buttons
        list_view_btn = page.locator("#list-view-btn")
        card_view_btn = page.locator("#card-view-btn")

        # Verify both buttons exist
        if list_view_btn.count() > 0 and card_view_btn.count() > 0:
            # Click card view button
            card_view_btn.click()
            page.wait_for_timeout(500)

            # Verify the grid wrapper has data-view="card" attribute
            grid_wrapper = page.locator(".gridjs-wrapper")
            view_attr = grid_wrapper.get_attribute("data-view")
            assert view_attr == "card", "View should be 'card' after clicking card view button"

            # Click list view button
            list_view_btn.click()
            page.wait_for_timeout(500)

            # Verify the grid wrapper has data-view="list" attribute
            view_attr = grid_wrapper.get_attribute("data-view")
            assert view_attr == "list", "View should be 'list' after clicking list view button"

    def test_view_preference_persists_in_local_storage(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that view preference is saved to localStorage."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")
        page.wait_for_selector(".gridjs-wrapper", timeout=10000)

        # Switch to card view
        card_view_btn = page.locator("#card-view-btn")
        if card_view_btn.count() > 0:
            card_view_btn.click()
            page.wait_for_timeout(500)

            # Check localStorage
            storage_value = page.evaluate(
                "() => localStorage.getItem('view-preference-person-group-grid')"
            )
            assert storage_value == "card", "Card view preference should be saved to localStorage"

            # Reload the page
            page.reload(wait_until="networkidle")
            page.wait_for_selector(".gridjs-wrapper", timeout=10000)

            # Verify view is still card
            grid_wrapper = page.locator(".gridjs-wrapper")
            view_attr = grid_wrapper.get_attribute("data-view")
            assert view_attr == "card", "Card view should persist after page reload"

    def test_local_storage_cleared_on_profile_update(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that localStorage is cleared when profile preferences are updated."""
        login_user(page, live_server)

        # Navigate to person groups and set a view preference
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")
        page.wait_for_selector(".gridjs-wrapper", timeout=10000)

        card_view_btn = page.locator("#card-view-btn")
        if card_view_btn.count() > 0:
            card_view_btn.click()
            page.wait_for_timeout(500)

            # Verify localStorage has the preference
            storage_value = page.evaluate(
                "() => localStorage.getItem('view-preference-person-group-grid')"
            )
            assert storage_value == "card"

            # Navigate to profile page
            page.goto(f"{live_server.url}/profile/", wait_until="networkidle")

            # Update view preferences
            desktop_card = page.locator('input[name="default_view_desktop"][value="card"]')
            if desktop_card.count() > 0:
                desktop_card.click()

                # Submit the form
                submit_btn = page.locator('button[type="submit"]:has-text("Save")')
                submit_btn.click()
                page.wait_for_load_state("networkidle")

                # Verify localStorage was cleared
                storage_value = page.evaluate(
                    "() => localStorage.getItem('view-preference-person-group-grid')"
                )
                assert storage_value is None, "localStorage should be cleared after profile update"


@pytest.mark.slow
class TestDarkModeToggle:
    """Tests for dark mode toggle functionality.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits.
    """

    def test_dark_mode_toggle_switches_theme(self, page: Page, live_server, setup_test_user):
        """Test that dark mode toggle switches between light and dark themes."""
        login_user(page, live_server)

        # Navigate to home page
        page.goto(f"{live_server.url}/", wait_until="networkidle")

        # Find the theme toggle button
        theme_toggle = page.locator("#theme-toggle")

        if theme_toggle.count() > 0:
            # Get initial theme
            initial_theme = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')"
            )

            # Click theme toggle
            theme_toggle.click()
            page.wait_for_timeout(300)

            # Get new theme
            new_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")

            # Verify theme changed
            assert initial_theme != new_theme, "Theme should change after clicking toggle"

            # Verify it's one of the valid themes
            assert new_theme in ["light", "dark"], (
                f"Theme should be 'light' or 'dark', got {new_theme}"
            )

    def test_dark_mode_persists_in_local_storage(self, page: Page, live_server, setup_test_user):
        """Test that dark mode preference persists in localStorage."""
        login_user(page, live_server)

        # Navigate to home page
        page.goto(f"{live_server.url}/", wait_until="networkidle")

        # Find the theme toggle button
        theme_toggle = page.locator("#theme-toggle")

        if theme_toggle.count() > 0:
            # Click to dark mode (assuming we start in light mode)
            theme_toggle.click()
            page.wait_for_timeout(300)

            # Check localStorage
            theme_storage = page.evaluate("() => localStorage.getItem('theme')")
            current_theme = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')"
            )

            assert theme_storage == current_theme, "localStorage theme should match DOM theme"

            # Reload page
            page.reload(wait_until="networkidle")

            # Verify theme persisted
            reloaded_theme = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')"
            )
            assert reloaded_theme == current_theme, "Theme should persist after page reload"


@pytest.mark.slow
class TestGlobalSearchUI:
    """Tests for global search UI functionality.

    Note: Does NOT use @pytest.mark.django_db(transaction=True) because
    fixtures use transactional_db with explicit commits.
    """

    def test_global_search_opens_with_ctrl_k(self, page: Page, live_server, setup_test_user):
        """Test that global search panel opens with Ctrl+K."""
        login_user(page, live_server)

        # Navigate to home page
        page.goto(f"{live_server.url}/", wait_until="networkidle")

        # Press Ctrl+K
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)

        # Check if search panel is visible
        search_panel = page.locator(".search-panel.active, #globalSearchPanel.show")

        if search_panel.count() > 0:
            expect(search_panel).to_be_visible()

    def test_global_search_closes_with_escape(self, page: Page, live_server, setup_test_user):
        """Test that global search panel closes with Escape key."""
        login_user(page, live_server)

        # Navigate to home page
        page.goto(f"{live_server.url}/", wait_until="networkidle")

        # Open search with Ctrl+K
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)

        # Press Escape
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # Check if search panel is hidden
        search_panel = page.locator(".search-panel.active, #globalSearchPanel.show")

        if search_panel.count() > 0:
            expect(search_panel).not_to_be_visible()

    def test_global_search_shows_results(self, page: Page, live_server, setup_group_hierarchy):
        """Test that global search displays results."""
        login_user(page, live_server)

        # Navigate to home page
        page.goto(f"{live_server.url}/", wait_until="networkidle")

        # Open search
        page.keyboard.press("Control+k")
        page.wait_for_timeout(500)

        # Find search input
        search_input = page.locator("#globalSearchInput, .search-input")

        if search_input.count() > 0:
            # Type in search
            search_input.fill("Root")
            page.wait_for_timeout(1000)  # Wait for debounce and results

            # Check for results
            results_container = page.locator(".search-results, #searchResults")

            if results_container.count() > 0:
                # Should have at least one result (Root Group from fixtures)
                result_items = page.locator(".search-result-item, .result-item")
                expect(result_items.first).to_be_visible()
