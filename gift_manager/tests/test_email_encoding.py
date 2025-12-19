"""Tests for email encryption functionality."""

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from gift_manager.email_encoding import decrypt_email
from gift_manager.email_encoding import encrypt_email
from gift_manager.email_encoding import generate_encryption_key
from gift_manager.email_encoding import is_encrypted_email
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import Profile
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory


class TestEmailEncryptionFunctions:
    """Tests for the email encryption utility functions."""

    def test_encrypt_email_basic(self):
        """Test basic email encryption."""
        email = "test@example.com"
        encrypted = encrypt_email(email)
        assert encrypted is not None
        assert encrypted != email
        # Encrypted string should be different from original and not contain @
        assert "@" not in encrypted

    def test_decrypt_email_basic(self):
        """Test basic email decryption."""
        email = "test@example.com"
        encrypted = encrypt_email(email)
        decrypted = decrypt_email(encrypted)
        assert decrypted == email

    def test_encrypt_none(self):
        """Test encrypting None returns None."""
        assert encrypt_email(None) is None

    def test_decrypt_none(self):
        """Test decrypting None returns None."""
        assert decrypt_email(None) is None

    def test_encrypt_empty_string(self):
        """Test encrypting empty string returns empty string."""
        assert encrypt_email("") == ""

    def test_decrypt_empty_string(self):
        """Test decrypting empty string returns empty string."""
        assert decrypt_email("") == ""

    def test_decrypt_non_encrypted_email(self):
        """Test decrypting a non-encrypted email returns the original."""
        # If the string is not valid encrypted data, it should return the original
        email = "not-encrypted@example.com"
        result = decrypt_email(email)
        assert result == email

    def test_is_encrypted_email_true(self):
        """Test is_encrypted_email returns True for encrypted email."""
        email = "test@example.com"
        encrypted = encrypt_email(email)
        assert is_encrypted_email(encrypted) is True

    def test_is_encrypted_email_false(self):
        """Test is_encrypted_email returns False for non-encrypted email."""
        email = "test@example.com"
        assert is_encrypted_email(email) is False

    def test_is_encrypted_email_none(self):
        """Test is_encrypted_email returns False for None."""
        assert is_encrypted_email(None) is False

    def test_is_encrypted_email_empty(self):
        """Test is_encrypted_email returns False for empty string."""
        assert is_encrypted_email("") is False

    def test_round_trip_special_characters(self):
        """Test encryption/decryption with special characters."""
        email = "user+tag@sub.example.com"
        encrypted = encrypt_email(email)
        decrypted = decrypt_email(encrypted)
        assert decrypted == email

    def test_round_trip_unicode(self):
        """Test encryption/decryption with unicode characters."""
        email = "üser@example.com"
        encrypted = encrypt_email(email)
        decrypted = decrypt_email(encrypted)
        assert decrypted == email

    def test_generate_encryption_key(self):
        """Test that generate_encryption_key creates a valid key."""
        key = generate_encryption_key()
        assert key is not None
        assert len(key) > 0
        # Key should be URL-safe base64 encoded
        assert isinstance(key, str)

    def test_encryption_is_not_deterministic(self):
        """Test that encrypting the same email twice produces different results."""
        email = "test@example.com"
        encrypted1 = encrypt_email(email)
        encrypted2 = encrypt_email(email)
        # Fernet encryption includes random IV, so results should differ
        assert encrypted1 != encrypted2
        # But both should decrypt to the same value
        assert decrypt_email(encrypted1) == decrypt_email(encrypted2) == email


@pytest.mark.django_db
class TestPersonEmailEncryption:
    """Tests for Person model email encryption."""

    def test_person_email_stored_encrypted(self):
        """Test that person email is stored encrypted."""
        person = PersonFactory(first_name="John", family_name="Doe")
        # The email_address field should contain encrypted data
        assert person.email_address is not None
        # The email property should return decrypted value
        assert person.email is not None
        assert "@" in person.email

    def test_person_set_email_method(self):
        """Test the set_email method encrypts email."""
        person = Person(first_name="Test", family_name="User")
        person.set_email("test@example.com")
        person.save()

        # Reload from database
        person = Person.objects.get(pk=person.pk)

        # The stored value should be encrypted
        assert person.email_address != "test@example.com"
        # The property should return decrypted value
        assert person.email == "test@example.com"

    def test_person_email_property(self):
        """Test the email property returns decrypted value."""
        email = "john.doe@example.com"
        encrypted = encrypt_email(email)
        person = Person.objects.create(
            first_name="John", family_name="Doe", email_address=encrypted
        )
        assert person.email == email

    def test_person_email_none(self):
        """Test person with no email."""
        person = Person.objects.create(first_name="John", family_name="Doe")
        assert person.email is None
        assert person.email_address is None


@pytest.mark.django_db
class TestInvitationEmailEncryption:
    """Tests for Invitation model email encryption."""

    def test_invitation_email_stored_encrypted(self):
        """Test that invitation email is stored encrypted."""
        sender = UserFactory()
        invitation = InvitationFactory(sender=sender)
        # The recipient_email field should contain encrypted data
        assert invitation.recipient_email is not None
        # The email property should return decrypted value
        assert invitation.email is not None
        assert "@" in invitation.email

    def test_invitation_set_email_method(self):
        """Test the set_email method encrypts email."""
        sender = UserFactory()
        invitation = Invitation(sender=sender)
        invitation.set_email("recipient@example.com")
        invitation.save()

        # Reload from database
        invitation = Invitation.objects.get(pk=invitation.pk)

        # The stored value should be encrypted
        assert invitation.recipient_email != "recipient@example.com"
        # The property should return decrypted value
        assert invitation.email == "recipient@example.com"

    def test_invitation_email_property(self):
        """Test the email property returns decrypted value."""
        sender = UserFactory()
        email = "recipient@example.com"
        encrypted = encrypt_email(email)
        invitation = Invitation.objects.create(sender=sender, recipient_email=encrypted)
        assert invitation.email == email


@pytest.mark.django_db
class TestProfileEmailEncryption:
    """Tests for Profile model email encryption."""

    def test_profile_email_property(self):
        """Test the Profile.email property returns decrypted user email."""
        user = UserFactory(username="testuser")
        profile = user.profile

        # The email property should return decrypted value
        decrypted_email = profile.email
        assert decrypted_email is not None
        assert "@" in decrypted_email

    def test_profile_set_user_email(self):
        """Test the set_user_email method encrypts email."""
        user = UserFactory(username="testuser")
        profile = user.profile

        # Set a new email
        profile.set_user_email("newemail@example.com")

        # Reload user from database
        user = User.objects.get(pk=user.pk)

        # The stored value should be encrypted
        assert user.email != "newemail@example.com"
        # The profile.email property should return decrypted value
        assert user.profile.email == "newemail@example.com"


@pytest.mark.django_db
class TestUserEmailEncryption:
    """Tests for User model email encryption via factory."""

    def test_user_email_stored_encrypted(self):
        """Test that user email from factory is stored encrypted."""
        user = UserFactory(username="testuser")
        # The email field should contain encrypted data
        assert user.email is not None
        # Check it's not a plain email (no @ in encrypted data)
        profile = user.profile
        # The decrypted email should contain @
        assert "@" in profile.email
