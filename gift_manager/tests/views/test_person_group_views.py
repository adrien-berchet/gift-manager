"""Tests for PersonGroup views."""

import json

import pytest
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestPersonGroupListView:
    """Tests for PersonGroupListView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def test_list_view_empty(self):
        """Test list view with no groups."""
        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        assert "data" in response.context
        assert len(response.context["data"]) == 0
        assert response.context["has_hierarchy"] is False

    def test_list_view_with_groups(self):
        """Test list view shows accessible groups."""
        group1 = PersonGroupFactory(name="Group A")
        group2 = PersonGroupFactory(name="Group B")
        create_or_update_permission(self.user, group1, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, group2, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        assert len(response.context["data"]) == 2

    def test_list_view_only_shows_accessible_groups(self):
        """Test that only groups shared with user are shown."""
        accessible = PersonGroupFactory(name="Accessible")
        inaccessible = PersonGroupFactory(name="Inaccessible")
        create_or_update_permission(self.user, accessible, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        assert len(response.context["data"]) == 1
        assert response.context["data"][0]["name"] == "Accessible"

    def test_list_view_with_hierarchy(self):
        """Test list view detects hierarchy."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, child, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.context["has_hierarchy"] is True

    def test_list_view_tree_data(self):
        """Test tree data structure is correctly built."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, child, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        tree_data = response.context["tree_data"]
        # Tree data should be flattened, parent first then child
        assert len(tree_data) == 2
        assert tree_data[0]["name"] == "Parent"
        assert tree_data[0]["depth"] == 0
        assert tree_data[0]["has_children"] is True
        assert tree_data[1]["name"] == "Child"
        assert tree_data[1]["depth"] == 1

    def test_list_view_member_count(self):
        """Test member count is correctly computed."""
        group = PersonGroupFactory(name="Group with members")
        person1 = PersonFactory(first_name="John", family_name="Doe")
        person2 = PersonFactory(first_name="Jane", family_name="Doe")
        person1.groups.add(group)
        person2.groups.add(group)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        tree_data = response.context["tree_data"]
        assert len(tree_data) == 1
        assert tree_data[0]["member_count"] == 2

    def test_list_view_requires_login(self):
        """Test list view requires authentication."""
        self.client.logout()
        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url


@pytest.mark.django_db
class TestPersonGroupCreateView:
    """Tests for PersonGroupCreateView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_create_view_get(self):
        """Test create view renders form."""
        url = reverse("gift_manager:person_group_create")
        response = self.client.get(url)

        assert response.status_code == 200
        assert "form" in response.context

    @override_settings(USE_I18N=False)
    def test_create_view_post_success(self):
        """Test creating a new group."""
        url = reverse("gift_manager:person_group_create")
        data = {"name": "New Test Group"}
        response = self.client.post(url, data)

        assert response.status_code == 302
        assert PersonGroup.objects.filter(name="New Test Group").exists()

    def test_create_view_requires_login(self):
        """Test create view requires authentication."""
        self.client.logout()
        url = reverse("gift_manager:person_group_create")
        response = self.client.get(url)

        assert response.status_code == 302


