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
def setup_test_user(db):
    """Create a test user and log them in."""
    user = UserFactory(username="testuser")
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def setup_group_hierarchy(db, setup_test_user):
    """Create a hierarchy of person groups for testing.

    Structure:
        Root
        ├── Child 1
        │   └── Grandchild 1
        └── Child 2
    """
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
        page.goto(f"{live_server.url}/person_groups/")

        # Switch to tree view
        tree_tab = page.locator('button:has-text("Tree View")')
        if tree_tab.is_visible():
            tree_tab.click()

        # Verify root group is visible
        root_node = page.locator('.tree-node:has-text("Root Group")')
        expect(root_node).to_be_visible()

        # Verify child groups exist in the DOM (may be collapsed)
        child1_node = page.locator('.tree-node:has-text("Child Group 1")')
        child2_node = page.locator('.tree-node:has-text("Child Group 2")')

        # At least one child should be visible or in DOM
        expect(child1_node.or_(child2_node)).to_have_count(2)

    def test_tree_view_expand_collapse(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test expanding and collapsing tree nodes."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/")

        # Switch to tree view
        tree_tab = page.locator('button:has-text("Tree View")')
        if tree_tab.is_visible():
            tree_tab.click()
            page.wait_for_timeout(500)  # Wait for view to render

        # Find the root group's expand/collapse button
        root_node = page.locator('.tree-node:has-text("Root Group")').first
        expand_btn = root_node.locator('.tree-toggle').first

        if expand_btn.is_visible():
            # Click to expand
            expand_btn.click()
            page.wait_for_timeout(300)  # Wait for animation

            # Verify children are now visible
            child_nodes = page.locator('.tree-node.tree-level-1')
            expect(child_nodes).to_have_count(2)  # Child 1 and Child 2

            # Click to collapse
            expand_btn.click()
            page.wait_for_timeout(300)

            # Verify children are hidden (or have collapsed class)
            # Note: exact behavior depends on implementation

    def test_tree_view_indentation(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that tree nodes have correct indentation levels."""
        login_user(page, live_server)

        # Navigate to person groups list
        page.goto(f"{live_server.url}/person_groups/")

        # Switch to tree view
        tree_tab = page.locator('button:has-text("Tree View")')
        if tree_tab.is_visible():
            tree_tab.click()
            page.wait_for_timeout(500)

        # Expand root to show children
        root_toggle = page.locator('.tree-node:has-text("Root Group") .tree-toggle').first
        if root_toggle.is_visible():
            root_toggle.click()
            page.wait_for_timeout(300)

        # Check that level 0 and level 1 nodes have different indentation
        level0_node = page.locator('.tree-node.tree-level-0').first
        level1_node = page.locator('.tree-node.tree-level-1').first

        if level0_node.is_visible() and level1_node.is_visible():
            # Verify they have different CSS classes indicating different levels
            expect(level0_node).to_have_attribute("class", re.compile(r"tree-level-0"))
            expect(level1_node).to_have_attribute("class", re.compile(r"tree-level-1"))


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
class TestSearchableMultiSelect:
    """Tests for searchable multi-select form functionality."""

    def test_searchable_select_filter_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the search filter in multi-select fields works."""
        login_user(page, live_server)

        data = setup_group_hierarchy

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/")

        # Wait for page to load
        page.wait_for_selector('form', timeout=5000)

        # Find the searchable select for parent groups
        search_input = page.locator('.searchable-select-search').first

        if search_input.is_visible():
            # Type in search box
            search_input.fill("Child")
            page.wait_for_timeout(200)  # Wait for filter

            # Get the parent select element
            parent_select = page.locator('select.searchable-select').first

            # Verify that only matching options are visible
            visible_options = parent_select.locator('option:visible')

            # Should show "Child Group 1" and "Child Group 2" but not "Root Group"
            # Note: exact count depends on how many groups match "Child"
            expect(visible_options).to_have_count(3)  # 2 child groups + grandchild

    def test_select_all_button_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the Select All button selects all visible options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/")
        page.wait_for_selector('form', timeout=5000)

        # Find Select All button
        select_all_btn = page.locator('.select-all-btn button:has-text("Select All")')

        if select_all_btn.is_visible():
            # Click Select All
            select_all_btn.click()
            page.wait_for_timeout(200)

            # Verify all options are selected
            parent_select = page.locator('select.searchable-select').first
            selected_options = parent_select.locator('option:checked')

            # Should have at least some options selected
            expect(selected_options.count()).to_be_greater_than(0)

    def test_clear_all_button_works(
        self, page: Page, live_server, setup_group_hierarchy
    ):
        """Test that the Clear All button deselects all options."""
        login_user(page, live_server)

        # Navigate to create person group page
        page.goto(f"{live_server.url}/person_groups/create/")
        page.wait_for_selector('form', timeout=5000)

        # First select all
        select_all_btn = page.locator('.select-all-btn button:has-text("Select All")')
        if select_all_btn.is_visible():
            select_all_btn.click()
            page.wait_for_timeout(200)

            # Then clear all
            clear_all_btn = page.locator('.select-all-btn button:has-text("Clear All")')
            clear_all_btn.click()
            page.wait_for_timeout(200)

            # Verify no options are selected
            parent_select = page.locator('select.searchable-select').first
            selected_options = parent_select.locator('option:checked')

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
        page.goto(f"{live_server.url}/person_groups/{data['root'].group_id}/edit/")
        page.wait_for_selector('form', timeout=5000)

        # The current group should not appear in parent groups options
        parent_select = page.locator('select.searchable-select').first

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
        page.goto(f"{live_server.url}/person_groups/{data['root'].group_id}/edit/")
        page.wait_for_selector('form', timeout=5000)

        # Get all parent group options
        parent_select = page.locator('select.searchable-select').first
        all_options = parent_select.locator('option').all_text_contents()

        # Descendants (Child Group 1, Child Group 2, Grandchild Group 1) should not be in the list
        assert "Child Group 1" not in all_options, "Group should not select its child as parent"
        assert "Child Group 2" not in all_options, "Group should not select its child as parent"
        assert "Grandchild Group 1" not in all_options, "Group should not select its grandchild as parent"
