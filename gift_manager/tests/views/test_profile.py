import uuid
from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email
from gift_manager.models import Gift
from gift_manager.models import Invitation
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Profile
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.services import PermissionService
from gift_manager.views import ProfileDetailView
from gift_manager.views.profile import INVITATION_TOKEN_SESSION_KEY


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
        cache.delete(f"gift_manager:invitation-send:{self.user.pk}")

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

        # Verify invitation was created (email is stored encrypted)
        invitation = Invitation.objects.get(sender=self.user)
        assert invitation.email == "recipient@example.com"  # Use decoded property
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

    @override_settings(USE_I18N=False)
    @patch("gift_manager.views.profile.send_mail")
    def test_post_normalizes_and_reuses_pending_invitation(self, mock_send_mail):
        """Repeated pending invitations to the same address reuse one token."""
        url = reverse("gift_manager:send_invitation")

        first_response = self.client.post(url, {"recipient_email": "Recipient@Example.COM"})
        second_response = self.client.post(url, {"recipient_email": "recipient@example.com"})

        assert first_response.status_code == 302
        assert second_response.status_code == 302
        invitations = Invitation.objects.filter(sender=self.user)
        assert invitations.count() == 1
        assert invitations.get().email == "recipient@example.com"
        assert mock_send_mail.call_count == 2
        assert (
            mock_send_mail.call_args_list[0].kwargs["message"]
            == mock_send_mail.call_args_list[1].kwargs["message"]
        )

    @override_settings(USE_I18N=False)
    @patch("gift_manager.views.profile.send_mail")
    def test_post_rejects_self_invitation(self, mock_send_mail):
        """Users cannot create invitation tokens for their own account email."""
        self.user.email = encode_email("sender@example.com")
        self.user.save(update_fields=["email"])
        url = reverse("gift_manager:send_invitation")

        response = self.client.post(url, {"recipient_email": "sender@example.com"})

        assert response.status_code == 302
        assert Invitation.objects.filter(sender=self.user).count() == 0
        mock_send_mail.assert_not_called()

    @override_settings(USE_I18N=False)
    @patch("gift_manager.views.profile.send_mail")
    def test_post_rejects_existing_friend_invitation(self, mock_send_mail):
        """Users cannot create invitation tokens for an existing friend."""
        friend = User.objects.create_user(
            username="friend_user",
            email=encode_email("friend@example.com"),
            password="testpass123",
        )
        self.user.profile.friends.add(friend.profile)
        friend.profile.friends.add(self.user.profile)
        url = reverse("gift_manager:send_invitation")

        response = self.client.post(url, {"recipient_email": "friend@example.com"})

        assert response.status_code == 302
        assert Invitation.objects.filter(sender=self.user).count() == 0
        mock_send_mail.assert_not_called()

    @override_settings(USE_I18N=False, INVITATION_SEND_LIMIT=1)
    @patch("gift_manager.views.profile.send_mail")
    def test_post_throttles_repeated_invitation_sends(self, mock_send_mail):
        """The invitation endpoint limits repeated email sends per sender."""
        url = reverse("gift_manager:send_invitation")

        first_response = self.client.post(url, {"recipient_email": "first@example.com"})
        second_response = self.client.post(url, {"recipient_email": "second@example.com"})

        assert first_response.status_code == 302
        assert second_response.status_code == 429
        assert Invitation.objects.filter(sender=self.user).count() == 1
        mock_send_mail.assert_called_once()


