"""Tests for PersonGroup views."""

# pylint: disable=too-many-lines
import json
from unittest.mock import patch

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client
from django.test import RequestFactory
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import PersonGroup
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views.person_group import _check_editor_permission
from gift_manager.views.person_group import get_person_group_management_context


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
        PersonGroupFactory(name="Inaccessible")
        accessible = PersonGroupFactory(name="Accessible")
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

    def test_list_view_tree_data_excludes_inaccessible_children(self):
        """Prefetched child groups are not rendered unless the user can access them."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Private child")
        child.parent_groups.add(parent)

        create_or_update_permission(self.user, parent, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        tree_data = response.context["tree_data"]
        assert [node["name"] for node in tree_data] == ["Parent"]
        assert tree_data[0]["has_children"] is False
        assert response.context["has_hierarchy"] is False

    def test_list_view_member_count(self):
        """Test member count is correctly computed."""
        group = PersonGroupFactory(name="Group with members")
        person1 = PersonFactory(first_name="John", family_name="Doe", shared_with=[self.user])
        person2 = PersonFactory(first_name="Jane", family_name="Doe", shared_with=[self.user])
        person1.groups.add(group)
        person2.groups.add(group)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        tree_data = response.context["tree_data"]
        assert len(tree_data) == 1
        assert tree_data[0]["member_count"] == 2

    def test_list_view_member_count_excludes_inaccessible_people(self):
        """Member count only includes people the user can access."""
        group = PersonGroupFactory(name="Group with hidden members")
        visible_person = PersonFactory(
            first_name="John", family_name="Doe", shared_with=[self.user]
        )
        hidden_person = PersonFactory(first_name="Jane", family_name="Doe")
        visible_person.groups.add(group)
        hidden_person.groups.add(group)

        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        tree_data = response.context["tree_data"]
        assert len(tree_data) == 1
        assert tree_data[0]["member_count"] == 1

    def test_management_context_can_skip_permission_json(self):
        """The list view can keep the permission mapping already built by its mixin."""
        group = PersonGroupFactory(name="Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        context = get_person_group_management_context(self.user, include_permissions=False)

        assert "user_permissions_json" not in context

    def test_list_view_reuses_permission_context(self):
        """The management helper does not recompute permissions after the mixin."""
        group1 = PersonGroupFactory(name="Group A")
        group2 = PersonGroupFactory(name="Group B")
        create_or_update_permission(self.user, group1, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user, group2, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_groups")
        with patch(
            "gift_manager.services.PermissionService.get_effective_permission",
            return_value=PermissionLevel.VIEWER,
        ) as get_effective_permission:
            response = self.client.get(url)

        assert response.status_code == 200
        assert get_effective_permission.call_count == 2

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

        # Viewer cannot access the edit form
        response = self.client.get(url)
        assert response.status_code == 403

        # Submitting changes should fail
        response = self.client.post(url, {"name": "Hacked Name"})
        assert response.status_code == 403
        other_group.refresh_from_db()
        assert other_group.name == "Other Group"  # Name unchanged

    @override_settings(USE_I18N=False)
    def test_update_view_honors_inherited_editor_permission(self):
        """Parent group editor permission can explicitly cascade to child edits."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)
        permission = create_or_update_permission(
            self.user, parent, permission_level=PermissionLevel.EDITOR
        )
        permission.inherit_permissions = True
        permission.save()

        url = reverse("gift_manager:person_group_edit", kwargs={"pk": child.group_id})

        get_response = self.client.get(url)
        post_response = self.client.post(url, {"name": "Updated Child"})

        child.refresh_from_db()
        assert get_response.status_code == 200
        assert post_response.status_code == 302
        assert child.name == "Updated Child"


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
        """Test that deleting a shared group keeps the final owner."""
        other_user = UserFactory(username="otheruser")
        group = PersonGroupFactory(name="Shared Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(other_user, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_delete", kwargs={"pk": group.group_id})
        response = self.client.post(url)

        assert response.status_code == 403
        group.refresh_from_db()
        assert group.name == "Shared Group"
        assert get_permission(group, self.user) == PermissionLevel.OWNER
        assert get_permission(group, other_user, "group") == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_delete_view_shared_group_unshares_when_another_owner_remains(self):
        """Test shared group delete removes current user if another owner remains."""
        other_owner = UserFactory(username="otherowner")
        viewer = UserFactory(username="viewer")
        group = PersonGroupFactory(name="Shared Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(other_owner, group, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(viewer, group, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:person_group_delete", kwargs={"pk": group.group_id})
        response = self.client.post(url)

        assert response.status_code == 302
        group.refresh_from_db()
        assert get_permission(group, self.user, "group") == PermissionLevel.NONE
        assert get_permission(group, other_owner, "group") == PermissionLevel.OWNER
        assert get_permission(group, viewer, "group") == PermissionLevel.VIEWER


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

        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id}
        )
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.context["selected_group"] == group

    def test_explorer_no_access_redirects(self):
        """Test explorer redirects when user has no access to group."""
        group = PersonGroupFactory(name="Private Group")
        # No permission granted

        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id}
        )
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

        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": parent.group_id}
        )
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

        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": group.group_id}
        )
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
        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        # Mock messages framework

        request.session = "session"
        messages = FallbackStorage(request)
        request._messages = messages  # pylint: disable=protected-access

        result = _check_editor_permission(request, group)
        assert result is True

    def test_returns_false_for_viewer(self):
        """Test helper returns False for viewer."""
        group = PersonGroupFactory(name="Test Group")
        create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        # Mock messages framework

        request.session = "session"
        messages = FallbackStorage(request)
        request._messages = messages  # pylint: disable=protected-access

        result = _check_editor_permission(request, group)
        assert result is False


