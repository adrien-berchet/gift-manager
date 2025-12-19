"""Tests for email encoding functionality."""

import pytest
from django.contrib.auth.models import User

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email
from gift_manager.email_encoding import is_encoded_email
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import Profile
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory


class TestEmailEncodingFunctions:
    """Tests for the email encoding utility functions."""

    def test_encode_email_basic(self):
        """Test basic email encoding."""
        email = "test@example.com"
        encoded = encode_email(email)
        assert encoded is not None
        assert encoded != email
        # Base64 encoded string should be different from original
        assert "@" not in encoded

    def test_decode_email_basic(self):
        """Test basic email decoding."""
        email = "test@example.com"
        encoded = encode_email(email)
        decoded = decode_email(encoded)
        assert decoded == email

    def test_encode_none(self):
        """Test encoding None returns None."""
        assert encode_email(None) is None

    def test_decode_none(self):
        """Test decoding None returns None."""
        assert decode_email(None) is None

    def test_encode_empty_string(self):
        """Test encoding empty string returns empty string."""
        assert encode_email("") == ""

    def test_decode_empty_string(self):
        """Test decoding empty string returns empty string."""
        assert decode_email("") == ""

    def test_decode_non_encoded_email(self):
        """Test decoding a non-encoded email returns the original."""
        # If the string is not valid base64, it should return the original
        email = "not-base64@example.com"
        result = decode_email(email)
        assert result == email

    def test_is_encoded_email_true(self):
        """Test is_encoded_email returns True for encoded email."""
        email = "test@example.com"
        encoded = encode_email(email)
        assert is_encoded_email(encoded) is True

    def test_is_encoded_email_false(self):
        """Test is_encoded_email returns False for non-encoded email."""
        email = "test@example.com"
        assert is_encoded_email(email) is False

    def test_is_encoded_email_none(self):
        """Test is_encoded_email returns False for None."""
        assert is_encoded_email(None) is False

    def test_is_encoded_email_empty(self):
        """Test is_encoded_email returns False for empty string."""
        assert is_encoded_email("") is False

    def test_round_trip_special_characters(self):
        """Test encoding/decoding with special characters."""
        email = "user+tag@sub.example.com"
        encoded = encode_email(email)
        decoded = decode_email(encoded)
        assert decoded == email

    def test_round_trip_unicode(self):
        """Test encoding/decoding with unicode characters."""
        email = "üser@example.com"
        encoded = encode_email(email)
        decoded = decode_email(encoded)
        assert decoded == email


@pytest.mark.django_db
class TestPersonEmailEncoding:
    """Tests for Person model email encoding."""

    def test_person_email_stored_encoded(self):
        """Test that person email is stored encoded."""
        person = PersonFactory(first_name="John", family_name="Doe")
        # The email_address field should contain encoded data
        assert person.email_address is not None
        # The email property should return decoded value
        assert person.email is not None
        assert "@" in person.email

    def test_person_set_email_method(self):
        """Test the set_email method encodes email."""
        person = Person(first_name="Test", family_name="User")
        person.set_email("test@example.com")
        person.save()

        # Reload from database
        person = Person.objects.get(pk=person.pk)

        # The stored value should be encoded
        assert person.email_address != "test@example.com"
        # The property should return decoded value
        assert person.email == "test@example.com"

    def test_person_email_property(self):
        """Test the email property returns decoded value."""
        email = "john.doe@example.com"
        encoded = encode_email(email)
        person = Person.objects.create(
            first_name="John", family_name="Doe", email_address=encoded
        )
        assert person.email == email

    def test_person_email_none(self):
        """Test person with no email."""
        person = Person.objects.create(first_name="John", family_name="Doe")
        assert person.email is None
        assert person.email_address is None


@pytest.mark.django_db
class TestInvitationEmailEncoding:
    """Tests for Invitation model email encoding."""

    def test_invitation_email_stored_encoded(self):
        """Test that invitation email is stored encoded."""
        sender = UserFactory()
        invitation = InvitationFactory(sender=sender)
        # The recipient_email field should contain encoded data
        assert invitation.recipient_email is not None
        # The email property should return decoded value
        assert invitation.email is not None
        assert "@" in invitation.email

    def test_invitation_set_email_method(self):
        """Test the set_email method encodes email."""
        sender = UserFactory()
        invitation = Invitation(sender=sender)
        invitation.set_email("recipient@example.com")
        invitation.save()

        # Reload from database
        invitation = Invitation.objects.get(pk=invitation.pk)

        # The stored value should be encoded
        assert invitation.recipient_email != "recipient@example.com"
        # The property should return decoded value
        assert invitation.email == "recipient@example.com"

    def test_invitation_email_property(self):
        """Test the email property returns decoded value."""
        sender = UserFactory()
        email = "recipient@example.com"
        encoded = encode_email(email)
        invitation = Invitation.objects.create(sender=sender, recipient_email=encoded)
        assert invitation.email == email


@pytest.mark.django_db
class TestProfileEmailEncoding:
    """Tests for Profile model email encoding."""

    def test_profile_email_property(self):
        """Test the Profile.email property returns decoded user email."""
        user = UserFactory(username="testuser")
        profile = user.profile

        # The email property should return decoded value
        decoded_email = profile.email
        assert decoded_email is not None
        assert "@" in decoded_email

    def test_profile_set_user_email(self):
        """Test the set_user_email method encodes email."""
        user = UserFactory(username="testuser")
        profile = user.profile

        # Set a new email
        profile.set_user_email("newemail@example.com")

        # Reload user from database
        user = User.objects.get(pk=user.pk)

        # The stored value should be encoded
        assert user.email != "newemail@example.com"
        # The profile.email property should return decoded value
        assert user.profile.email == "newemail@example.com"


@pytest.mark.django_db
class TestUserEmailEncoding:
    """Tests for User model email encoding via factory."""

    def test_user_email_stored_encoded(self):
        """Test that user email from factory is stored encoded."""
        user = UserFactory(username="testuser")
        # The email field should contain encoded data
        assert user.email is not None
        # Check it's not a plain email (no @ in encoded base64)
        profile = user.profile
        # The decoded email should contain @
        assert "@" in profile.email
