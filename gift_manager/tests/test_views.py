import json
import uuid
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.http.request import QueryDict
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import Gift
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.views import FilterByUserMixin
from gift_manager.views import GetObjectByTokenMixin
from gift_manager.views import ProfileDetailView
from gift_manager.views import ShareObjectsView
from gift_manager.views import get_user
from gift_manager.views import home


@pytest.mark.django_db
class TestGetUser:
    """Tests for get_user."""

    def test_user_not_found(self):
        """Test that get_user raises `User.DoesNotExist` when user is not found."""
        # Act / Assert
        with pytest.raises(User.DoesNotExist):
            get_user("123")

    def test_user_found(self, user, username):
        """Test that get_user returns the proper User object."""
        # Act / Assert
        retrieved_user = get_user(user.id)
        assert retrieved_user == (user, username)

    def test_user_found_return_id(self, user, username):
        """Test that get_user returns the proper User object and its ID."""
        # Act / Assert
        retrieved_user = get_user(user.id, return_id=True)
        assert retrieved_user == (user, username, user.id)


@patch("gift_manager.views.render")
def test_home_view(mock_render):
    """Test that home view renders correct template."""
    # Arrange
    mock_request = Mock()

    # Act
    result = home(mock_request)

    # Assert
    mock_render.assert_called_once_with(mock_request, "gift_manager/home.html")
    assert result == mock_render.return_value


@pytest.mark.django_db
class TestProfileDetailView:
    """Tests for ProfileDetailView."""

    def test_get_object(self, user):
        """Test that get_object returns the profile of the current user."""
        # Arrange
        view = ProfileDetailView()
        view.request = Mock()
        view.request.user = user

        # Act
        profile = view.get_object()

        # Assert
        assert profile == user.profile

    @override_settings(USE_I18N=False)
    def test_profile_detail_view(self, user):
        """Test la vue complète ProfileDetailView."""
        # Arrange
        client = Client()
        client.force_login(user)
        url = reverse("gift_manager:profile_detail")

        # Act
        response = client.get(url)

        # Assert
        assert response.status_code == 200
        assert "gift_manager/profile_detail.html" in [t.name for t in response.templates]
        assert response.context["profile"] == user.profile


@pytest.mark.django_db
class TestSendInvitationView:
    """Tests for SendInvitationView."""

    @pytest.fixture(autouse=True)
    def setup_user(self, user):
        """Create a test user and authenticate the client."""
        self.user = user
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(USE_I18N=False)
    def test_get(self):
        """Test that GET request renders send_invitation.html template."""
        # Arrange
        url = reverse("gift_manager:send_invitation")

        # Act
        response = self.client.get(url)

        # Assert
        assert response.status_code == 200
        assert "gift_manager/send_invitation.html" in [t.name for t in response.templates]

    @override_settings(USE_I18N=False)
    @patch("gift_manager.views.send_mail")
    def test_post(self, mock_send_mail):
        """Test that POST request creates invitation, sends email and redirects."""
        # Arrange
        url = reverse("gift_manager:send_invitation")
        data = {"recipient_email": "recipient@example.com"}

        # Act
        response = self.client.post(url, data)

        # Assert
        # Check redirection
        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url

        # Verify invitation was created
        invitation = Invitation.objects.get(recipient_email="recipient@example.com")
        assert invitation.sender == self.user
        assert invitation.token is not None

        # Verify email was sent
        mock_send_mail.assert_called_once()
        assert mock_send_mail.called

        # Check email parameters in the call
        call_args = mock_send_mail.call_args_list[0].kwargs
        assert call_args["subject"] == "Join my friends on Gift Manager"
        assert call_args["message"].startswith(
            "To accept the invitation, click on the following link: "
        )
        assert "recipient@example.com" in call_args["recipient_list"]