@pytest.mark.django_db
class TestAcceptInvitationView:
    """Tests for AcceptInvitationView with a real database."""

    @pytest.fixture(autouse=True)
    def setup_invitation(self):
        """Prepares the test environment with users and invitation."""
        # Create a sender user (email stored encrypted)
        self.sender = User.objects.create_user(
            username="sender_user",
            email=encode_email("sender@example.com"),
            password="testpass123",
        )
        # Create a recipient user (email stored encrypted)
        self.recipient = User.objects.create_user(
            username="recipient_user",
            email=encode_email("recipient@example.com"),
            password="testpass123",
        )
        # Create an invitation with a valid UUID token (email stored encrypted)
        self.token = str(uuid.uuid4())
        self.invitation = Invitation.objects.create(
            sender=self.sender,
            recipient_email=encode_email("recipient@example.com"),
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
    def test_accept_invitation_authenticated_must_match_invited_email(self):
        """A forwarded invitation token cannot be accepted by another account."""
        attacker = User.objects.create_user(
            username="attacker_user",
            email=encode_email("attacker@example.com"),
            password="testpass123",
        )
        self.client.login(username="attacker_user", password="testpass123")
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        response = self.client.get(url)

        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None
        attacker_profile = Profile.objects.get(user=attacker)
        sender_profile = Profile.objects.get(user=self.sender)
        assert sender_profile not in attacker_profile.friends.all()
        assert attacker_profile not in sender_profile.friends.all()

    @override_settings(USE_I18N=False)
    def test_accept_invitation_rejects_unverified_allauth_email(self):
        """An unverified secondary email does not prove control of the invited address."""
        attacker = User.objects.create_user(
            username="attacker_user",
            email=encode_email("attacker@example.com"),
            password="testpass123",
        )
        EmailAddress.objects.create(
            user=attacker,
            email="recipient@example.com",
            primary=False,
            verified=False,
        )
        self.client.login(username="attacker_user", password="testpass123")
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        response = self.client.get(url)

        assert response.status_code == 302
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None
        attacker_profile = Profile.objects.get(user=attacker)
        sender_profile = Profile.objects.get(user=self.sender)
        assert sender_profile not in attacker_profile.friends.all()

    @override_settings(USE_I18N=False)
    def test_accept_invitation_authenticated_matches_allauth_email(self):
        """Invitation acceptance can match an allauth account email for the user."""
        self.recipient.email = encode_email("different@example.com")
        self.recipient.save(update_fields=["email"])
        EmailAddress.objects.create(
            user=self.recipient,
            email="recipient@example.com",
            primary=True,
            verified=True,
        )
        self.client.login(username="recipient_user", password="testpass123")
        url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})

        response = self.client.get(url)

        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is True
        recipient_profile = Profile.objects.get(user=self.recipient)
        sender_profile = Profile.objects.get(user=self.sender)
        assert sender_profile in recipient_profile.friends.all()

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
        assert self.client.session[INVITATION_TOKEN_SESSION_KEY] == self.token

        # Verify that the invitation has not been accepted
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.invitation.accepted_at is None


@pytest.mark.django_db
class TestInvitationBoundSignupView:
    """Tests for accepting invitations through signup and email verification."""

    @pytest.fixture(autouse=True)
    def setup_invitation(self):
        self.sender = User.objects.create_user(
            username="sender_user",
            email=encode_email("sender@example.com"),
            password="testpass123",
        )
        self.token = str(uuid.uuid4())
        self.invitation = Invitation.objects.create(
            sender=self.sender,
            recipient_email=encode_email("recipient@example.com"),
            token=self.token,
            accepted=False,
        )
        self.client = Client()

    @override_settings(USE_I18N=False)
    def test_signup_with_invitation_requires_invited_email(self):
        """A pending invitation cannot be claimed by signing up with another email."""
        accept_url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})
        self.client.get(accept_url)

        response = self.client.post(
            reverse("account_signup"),
            {
                "username": "wrong_recipient",
                "email": "wrong@example.com",
                "email2": "wrong@example.com",
                "password1": "StrongPassword123!",
                "password2": "StrongPassword123!",
            },
        )

        assert response.status_code == 200
        assert b"Use the email address this invitation was sent to." in response.content
        assert User.objects.filter(username="wrong_recipient").exists() is False
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.client.session[INVITATION_TOKEN_SESSION_KEY] == self.token

    @override_settings(USE_I18N=False)
    def test_signup_with_invitation_accepts_after_email_confirmation(self):
        """The invite is accepted only after allauth verifies the matching email."""
        accept_url = reverse("gift_manager:accept_invitation", kwargs={"token": self.token})
        self.client.get(accept_url)

        response = self.client.post(
            reverse("account_signup"),
            {
                "username": "recipient_signup",
                "email": "recipient@example.com",
                "email2": "recipient@example.com",
                "password1": "StrongPassword123!",
                "password2": "StrongPassword123!",
            },
        )

        assert response.status_code == 302
        user = User.objects.get(username="recipient_signup")
        email_address = EmailAddress.objects.get(user=user, email="recipient@example.com")
        assert email_address.verified is False
        assert user.email != "recipient@example.com"
        assert decode_email(user.email) == "recipient@example.com"
        self.invitation.refresh_from_db()
        assert self.invitation.accepted is False
        assert self.client.session[INVITATION_TOKEN_SESSION_KEY] == self.token

        email_address.verified = True
        email_address.save(update_fields=["verified"])
        request = Mock(GET={}, POST={}, session=self.client.session)
        email_confirmed.send(sender=EmailAddress, request=request, email_address=email_address)

        self.invitation.refresh_from_db()
        assert self.invitation.accepted is True
        assert self.invitation.accepted_at is not None
        recipient_profile = Profile.objects.get(user=user)
        sender_profile = Profile.objects.get(user=self.sender)
        assert sender_profile in recipient_profile.friends.all()
        assert recipient_profile in sender_profile.friends.all()
        assert INVITATION_TOKEN_SESSION_KEY not in request.session
        user.refresh_from_db()
        assert user.email != "recipient@example.com"
        assert decode_email(user.email) == "recipient@example.com"


