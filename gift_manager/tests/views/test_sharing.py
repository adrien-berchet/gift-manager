# pylint: disable=protected-access
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.http.request import QueryDict
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.views import ShareObjectsView


@pytest.mark.django_db
class TestShareObjectsView:
    """Tests for ShareObjectsView."""

    @pytest.fixture(autouse=True)
    def setup_users_and_relations(self, user, userpassword, person, group, gift, event, status):
        """Create test users and relations."""
        # Create owner user
        self.owner = user

        # Create friend user
        self.friend = User.objects.create_user(
            username="friend",
            email="friend@example.com",
            password=userpassword,
        )
        self.owner.profile.friends.add(self.friend.profile)

        # Create a non-friend user for forged recipient checks
        self.stranger = User.objects.create_user(
            username="stranger",
            email="stranger@example.com",
            password=userpassword,
        )

        # Create test person
        self.person = person
        create_or_update_permission(self.owner, self.person, permission_level=PermissionLevel.OWNER)

        # Create test group
        self.group = group
        create_or_update_permission(
            self.owner, self.group, permission_level=PermissionLevel.OWNER, object_attr="group"
        )

        # Create test event
        self.event = event
        create_or_update_permission(self.owner, self.event, permission_level=PermissionLevel.OWNER)

        # Create test gift
        self.gift = gift
        create_or_update_permission(self.owner, self.gift, permission_level=PermissionLevel.OWNER)

        # Create test relation status
        self.status = status

        # Create test relations
        self.relation_person = Relation.objects.create(
            person=self.person,
            gift=self.gift,
            event=self.event,
            status=status,
        )
        create_or_update_permission(
            self.owner, self.relation_person, permission_level=PermissionLevel.OWNER
        )
        self.relation_group = Relation.objects.create(
            gift=self.gift,
            group=self.group,
            event=self.event,
            status=status,
        )
        create_or_update_permission(
            self.owner, self.relation_group, permission_level=PermissionLevel.OWNER
        )

        # Authenticate the client
        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_get_share_objects_view(self):
        """Test that GET request renders share_objects.html template."""
        # Arrange
        url = reverse("gift_manager:share_objects")

        # Act
        response = self.client.get(url)

        # Assert
        assert response.status_code == 200
        assert "gift_manager/share_objects.html" in [t.name for t in response.templates]

    @override_settings(USE_I18N=False)
    def test_post_share_objects_success(self):
        """Test sharing objects with a friend."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            "relations": [self.relation_person.relation_id, self.relation_group.relation_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        # Check redirection
        assert response.status_code == 302
        assert reverse("gift_manager:share_objects") in response.url

        assert get_permission(self.relation_person, self.friend) == PermissionLevel.VIEWER
        assert get_permission(self.relation_group, self.friend) == PermissionLevel.VIEWER
        assert get_permission(self.gift, self.friend) == PermissionLevel.VIEWER
        assert get_permission(self.person, self.friend) == PermissionLevel.VIEWER
        assert get_permission(self.group, self.friend, "group") == PermissionLevel.VIEWER
        assert get_permission(self.event, self.friend) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_post_share_objects_with_invalid_data(self):
        """Test sharing objects with invalid data."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            # Missing object IDs
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        # Should return to the form with errors
        assert response.status_code == 200

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_non_friend_recipient(self):
        """Test that posted user IDs must belong to the current user's friends."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            "gifts": [self.gift.gift_id],
            "friends": [self.stranger.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.gift, self.stranger) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_mixed_friend_and_non_friend_recipients(self):
        """Test one forged recipient rejects the whole share operation."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            "gifts": [self.gift.gift_id],
            "friends": [self.friend.id, self.stranger.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.gift, self.friend) == PermissionLevel.NONE
        assert get_permission(self.gift, self.stranger) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_forged_private_object_id(self, userpassword):
        """Test that posted object IDs must be shareable by the current user."""
        # Arrange
        other_owner = User.objects.create_user(
            username="other-owner",
            email="other-owner@example.com",
            password=userpassword,
        )
        private_gift = Gift.objects.create(name="Private gift")
        create_or_update_permission(
            other_owner,
            private_gift,
            permission_level=PermissionLevel.OWNER,
        )

        url = reverse("gift_manager:share_objects")
        data = {
            "gifts": [self.gift.gift_id, private_gift.gift_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(private_gift, self.friend) == PermissionLevel.NONE
        assert get_permission(self.gift, self.friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_viewer_sharing_onward(self, userpassword):
        """Test that users with view-only access cannot share objects onward."""
        # Arrange
        recipient = User.objects.create_user(
            username="recipient",
            email="recipient@example.com",
            password=userpassword,
        )
        self.friend.profile.friends.add(recipient.profile)
        create_or_update_permission(
            self.friend,
            self.gift,
            permission_level=PermissionLevel.VIEWER,
        )
        self.client.force_login(self.friend)

        url = reverse("gift_manager:share_objects")
        data = {
            "gifts": [self.gift.gift_id],
            "friends": [recipient.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.gift, recipient) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_grant_above_actor_permission(self, userpassword):
        """Test that users cannot grant a permission level higher than their own."""
        # Arrange
        recipient = User.objects.create_user(
            username="editor-recipient",
            email="editor-recipient@example.com",
            password=userpassword,
        )
        self.friend.profile.friends.add(recipient.profile)
        create_or_update_permission(
            self.friend,
            self.gift,
            permission_level=PermissionLevel.EDITOR,
        )
        self.client.force_login(self.friend)

        url = reverse("gift_manager:share_objects")
        data = {
            "gifts": [self.gift.gift_id],
            "friends": [recipient.id],
            "permission_level": PermissionLevel.OWNER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.gift, recipient) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_user_link_owner_can_share_despite_lower_explicit_permission(self):
        """Test effective owner permission wins over stale lower explicit rows."""
        # Arrange
        self.person.user_link = self.owner
        self.person.save(update_fields=["user_link"])
        create_or_update_permission(
            self.owner,
            self.person,
            permission_level=PermissionLevel.VIEWER,
        )

        url = reverse("gift_manager:share_objects")
        data = {
            "persons": [self.person.person_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.EDITOR,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302
        assert get_permission(self.person, self.friend) == PermissionLevel.EDITOR

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_relation_with_unshareable_related_object(self):
        """Test relation cascading cannot share related objects the actor cannot share."""
        # Arrange
        private_gift = Gift.objects.create(name="Unshareable related gift")
        relation = Relation.objects.create(
            person=self.person,
            gift=private_gift,
            event=self.event,
            status=self.status,
        )
        create_or_update_permission(self.owner, relation, permission_level=PermissionLevel.OWNER)

        url = reverse("gift_manager:share_objects")
        data = {
            "relations": [relation.relation_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(relation, self.friend) == PermissionLevel.NONE
        assert get_permission(private_gift, self.friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_group_share_with_unshareable_member(self):
        """Test group member cascading cannot share persons the actor cannot share."""
        # Arrange
        private_person = Person.objects.create(first_name="Private", family_name="Member")
        private_person.groups.add(self.group)

        url = reverse("gift_manager:share_objects")
        data = {
            "person_groups": [self.group.group_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
            "share_group_persons": "on",
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.group, self.friend, "group") == PermissionLevel.NONE
        assert get_permission(private_person, self.friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_rejects_group_share_with_unshareable_child(self):
        """Test child-group cascading cannot share groups the actor cannot share."""
        # Arrange
        private_child_group = PersonGroup.objects.create(name="Private child group")
        private_child_group.parent_groups.add(self.group)

        url = reverse("gift_manager:share_objects")
        data = {
            "person_groups": [self.group.group_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
            "share_child_groups": "on",
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        assert get_permission(self.group, self.friend, "group") == PermissionLevel.NONE
        assert get_permission(private_child_group, self.friend, "group") == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_share_objects_editor_permission(self):
        """Test sharing objects with editor permission level."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            "relations": [self.relation_person.relation_id, self.relation_group.relation_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.EDITOR,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        # Check redirection
        assert response.status_code == 302

        # Check permissions were created with correct level
        # Simplified check - adapt based on your permissions model
        for obj in [
            self.relation_person,
            self.relation_group,
            self.gift,
            self.person,
            self.group,
            self.event,
        ]:
            perm = get_permission(obj, self.friend)
            assert perm == PermissionLevel.EDITOR

    @override_settings(USE_I18N=False)
    def test_post_share_objects_with_share_group_persons(self):
        """Test sharing person groups with the option to share group members."""
        # Arrange
        url = reverse("gift_manager:share_objects")
        data = {
            "person_groups": [self.group.group_id],
            "friends": [self.friend.id],
            "permission_level": PermissionLevel.VIEWER,
            "share_group_persons": "on",  # Option to share persons in the group
        }
        self.person.groups.add(self.group)

        # Act
        response = self.client.post(url, data)

        # Assert
        # Check redirection
        assert response.status_code == 302

        # Check permissions for group
        group_permissions = get_permission(self.group, self.friend, "group")
        assert group_permissions == PermissionLevel.VIEWER

        # Check permissions for persons in the group
        for person in self.group.person_set.all():
            person_permissions = get_permission(person, self.friend)
            assert person_permissions == PermissionLevel.VIEWER

    def test_share_objects_view_helper_methods(self):
        """Test helper methods of the ShareObjectsView class."""
        # Arrange
        view = ShareObjectsView()
        friends = [self.friend]

        # Test _share_persons method
        person_ids = [self.person.person_id]
        num_shared = view._share_persons(
            person_ids,
            friends,
            PermissionLevel.EDITOR,
            actor=self.owner,
        )
        assert num_shared == 1
        permissions = get_permission(self.person, self.friend)
        assert permissions == PermissionLevel.EDITOR

        # Test _share_events method
        event_ids = [self.event.event_id]
        num_shared = view._share_events(
            event_ids,
            friends,
            PermissionLevel.EDITOR,
            actor=self.owner,
        )
        assert num_shared == 1
        permissions = get_permission(self.event, self.friend)
        assert permissions == PermissionLevel.EDITOR

        # Test _share_gifts method
        gift_ids = [self.gift.gift_id]
        num_shared = view._share_gifts(
            gift_ids,
            friends,
            PermissionLevel.EDITOR,
            actor=self.owner,
        )
        assert num_shared == 1
        permissions = get_permission(self.gift, self.friend)
        assert permissions == PermissionLevel.EDITOR

    def test_get_selected_friends_and_selection(self):
        """Test methods for extracting friends and object selection from request."""
        # Create mock request with POST data
        mock_request = Mock()
        mock_request.user = self.owner
        mock_request.POST = QueryDict("", mutable=True)
        mock_request.POST.setlist("friends", [str(self.friend.id)])
        mock_request.POST.setlist("persons", [str(self.person.person_id)])
        mock_request.POST.setlist("person_groups", [str(self.group.group_id)])
        mock_request.POST.setlist("gifts", [str(self.gift.gift_id)])
        mock_request.POST.setlist("events", [str(self.event.event_id)])
        mock_request.POST.setlist("relations", [str(self.relation_person.relation_id)])

        # Test _get_selected_friends
        view = ShareObjectsView()
        friends = view._get_selected_friends(mock_request)
        assert friends == [self.friend]

        # Test _get_selection_from_request
        view = ShareObjectsView()
        selection = view._get_selection_from_request(mock_request)
        assert selection["person_ids"] == mock_request.POST.getlist("persons")
        assert selection["person_group_ids"] == mock_request.POST.getlist("person_groups")
        assert selection["gift_ids"] == mock_request.POST.getlist("gifts")
        assert selection["event_ids"] == mock_request.POST.getlist("events")
        assert selection["relation_ids"] == mock_request.POST.getlist("relations")
