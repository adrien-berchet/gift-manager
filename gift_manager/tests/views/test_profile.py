import uuid
from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import Invitation
from gift_manager.models import Profile
from gift_manager.views import ProfileDetailView


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
        """Test the complete ProfileDetailView."""
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
    @patch("gift_manager.views.profile.send_mail")
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
class TestAcceptInvitationViewExpiration:
    """Tests for AcceptInvitationView expiration handling."""

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

    @override_settings(USE_I18N=False, INVITATION_EXPIRY_DAYS=7)
    def test_accept_invitation_expired_authenticated(self):
        """Test accepting an expired invitation by an authenticated user."""
        # Make the invitation expired by modifying its creation date
        self.invitation.created_at = timezone.now() - timedelta(days=8)
        self.invitation.save()

        # Authenticate the user
        self.client.login(username="recipient_user", password="testpass123")

        # URL to accept the invitation
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        # Perform the GET request
        response = self.client.get(url)

        # Verify that the user is redirected to the invitation expired page
        assert response.status_code == 302
        assert reverse("gift_manager:invitation_expired") in response.url

        # Verify that the invitation has not been accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None

    @override_settings(USE_I18N=False, INVITATION_EXPIRY_DAYS=7)
    def test_accept_invitation_expired_unauthenticated(self):
        """Test accepting an expired invitation by an unauthenticated user."""
        # Make the invitation expired by modifying its creation date
        self.invitation.created_at = timezone.now() - timedelta(days=8)
        self.invitation.save()

        # URL to accept the invitation without being logged in
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        # Perform the GET request
        response = self.client.get(url)

        # Verify that the user is redirected to the invitation expired page
        assert response.status_code == 302
        assert reverse("gift_manager:invitation_expired") in response.url

        # Verify that the invitation has not been accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None

    @override_settings(USE_I18N=False)
    def test_accept_invitation_no_expiry_setting(self):
        """Test accepting an invitation when no expiry setting is configured."""
        # Make the invitation old but should not expire if no setting
        self.invitation.created_at = timezone.now() - timedelta(days=365)
        self.invitation.save()

        # Authenticate the user
        self.client.login(username="recipient_user", password="testpass123")

        # URL to accept the invitation
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        # Perform the GET request
        response = self.client.get(url)

        # Verify that the invitation is accepted (no expiration without setting)
        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url

        # Verify that the invitation has been accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is True
        assert self.invitation.accepted_at is not None


@pytest.mark.django_db
class TestInvitationExpiredView:
    """Tests for InvitationExpiredView."""

    @override_settings(USE_I18N=False)
    def test_get_invitation_expired_page(self):
        """Test that GET request renders the invitation expired template."""
        # Arrange
        url = reverse("gift_manager:invitation_expired")
        client = Client()

        # Act
        response = client.get(url)

        # Assert
        assert response.status_code == 200
        assert "gift_manager/invitation_expired.html" in [t.name for t in response.templates]


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
