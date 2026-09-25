"""Tests closing the email encryption gap for User.email and EmailAddress.email.

Covers:
- gift_manager.deterministic_encryption (the AES-SIV primitive).
- Transparent encryption of allauth's EmailAddress.email
  (gift_manager.allauth_email_encryption): stored ciphertext, decrypted reads,
  plaintext lookups, and allauth's own manager methods.
- The User.email pre_save signal covering write paths that bypass the allauth
  signup adapter (admin edits, createsuperuser-style direct creation).
- The backfill migration (0028) that encrypts pre-existing plaintext rows.
"""

from importlib import import_module
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.db import connection

from gift_manager.deterministic_encryption import decrypt_email_deterministic
from gift_manager.deterministic_encryption import encrypt_email_deterministic
from gift_manager.deterministic_encryption import generate_key
from gift_manager.deterministic_encryption import is_deterministically_encrypted
from gift_manager.email_encoding import decrypt_email
from gift_manager.email_encoding import is_encrypted_email
from gift_manager.tests.factories import UserFactory


class TestDeterministicEncryptionFunctions:
    """Tests for the AES-SIV deterministic encryption primitive."""

    def test_encrypt_decrypt_round_trip(self):
        email = "test@example.com"
        encrypted = encrypt_email_deterministic(email)
        assert encrypted != email
        assert decrypt_email_deterministic(encrypted) == email

    def test_encryption_is_deterministic(self):
        """Unlike Fernet, encrypting the same email twice must be identical."""
        email = "test@example.com"
        assert encrypt_email_deterministic(email) == encrypt_email_deterministic(email)

    def test_normalizes_case_and_whitespace(self):
        assert encrypt_email_deterministic("  Test@Example.com  ") == encrypt_email_deterministic(
            "test@example.com"
        )

    def test_different_emails_produce_different_ciphertext(self):
        assert encrypt_email_deterministic("a@example.com") != encrypt_email_deterministic(
            "b@example.com"
        )

    def test_encrypt_none_and_empty(self):
        assert encrypt_email_deterministic(None) is None
        assert encrypt_email_deterministic("") == ""

    def test_decrypt_none_and_empty(self):
        assert decrypt_email_deterministic(None) is None
        assert decrypt_email_deterministic("") == ""

    def test_decrypt_plaintext_passthrough(self):
        assert decrypt_email_deterministic("not-encrypted@example.com") == (
            "not-encrypted@example.com"
        )

    def test_is_deterministically_encrypted(self):
        encrypted = encrypt_email_deterministic("test@example.com")
        assert is_deterministically_encrypted(encrypted) is True
        assert is_deterministically_encrypted("plain@example.com") is False
        assert is_deterministically_encrypted(None) is False

    def test_generate_key_produces_valid_key(self):
        key = generate_key()
        assert isinstance(key, str)
        assert len(key) > 0


