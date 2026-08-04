import json
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views import FilterByUserMixin
from gift_manager.views import GetObjectByTokenMixin


class TestFilterByUserMixin:
    """Tests for FilterByUserMixin."""

    def test_get_queryset(self):
        """Test queryset is filtered by current user."""
        # Arrange
        mixin = FilterByUserMixin()
        mixin.model = Mock()
        mixin.request = Mock()
        mixin.request.user = Mock(spec=User)

        mock_queryset = Mock()
        mixin.model.objects.accessible_by.return_value = mock_queryset

        # Act
        result = mixin.get_queryset()

        # Assert
        mixin.model.objects.accessible_by.assert_called_once_with(mixin.request.user)
        assert result == mock_queryset


class TestGetObjectByTokenMixin:
    """Tests for GetObjectByTokenMixin."""

    def test_get_object_success(self):
        """Test getting object by token successfully."""
        # Arrange
        mixin = GetObjectByTokenMixin()
        mixin.pk_name = "test_id"
        mixin.get_queryset = Mock(return_value=Mock())
        mixin.kwargs = {"pk": "123"}

        with patch(
            "gift_manager.views.base.get_object_or_404", return_value="found_object"
        ) as mock_get:
            # Act
            result = mixin.get_object()

            # Assert
            mock_get.assert_called_once_with(mixin.get_queryset.return_value, test_id="123")
            assert result == "found_object"

    def test_get_object_missing_pk(self):
        """Test error when pk is missing."""
        # Arrange
        mixin = GetObjectByTokenMixin()
        mixin.get_queryset = Mock(return_value=Mock())


