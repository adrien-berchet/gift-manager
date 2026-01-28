"""Property-based tests for inline editing functionality."""

import json
import pytest
from hypothesis import given, strategies as st
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from gift_manager.models import Person, Gift, PermissionLevel
from gift_manager.tests.factories import UserFactory, PersonFactory, GiftFactory
from gift_manager.permissions import create_or_update_permission

User = get_user_model()


@pytest.mark.django_db
class TestInlineEditingProperty:
    """Property-based tests for inline editing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    @given(
        field_name=st.sampled_from(['first_name', 'family_name']),
        new_value=st.text(min_size=1, max_size=50).filter(
            lambda x: x.strip() and all(ord(char) >= 32 or char in '\t\n\r' for char in x)
        )
    )
    def test_inline_editing_functionality_property(self, field_name, new_value):
        """
        **Property 8: Inline Editing Functionality**
        **Validates: Requirements 4.3, 4.4**

        For any editable field in list views, double-clicking should activate inline editing,
        and completing the edit should save the change via AJAX with visual feedback.
        """
        # Create a person with editor permissions
        person = PersonFactory()
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Get original value
        original_value = getattr(person, field_name)

        # Clean the new value the same way the server does
        cleaned_new_value = ''.join(char for char in str(new_value) if ord(char) >= 32 or char in '\t\n\r')
        cleaned_new_value = cleaned_new_value.strip()

        # Skip if cleaned value is same as original or empty
        if cleaned_new_value == original_value or not cleaned_new_value:
            return

        # Make inline update request
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': field_name,
            'value': new_value
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Property: AJAX update should succeed for valid data
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        response_data = response.json()
        assert response_data['success'] is True, f"Update failed: {response_data.get('error', 'Unknown error')}"

        # Property: Response should contain old and new values
        assert 'old_value' in response_data, "Response missing old_value"
        assert 'new_value' in response_data, "Response missing new_value"
        assert response_data['old_value'] == original_value, "Old value mismatch"
        assert response_data['new_value'] == cleaned_new_value, "New value mismatch (should be cleaned)"

        # Property: Database should be updated
        person.refresh_from_db()
        updated_value = getattr(person, field_name)
        assert updated_value == cleaned_new_value, f"Database not updated: expected {cleaned_new_value}, got {updated_value}"

        # Property: Success message should be provided (visual feedback)
        assert 'message' in response_data, "Response missing success message"
        assert len(response_data['message']) > 0, "Success message is empty"

    @given(
        field_name=st.sampled_from(['first_name', 'family_name', 'email_address']),
        permission_level=st.sampled_from([PermissionLevel.NONE, PermissionLevel.VIEWER])
    )
    def test_inline_editing_permission_property(self, field_name, permission_level):
        """
        **Property 8: Inline Editing Functionality (Permission Check)**
        **Validates: Requirements 4.3, 4.4**

        For any field, users without proper permissions should not be able to perform inline edits.
        """
        # Create a person with insufficient permissions
        person = PersonFactory()
        if permission_level > PermissionLevel.NONE:
            create_or_update_permission(self.user, person, permission_level=permission_level)

        # Make inline update request
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': field_name,
            'value': 'New Value'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Property: Should be denied for insufficient permissions
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

        response_data = response.json()
        assert response_data['success'] is False, "Update should have failed due to permissions"
        assert 'permission' in response_data['error'].lower(), "Error message should mention permissions"

    @given(
        invalid_field=st.text().filter(lambda x: x not in ['first_name', 'family_name', 'email_address'])
    )
    def test_inline_editing_invalid_field_property(self, invalid_field):
        """
        **Property 8: Inline Editing Functionality (Field Validation)**
        **Validates: Requirements 4.3, 4.4**

        For any non-editable field, inline editing should be rejected.
        """
        # Create a person with editor permissions
        person = PersonFactory()
        create_or_update_permission(self.user, person, permission_level=PermissionLevel.EDITOR)

        # Make inline update request for invalid field
        url = reverse('gift_manager:person_inline_update', kwargs={'pk': person.person_id})
        data = {
            'field': invalid_field,
            'value': 'Some Value'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Property: Should be rejected for invalid fields
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

        response_data = response.json()
        assert response_data['success'] is False, "Update should have failed for invalid field"
        assert 'not editable inline' in response_data['error'], "Error message should mention field not editable"