@pytest.mark.django_db
class TestEmailAddressEncryptionAtRest:
    """Tests that EmailAddress.email is encrypted in the database."""

    def test_stored_ciphertext_in_database(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com")

        with connection.cursor() as cursor:
            cursor.execute("SELECT email FROM account_emailaddress WHERE user_id = %s", [user.pk])
            (raw_value,) = cursor.fetchone()

        assert raw_value != "alice@example.com"
        assert is_deterministically_encrypted(raw_value)
        assert decrypt_email_deterministic(raw_value) == "alice@example.com"

    def test_email_attribute_is_plaintext_after_create(self):
        user = UserFactory()
        email_address = EmailAddress.objects.create(user=user, email="alice@example.com")
        # Regression guard: pre_save must not leave the live instance holding
        # ciphertext after save() returns (allauth sends confirmation mail
        # right after creating the instance).
        assert email_address.email == "alice@example.com"

    def test_email_attribute_is_plaintext_after_fetch(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com")

        fetched = EmailAddress.objects.get(user=user)
        assert fetched.email == "alice@example.com"

    def test_save_again_keeps_email_plaintext_on_instance(self):
        user = UserFactory()
        email_address = EmailAddress.objects.create(user=user, email="alice@example.com")

        email_address.verified = True
        email_address.save(update_fields=["verified"])

        assert email_address.email == "alice@example.com"
        refetched = EmailAddress.objects.get(pk=email_address.pk)
        assert refetched.email == "alice@example.com"
        assert refetched.verified is True


@pytest.mark.django_db
class TestEmailAddressLookupsByPlaintext:
    """Tests that exact-match lookups against the encrypted column work."""

    def test_get_by_plaintext_email(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com")

        found = EmailAddress.objects.get(email="alice@example.com")
        assert found.user_id == user.pk

    def test_filter_by_plaintext_email(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com")

        results = list(EmailAddress.objects.filter(email="alice@example.com"))
        assert len(results) == 1
        assert results[0].email == "alice@example.com"

    def test_filter_email_in(self):
        user1 = UserFactory()
        user2 = UserFactory()
        EmailAddress.objects.create(user=user1, email="alice@example.com")
        EmailAddress.objects.create(user=user2, email="bob@example.com")

        results = EmailAddress.objects.filter(email__in=["alice@example.com", "bob@example.com"])
        assert {ea.email for ea in results} == {"alice@example.com", "bob@example.com"}

    def test_get_or_create_matches_existing_row_by_plaintext(self):
        user = UserFactory()
        first, created_first = EmailAddress.objects.get_or_create(
            user=user, email="alice@example.com", defaults={"verified": True}
        )
        assert created_first is True

        second, created_second = EmailAddress.objects.get_or_create(
            user=user, email="alice@example.com", defaults={"verified": True}
        )
        assert created_second is False
        assert second.pk == first.pk

    def test_get_or_create_creates_with_plaintext_email_on_instance(self):
        user = UserFactory()
        email_address, created = EmailAddress.objects.get_or_create(
            user=user, email="alice@example.com", defaults={"verified": True}
        )
        assert created is True
        assert email_address.email == "alice@example.com"


@pytest.mark.django_db
class TestAllauthManagerMethodsAgainstEncryptedStorage:
    """Regression tests: allauth's own EmailAddressManager helpers still work."""

    def test_get_for_user(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com", verified=True)

        found = EmailAddress.objects.get_for_user(user, "alice@example.com")
        assert found.email == "alice@example.com"

    def test_is_verified(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com", verified=True)

        assert EmailAddress.objects.is_verified("alice@example.com") is True
        assert EmailAddress.objects.is_verified("unknown@example.com") is False

    def test_get_users_for(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com", verified=True)

        users = EmailAddress.objects.get_users_for("alice@example.com")
        assert users == [user]

    def test_get_primary_email(self):
        user = UserFactory()
        EmailAddress.objects.create(
            user=user, email="alice@example.com", primary=True, verified=True
        )

        assert EmailAddress.objects.get_primary_email(user) == "alice@example.com"

    def test_add_email(self, rf):
        user = UserFactory()
        request = rf.get("/")
        email_address = EmailAddress.objects.add_email(
            request, user, "new@example.com", confirm=False
        )
        assert email_address.email == "new@example.com"
        assert EmailAddress.objects.filter(user=user, email="new@example.com").exists()


@pytest.mark.django_db
class TestUserEmailPreSaveEnforcement:
    """Tests that User.email is encrypted on every write path, not just signup."""

    def test_create_user_directly_gets_encrypted(self):
        """Simulates admin/createsuperuser-style direct creation (no adapter)."""
        user = User.objects.create_user(
            username="direct", email="direct@example.com", password="pw"
        )
        assert user.email != "direct@example.com"
        assert is_encrypted_email(user.email)
        assert decrypt_email(user.email) == "direct@example.com"

    def test_admin_style_edit_gets_encrypted(self):
        """Simulates a Django admin edit setting a fresh plaintext email."""
        user = UserFactory()
        user.email = "changed@example.com"
        user.save(update_fields=["email"])

        user.refresh_from_db()
        assert is_encrypted_email(user.email)
        assert decrypt_email(user.email) == "changed@example.com"

    def test_already_encrypted_email_is_not_double_encrypted(self):
        user = UserFactory()
        original_email = user.email
        user.first_name = "Changed"
        user.save(update_fields=["first_name", "email"])

        assert user.email == original_email


@pytest.mark.django_db
class TestBackfillMigration:
    """Regression tests for the 0028 plaintext backfill migration."""

    @staticmethod
    def _migration():
        return import_module("gift_manager.migrations.0028_encrypt_email_address_and_backfill")

    @staticmethod
    def _fake_schema_editor():
        """Minimal stand-in exposing `.connection`, as real migrations receive."""
        return SimpleNamespace(connection=connection)

    def test_encrypts_plaintext_user_email(self):
        user = User.objects.create(username="legacy_user")
        User.objects.filter(pk=user.pk).update(email="legacy@example.com")

        self._migration().encrypt_plaintext_emails(None, self._fake_schema_editor())

        user.refresh_from_db()
        assert is_encrypted_email(user.email)
        assert decrypt_email(user.email) == "legacy@example.com"

    def test_encrypts_plaintext_email_address(self):
        user = UserFactory()
        email_address = EmailAddress.objects.create(user=user, email="alice@example.com")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE account_emailaddress SET email = %s WHERE id = %s",
                ["legacy@example.com", email_address.pk],
            )

        self._migration().encrypt_plaintext_emails(None, self._fake_schema_editor())

        email_address.refresh_from_db()
        assert email_address.email == "legacy@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT email FROM account_emailaddress WHERE id = %s", [email_address.pk]
            )
            (raw_value,) = cursor.fetchone()
        assert is_deterministically_encrypted(raw_value)

    def test_backfill_is_idempotent(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email="alice@example.com")

        migration = self._migration()
        schema_editor = self._fake_schema_editor()
        migration.encrypt_plaintext_emails(None, schema_editor)
        migration.encrypt_plaintext_emails(None, schema_editor)

        email_address = EmailAddress.objects.get(user=user)
        assert email_address.email == "alice@example.com"

    def test_reverse_decrypts_both_fields(self):
        user = UserFactory()
        decrypted_factory_email = decrypt_email(user.email)
        email_address = EmailAddress.objects.create(user=user, email="alice@example.com")

        migration = self._migration()
        migration.decrypt_encrypted_emails(None, self._fake_schema_editor())

        with connection.cursor() as cursor:
            cursor.execute("SELECT email FROM auth_user WHERE id = %s", [user.pk])
            (raw_user_email,) = cursor.fetchone()
            cursor.execute(
                "SELECT email FROM account_emailaddress WHERE id = %s", [email_address.pk]
            )
            (raw_email_address,) = cursor.fetchone()

        assert raw_user_email == decrypted_factory_email
        assert raw_email_address == "alice@example.com"
