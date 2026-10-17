# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from gift_manager.email_encoding import encode_email
from gift_manager.models import Invitation
from gift_manager.models import Profile
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestProfile:
    """Tests for the Profile model."""

    @pytest.fixture
    def friend(self):
        """Create a second test user using factory."""
        return UserFactory(username="testfriend")

    def test_save_user_profile_with_existing_profile(self, user):
        """Test saving a user that already has a profile."""
        # Get the initial profile
        initial_profile = user.profile

        # Modify the user and save it
        user.username = "modified_username"
        user.save()

        # Check that the same profile instance was saved, not a new one created
        assert user.profile == initial_profile
        assert Profile.objects.filter(user=user).count() == 1

    def test_save_user_profile_without_existing_profile(self, user):
        """Test saving a user that doesn't have a profile."""
        # Delete the profile manually to simulate a user without profile
        Profile.objects.filter(user=user).delete()

        # Reload user from database to clear the profile attribute
        user = User.objects.get(pk=user.pk)

        # Verify the profile is gone
        assert not hasattr(user, "profile")
        assert Profile.objects.filter(user=user).count() == 0

        # Save the user to trigger the signal
        user.username = "another_username"
        user.save()

        # Verify a new profile was created
        assert hasattr(user, "profile")
        assert Profile.objects.filter(user=user).count() == 1
        assert user.profile is not None
        assert isinstance(user.profile, Profile)

    def test_profile_creation(self, user):
        """Test that a profile is automatically created when a user is created."""
        assert hasattr(user, "profile")
        assert user.profile is not None
        assert isinstance(user.profile, Profile)

    def test_profile_string_representation(self, user):
        """Test the string representation of a profile."""
        assert "Profile of" in str(user.profile)
        assert user.username in str(user.profile)

    def test_profile_friends(self, user, friend):
        """Test adding friends to a profile."""
        user.profile.friends.add(friend.profile)
        assert friend.profile in user.profile.friends.all()
        # Test symmetry
        assert user.profile in friend.profile.friends.all()


@pytest.mark.django_db
class TestInvitation:
    """Tests for the Invitation model."""

    @pytest.fixture
    def sender(self):
        """Create a test sender user using factory."""
        return UserFactory(username="sender")

    @pytest.fixture
    def invitation(self, sender):
        """Create a test invitation using factory."""
        # Email is stored encoded
        return InvitationFactory(
            sender=sender, recipient_email=encode_email("recipient@example.com")
        )

    @override_settings(INVITATION_EXPIRY_DAYS=7)
    def test_expires_at_uses_configured_expiry(self, invitation):
        """expires_at is created_at plus the configured number of days."""
        assert invitation.expires_at == invitation.created_at + timedelta(days=7)

    @override_settings(INVITATION_EXPIRY_DAYS=None)
    def test_expires_at_is_none_without_expiry_setting(self, invitation):
        """Invitations never expire when no expiry is configured."""
        assert invitation.expires_at is None
        assert not invitation.is_expired()

    @override_settings(INVITATION_EXPIRY_DAYS=7)
    def test_expires_at_is_none_for_unsaved_invitation(self, sender):
        """An unsaved invitation has no created_at, so it has no expiry yet."""
        assert Invitation(sender=sender).expires_at is None

    def test_invitation_creation(self, invitation):
        """Test creating an invitation."""
        assert invitation.token is not None
        assert isinstance(invitation.token, uuid.UUID)
        # recipient_email is stored encoded, use email property for decoded value
        assert invitation.email == "recipient@example.com"
        assert invitation.accepted is False
        assert invitation.accepted_at is None
        assert isinstance(invitation.created_at, datetime)

    def test_invitation_string_representation(self, invitation, sender):
        """Test the string representation of an invitation."""
        assert "Invitation from" in str(invitation)
        assert sender.username in str(invitation)
        # __str__ uses the decoded email property
        assert invitation.email in str(invitation)

    @override_settings(INVITATION_EXPIRY_DAYS=7)
    def test_invitation_is_expired_with_setting(self, invitation):
        """Test is_expired method with expiry setting configured."""
        # Test non-expired invitation
        assert invitation.is_expired() is False

        # Test expired invitation
        invitation.created_at = timezone.now() - timedelta(days=8)
        invitation.save()
        assert invitation.is_expired() is True

        # Test invitation on the edge (exactly 7 days)
        invitation.created_at = timezone.now() - timedelta(days=7)
        invitation.save()
        assert invitation.is_expired() is True

    def test_invitation_is_expired_without_setting(self, invitation):
        """Test is_expired method without expiry setting configured."""
        # Remove the setting if it exists
        if hasattr(settings, "INVITATION_EXPIRY_DAYS"):
            del settings.INVITATION_EXPIRY_DAYS

        # Test old invitation without setting (should not expire)
        invitation.created_at = timezone.now() - timedelta(days=365)
        invitation.save()
        assert invitation.is_expired() is False

    @override_settings(INVITATION_EXPIRY_DAYS=30)
    def test_invitation_is_expired_different_expiry_days(self, invitation):
        """Test is_expired method with different expiry days setting."""
        # Test with 30 days setting
        invitation.created_at = timezone.now() - timedelta(days=29)
        invitation.save()
        assert invitation.is_expired() is False

        invitation.created_at = timezone.now() - timedelta(days=31)
        invitation.save()
        assert invitation.is_expired() is True


@pytest.mark.django_db
class TestEmailProperties:
    """Tests for email properties and setters on Profile, Person, and Invitation."""

    def test_profile_email_property(self, user):
        """Test Profile.email property returns decoded email."""
        # Set encoded email
        user.email = encode_email("test@example.com")
        user.save()

        # Profile.email should decode it
        assert user.profile.email == "test@example.com"

    def test_profile_set_user_email(self, user):
        """Test Profile.set_user_email encodes and saves email."""
        user.profile.set_user_email("newemail@example.com")

        # Reload user
        user.refresh_from_db()

        # Check email is encoded in DB but decodes correctly
        assert user.profile.email == "newemail@example.com"

    def test_person_email_property(self):
        """Test Person.email property returns decoded email."""
        person = PersonFactory(
            first_name="Test",
            family_name="User",
            email_address=encode_email("person@example.com"),
        )

        assert person.email == "person@example.com"

    def test_person_set_email(self):
        """Test Person.set_email encodes email address."""
        person = PersonFactory(first_name="Test", family_name="User")
        person.set_email("encoded@example.com")

        # Should be encoded in email_address field but decode via property
        assert person.email == "encoded@example.com"

    def test_invitation_set_email(self, user):
        """Test Invitation.set_email encodes recipient email."""
        invitation = InvitationFactory(sender=user)
        invitation.set_email("invited@example.com")

        # Should be encoded but decode correctly via property
        assert invitation.email == "invited@example.com"