@pytest.mark.django_db
class TestAcceptInvitationView:
    """Tests for AcceptInvitationView with a real database."""

    @pytest.fixture(autouse=True)
    def setup_invitation(self):
        """Prepares the test environment with users and invitation."""
        # Create a sender user
        self.sender = User.objects.create_user(
            username="sender_user", email="sender@example.com", password="testpass123"
        )
        # Create a recipient user
        self.recipient = User.objects.create_user(
            username="recipient_user", email="recipient@example.com", password="testpass123"
        )
        # Create an invitation with a valid UUID token
        self.token = str(uuid.uuid4())
        self.invitation = Invitation.objects.create(
            sender=self.sender,
            recipient_email="recipient@example.com",
            token=self.token,
            accepted=False,
        )
        self.client = Client()

    @override_settings(USE_I18N=False)
    def test_accept_invitation_authenticated(self):
        """Test accepting an invitation by an authenticated user."""
        # Authenticate the user
        self.client.login(username="recipient_user", password="testpass123")

        # URL to accept the invitation
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        # Perform the GET request
        response = self.client.get(url)

        # Verify that the redirection works
        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url

        # Verify that the invitation has been marked as accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is True
        assert self.invitation.accepted_at is not None

        # Verify that the profiles are linked as friends
        recipient_profile = Profile.objects.get(user=self.recipient)
        sender_profile = Profile.objects.get(user=self.sender)
        assert sender_profile in recipient_profile.friends.all()
        assert recipient_profile in sender_profile.friends.all()

    @override_settings(USE_I18N=False)
    def test_accept_invitation_unauthenticated(self):
        """Test accepting an invitation by an unauthenticated user."""
        # URL to accept the invitation without being logged in
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        # Perform the GET request
        response = self.client.get(url)

        # Verify that the user is redirected to the signup page
        assert response.status_code == 302
        assert "accounts/signup" in response.url
        assert f"invitation_token={self.token}" in response.url

        # Verify that the invitation has not been accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None