@pytest.mark.django_db
class TestAcceptInvitationViewExpiration:
    """Tests for AcceptInvitationView expiration handling."""

    @pytest.fixture(autouse=True)
    def setup_invitation(self):
        """Prepares the test environment with users and invitation."""
        # Create a sender user (email stored encrypted)
        self.sender = User.objects.create_user(
            username="sender_user",
            email=encode_email("sender@example.com"),
            password="testpass123",
        )
        # Create a recipient user (email stored encrypted)
        self.recipient = User.objects.create_user(
            username="recipient_user",
            email=encode_email("recipient@example.com"),
            password="testpass123",
        )
        # Create an invitation with a valid UUID token (email stored encrypted)
        self.token = str(uuid.uuid4())
        self.invitation = Invitation.objects.create(
            sender=self.sender,
            recipient_email=encode_email("recipient@example.com"),
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

    @override_settings(USE_I18N=False, INVITATION_EXPIRY_DAYS=None)
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
class TestUpdateViewPreferencesView:
    """Tests for UpdateViewPreferencesView."""

    @pytest.fixture(autouse=True)
    def setup_user(self, user):
        """Create a test user and authenticate the client."""
        self.user = user
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(USE_I18N=False)
    def test_update_desktop_to_card(self):
        """Test updating desktop view preference to card."""
        # Arrange
        url = reverse("gift_manager:update_view_preferences")
        data = {"default_view_desktop": "card", "default_view_mobile": "card"}

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302
        assert reverse("gift_manager:profile_detail") in response.url

        # Verify the preference was saved
        self.user.profile.refresh_from_db()
        assert self.user.profile.default_view_desktop == "card"
        assert self.user.profile.default_view_mobile == "card"

    @override_settings(USE_I18N=False)
    def test_update_mobile_to_list(self):
        """Test updating mobile view preference to list."""
        # Arrange
        url = reverse("gift_manager:update_view_preferences")
        data = {"default_view_desktop": "list", "default_view_mobile": "list"}

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302

        # Verify the preference was saved
        self.user.profile.refresh_from_db()
        assert self.user.profile.default_view_desktop == "list"
        assert self.user.profile.default_view_mobile == "list"

    @override_settings(USE_I18N=False)
    def test_invalid_value_ignored(self):
        """Test that invalid view preference values are ignored."""
        # Arrange
        # First set valid values
        self.user.profile.default_view_desktop = "list"
        self.user.profile.default_view_mobile = "card"
        self.user.profile.save()

        url = reverse("gift_manager:update_view_preferences")
        data = {"default_view_desktop": "invalid", "default_view_mobile": "also_invalid"}

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 302

        # Verify the invalid values were ignored (preferences remain unchanged)
        self.user.profile.refresh_from_db()
        assert self.user.profile.default_view_desktop == "list"
        assert self.user.profile.default_view_mobile == "card"

    @override_settings(USE_I18N=False)
    def test_unauthenticated_user_redirected(self):
        """Test that unauthenticated users are redirected to login."""
        # Arrange
        client = Client()  # New client without authentication
        url = reverse("gift_manager:update_view_preferences")
        data = {"default_view_desktop": "card", "default_view_mobile": "list"}

        # Act
        response = client.post(url, data)

        # Assert
        assert response.status_code == 302
        assert "login" in response.url


@pytest.mark.django_db
class TestViewPreferencesInTemplates:
    """Tests for view preferences being passed to templates."""

    @pytest.fixture(autouse=True)
    def setup_user(self, user):
        """Create a test user and authenticate the client."""
        self.user = user
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(USE_I18N=False)
    def test_preferences_in_gift_list_page(self):
        """Test that view preferences are included in the gift list page."""
        # Arrange
        self.user.profile.default_view_desktop = "card"
        self.user.profile.default_view_mobile = "list"
        self.user.profile.save()

        url = reverse("gift_manager:gifts")

        # Act
        response = self.client.get(url)

        # Assert
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "window.userViewPreferences" in content
        assert "desktop: 'card'" in content
        assert "mobile: 'list'" in content

    @override_settings(USE_I18N=False)
    def test_preferences_in_person_list_page(self):
        """Test that view preferences are included in the person list page."""
        # Arrange
        self.user.profile.default_view_desktop = "list"
        self.user.profile.default_view_mobile = "card"
        self.user.profile.save()

        url = reverse("gift_manager:persons")

        # Act
        response = self.client.get(url)

        # Assert
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "window.userViewPreferences" in content
        assert "desktop: 'list'" in content
        assert "mobile: 'card'" in content

    @override_settings(USE_I18N=False)
    def test_preferences_default_values(self):
        """Test that default view preferences are used when not explicitly set."""
        # Arrange - use default profile values (list for desktop, card for mobile)
        url = reverse("gift_manager:gifts")

        # Act
        response = self.client.get(url)

        # Assert
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "window.userViewPreferences" in content
        # Default values from Profile model
        assert "desktop: 'list'" in content
        assert "mobile: 'card'" in content


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
    def test_post_remove_friend(self, setup_users):
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
    def test_post_remove_friend_removes_former_friend_from_requester_owned_objects(
        self, setup_users
    ):
        """Test removing a friend drops their non-owner access to requester-owned objects."""
        self.client.force_login(self.user1)
        gift = Gift.objects.create(name="Requester owned")
        create_or_update_permission(self.user1, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(self.user2, gift, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        assert get_permission(gift, self.user1) == PermissionLevel.OWNER
        assert get_permission(gift, self.user2) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_preserves_former_friend_owner_permission(self, setup_users):
        """Test removing a friend never revokes ownership from the former friend."""
        self.client.force_login(self.user1)
        gift = Gift.objects.create(name="Friend owned")
        create_or_update_permission(self.user2, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(self.user1, gift, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        assert get_permission(gift, self.user2) == PermissionLevel.OWNER
        assert get_permission(gift, self.user1) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_revokes_requester_access_to_friend_linked_person(self, setup_users):
        """Test cleanup handles former friend ownership implied by Person.user_link."""
        self.client.force_login(self.user1)
        person = Person.objects.create(
            first_name="Friend",
            family_name="Linked",
            user_link=self.user2,
        )
        create_or_update_permission(self.user1, person, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        person.refresh_from_db()
        assert person.user_link == self.user2
        assert (
            PermissionService.get_effective_permission(person, self.user2) == PermissionLevel.OWNER
        )
        assert get_permission(person, self.user1) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_revokes_friend_access_to_requester_linked_person(self, setup_users):
        """Test cleanup preserves requester user_link ownership and drops friend access."""
        self.client.force_login(self.user1)
        person = Person.objects.create(
            first_name="Requester",
            family_name="Linked",
            user_link=self.user1,
        )
        create_or_update_permission(self.user2, person, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        person.refresh_from_db()
        assert person.user_link == self.user1
        assert (
            PermissionService.get_effective_permission(person, self.user1) == PermissionLevel.OWNER
        )
        assert get_permission(person, self.user2) == PermissionLevel.NONE

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_preserves_mutual_owner_permissions(self, setup_users):
        """Test cleanup never deletes direct owner rows when both users are owners."""
        self.client.force_login(self.user1)
        gift = Gift.objects.create(name="Co-owned")
        create_or_update_permission(self.user1, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(self.user2, gift, permission_level=PermissionLevel.OWNER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        assert get_permission(gift, self.user1) == PermissionLevel.OWNER
        assert get_permission(gift, self.user2) == PermissionLevel.OWNER

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_preserves_third_party_shared_objects(self, setup_users):
        """Test friend removal does not revoke access on third-party-owned objects."""
        self.client.force_login(self.user1)
        owner = User.objects.create_user(username="owner", email="owner@example.com")
        gift = Gift.objects.create(name="Third party owned")
        create_or_update_permission(owner, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(self.user1, gift, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(self.user2, gift, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": self.profile2.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        assert get_permission(gift, owner) == PermissionLevel.OWNER
        assert get_permission(gift, self.user1) == PermissionLevel.VIEWER
        assert get_permission(gift, self.user2) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_requires_confirmed_friendship_for_permission_cleanup(
        self, setup_users
    ):
        """Test forged non-friend removal does not clean up permissions."""
        self.client.force_login(self.user1)
        non_friend = User.objects.create_user(username="nonfriend", email="nonfriend@example.com")
        gift = Gift.objects.create(name="Forged cleanup")
        create_or_update_permission(self.user1, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(non_friend, gift, permission_level=PermissionLevel.VIEWER)

        url = reverse("gift_manager:remove_friend", kwargs={"friend_id": non_friend.profile.pk})
        response = self.client.post(url)

        assert response.status_code == 302
        assert get_permission(gift, self.user1) == PermissionLevel.OWNER
        assert get_permission(gift, non_friend) == PermissionLevel.VIEWER

    @override_settings(USE_I18N=False)
    def test_post_remove_friend_unauthenticated(self, setup_users):
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