@pytest.mark.django_db
class TestComplexHierarchies:
    """Tests for complex group hierarchies with multiple levels."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def _grant_access(self, *groups):
        """Grant viewer access to multiple groups."""
        for group in groups:
            create_or_update_permission(self.user, group, permission_level=PermissionLevel.VIEWER)

    def _grant_editor(self, *groups):
        """Grant editor access to multiple groups."""
        for group in groups:
            create_or_update_permission(self.user, group, permission_level=PermissionLevel.EDITOR)

    def test_deep_hierarchy_tree_view(self):
        """Test list view handles deep hierarchies (4 levels)."""
        # Create: grandparent -> parent -> child -> grandchild
        grandparent = PersonGroupFactory(name="Grandparent")
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        grandchild = PersonGroupFactory(name="Grandchild")

        parent.parent_groups.add(grandparent)
        child.parent_groups.add(parent)
        grandchild.parent_groups.add(child)

        self._grant_access(grandparent, parent, child, grandchild)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        tree_data = response.context["tree_data"]

        # Should have 4 nodes in the flattened tree
        assert len(tree_data) == 4

        # Check depths are correct
        depths = {node["name"]: node["depth"] for node in tree_data}
        assert depths["Grandparent"] == 0
        assert depths["Parent"] == 1
        assert depths["Child"] == 2
        assert depths["Grandchild"] == 3

    def test_multiple_parents_dag_structure(self):
        """Test handling of DAG structure (group with multiple parents)."""
        # Create diamond structure:
        #       root
        #      /    \
        #   left    right
        #      \    /
        #       leaf
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left Branch")
        right = PersonGroupFactory(name="Right Branch")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        self._grant_access(root, left, right, leaf)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        tree_data = response.context["tree_data"]

        # Leaf should have multiple parent_ids
        leaf_node = next(n for n in tree_data if n["name"] == "Leaf")
        assert len(leaf_node["parent_ids"]) == 2

    def test_multiple_children_tree_view(self):
        """Test handling of groups with multiple children."""
        parent = PersonGroupFactory(name="Parent")
        child1 = PersonGroupFactory(name="Child 1")
        child2 = PersonGroupFactory(name="Child 2")
        child3 = PersonGroupFactory(name="Child 3")

        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)
        child3.parent_groups.add(parent)

        self._grant_access(parent, child1, child2, child3)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        tree_data = response.context["tree_data"]

        # Parent should show has_children = True
        parent_node = next(n for n in tree_data if n["name"] == "Parent")
        assert parent_node["has_children"] is True

        # All children should be in the tree
        child_names = {n["name"] for n in tree_data if n["depth"] == 1}
        assert child_names == {"Child 1", "Child 2", "Child 3"}

    def test_deep_hierarchy_explorer_navigation(self):
        """Test explorer navigation through deep hierarchy."""
        # Create 4-level hierarchy
        level1 = PersonGroupFactory(name="Level 1")
        level2 = PersonGroupFactory(name="Level 2")
        level3 = PersonGroupFactory(name="Level 3")
        level4 = PersonGroupFactory(name="Level 4")

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)
        level4.parent_groups.add(level3)

        self._grant_access(level1, level2, level3, level4)

        # Navigate through hierarchy building breadcrumbs
        # Visit level 1
        url1 = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": level1.group_id}
        )
        self.client.get(url1)

        # Visit level 2 from level 1
        url2 = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": level2.group_id}
        )
        self.client.get(url2 + f"?from_group={level1.group_id}")

        # Visit level 3 from level 2
        url3 = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": level3.group_id}
        )
        self.client.get(url3 + f"?from_group={level2.group_id}")

        # Visit level 4 from level 3 - should have full breadcrumb trail
        url4 = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": level4.group_id}
        )
        response = self.client.get(url4 + f"?from_group={level3.group_id}")

        assert response.status_code == 200
        breadcrumbs = response.context["breadcrumbs"]
        assert len(breadcrumbs) == 4
        assert [b.name for b in breadcrumbs] == ["Level 1", "Level 2", "Level 3", "Level 4"]

    def test_explorer_child_groups_in_hierarchy(self):
        """Test explorer shows correct child groups at each level."""
        parent = PersonGroupFactory(name="Parent")
        child1 = PersonGroupFactory(name="Child 1")
        child2 = PersonGroupFactory(name="Child 2")
        grandchild = PersonGroupFactory(name="Grandchild")

        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)
        grandchild.parent_groups.add(child1)

        self._grant_access(parent, child1, child2, grandchild)

        # Check parent's children
        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": parent.group_id}
        )
        response = self.client.get(url)

        assert response.status_code == 200
        child_names = {g.name for g in response.context["child_groups"]}
        assert child_names == {"Child 1", "Child 2"}

        # Check child1's children
        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": child1.group_id}
        )
        response = self.client.get(url)

        child_names = {g.name for g in response.context["child_groups"]}
        assert child_names == {"Grandchild"}

    def test_explorer_parent_groups_in_hierarchy(self):
        """Test explorer shows correct parent groups."""
        grandparent = PersonGroupFactory(name="Grandparent")
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")

        parent.parent_groups.add(grandparent)
        child.parent_groups.add(parent)

        self._grant_access(grandparent, parent, child)

        # Check child's parents
        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": child.group_id}
        )
        response = self.client.get(url)

        assert response.status_code == 200
        parent_names = {g.name for g in response.context["parent_groups"]}
        assert parent_names == {"Parent"}

    def test_reparent_in_deep_hierarchy(self):
        """Test reparenting a group in a deep hierarchy."""
        level1 = PersonGroupFactory(name="Level 1")
        level2 = PersonGroupFactory(name="Level 2")
        level3 = PersonGroupFactory(name="Level 3")
        level4 = PersonGroupFactory(name="Level 4")

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)
        level4.parent_groups.add(level3)

        self._grant_editor(level4)
        self._grant_access(level1, level2, level3)

        # Move level4 to be a direct child of level1 (skip levels 2 and 3)
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.post(
            url,
            json.dumps(
                {
                    "group_id": str(level4.group_id),
                    "parent_ids": [str(level1.group_id)],
                    "action": "set",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        level4.refresh_from_db()
        assert level1 in level4.parent_groups.all()
        assert level3 not in level4.parent_groups.all()

    def test_reparent_add_second_parent(self):
        """Test adding a second parent to create DAG."""
        parent1 = PersonGroupFactory(name="Parent 1")
        parent2 = PersonGroupFactory(name="Parent 2")
        child = PersonGroupFactory(name="Child")

        child.parent_groups.add(parent1)

        self._grant_editor(child)
        self._grant_access(parent1, parent2)

        # Add parent2 as additional parent
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.post(
            url,
            json.dumps(
                {
                    "group_id": str(child.group_id),
                    "parent_ids": [str(parent2.group_id)],
                    "action": "add",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        child.refresh_from_db()
        assert parent1 in child.parent_groups.all()
        assert parent2 in child.parent_groups.all()
        assert child.parent_groups.count() == 2

    def test_reparent_remove_one_of_multiple_parents(self):
        """Test removing one parent from a group with multiple parents."""
        parent1 = PersonGroupFactory(name="Parent 1")
        parent2 = PersonGroupFactory(name="Parent 2")
        parent3 = PersonGroupFactory(name="Parent 3")
        child = PersonGroupFactory(name="Child")

        child.parent_groups.add(parent1, parent2, parent3)

        self._grant_editor(child)
        self._grant_access(parent1, parent2, parent3)

        # Remove parent2
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.post(
            url,
            json.dumps(
                {
                    "group_id": str(child.group_id),
                    "parent_ids": [str(parent2.group_id)],
                    "action": "remove",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        child.refresh_from_db()
        assert parent1 in child.parent_groups.all()
        assert parent2 not in child.parent_groups.all()
        assert parent3 in child.parent_groups.all()
        assert child.parent_groups.count() == 2

    def test_cycle_detection_in_deep_hierarchy(self):
        """Test cycle detection prevents creating cycles in deep hierarchies."""
        # Create: A -> B -> C -> D
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")
        d = PersonGroupFactory(name="D")

        b.parent_groups.add(a)
        c.parent_groups.add(b)
        d.parent_groups.add(c)

        self._grant_editor(a)
        self._grant_access(b, c, d)

        # Try to make A a child of D (would create cycle: A -> B -> C -> D -> A)
        url = reverse("gift_manager:api_reparent_group")
        response = self.client.post(
            url,
            json.dumps(
                {
                    "group_id": str(a.group_id),
                    "parent_ids": [str(d.group_id)],
                    "action": "add",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "cycle" in data["message"].lower()

    def test_detail_view_nested_members_in_hierarchy(self):
        """Test detail view shows nested members from child groups."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        grandchild = PersonGroupFactory(name="Grandchild")

        child.parent_groups.add(parent)
        grandchild.parent_groups.add(child)

        # Add members at different levels
        person_parent = PersonFactory(first_name="Parent", family_name="Member")
        person_child = PersonFactory(first_name="Child", family_name="Member")
        person_grandchild = PersonFactory(first_name="Grandchild", family_name="Member")

        person_parent.groups.add(parent)
        person_child.groups.add(child)
        person_grandchild.groups.add(grandchild)

        self._grant_access(parent, child, grandchild)
        create_or_update_permission(
            self.user, person_parent, permission_level=PermissionLevel.VIEWER
        )
        create_or_update_permission(
            self.user, person_child, permission_level=PermissionLevel.VIEWER
        )
        create_or_update_permission(
            self.user, person_grandchild, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_group_detail", kwargs={"pk": parent.group_id})
        response = self.client.get(url)

        assert response.status_code == 200

        # Direct members should only include parent's member
        direct_members = list(response.context["members"])
        assert len(direct_members) == 1
        assert direct_members[0].first_name == "Parent"

        # Nested members should include all members from hierarchy
        nested_members = list(response.context["nested_members"])
        nested_names = {m.first_name for m in nested_members}
        assert nested_names == {"Parent", "Child", "Grandchild"}

    def test_list_view_handles_complex_dag(self):
        """Test list view correctly handles complex DAG with shared descendants."""
        #       root1    root2
        #         |   \ /   |
        #         A    B    C
        #          \  / \  /
        #           D    E
        #            \  /
        #             F
        root1 = PersonGroupFactory(name="Root1")
        root2 = PersonGroupFactory(name="Root2")
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")
        d = PersonGroupFactory(name="D")
        e = PersonGroupFactory(name="E")
        f = PersonGroupFactory(name="F")

        a.parent_groups.add(root1)
        b.parent_groups.add(root1, root2)
        c.parent_groups.add(root2)
        d.parent_groups.add(a, b)
        e.parent_groups.add(b, c)
        f.parent_groups.add(d, e)

        self._grant_access(root1, root2, a, b, c, d, e, f)

        url = reverse("gift_manager:person_groups")
        response = self.client.get(url)

        assert response.status_code == 200
        tree_data = response.context["tree_data"]

        # All 8 groups should be present
        all_names = {n["name"] for n in tree_data}
        assert all_names == {"Root1", "Root2", "A", "B", "C", "D", "E", "F"}

        # Check that has_hierarchy is True
        assert response.context["has_hierarchy"] is True

    def test_explorer_with_multiple_roots(self):
        """Test explorer shows multiple root groups."""
        root1 = PersonGroupFactory(name="Root 1")
        root2 = PersonGroupFactory(name="Root 2")
        root3 = PersonGroupFactory(name="Root 3")
        child = PersonGroupFactory(name="Child of Root 1")
        child.parent_groups.add(root1)

        self._grant_access(root1, root2, root3, child)

        # Visit explorer without selecting a group
        url = reverse("gift_manager:person_group_explorer")
        response = self.client.get(url)

        assert response.status_code == 200
        root_names = {g.name for g in response.context["root_groups"]}
        # Only groups without parents should be shown as roots
        assert root_names == {"Root 1", "Root 2", "Root 3"}