@pytest.mark.django_db
class TestRemoveFriendView:
    """Tests for RemoveFriendView."""

    @pytest.fixture
    def setup_users(self, user, userpassword, user_email):
        """Creates two user friends to test friend removal."""
        # Create two users
        self.user1 = user
        self.user2 = User.objects.create_user(
            username="user2", email=user_email, password=userpassword
        )

        # Create associated profiles
        self.profile1 = self.user1.profile
        self.profile2 = self.user2.profile

        # Add user2 as a friend of user1
        self.profile1.friends.add(self.profile2)
        self.profile2.friends.add(self.profile1)

        self.client = Client()

    @override_settings(USE_I18N=False)
    def test_post_remove_friend(self, setup_users):  # noqa: ARG002
        """Test that post method correctly removes a friend."""
        # Authenticate the user
        self.client.force_login(self.user1)

        # URL to remove a friend
        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})

        # Perform the POST request
        response = self.client.post(url)

        # Verify that redirection works
        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url

        # Verify that the friend has been removed from both sides
        self.profile1.refresh_from_db()
        self.profile2.refresh_from_db()

        assert self.profile2 not in self.profile1.friends.all()
        assert self.profile1 not in self.profile2.friends.all()

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_unauthenticated(self, setup_users):  # noqa: ARG002
        """Test that friend removal fails for an unauthenticated user."""
        # URL to remove a friend without being logged in
        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})

        # Perform the POST request
        response = self.client.post(url)

        # Verify that the user is redirected to the login page
        assert response.status_code == 302
        assert "login" in response.url

        # Verify that the friend has not been removed
        self.profile1.refresh_from_db()
        self.profile2.refresh_from_db()

        assert self.profile2 in self.profile1.friends.all()
        assert self.profile1 in self.profile2.friends.all()


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
        mixin.model.objects.filter.return_value = mock_queryset

        # Act
        result = mixin.get_queryset()

        # Assert
        mixin.model.objects.filter.assert_called_once()
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

        with patch("gift_manager.views.get_object_or_404", return_value="found_object") as mock_get:
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

        # Check permissions were created
        # Verify permissions for relation and associated objects
        for obj in [
            self.relation_person,
            self.relation_group,
            self.gift,
            self.person,
            self.group,
            self.event,
        ]:
            obj_type = obj.__class__.__name__.lower()
            perm = obj_type + "_permissions"

            # Get permissions objects - implementation depends on your permissions model
            # This is a simplified check - you'll need to adapt to your actual permissions model
            if hasattr(obj, perm):
                permissions = getattr(obj, perm).filter(user=self.friend)
                assert permissions.exists()
                assert permissions.first().permission_level == PermissionLevel.VIEWER

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
        num_shared = view._share_persons(person_ids, friends, PermissionLevel.EDITOR)
        assert num_shared == 1
        permissions = get_permission(self.person, self.friend)
        assert permissions == PermissionLevel.EDITOR

        # Test _share_events method
        event_ids = [self.event.event_id]
        num_shared = view._share_events(event_ids, friends, PermissionLevel.EDITOR)
        assert num_shared == 1
        permissions = get_permission(self.event, self.friend)
        assert permissions == PermissionLevel.EDITOR

        # Test _share_gifts method
        gift_ids = [self.gift.gift_id]
        num_shared = view._share_gifts(gift_ids, friends, PermissionLevel.EDITOR)
        assert num_shared == 1
        permissions = get_permission(self.gift, self.friend)
        assert permissions == PermissionLevel.EDITOR

    def test_get_selected_friends_and_selection(self):
        """Test methods for extracting friends and object selection from request."""
        # Create mock request with POST data
        mock_request = Mock()
        mock_request.POST = QueryDict("", mutable=True)
        mock_request.POST.update(
            {
                "friends": [str(self.friend.id)],
                "persons": [str(self.person.person_id)],
                "person_groups": [str(self.group.group_id)],
                "gifts": [str(self.gift.gift_id)],
                "events": [str(self.event.event_id)],
                "relations": [str(self.relation_person.relation_id)],
            }
        )

        # Setup mock User.objects.filter to return our friend user
        with patch("gift_manager.views.User.objects.filter") as mock_filter:
            mock_filter.return_value = [self.friend]

            # Test _get_selected_friends
            view = ShareObjectsView()
            friends = view._get_selected_friends(mock_request)
            assert friends == [self.friend]
            mock_filter.assert_called_once_with(id__in=mock_request.POST.getlist("friends"))

        # Test _get_selection_from_request
        view = ShareObjectsView()
        selection = view._get_selection_from_request(mock_request)
        assert selection["person_ids"] == mock_request.POST.getlist("persons")
        assert selection["person_group_ids"] == mock_request.POST.getlist("person_groups")
        assert selection["gift_ids"] == mock_request.POST.getlist("gifts")
        assert selection["event_ids"] == mock_request.POST.getlist("events")
        assert selection["relation_ids"] == mock_request.POST.getlist("relations")


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
        # Create a friend user
        friend = User.objects.create_user(
            username="testfriend", email="friend@example.com", password="password123"
        )
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

        # Check that gift was created
        gift = Gift.objects.get(name="Test Shared Gift")
        assert gift is not None

        # Check that sharing was created
        permissions = get_permission(gift, friend)
        assert permissions == PermissionLevel.VIEWER


