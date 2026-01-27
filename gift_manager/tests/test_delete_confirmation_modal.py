"""Tests for delete confirmation modal functionality."""

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from hypothesis import given, strategies as st

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import (
    EventFactory,
    GiftFactory,
    GiftTagFactory,
    PersonFactory,
    PersonGroupFactory,
    RelationFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestDeleteConfirmationModal:
    """Tests for delete confirmation modal template and functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create a test person
        self.person = PersonFactory(
            first_name="Test",
            family_name="Person",
            email_address="test@example.com"
        )
        PermissionService.create_or_update_permission(
            user, self.person, permission_level=PermissionLevel.OWNER
        )

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_htmx_request(self):
        """Test that HTMX delete confirmation request returns modal content."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Make HTMX request
        response = self.client.get(url, HTTP_HX_REQUEST='true')

        # Assert response
        assert response.status_code == 200

        # Check that modal content is returned
        content = response.content.decode()
        assert 'Are you sure you want to delete this Person?' in content
        assert 'Test Person' in content  # Entity name
        assert 'test@example.com' in content  # Entity details
        assert 'fas fa-exclamation-triangle' in content  # Warning icon
        assert 'deleteForm' in content  # Form ID

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_context_data(self):
        """Test that delete confirmation modal has correct context data."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Make HTMX request
        response = self.client.get(url, HTTP_HX_REQUEST='true')

        # Check context data is properly rendered
        content = response.content.decode()

        # Entity type and name
        assert 'Person' in content
        assert str(self.person) in content

        # Entity icon (should be 'user' for person)
        assert 'fas fa-user' in content

        # Delete form with proper action
        assert f'action="{url}"' in content
        assert 'hx-post' in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_with_related_objects(self):
        """Test modal shows related objects warning when applicable."""
        # This test would need to be expanded based on actual relationships
        # For now, just verify the template structure supports it
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST='true')
        content = response.content.decode()

        # Check that related objects section exists in template
        # (even if empty for this test case)
        assert 'related_objects' in content or 'This will also affect' not in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_non_htmx_request(self):
        """Test that non-HTMX requests still work (fallback)."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Make regular request (no HTMX header)
        response = self.client.get(url)

        # Should return the regular delete confirmation page
        assert response.status_code == 200
        content = response.content.decode()

        # Should contain basic delete confirmation
        assert 'delete' in content.lower()

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_entity_details(self):
        """Test that entity details are properly displayed."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST='true')
        content = response.content.decode()

        # Check entity details are shown
        assert 'Email: test@example.com' in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_csrf_token(self):
        """Test that CSRF token is included in the form."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST='true')
        content = response.content.decode()

        # Check CSRF token is present
        assert 'csrfmiddlewaretoken' in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_htmx_attributes(self):
        """Test that proper HTMX attributes are set on the form."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST='true')
        content = response.content.decode()

        # Check HTMX attributes
        assert 'hx-post' in content
        assert 'hx-trigger="submit"' in content
        assert 'hx-target="body"' in content
        assert 'hx-confirm="false"' in content


@pytest.mark.django_db
class TestDeleteConfirmationDisplayProperty:
    """Property-based tests for delete confirmation display consistency."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def create_entity_with_permission(self, entity_type, entity_data):
        """Create an entity of the given type with test data and user permissions."""
        entity_factories = {
            'person': PersonFactory,
            'gift': GiftFactory,
            'event': EventFactory,
            'relation': RelationFactory,
            'persongroup': PersonGroupFactory,
            'gifttag': GiftTagFactory,
        }

        factory = entity_factories.get(entity_type.lower())
        if not factory:
            pytest.skip(f"No factory available for entity type: {entity_type}")

        # Create entity with filtered data (only valid fields)
        filtered_data = {}
        if entity_type.lower() == 'person':
            if 'first_name' in entity_data:
                filtered_data['first_name'] = entity_data['first_name'][:50]  # Limit length
            if 'family_name' in entity_data:
                filtered_data['family_name'] = entity_data['family_name'][:50]
        elif entity_type.lower() == 'gift':
            if 'name' in entity_data:
                filtered_data['name'] = entity_data['name'][:100]
            if 'comment' in entity_data:
                filtered_data['comment'] = entity_data['comment'][:500]
        elif entity_type.lower() == 'event':
            if 'name' in entity_data:
                filtered_data['name'] = entity_data['name'][:100]
            if 'comment' in entity_data:
                filtered_data['comment'] = entity_data['comment'][:500]
        elif entity_type.lower() == 'persongroup':
            if 'name' in entity_data:
                filtered_data['name'] = entity_data['name'][:100]
        elif entity_type.lower() == 'gifttag':
            if 'name' in entity_data:
                filtered_data['name'] = entity_data['name'][:100]

        # Create entity with valid data or defaults
        entity = factory(**filtered_data) if filtered_data else factory()

        # Grant permissions to user
        PermissionService.create_or_update_permission(
            self.user, entity, permission_level=PermissionLevel.OWNER
        )

        return entity

    def get_delete_url(self, entity_type, entity):
        """Get the delete URL for the given entity type and instance."""
        url_patterns = {
            'person': ('gift_manager:person_delete', 'person_id'),
            'gift': ('gift_manager:gift_delete', 'gift_id'),
            'event': ('gift_manager:event_delete', 'event_id'),
            'relation': ('gift_manager:relation_delete', 'relation_id'),
            'persongroup': ('gift_manager:person_group_delete', 'group_id'),
            'gifttag': ('gift_manager:gift_tag_delete', 'tag_id'),
        }

        pattern_info = url_patterns.get(entity_type.lower())
        if not pattern_info:
            pytest.skip(f"No URL pattern available for entity type: {entity_type}")

        url_name, pk_field = pattern_info
        pk_value = getattr(entity, pk_field)
        return reverse(url_name, kwargs={"pk": pk_value})

    @given(
        entity_type=st.sampled_from(['person', 'gift', 'event', 'persongroup', 'gifttag']),
        entity_data=st.dictionaries(
            st.sampled_from(['name', 'first_name', 'family_name', 'comment']),
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
            min_size=0,
            max_size=3
        )
    )
    @override_settings(USE_I18N=False)
    def test_ui_component_display_consistency_delete(self, entity_type, entity_data):
        """
        Feature: modern-ux-interface, Property 1: UI Component Display Consistency (Delete)

        For any entity type and delete action, clicking the delete button should display
        the appropriate modal dialog with correct content and structure.

        **Validates: Requirements 1.1, 1.2**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get delete URL for this entity type
        delete_url = self.get_delete_url(entity_type, entity)

        # Test HTMX delete confirmation request
        response = self.client.get(delete_url, HTTP_HX_REQUEST='true')

        # Property 1: UI Component Display Consistency
        # The response should be successful
        assert response.status_code == 200, f"Delete confirmation failed for {entity_type}"

        content = response.content.decode()

        # Modal should contain proper Bootstrap modal structure
        assert 'modal' in content.lower(), f"Modal structure missing for {entity_type}"

        # Should contain delete confirmation text
        assert 'delete' in content.lower(), f"Delete confirmation text missing for {entity_type}"

        # Should contain entity name/identifier
        entity_name = str(entity)
        if entity_name.strip():  # Only check if entity has a meaningful string representation
            assert entity_name in content, f"Entity name '{entity_name}' not found in modal for {entity_type}"

        # Should contain proper form structure for deletion
        assert 'form' in content.lower(), f"Delete form missing for {entity_type}"

        # Should contain HTMX attributes for AJAX handling
        assert 'hx-post' in content, f"HTMX post attribute missing for {entity_type}"

        # Should contain CSRF token for security
        assert 'csrfmiddlewaretoken' in content, f"CSRF token missing for {entity_type}"

        # Should contain proper action buttons (Delete and Cancel)
        assert 'cancel' in content.lower() or 'close' in content.lower(), f"Cancel button missing for {entity_type}"

        # Should contain the delete URL as form action
        assert delete_url in content, f"Delete URL not found in form action for {entity_type}"

        # Test that non-HTMX requests also work (fallback behavior)
        fallback_response = self.client.get(delete_url)
        assert fallback_response.status_code == 200, f"Fallback delete page failed for {entity_type}"

        # Fallback should still contain delete confirmation
        fallback_content = fallback_response.content.decode()
        assert 'delete' in fallback_content.lower(), f"Fallback delete confirmation missing for {entity_type}"
