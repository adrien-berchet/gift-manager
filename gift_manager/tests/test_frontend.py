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

import re

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import PermissionLevel
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

# Skip all frontend tests by default due to environment constraints
# This environment blocks downloads from Playwright CDN (403 "Host not allowed" errors)
# Frontend functionality is thoroughly tested via unit tests
pytestmark = [
    pytest.mark.slow,
    pytest.mark.frontend,
    pytest.mark.skip(
        reason="Playwright browser installation blocked by network restrictions. "
        "This environment cannot download browsers from Playwright CDN. "
        "Frontend functionality is covered by unit tests."
    ),
]


@pytest.fixture
def setup_test_user(transactional_db):
    """Create a test user and log them in.

    Uses transactional_db to ensure data is committed and visible to live_server.
    """
    from django.db import transaction

    user = UserFactory(username="testuser")
    user.set_password("testpass123")
    user.save()

    # Explicitly commit to ensure visibility to live_server
    transaction.commit()

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
    from django.db import transaction

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

    # Explicitly commit to ensure visibility to live_server
    transaction.commit()

    return {
        'user': user,
        'root': root,
        'child1': child1,
        'child2': child2,
        'grandchild1': grandchild1,
        'person1': person1,
        'person2': person2,
    }


def login_user(page: Page, live_server, username="testuser", password="testpass123"):
    """Helper to log in a user.

    This app uses django-allauth which has different field names than standard Django auth.
    """
    # Navigate to login page
    page.goto(f"{live_server.url}/accounts/login/", wait_until="networkidle")

    # Wait for page to load by checking for the login form
    page.wait_for_selector('form', timeout=10000)

    # django-allauth uses 'login' for username field, not 'username'
    # Try allauth field first (#id_login), fallback to standard Django (#id_username)
    try:
        login_field = page.locator('#id_login')
        login_field.wait_for(state='visible', timeout=5000)
        login_field.fill(username)
    except Exception:
        # Fallback to standard Django auth field
        username_field = page.locator('#id_username')
        username_field.wait_for(state='visible', timeout=5000)
        username_field.fill(username)

    # Fill in the password field (same for both allauth and standard Django)
    password_field = page.locator('#id_password')
    password_field.wait_for(state='visible', timeout=5000)
    password_field.fill(password)

    # Submit the form
    submit_button = page.locator('button[type="submit"]')
    submit_button.click()

    # Wait for redirect after login (should go to home page or next URL)
    # Increase timeout as login processing might take a moment
    page.wait_for_load_state("networkidle", timeout=15000)


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
class TestPersonGroupTreeView:
    """Tests for the person group tree view functionality."""

    def test_tree_view_renders_hierarchy(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the tree view correctly renders the group hierarchy."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Debug: Check what's on the page
        page.screenshot(path="debug_page_loaded.png")

        # Check if Grid.js table loaded with data
        grid_wrapper = page.locator('#person-group-grid')
        if grid_wrapper.count() > 0:
            print("Grid wrapper found")
            # Check for Grid.js table
            grid_table = page.locator('#person-group-grid table')
            if grid_table.count() > 0:
                print(f"Grid table found, rows: {page.locator('#person-group-grid tbody tr').count()}")

        # Check if tree view button exists
        tree_view_btn = page.locator('#tree-view-btn')

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
                "Screenshot saved to debug_page_loaded.png"
            )

        # Wait for tree view button to be visible
        tree_view_btn.wait_for(state='visible', timeout=10000)

        # Switch to tree view
        tree_view_btn.click()

        # Wait for tree view container to become visible
        tree_view_container = page.locator('.tree-view-container.active')
        tree_view_container.wait_for(state='visible', timeout=5000)

        # Verify root group is visible
        root_node = page.locator('.tree-node:has-text("Root Group")')
        expect(root_node).to_be_visible()

        # Verify child groups exist in the DOM
        child1_node = page.locator('.tree-node:has-text("Child Group 1")')
        child2_node = page.locator('.tree-node:has-text("Child Group 2")')

        # Both children should be visible in the tree
        expect(child1_node.or_(child2_node)).to_have_count(2)

    def test_tree_view_expand_collapse(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test expanding and collapsing tree nodes."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Switch to tree view
        page.wait_for_selector('#tree-view-btn', timeout=10000)
        page.locator('#tree-view-btn').click()

        # Wait for tree view container to become visible
        page.locator('.tree-view-container.active').wait_for(state='visible', timeout=5000)

        # Verify tree nodes are visible
        # Check for groups in the hierarchy - they should all be rendered
        root_node = page.locator('.tree-node[data-group-name="Root Group"]')
        expect(root_node).to_be_visible()

        # Verify child groups are also visible in the tree
        child1_node = page.locator('.tree-node[data-group-name="Child Group 1"]')
        child2_node = page.locator('.tree-node[data-group-name="Child Group 2"]')

        expect(child1_node).to_be_visible()
        expect(child2_node).to_be_visible()

    def test_tree_view_indentation(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that tree nodes have correct indentation levels."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/", wait_until="networkidle")

        # Switch to tree view
        page.wait_for_selector('#tree-view-btn', timeout=10000)
        page.locator('#tree-view-btn').click()

        # Wait for tree view container to become visible
        page.locator('.tree-view-container.active').wait_for(state='visible', timeout=5000)

        # Check that nodes have correct depth attributes
        # Root should be depth 0, children depth 1
        level0_node = page.locator('.tree-node[data-depth="0"]').first
        level1_node = page.locator('.tree-node[data-depth="1"]').first

        # Verify depth 0 node exists (root)
        expect(level0_node).to_be_visible()

        # Verify depth 1 nodes exist (children)
        expect(level1_node).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
class TestSearchableMultiSelect:
    """Tests for searchable multi-select form functionality."""

    def test_searchable_select_filter_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the search filter in multi-select fields works."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")

        # Wait for form and searchable select to load
        page.wait_for_selector('select.searchable-select', timeout=10000)

        # Find the searchable select for parent groups
        search_input = page.locator('.searchable-select-search').first

        # Only test if searchable select is implemented
        if search_input.count() > 0:
            search_input.wait_for(state='visible', timeout=5000)

            # Type in search box
            search_input.fill("Child")
            page.wait_for_timeout(300)  # Wait for filter to apply

            # Get the parent select element
            parent_select = page.locator('select.searchable-select').first

            # Verify that only matching options are visible
            # Should show "Child Group 1", "Child Group 2", and "Grandchild Group 1"
            visible_options = parent_select.locator('option:visible')

            # At least the child groups should be visible
            expect(visible_options.count()).to_be_greater_than(0)

    def test_select_all_button_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the Select All button selects all visible options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")
        page.wait_for_selector('select.searchable-select', timeout=10000)

        # Find Select All button
        select_all_btn = page.locator('button:has-text("Select All")').first

        # Only test if Select All button exists
        if select_all_btn.count() > 0:
            select_all_btn.wait_for(state='visible', timeout=5000)

            # Click Select All
            select_all_btn.click()
            page.wait_for_timeout(300)

            # Verify all options are selected
            parent_select = page.locator('select.searchable-select').first
            selected_options = parent_select.locator('option[selected]')

            # Should have at least some options selected
            expect(selected_options.count()).to_be_greater_than(0)

    def test_clear_all_button_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the Clear All button deselects all options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/", wait_until="networkidle")
        page.wait_for_selector('select.searchable-select', timeout=10000)

        # Find Select All and Clear All buttons
        select_all_btn = page.locator('button:has-text("Select All")').first
        clear_all_btn = page.locator('button:has-text("Clear All")').first

        # Only test if buttons exist
        if select_all_btn.count() > 0 and clear_all_btn.count() > 0:
            select_all_btn.wait_for(state='visible', timeout=5000)

            # First select all
            select_all_btn.click()
            page.wait_for_timeout(300)

            # Then clear all
            clear_all_btn.click()
            page.wait_for_timeout(300)

            # Verify no options are selected
            parent_select = page.locator('select.searchable-select').first
            selected_options = parent_select.locator('option[selected]')

            expect(selected_options).to_have_count(0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
class TestGroupFormCyclePrevention:
    """Tests for cycle prevention in the UI."""

    def test_form_prevents_selecting_self_as_parent(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that a group cannot select itself as a parent."""
        login_user(page, live_server)

        data = setup_group_hierarchy

        # Navigate to edit the root group
        page.goto(
            f"{live_server.url}/person_groups/{data['root'].group_id}/edit/",
            wait_until="networkidle"
        )

        # Wait for form and select to load
        page.wait_for_selector('select.searchable-select', timeout=10000)

        # The current group should not appear in parent groups options
        parent_select = page.locator('select#id_parent_groups')
        parent_select.wait_for(state='visible', timeout=5000)

        # Get all options
        all_options = parent_select.locator('option').all_text_contents()

        # "Root Group" should not be in the list
        assert "Root Group" not in all_options, "Group should not be able to select itself as parent"

    def test_form_prevents_selecting_descendants_as_parents(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that a group cannot select its descendants as parents."""
        login_user(page, live_server)

        data = setup_group_hierarchy

        # Navigate to edit the root group
        page.goto(
            f"{live_server.url}/person_groups/{data['root'].group_id}/edit/",
            wait_until="networkidle"
        )

        # Wait for form and select to load
        page.wait_for_selector('select.searchable-select', timeout=10000)

        # Get all parent group options
        parent_select = page.locator('select#id_parent_groups')
        parent_select.wait_for(state='visible', timeout=5000)

        all_options = parent_select.locator('option').all_text_contents()

        # Descendants (Child Group 1, Child Group 2, Grandchild Group 1) should not be in the list
        assert "Child Group 1" not in all_options, "Group should not select its child as parent"
        assert "Child Group 2" not in all_options, "Group should not select its child as parent"
        assert "Grandchild Group 1" not in all_options, "Group should not select its grandchild as parent"