@pytest.mark.django_db
class TestEditPermissionMixin:
    """Tests for EditPermissionMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user, userpassword, person):
        """Setup test fixtures."""
        self.user = user
        self.person = person

        # Create a friend
        self.friend = User.objects.create_user(
            username="testfriend", email="friend@example.com", password=userpassword
        )

        # Add the friend to the user's profile
        self.user.profile.friends.add(self.friend.profile)

        # Create a permission for the person
        create_or_update_permission(self.user, self.person, permission_level=PermissionLevel.OWNER)

        self.client = Client()
        self.client.force_login(user)

    @override_settings(USE_I18N=False)
    def test_update_permission_ajax(self):
        """Test updating a permission via AJAX."""
        # Share the person with the friend first
        create_or_update_permission(
            self.friend, self.person, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})

        # AJAX request data
        data = {
            "update_permission": "1",
            "user_id": self.friend.id,
            "permission": PermissionLevel.EDITOR,
        }

        # Set AJAX header
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

        # Act
        response = self.client.post(url, data, **headers)

        # Assert
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data["success"] is True

        # Check database
        permissions = get_permission(self.person, self.friend)
        assert permissions == PermissionLevel.EDITOR

    @override_settings(USE_I18N=False)
    def test_remove_share_ajax(self):
        """Test removing a share via AJAX."""
        # Share the person with the friend first
        create_or_update_permission(
            self.friend, self.person, permission_level=PermissionLevel.VIEWER
        )

        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})

        # AJAX request data
        data = {
            "remove_share": "1",
            "user_id": self.friend.id,
        }

        # Set AJAX header
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

        # Act
        response = self.client.post(url, data, **headers)

        # Assert
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data["success"] is True

        # Check database
        assert get_permission(self.person, self.friend) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_share_with_ajax(self):
        """Test sharing with a new user via AJAX."""
        url = reverse("gift_manager:person_edit", kwargs={"pk": self.person.person_id})

        # AJAX request data
        data = {
            "share_with": "1",
            "user_id": self.friend.id,
            "permission": PermissionLevel.VIEWER,
        }

        # Set AJAX header
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

        # Act
        response = self.client.post(url, data, **headers)

        # Assert
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data["success"] is True

        # Check database
        permissions = get_permission(self.person, self.friend)
        assert permissions == PermissionLevel.VIEWER


@pytest.mark.django_db
class TestUpdateRelationStatus:
    """Tests for update_relation_status view."""

    @pytest.fixture(autouse=True)
    def setup(self, user, person_relation):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create a test status
        self.new_status = RelationStatus.objects.create(status="Testing")

        # Create a test relation
        self.relation = person_relation
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.OWNER)

    @override_settings(USE_I18N=False)
    def test_update_relation_status_success(self):
        """Test updating a relation status successfully."""
        url = reverse("gift_manager:relation_status_update")
        data = {
            "relation_id": self.relation.relation_id,
            "new_status": self.new_status.pk,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data["success"] is True

        # Check database
        self.relation.refresh_from_db()
        assert self.relation.status == self.new_status

    @override_settings(USE_I18N=False)
    def test_update_relation_status_not_found(self):
        """Test updating a non-existent relation status."""
        url = reverse("gift_manager:relation_status_update")
        fake_uuid = str(uuid.uuid4())
        data = {
            "relation_id": fake_uuid,
            "new_status": self.new_status.pk,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert "error" in response_data


@pytest.mark.django_db
class TestDeleteSharedMixin:
    """Tests for DeleteSharedMixin."""

    @pytest.fixture(autouse=True)
    def setup(self, user, userpassword):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create another user
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password=userpassword
        )

        # Create a test person shared with both users
        self.person = Person.objects.create(
            first_name="Shared",
            family_name="Person",
        )
        create_or_update_permission(user, self.person, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(
            self.other_user, self.person, permission_level=PermissionLevel.VIEWER
        )

        # Create a test person shared only with current user
        self.person_not_shared = Person.objects.create(
            first_name="Not",
            family_name="Shared",
        )
        create_or_update_permission(
            user, self.person_not_shared, permission_level=PermissionLevel.OWNER
        )

    @override_settings(USE_I18N=False)
    def test_delete_shared_object(self):
        """Test deleting an object shared with other users."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Act
        response = self.client.post(url)

        # Assert
        assert response.status_code == 302  # Redirect after action

        # The person should still exist (only sharing is removed)
        self.person.refresh_from_db()

        # Current user should not have access anymore
        assert get_permission(self.person, self.user) == PermissionLevel.NONE

        # Other user should still have access
        assert get_permission(self.person, self.other_user) == PermissionLevel.VIEWER

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
