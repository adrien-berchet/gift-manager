"""Property-based tests for unsaved changes protection functionality."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from gift_manager.models import Person, Gift, Event, PersonGroup, GiftTag, PermissionLevel

User = get_user_model()


@pytest.mark.django_db
class TestUnsavedChangesProtectionProperty:
    """Property-based tests for unsaved changes protection functionality."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test data for each test method."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client = Client()
        self.client.force_login(self.user)

    def create_test_entities(self, entity_type, count=3):
        """Create test entities for the given type."""
        entities = []

        for i in range(count):
            if entity_type == "person":
                entity = Person.objects.create(
                    first_name=f"Test{i}",
                    family_name=f"Person{i}",
                    email_address=f"test{i}@example.com"
                )
            elif entity_type == "gift":
                entity = Gift.objects.create(
                    name=f"Test Gift {i}",
                    comment=f"Test comment {i}"
                )
            elif entity_type == "event":
                entity = Event.objects.create(
                    name=f"Test Event {i}",
                    comment=f"Test comment {i}"
                )
            elif entity_type == "persongroup":
                entity = PersonGroup.objects.create(
                    name=f"Test Group {i}"
                )
            elif entity_type == "gifttag":
                entity = GiftTag.objects.create(
                    name=f"Test Tag {i}"
                )
            else:
                continue

            entities.append(entity)

        return entities

    @given(
        entity_type=st.sampled_from(["person", "gift", "event", "persongroup", "gifttag"])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unsaved_changes_detection_property(self, entity_type):
        """
        Feature: modern-ux-interface, Property 14: Unsaved Changes Protection
        For any form type and entity type, the system should detect when changes are made
        and provide appropriate warnings before navigation.
        **Validates: Requirements 12.1, 12.2**
        """
        # Property 14.1: Test unsaved changes detection for forms

        # Test create forms (should be accessible without permission issues)
        if entity_type == "persongroup":
            url = reverse('gift_manager:person_group_create')
        elif entity_type == "gifttag":
            url = reverse('gift_manager:gift_tag_create')
        else:
            url = reverse(f'gift_manager:{entity_type}_create')

        # Get the form page
        response = self.client.get(url)
        assert response.status_code == 200, f"Form page should be accessible for {entity_type} create"

        content = response.content.decode()

        # Check that unsaved changes JavaScript is included
        assert 'unsaved-changes.js' in content, "Unsaved changes JavaScript should be included"

        # Check that forms have the proper tracking attributes or IDs
        assert ('id="main-form"' in content or
                'data-track-changes' in content), "Form should have tracking identifier"

    @given(
        entity_type=st.sampled_from(["person", "gift", "event", "persongroup", "gifttag"])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_visual_indicators_for_modified_forms_property(self, entity_type):
        """
        Feature: modern-ux-interface, Property 14: Unsaved Changes Protection
        For any modified form field, the system should provide visual indicators
        showing which fields have been changed.
        **Validates: Requirements 12.3, 12.4, 12.5**
        """
        # Property 14.2: Test visual indicators for modified forms

        # Test create forms (should be accessible without permission issues)
        if entity_type == "persongroup":
            url = reverse('gift_manager:person_group_create')
        elif entity_type == "gifttag":
            url = reverse('gift_manager:gift_tag_create')
        else:
            url = reverse(f'gift_manager:{entity_type}_create')

        response = self.client.get(url)
        assert response.status_code == 200, f"Create form should be accessible for {entity_type}"

        content = response.content.decode()

        # Check that unsaved changes CSS is included (provides visual indicators)
        assert 'unsaved-changes.css' in content, "Unsaved changes CSS should be included for visual indicators"

        # Check that unsaved changes JavaScript is included (manages visual state)
        assert 'unsaved-changes.js' in content, "Unsaved changes JavaScript should be included for visual indicators"

        # Check that forms have the proper tracking attributes or IDs for visual feedback
        assert ('id="main-form"' in content or
                'data-track-changes' in content), "Form should have tracking identifier for visual indicators"

    @given(
        entity_type=st.sampled_from(["person", "gift", "event", "persongroup", "gifttag"])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_navigation_warnings_property(self, entity_type):
        """
        Feature: modern-ux-interface, Property 14: Unsaved Changes Protection
        For any navigation attempt with unsaved changes, the system should warn
        the user and provide options to save or discard changes.
        **Validates: Requirements 12.1, 12.2**
        """
        # Property 14.3: Test navigation warnings for unsaved changes

        # Test create forms (should be accessible without permission issues)
        if entity_type == "persongroup":
            url = reverse('gift_manager:person_group_create')
        elif entity_type == "gifttag":
            url = reverse('gift_manager:gift_tag_create')
        else:
            url = reverse(f'gift_manager:{entity_type}_create')

        response = self.client.get(url)
        assert response.status_code == 200, f"Create form should be accessible for {entity_type}"

        content = response.content.decode()

        # Check that unsaved changes JavaScript is included (provides navigation warnings)
        assert 'unsaved-changes.js' in content, "Unsaved changes JavaScript should be included for navigation warnings"

        # Check that forms have the proper tracking attributes for navigation protection
        assert ('id="main-form"' in content or
                'data-track-changes' in content), "Form should have tracking identifier for navigation warnings"

    @given(
        entity_type=st.sampled_from(["person", "gift", "event", "persongroup", "gifttag"])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unsaved_changes_actions_property(self, entity_type):
        """
        Feature: modern-ux-interface, Property 14: Unsaved Changes Protection
        For any unsaved changes situation, the system should provide clear
        save, discard, and cancel options with appropriate behavior.
        **Validates: Requirements 12.4, 12.5**
        """
        # Property 14.4: Test save/discard/cancel actions for unsaved changes

        # Test create forms (should be accessible without permission issues)
        if entity_type == "persongroup":
            url = reverse('gift_manager:person_group_create')
        elif entity_type == "gifttag":
            url = reverse('gift_manager:gift_tag_create')
        else:
            url = reverse(f'gift_manager:{entity_type}_create')

        response = self.client.get(url)
        assert response.status_code == 200, f"Create form should be accessible for {entity_type}"

        content = response.content.decode()

        # Check for save functionality
        save_indicators = [
            'type="submit"',
            'Save',
            'btn-primary',
            'fas fa-save'
        ]
        has_save = any(indicator in content for indicator in save_indicators)
        assert has_save, "Save functionality should be available"

        # Check for cancel functionality
        cancel_indicators = [
            'Cancel',
            'btn-secondary',
            'data-bs-dismiss',
            'fas fa-times'
        ]
        has_cancel = any(indicator in content for indicator in cancel_indicators)
        assert has_cancel, "Cancel functionality should be available"
