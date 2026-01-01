"""Tests for authentication and email verification."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestEmailVerification:
    """Test email verification during signup and login."""

    def test_user_cannot_login_before_email_verification(self):
        """Test that users must verify email before logging in when verification is mandatory."""
        client = Client()

        # Create a user programmatically (simulating signup without email verification)
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="TestPassword123!"
        )

        # Create unverified email address
        EmailAddress.objects.create(
            user=user, email="test@example.com", primary=True, verified=False
        )

        # Attempt to login
        login_url = reverse("account_login")
        response = client.post(
            login_url, {"login": "testuser", "password": "TestPassword123!"}, follow=True
        )

        # Should not be logged in successfully
        assert not response.wsgi_request.user.is_authenticated, (
            "User should not be able to login before email verification"
        )

    def test_user_can_login_after_email_verification(self):
        """Test that users can login after verifying their email."""
        client = Client()

        # Create a user with verified email
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="TestPassword123!"
        )

        # Create verified email address
        EmailAddress.objects.create(
            user=user, email="test@example.com", primary=True, verified=True
        )

        # Attempt to login
        login_url = reverse("account_login")
        response = client.post(
            login_url,
            {"login": "testuser", "password": "TestPassword123!"},
            follow=True,
        )

        # Should be logged in successfully
        assert response.wsgi_request.user.is_authenticated, (
            "User should be able to login after email verification"
        )
        assert response.wsgi_request.user.username == "testuser"

    def test_signup_creates_unverified_email_address(self):
        """Test that signup creates an unverified EmailAddress entry."""
        client = Client()

        # Signup with new account
        signup_url = reverse("account_signup")
        client.post(
            signup_url,
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "email2": "newuser@example.com",
                "password1": "StrongPassword123!",
                "password2": "StrongPassword123!",
            },
            follow=True,
        )

        # Check that user was created
        user = User.objects.filter(username="newuser").first()
        assert user is not None, "User should be created after signup"

        # Check that EmailAddress entry exists and is unverified
        email_address = EmailAddress.objects.filter(user=user, email="newuser@example.com").first()
        assert email_address is not None, "EmailAddress entry should be created"
        assert not email_address.verified, "Email should not be verified immediately after signup"

    def test_email_required_setting_enforced(self):
        """Test that ACCOUNT_EMAIL_REQUIRED setting is enforced during signup."""
        client = Client()

        # Attempt to signup without email (should fail with ACCOUNT_EMAIL_REQUIRED=True)
        signup_url = reverse("account_signup")
        client.post(
            signup_url,
            {
                "username": "nousermail",
                "password1": "StrongPassword123!",
                "password2": "StrongPassword123!",
            },
            follow=True,
        )

        # Check that user was NOT created
        user = User.objects.filter(username="nousermail").first()
        assert user is None, (
            "User should not be created without email when ACCOUNT_EMAIL_REQUIRED=True"
        )