@pytest.mark.django_db
class TestBaseCreateView:
    """Tests for BaseCreateView."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_gift_create_view_with_shared_permissions(self):
        """Test creating an object with sharing permissions."""
        # Create a friend user using factory
        friend = UserFactory(username="testfriend", email="friend@example.com")
        # Add the friend to the user's profile
        self.user.profile.friends.add(friend.profile)

        # Create gift with sharing
        url = reverse("gift_manager:gift_create")
        data = {
            "name": "Test Shared Gift",
            "comment": "Gift with sharing",
            "share_with_" + str(friend.id): PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302  # Redirect after success
        assert response.url == reverse("gift_manager:gifts")

        # Check that gift was created
        gift = Gift.objects.get(name="Test Shared Gift")
        assert gift is not None

        # Check that sharing was created
        permissions = get_permission(gift, friend)
        assert permissions == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_gift_create_can_redirect_to_new_gift_plan_form(self):
        """The secondary save action continues into the new gift's gift plan flow."""
        url = reverse("gift_manager:gift_create")

        response = self.client.post(
            url,
            {
                "name": "Gift with immediate plan",
                "comment": "Continue planning after save",
                "after_save": "create_gift_plan",
            },
        )

        gift = Gift.objects.get(name="Gift with immediate plan")
        assert response.status_code == 302
        assert response.url == reverse(
            "gift_manager:gift_relation_create", kwargs={"pk": gift.gift_id}
        )
        assert get_permission(gift, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_htmx_gift_create_can_continue_to_new_gift_plan_form(self):
        """The offcanvas secondary save action swaps in the new gift's plan form."""
        url = reverse("gift_manager:gift_create")

        response = self.client.post(
            url,
            {
                "name": "HTMX gift with immediate plan",
                "comment": "Continue planning after save",
                "after_save": "create_gift_plan",
            },
            HTTP_HX_REQUEST="true",
        )

        gift = Gift.objects.get(name="HTMX gift with immediate plan")
        plan_url = reverse("gift_manager:gift_relation_create", kwargs={"pk": gift.gift_id})
        content = response.content.decode()
        triggers = json.loads(response["HX-Trigger"])

        assert response.status_code == 200
        assert "HX-Redirect" not in response
        assert "offcanvas:close" not in triggers
        assert "list:update" in triggers
        assert triggers["showNotification"]["type"] == "success"
        assert 'id="relation-form"' in content
        assert f'action="{plan_url}"' in content
        assert f'hx-post="{plan_url}"' in content
        assert 'name="recipient"' in content
        assert get_permission(gift, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_invalid_gift_create_does_not_redirect_to_new_gift_plan_form(self):
        """Invalid secondary submissions stay on the gift form."""
        response = self.client.post(
            reverse("gift_manager:gift_create"),
            {
                "name": "",
                "comment": "Missing name",
                "after_save": "create_gift_plan",
            },
        )

        assert response.status_code == 200
        assert "HX-Redirect" not in response
        assert not Gift.objects.filter(comment="Missing name").exists()

    @override_settings(USE_I18N=False)
    def test_gift_create_rejects_forged_non_friend_share(self):
        """Test create forms do not trust forged non-friend share IDs."""
        non_friend = UserFactory(username="stranger", email="stranger@example.com")

        url = reverse("gift_manager:gift_create")
        response = self.client.post(
            url,
            {
                "name": "Forged Shared Gift",
                "comment": "Gift with forged sharing",
                f"share_with_{non_friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 403
        assert not Gift.objects.filter(name="Forged Shared Gift").exists()

    @override_settings(USE_I18N=False)
    def test_gift_create_rejects_invalid_share_permission_level(self):
        """Test create forms reject forged permission levels."""
        friend = UserFactory(username="testfriend", email="friend@example.com")
        self.user.profile.friends.add(friend.profile)

        url = reverse("gift_manager:gift_create")
        response = self.client.post(
            url,
            {
                "name": "Invalid Permission Gift",
                "comment": "Gift with invalid sharing",
                f"share_with_{friend.id}": "999",
            },
        )

        assert response.status_code == 403
        assert not Gift.objects.filter(name="Invalid Permission Gift").exists()


@pytest.mark.django_db
class TestEditPermissionMixin:
    """Tests for EditPermissionMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user, person):
        """Setup test fixtures."""
        self.user = user
        self.person = person

        # Create a friend using factory
        self.friend = UserFactory(username="testfriend", email="friend@example.com")

        # Add the friend to the user's profile
        self.user.profile.friends.add(self.friend.profile)

        # Create a permission for the person
        create_or_update_permission(self.user, self.person, permission_level=PermissionLevel.OWNER)

        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_viewer_cannot_get_update_form(self):
        """Test view-only users cannot access edit forms."""
        viewer = UserFactory(username="viewer", email="viewer@example.com")
        create_or_update_permission(viewer, self.person, permission_level=PermissionLevel.VIEWER)
        self.client.force_login(viewer)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.get(url)

        assert response.status_code == 403

    @override_settings(USE_I18N=False)
    def test_viewer_cannot_post_update_or_self_elevate(self):
        """Test view-only users cannot update objects or gain editor permission."""
        viewer = UserFactory(username="viewer", email="viewer@example.com")
        create_or_update_permission(viewer, self.person, permission_level=PermissionLevel.VIEWER)
        self.person.user_link = self.user
        self.person.save(update_fields=["user_link"])
        self.client.force_login(viewer)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Hacked",
                "family_name": "Person",
                "email_address": "hacked@example.com",
            },
        )

        assert response.status_code == 403
        self.person.refresh_from_db()
        assert self.person.first_name != "Hacked"
        assert self.person.user_link == self.user
        assert get_permission(self.person, viewer) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_editor_can_update_without_permission_escalation(self):
        """Test editors can update objects without being promoted to owner."""
        editor = UserFactory(username="editor", email="editor@example.com")
        editor.profile.friends.add(self.friend.profile)
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        self.person.user_link = self.user
        self.person.save(update_fields=["user_link"])
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Edited",
                "family_name": "Person",
                "email_address": "edited@example.com",
                f"permission_{self.friend.id}": "not_shared",
            },
        )

        assert response.status_code == 302
        self.person.refresh_from_db()
        assert self.person.first_name == "Edited"
        assert self.person.user_link == self.user
        assert get_permission(self.person, self.friend) == PermissionLevel.NONE
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_editor_can_update_with_unchanged_existing_permission_field(self):
        """Test editors can save when submitted sharing fields are unchanged."""
        editor = UserFactory(username="editor", email="editor@example.com")
        editor.profile.friends.add(self.friend.profile)
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        create_or_update_permission(
            self.friend, self.person, permission_level=PermissionLevel.VIEWER
        )
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Edited Again",
                "family_name": "Person",
                "email_address": "edited-again@example.com",
                f"permission_{self.friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 302
        self.person.refresh_from_db()
        assert self.person.first_name == "Edited Again"
        assert get_permission(self.person, self.friend) == PermissionLevel.VIEWER
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR

    @override_settings(USE_I18N=False)
    def test_owner_can_update_without_permission_change(self):
        """Test owners can update objects without changing ownership metadata."""
        self.person.user_link = self.user
        self.person.save(update_fields=["user_link"])

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Owned",
                "family_name": "Person",
                "email_address": "owned@example.com",
            },
        )

        assert response.status_code == 302
        self.person.refresh_from_db()
        assert self.person.first_name == "Owned"
        assert self.person.user_link == self.user
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_viewer_cannot_update_permissions_or_self_elevate(self):
        """Test permission update requests require edit access to the object."""
        viewer = UserFactory(username="viewer", email="viewer@example.com")
        create_or_update_permission(viewer, self.person, permission_level=PermissionLevel.VIEWER)
        self.client.force_login(viewer)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(viewer.id),
                "permission": str(PermissionLevel.EDITOR),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, viewer) == PermissionLevel.VIEWER
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_editor_cannot_promote_self_to_owner_via_permission_update(self):
        """Test editors cannot elevate themselves through permission update requests."""
        editor = UserFactory(username="editor", email="editor@example.com")
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(editor.id),
                "permission": str(PermissionLevel.OWNER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_editor_cannot_downgrade_owner_via_permission_update(self):
        """Test editors cannot reduce an owner's permissions."""
        editor = UserFactory(username="editor", email="editor@example.com")
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(self.user.id),
                "permission": str(PermissionLevel.VIEWER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_editor_cannot_remove_owner_via_permission_action(self):
        """Test explicit permission actions cannot let editors remove owners."""
        editor = UserFactory(username="editor", email="editor@example.com")
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "remove_share": "1",
                "user_id": str(self.user.id),
            },
        )

        assert response.status_code == 403
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_editor_main_form_permission_fields_do_not_mutate_permissions(self):
        """Test editors cannot smuggle permission changes through normal edit forms."""
        editor = UserFactory(username="editor", email="editor@example.com")
        editor.profile.friends.add(self.friend.profile)
        create_or_update_permission(editor, self.person, permission_level=PermissionLevel.EDITOR)
        self.client.force_login(editor)

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Should Roll Back",
                "family_name": "Person",
                "email_address": "rollback@example.com",
                f"permission_{self.friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 403
        self.person.refresh_from_db()
        assert self.person.first_name != "Should Roll Back"
        assert get_permission(self.person, self.friend) == PermissionLevel.NONE
        assert get_permission(self.person, editor) == PermissionLevel.EDITOR

    @override_settings(USE_I18N=False)
    def test_owner_cannot_remove_last_owner_via_permission_update(self):
        """Test the final owner cannot be removed from an object."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(self.user.id),
                "permission": "not_shared",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_owner_can_update_friend_permission(self):
        """Test owners can still manage sharing for editable objects."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(self.friend.id),
                "permission": str(PermissionLevel.VIEWER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert get_permission(self.person, self.friend) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_owner_cannot_share_with_non_friend_via_permission_update(self):
        """Test owners cannot forge permission-update targets outside their friends."""
        non_friend = UserFactory(username="stranger", email="stranger@example.com")

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(non_friend.id),
                "permission": str(PermissionLevel.VIEWER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, non_friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_owner_cannot_share_with_non_friend_via_ajax_permission_update(self):
        """Test AJAX permission updates reject forged non-friend targets."""
        non_friend = UserFactory(username="stranger", email="stranger@example.com")

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(non_friend.id),
                "permission_level": str(PermissionLevel.VIEWER),
            },
            HTTP_X_PERMISSION_UPDATE="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, non_friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_owner_cannot_share_with_non_friend_via_permission_action(self):
        """Test explicit permission actions reject forged non-friend targets."""
        non_friend = UserFactory(username="stranger", email="stranger@example.com")

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "share_with": "1",
                "user_id": str(non_friend.id),
                "permission": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 403
        assert get_permission(self.person, non_friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_owner_cannot_share_with_non_friend_via_main_form_field(self):
        """Test forged normal form permission fields reject non-friend targets."""
        non_friend = UserFactory(username="stranger", email="stranger@example.com")

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "first_name": "Should Roll Back",
                "family_name": "Person",
                "email_address": "rollback@example.com",
                f"permission_{non_friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 403
        self.person.refresh_from_db()
        assert self.person.first_name != "Should Roll Back"
        assert get_permission(self.person, non_friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_owner_cannot_raise_existing_non_friend_collaborator_permission(self):
        """Test non-friend collaborators cannot receive expanded access."""
        collaborator = UserFactory(username="collaborator", email="collaborator@example.com")
        create_or_update_permission(
            collaborator, self.person, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(collaborator.id),
                "permission": str(PermissionLevel.EDITOR),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert get_permission(self.person, collaborator) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_owner_cannot_raise_existing_non_friend_via_permission_action(self):
        """Test explicit permission actions cannot expand non-friend access."""
        collaborator = UserFactory(username="collaborator", email="collaborator@example.com")
        create_or_update_permission(
            collaborator, self.person, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "update_permission": "1",
                "user_id": str(collaborator.id),
                "permission": str(PermissionLevel.EDITOR),
            },
        )

        assert response.status_code == 403
        assert get_permission(self.person, collaborator) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_owner_can_lower_existing_non_friend_collaborator_permission(self):
        """Test owners can reduce existing non-friend collaborator access."""
        collaborator = UserFactory(username="collaborator", email="collaborator@example.com")
        create_or_update_permission(
            collaborator, self.person, permission_level=PermissionLevel.EDITOR
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(collaborator.id),
                "permission": str(PermissionLevel.VIEWER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert get_permission(self.person, collaborator) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_owner_can_remove_existing_non_friend_collaborator(self):
        """Test owners can remove existing collaborators who are no longer friends."""
        collaborator = UserFactory(username="collaborator", email="collaborator@example.com")
        create_or_update_permission(
            collaborator, self.person, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(collaborator.id),
                "permission": "not_shared",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert get_permission(self.person, collaborator) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_permission_update_rejects_invalid_permission_value(self):
        """Test permission update requests validate posted permission levels."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": str(self.friend.id),
                "permission": "999",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert get_permission(self.person, self.friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_permission_update_rejects_unknown_user(self):
        """Test permission update requests reject unknown target users."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})
        response = self.client.post(
            url,
            {
                "user_id": "999999",
                "permission": str(PermissionLevel.VIEWER),
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 404
        assert self.person.shared_with.count() == 1

    @override_settings(USE_I18N=False)
    def test_gift_tag_update_does_not_reveal_inaccessible_tag(self):
        """Test inaccessible gift tag edit URLs use the filtered queryset."""
        tag = GiftTag.objects.create(name="Private")

        url = reverse("gift_manager:gift_tag_edit", kwargs={"pk": tag.tag_id})
        response = self.client.get(url)

        assert response.status_code == 404


@pytest.mark.django_db
class TestDeleteSharedMixin:
    """Tests for DeleteSharedMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create another user using factory
        self.other_user = UserFactory(username="otheruser", email="other@example.com")

        # Create a test person shared with both users using factory
        self.person = PersonFactory(first_name="Shared", family_name="Person")
        create_or_update_permission(user, self.person, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(
            self.other_user, self.person, permission_level=PermissionLevel.VIEWER
        )

        # Create a test person shared only with current user
        self.person_not_shared = PersonFactory(first_name="Not", family_name="Shared")
        create_or_update_permission(
            user, self.person_not_shared, permission_level=PermissionLevel.OWNER
        )

    @override_settings(USE_I18N=False)
    def test_delete_shared_object_keeps_last_owner(self):
        """Test owners cannot unshare themselves when no other owner remains."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Act
        response = self.client.post(url)

        # Assert
        assert response.status_code == 403
        self.person.refresh_from_db()
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER
        assert get_permission(self.person, self.other_user) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_delete_shared_object_with_another_owner_removes_current_user(self):
        """Test deleting a shared object can remove current user when another owner remains."""
        other_owner = UserFactory(username="otherowner", email="owner@example.com")
        create_or_update_permission(
            other_owner, self.person, permission_level=PermissionLevel.OWNER
        )

        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})
        response = self.client.post(url)

        assert response.status_code == 302
        self.person.refresh_from_db()
        assert get_permission(self.person, self.user) == PermissionLevel.NONE
        assert get_permission(self.person, other_owner) == PermissionLevel.OWNER
        assert get_permission(self.person, self.other_user) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_viewer_cannot_use_delete_post_to_leave_shared_object(self):
        """Viewer delete posts must not delete or silently unshare the object."""
        self.client.force_login(self.other_user)
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.post(url)

        assert response.status_code == 403
        self.person.refresh_from_db()
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER
        assert get_permission(self.person, self.other_user) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_viewer_can_explicitly_leave_shared_object(self):
        """The explicit leave-access action removes only the viewer's share."""
        self.client.force_login(self.other_user)
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.post(url, {"leave_access": "1"})

        assert response.status_code == 302
        self.person.refresh_from_db()
        assert get_permission(self.person, self.user) == PermissionLevel.OWNER
        assert get_permission(self.person, self.other_user) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_delete_preserves_person_with_implicit_user_link_owner(self):
        """Test editors cannot delete a person owned only through user_link."""
        linked_owner = UserFactory(username="linkedowner", email="linked@example.com")
        editor = UserFactory(username="editor", email="editor@example.com")
        person = PersonFactory(
            user_link=linked_owner,
            first_name="Implicit",
            family_name="Owner",
        )
        create_or_update_permission(editor, person, permission_level=PermissionLevel.EDITOR)
        self.client.force_login(editor)

        url = reverse("gift_manager:person_delete", kwargs={"pk": person.person_id})
        response = self.client.post(url)

        assert response.status_code == 302
        person.refresh_from_db()
        assert person.user_link == linked_owner
        assert get_permission(person, editor) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_delete_non_shared_object(self):
        """Test deleting an object not shared with other users."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person_not_shared.person_id})

        # Act
        response = self.client.post(url)

        # Assert
        assert response.status_code == 302  # Redirect after action

        # The person should be completely deleted
        with pytest.raises(Person.DoesNotExist):
            self.person_not_shared.refresh_from_db()
