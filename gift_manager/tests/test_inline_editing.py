"""Tests for inline editing functionality."""

import json
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from gift_manager.models import Person, Gift, PermissionLevel
from gift_manager.tests.factories import UserFactory, PersonFactory, GiftFactory
from gift_manager.permissions import create_or_update_permission

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
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': 'first_name',
            'value': 'Jane'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['success'] is True
        assert response_data['old_value'] == 'John'
        assert response_data['new_value'] == 'Jane'

        # Verify database update
        person.refresh_from_db()
        assert person.first_name == 'Jane'

    def test_person_inline_update_permission_denied(self):
        """Test inline update fails without proper permissions."""
        # Create a person without editor permissions (viewer only)
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.VIEWER)

        # Make inline update request
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': 'first_name',
            'value': 'Jane'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 403
        response_data = response.json()
        assert response_data['success'] is False
        assert 'permission' in response_data['error'].lower()

        # Verify database not updated
        person.refresh_from_db()
        assert person.first_name == 'John'

    def test_person_inline_update_invalid_field(self):
        """Test inline update fails for non-allowed fields."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request for non-allowed field
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': 'person_id',  # Not in allowed_fields
            'value': 'some-value'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data['success'] is False
        assert 'not editable inline' in response_data['error']

    def test_gift_inline_update_success(self):
        """Test successful inline update of gift field."""
        # Create a gift with editor permissions
        gift = GiftFactory(name="Original Gift", comment="Original comment")
        create_or_update_permission(self.user, gift, permission_level=PermissionLevel.EDITOR)

        # Make inline update request
        url = reverse('gift_manager:gift_inline_update', kwargs={'pk': gift.gift_id})
        data = {
            'field': 'name',
            'value': 'Updated Gift'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['success'] is True
        assert response_data['old_value'] == 'Original Gift'
        assert response_data['new_value'] == 'Updated Gift'

        # Verify database update
        gift.refresh_from_db()
        assert gift.name == 'Updated Gift'

    def test_inline_update_validation_error(self):
        """Test inline update handles validation errors."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request with invalid email
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': 'email_address',
            'value': 'invalid-email'  # Invalid email format
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data['success'] is False
        assert 'error' in response_data

    def test_inline_update_invalid_json(self):
        """Test inline update handles invalid JSON."""
        # Create a person with editor permissions
        person = PersonFactory(first_name="John", family_name="Doe")
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request with invalid JSON
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})

        response = self.client.post(
            url,
            data='invalid json',
            content_type='application/json'
        )

        # Check response
        assert response.status_code == 400
        response_data = response.json()
        assert response_data['success'] is False
        assert 'Invalid JSON' in response_data['error']