@pytest.mark.django_db
class TestPersonGroupUpdateView:
    """Tests for PersonGroupUpdateView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        self.group = PersonGroupFactory(name="Original Name")
        create_or_update_permission(self.user, self.group, permission_level=PermissionLevel.EDITOR)

    @override_settings(USE_I18N=False)
    def test_update_view_get(self):
        """Test update view renders form with existing data."""
        url = reverse("gift_manager:person_group_edit", kwargs={"pk": self.group.group_id})
        response = self.client.get(url)

        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].initial["name"] == "Original Name"

    @override_settings(USE_I18N=False)
    def test_update_view_post_success(self):
        """Test updating a group."""
        url = reverse("gift_manager:person_group_edit", kwargs={"pk": self.group.group_id})
        data = {"name": "Updated Name"}
        response = self.client.post(url, data)

        assert response.status_code == 302
        self.group.refresh_from_db()
        assert self.group.name == "Updated Name"

    def test_update_view_requires_permission(self):
        """Test update view requires editor permission to submit changes."""
        other_group = PersonGroupFactory(name="Other Group")
        create_or_update_permission(self.user, other_group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_edit", kwargs={"pk": other_group.group_id})

        # Viewer can access the form (GET returns 200)
        response = self.client.get(url)
        assert response.status_code == 200

        # But submitting changes should fail or redirect
        response = self.client.post(url, {"name": "Hacked Name"})
        # Either redirects without saving, or returns 403
        assert response.status_code in [302, 403]
        other_group.refresh_from_db()
        assert other_group.name == "Other Group"  # Name unchanged


@pytest.mark.django_db
class TestAddMultiplePersonsToGroup:
    """Tests for add_multiple_persons_to_group view."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        self.group = PersonGroupFactory(name="Test Group")

    @override_settings(USE_I18N=False)
    def test_add_persons_requires_editor_permission(self):
        """Test that viewer cannot add persons to group."""
        create_or_update_permission(self.user, self.group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:add_person_group_person", kwargs={"pk": self.group.group_id})
        response = self.client.get(url)

        # Should redirect due to insufficient permissions
        assert response.status_code == 302
        # Redirects to group detail page (URL contains the group UUID)
        assert str(self.group.group_id) in response.url

    @override_settings(USE_I18N=False)
    def test_add_persons_editor_can_access(self):
        """Test that editor can access add persons form."""
        create_or_update_permission(self.user, self.group, permission_level=PermissionLevel.EDITOR)

        url = reverse("gift_manager:add_person_group_person", kwargs={"pk": self.group.group_id})
        response = self.client.get(url)

        assert response.status_code == 200
        assert "form" in response.context

    def test_add_persons_requires_login(self):
        """Test that login is required."""
        self.client.logout()
        url = reverse("gift_manager:add_person_group_person", kwargs={"pk": self.group.group_id})
        response = self.client.get(url)

        assert response.status_code == 302


@pytest.mark.django_db
class TestAddMultipleChildGroupsToGroup:
    """Tests for add_multiple_child_groups_to_group view."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        self.parent_group = PersonGroupFactory(name="Parent Group")

    @override_settings(USE_I18N=False)
    def test_add_child_groups_requires_editor_permission(self):
        """Test that viewer cannot add child groups."""
        create_or_update_permission(
            self.user, self.parent_group, permission_level=PermissionLevel.VIEWER
        )

        url = reverse(
            "gift_manager:add_child_groups_to_group",
            kwargs={"pk": self.parent_group.group_id},
        )
        response = self.client.get(url)

        # Should redirect due to insufficient permissions
        assert response.status_code == 302

    @override_settings(USE_I18N=False)
    def test_add_child_groups_editor_can_access(self):
        """Test that editor can access add child groups form."""
        create_or_update_permission(
            self.user, self.parent_group, permission_level=PermissionLevel.EDITOR
        )

        url = reverse(
            "gift_manager:add_child_groups_to_group",
            kwargs={"pk": self.parent_group.group_id},
        )
        response = self.client.get(url)

        assert response.status_code == 200
        assert "form" in response.context


@pytest.mark.django_db
class TestRemovePersonFromGroup:
    """Tests for remove_person_from_group view."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        self.group = PersonGroupFactory(name="Test Group")
        self.person = PersonFactory(first_name="John", family_name="Doe")
        self.person.groups.add(self.group)

    @override_settings(USE_I18N=False)
    def test_remove_person_requires_editor_permission(self):
        """Test that viewer cannot remove person from group."""
        create_or_update_permission(self.user, self.group, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, self.person, permission_level=PermissionLevel.VIEWER)

        url = reverse(
            "gift_manager:remove_person_group_person",
            kwargs={"pk": self.group.group_id, "person_id": self.person.person_id},
        )
        response = self.client.post(url)

        # Should redirect due to insufficient permissions
        assert response.status_code == 302
        # Person should still be in group
        assert self.person in self.group.person_set.all()

    @override_settings(USE_I18N=False)
    def test_remove_person_editor_can_remove(self):
        """Test that editor can remove person from group."""
        create_or_update_permission(self.user, self.group, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, self.person, permission_level=PermissionLevel.VIEWER)

        url = reverse(
            "gift_manager:remove_person_group_person",
            kwargs={"pk": self.group.group_id, "person_id": self.person.person_id},
        )
        response = self.client.post(url)

        assert response.status_code == 302
        # Person should be removed from group
        self.person.refresh_from_db()
        assert self.person not in self.group.person_set.all()


@pytest.mark.django_db
class TestPersonGroupDeleteView:
    """Tests for PersonGroupDeleteView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_delete_view_owner_can_delete(self):
        """Test that owner can delete group."""
        group = PersonGroupFactory(name="To Delete")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.OWNER)
        group_id = group.group_id

        url = reverse("gift_manager:person_group_delete", kwargs={"pk": group_id})
        response = self.client.post(url)

        assert response.status_code == 302
        assert not PersonGroup.objects.filter(group_id=group_id).exists()

    @override_settings(USE_I18N=False)
    def test_delete_view_shared_group_only_unshares(self):
        """Test that deleting a shared group only removes sharing."""
        other_user = UserFactory(username="otheruser")
        group = PersonGroupFactory(name="Shared Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(other_user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_delete", kwargs={"pk": group.group_id})
        response = self.client.post(url)

        assert response.status_code == 302
        # Group should still exist (shared with other user)
        group.refresh_from_db()
        assert group.name == "Shared Group"


@pytest.mark.django_db
class TestPersonGroupExplorerView:
    """Tests for PersonGroupExplorerView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def test_explorer_root_view(self):
        """Test explorer shows root groups when no group selected."""
        root_group = PersonGroupFactory(name="Root Group")
        create_or_update_permission(self.user, root_group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_explorer")
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.context["selected_group"] is None
        assert len(response.context["root_groups"]) == 1

    def test_explorer_selected_group(self):
        """Test explorer shows group details when selected."""
        group = PersonGroupFactory(name="Selected Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id})
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.context["selected_group"] == group

    def test_explorer_no_access_redirects(self):
        """Test explorer redirects when user has no access to group."""
        group = PersonGroupFactory(name="Private Group")
        # No permission granted

        url = reverse("gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id})
        response = self.client.get(url)

        assert response.status_code == 302

    def test_explorer_breadcrumbs(self):
        """Test explorer builds breadcrumbs from navigation history."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, child, permission_level=PermissionLevel.VIEWER)

        # First visit parent
        url_parent = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": parent.group_id}
        )
        self.client.get(url_parent)

        # Then visit child with from_group parameter
        url_child = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": child.group_id}
        )
        response = self.client.get(url_child + f"?from_group={parent.group_id}")

        assert response.status_code == 200
        breadcrumbs = response.context["breadcrumbs"]
        assert len(breadcrumbs) == 2
        assert breadcrumbs[0].name == "Parent"
        assert breadcrumbs[1].name == "Child"

    def test_explorer_shows_child_groups(self):
        """Test explorer shows child groups of selected group."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, child, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_explorer_with_group", kwargs={"pk": parent.group_id})
        response = self.client.get(url)

        assert response.status_code == 200
        assert len(response.context["child_groups"]) == 1
        assert response.context["child_groups"][0].name == "Child"

    def test_explorer_shows_members(self):
        """Test explorer shows members of selected group."""
        group = PersonGroupFactory(name="Group")
        person = PersonFactory(first_name="Member", family_name="Person")
        person.groups.add(group)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id})
        response = self.client.get(url)

        assert response.status_code == 200
        assert len(response.context["members"]) == 1

    def test_explorer_requires_login(self):
        """Test explorer requires authentication."""
        self.client.logout()
        url = reverse("gift_manager:person_group_explorer")
        response = self.client.get(url)

        assert response.status_code == 302


@pytest.mark.django_db
class TestReparentGroupAPI:
    """Tests for reparent_group API endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def _post_json(self, url, data):
        """Helper to post JSON data."""
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_reparent_requires_post(self):
        """Test reparent only accepts POST requests."""
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.get(url)
        assert response.status_code == 405

    def test_reparent_requires_valid_json(self):
        """Test reparent requires valid JSON."""
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.post(url, "invalid json", content_type="application/json")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_reparent_requires_group_id(self):
        """Test reparent requires group_id field."""
        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(url, {"parent_ids": []})

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "group_id" in data["message"]

    def test_reparent_group_not_found(self):
        """Test reparent returns 404 for non-existent group."""
        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url, {"group_id": "00000000-0000-0000-0000-000000000000", "parent_ids": []}
        )

        assert response.status_code == 404

    def test_reparent_requires_editor_permission(self):
        """Test reparent requires editor permission on group."""
        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(url, {"group_id": str(group.group_id), "parent_ids": []})

        assert response.status_code == 403

    def test_reparent_set_parents(self):
        """Test setting parents for a group."""
        group = PersonGroupFactory(name="Child Group")
        parent = PersonGroupFactory(name="Parent Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(group.group_id),
                "parent_ids": [str(parent.group_id)],
                "action": "set",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        group.refresh_from_db()
        assert parent in group.parent_groups.all()

    def test_reparent_add_parents(self):
        """Test adding parents to a group."""
        group = PersonGroupFactory(name="Child Group")
        parent1 = PersonGroupFactory(name="Parent 1")
        parent2 = PersonGroupFactory(name="Parent 2")
        group.parent_groups.add(parent1)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, parent1, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, parent2, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(group.group_id),
                "parent_ids": [str(parent2.group_id)],
                "action": "add",
            },
        )

        assert response.status_code == 200
        group.refresh_from_db()
        assert parent1 in group.parent_groups.all()
        assert parent2 in group.parent_groups.all()

    def test_reparent_remove_parents(self):
        """Test removing parents from a group."""
        group = PersonGroupFactory(name="Child Group")
        parent = PersonGroupFactory(name="Parent Group")
        group.parent_groups.add(parent)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(group.group_id),
                "parent_ids": [str(parent.group_id)],
                "action": "remove",
            },
        )

        assert response.status_code == 200
        group.refresh_from_db()
        assert parent not in group.parent_groups.all()

    def test_reparent_invalid_action(self):
        """Test reparent rejects invalid action."""
        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {"group_id": str(group.group_id), "parent_ids": [], "action": "invalid"},
        )

        assert response.status_code == 400

    def test_reparent_detects_cycle(self):
        """Test reparent detects and rejects cycles."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(self.user, child, permission_level=PermissionLevel.VIEWER)

        # Try to make parent a child of its own child (creates cycle)
        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(parent.group_id),
                "parent_ids": [str(child.group_id)],
                "action": "set",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "cycle" in data["message"].lower()

    def test_reparent_parent_not_found(self):
        """Test reparent returns 404 for non-existent parent."""
        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(group.group_id),
                "parent_ids": ["00000000-0000-0000-0000-000000000000"],
                "action": "set",
            },
        )

        assert response.status_code == 404

    def test_reparent_no_access_to_parent(self):
        """Test reparent requires access to parent groups."""
        group = PersonGroupFactory(name="Child Group")
        private_parent = PersonGroupFactory(name="Private Parent")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)
        # No permission on private_parent

        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(
            url,
            {
                "group_id": str(group.group_id),
                "parent_ids": [str(private_parent.group_id)],
                "action": "set",
            },
        )

        assert response.status_code == 403

    def test_reparent_requires_login(self):
        """Test reparent requires authentication."""
        self.client.logout()
        url = reverse("gift_manager:api_reparent_group")
        response = self._post_json(url, {"group_id": "test", "parent_ids": []})

        assert response.status_code == 302


@pytest.mark.django_db
class TestCheckEditorPermissionHelper:
    """Tests for _check_editor_permission helper function."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user

    def test_returns_true_for_editor(self):
        """Test helper returns True for editor."""
        from django.test import RequestFactory

        from gift_manager.views.person_group import _check_editor_permission

        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        # Mock messages framework
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", "session")
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        result = _check_editor_permission(request, group)
        assert result is True

    def test_returns_false_for_viewer(self):
        """Test helper returns False for viewer."""
        from django.test import RequestFactory

        from gift_manager.views.person_group import _check_editor_permission

        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        # Mock messages framework
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", "session")
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        result = _check_editor_permission(request, group)
        assert result is False
