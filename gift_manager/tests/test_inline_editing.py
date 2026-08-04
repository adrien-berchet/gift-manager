"""Tests for inline editing functionality."""

import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gift_manager.email_encoding import is_encrypted_email
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestInlineEditing:
    """Test cases for inline editing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_person_inline_update_success(self):
        """Test successful inline update of person field."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request
        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        # Check response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["old_value"] == "John"
        assert response_data["new_value"] == "Jane"

        # Verify database update
        person.refresh_from_db()
        assert person.first_name == "Jane"

    def test_person_inline_update_email_is_encoded(self):
        """Person email inline updates should use encoded storage."""
        person = PersonFactory(first_name="John", family_name="Doe")
        person.set_email("old@example.com")
        person.save(update_fields=["email_address"])
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "email_address", "value": "new@example.com"}

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["old_value"] == "old@example.com"
        assert response_data["new_value"] == "new@example.com"

        person.refresh_from_db()
        assert person.email_address != "new@example.com"
        assert is_encrypted_email(person.email_address)
        assert person.email == "new@example.com"

    def test_person_inline_update_rejects_missing_csrf_token(self):
        """Test inline updates require CSRF validation in normal middleware flow."""
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = csrf_client.post(url, data=json.dumps(data), content_type="application/json")

        assert response.status_code == 403
        person.refresh_from_db()
        assert person.first_name == "John"

    def test_person_inline_update_rejects_invalid_csrf_token(self):
        """Test inline updates reject mismatched CSRF tokens."""
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.cookies[settings.CSRF_COOKIE_NAME] = "a" * 32

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = csrf_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_CSRFTOKEN="b" * 32,
        )

        assert response.status_code == 403
        person.refresh_from_db()
        assert person.first_name == "John"

    def test_person_inline_update_accepts_valid_csrf_token(self):
        """Test editors can still update inline with a valid CSRF token."""
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.cookies[settings.CSRF_COOKIE_NAME] = "a" * 32

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = csrf_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_CSRFTOKEN="a" * 32,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        person.refresh_from_db()
        assert person.first_name == "Jane"

    def test_person_inline_update_requires_json_content_type(self):
        """Test inline updates reject non-JSON request bodies."""
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        response = self.client.post(url, data={"field": "first_name", "value": "Jane"})

        assert response.status_code == 415
        assert response.json()["success"] is False
        person.refresh_from_db()
        assert person.first_name == "John"

    def test_person_inline_update_permission_denied(self):
        """Test inline update fails without proper permissions."""
        # Create a person without editor permissions (viewer only)
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.VIEWER)

        # Make inline update request
        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        # Check response
        assert response.status_code == 403
        response_data = response.json()
        assert response_data["success"] is False
        assert "permission" in response_data["error"].lower()

        # Verify database not updated
        person.refresh_from_db()
        assert person.first_name == "John"

    def test_person_inline_update_returns_404_for_inaccessible_object(self):
        """Test private objects outside the editable queryset are not exposed."""
        person = PersonFactory(first_name="John", family_name="Doe")

        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {"field": "first_name", "value": "Jane"}

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        assert response.status_code == 404
        assert response.json()["success"] is False
        person.refresh_from_db()
        assert person.first_name == "John"

    def test_person_inline_update_invalid_field(self):
        """Test inline update fails for non-allowed fields."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request for non-allowed field
        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {
            "field": "person_id",  # Not in allowed_fields
            "value": "some-value",
        }

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data["success"] is False
        assert "not editable inline" in response_data["error"]

    def test_gift_inline_update_success(self):
        """Test successful inline update of gift field."""
        # Create a gift with editor permissions
        gift = GiftFactory(name="Original Gift", comment="Original comment")
        create_or_update_permission(self.user, gift, permission_level=PermissionLevel.EDITOR)

        # Make inline update request
        url = reverse("gift_manager:gift_inline_update", kwargs={"pk": gift.gift_id})
        data = {"field": "name", "value": "Updated Gift"}

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        # Check response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["old_value"] == "Original Gift"
        assert response_data["new_value"] == "Updated Gift"

        # Verify database update
        gift.refresh_from_db()
        assert gift.name == "Updated Gift"

    def test_inline_update_validation_error(self):
        """Test inline update handles validation errors."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request with invalid email
        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})
        data = {
            "field": "email_address",
            "value": "invalid-email",  # Invalid email format
        }

        response = self.client.post(url, data=json.dumps(data), content_type="application/json")

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data["success"] is False
        assert "error" in response_data

    def test_inline_update_invalid_json(self):
        """Test inline update handles invalid JSON."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request with invalid JSON
        url = reverse("gift_manager:person_inline_update", kwargs={"pk": person.person_id})

        response = self.client.post(url, data="invalid json", content_type="application/json")

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data["success"] is False
        assert "Invalid JSON" in response_data["error"]
