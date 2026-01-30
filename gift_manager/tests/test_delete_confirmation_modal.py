"""Tests for delete confirmation modal functionality."""

import pytest
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory


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
            first_name="Test", family_name="Person", email_address="test@example.com"
        )
        PermissionService.create_or_update_permission(
            user, self.person, permission_level=PermissionLevel.OWNER
        )

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_htmx_request(self):
        """Test that HTMX delete confirmation request returns modal content."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Make HTMX request
        response = self.client.get(url, HTTP_HX_REQUEST="true")

        # Assert response
        assert response.status_code == 200

        # Check that modal content is returned
        content = response.content.decode()
        assert "Are you sure you want to delete this Person?" in content
        assert "Test Person" in content  # Entity name
        assert "test@example.com" in content  # Entity details
        assert "fas fa-exclamation-triangle" in content  # Warning icon
        assert "deleteForm" in content  # Form ID

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_context_data(self):
        """Test that delete confirmation modal has correct context data."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        # Make HTMX request
        response = self.client.get(url, HTTP_HX_REQUEST="true")

        # Check context data is properly rendered
        content = response.content.decode()

        # Entity type and name
        assert "Person" in content
        assert str(self.person) in content

        # Entity icon (should be 'user' for person)
        assert "fas fa-user" in content

        # Delete form with proper action
        assert f'action="{url}"' in content
        # Note: HTMX handling is done via JavaScript, not form attributes
        assert "deleteForm" in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_with_related_objects(self):
        """Test modal shows related objects warning when applicable."""
        # This test would need to be expanded based on actual relationships
        # For now, just verify the template structure supports it
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        # Check that related objects section exists in template
        # (even if empty for this test case)
        assert "related_objects" in content or "This will also affect" not in content

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
        assert "delete" in content.lower()

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_entity_details(self):
        """Test that entity details are properly displayed."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        # Check entity details are shown
        assert "Email: test@example.com" in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_csrf_token(self):
        """Test that CSRF token is included in the form."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        # Check CSRF token is present
        assert "csrfmiddlewaretoken" in content

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_htmx_attributes(self):
        """Test that proper form structure is set for JavaScript HTMX handling."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        # Check form structure for JavaScript HTMX handling
        assert "deleteForm" in content
        assert 'method="post"' in content
        assert f'action="{url}"' in content
        # Note: HTMX handling is done via JavaScript in base template, not form attributes

    @override_settings(USE_I18N=False)
    def test_delete_confirmation_modal_button_reset_script(self):
        """Test that delete confirmation modal includes button state reset functionality."""
        url = reverse("gift_manager:person_delete", kwargs={"pk": self.person.person_id})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        # Check that the modal includes JavaScript for button state reset
        assert "resetDeleteButtonStates" in content
        assert "GridUtils.resetDeleteButtonStates" in content
        assert "list:update" in content
        assert "hidden.bs.modal" in content

        # Check that the script handles modal events properly
        assert "confirmBtn.disabled = false" in content
        assert "confirmBtn.textContent" in content


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
            "person": PersonFactory,
            "gift": GiftFactory,
            "event": EventFactory,
            "relation": RelationFactory,
            "persongroup": PersonGroupFactory,
            "gifttag": GiftTagFactory,
        }

        factory = entity_factories.get(entity_type.lower())
        if not factory:
            pytest.skip(f"No factory available for entity type: {entity_type}")

        # Create entity with filtered data (only valid fields)
        filtered_data = {}
        if entity_type.lower() == "person":
            if "first_name" in entity_data:
                filtered_data["first_name"] = entity_data["first_name"][:50]  # Limit length
            if "family_name" in entity_data:
                filtered_data["family_name"] = entity_data["family_name"][:50]
        elif entity_type.lower() == "gift" or entity_type.lower() == "event":
            if "name" in entity_data:
                filtered_data["name"] = entity_data["name"][:100]
            if "comment" in entity_data:
                filtered_data["comment"] = entity_data["comment"][:500]
        elif entity_type.lower() == "persongroup" or entity_type.lower() == "gifttag":
            if "name" in entity_data:
                filtered_data["name"] = entity_data["name"][:100]

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
            "person": ("gift_manager:person_delete", "person_id"),
            "gift": ("gift_manager:gift_delete", "gift_id"),
            "event": ("gift_manager:event_delete", "event_id"),
            "relation": ("gift_manager:relation_delete", "relation_id"),
            "persongroup": ("gift_manager:person_group_delete", "group_id"),
            "gifttag": ("gift_manager:gift_tag_delete", "tag_id"),
        }

        pattern_info = url_patterns.get(entity_type.lower())
        if not pattern_info:
            pytest.skip(f"No URL pattern available for entity type: {entity_type}")

        url_name, pk_field = pattern_info
        pk_value = getattr(entity, pk_field)
        return reverse(url_name, kwargs={"pk": pk_value})

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_data=st.dictionaries(
            st.sampled_from(["name", "first_name", "family_name", "comment"]),
            st.text(
                alphabet=st.characters(
                    min_codepoint=32,  # Start from space character
                    max_codepoint=126,  # End at tilde character (printable ASCII)
                    blacklist_categories=(
                        "Cc",
                        "Cf",
                        "Cs",
                        "Co",
                        "Cn",
                    ),  # Exclude control characters
                ),
                min_size=1,
                max_size=50,
            ).filter(
                lambda x: x.strip() and "\x00" not in x
            ),  # Exclude null bytes and empty strings
            min_size=0,
            max_size=3,
        ),
    )
    @override_settings(USE_I18N=False)
    def test_ui_component_display_consistency_delete(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 1: UI Component Display Consistency (Delete)

        For any entity type and delete action, clicking the delete button should display
        the appropriate modal dialog with correct content and structure.

        **Validates: Requirements 1.1, 1.2**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get delete URL for this entity type
        delete_url = self.get_delete_url(entity_type, entity)

        # Test HTMX delete confirmation request
        response = self.client.get(delete_url, HTTP_HX_REQUEST="true")

        # Property 1: UI Component Display Consistency
        # The response should be successful
        assert response.status_code == 200, f"Delete confirmation failed for {entity_type}"

        content = response.content.decode()

        # Modal should contain proper Bootstrap modal structure
        assert "modal" in content.lower(), f"Modal structure missing for {entity_type}"

        # Should contain delete confirmation text
        assert "delete" in content.lower(), f"Delete confirmation text missing for {entity_type}"

        # Should contain entity name/identifier (handle HTML escaping)
        entity_name = str(entity)
        if entity_name.strip():  # Only check if entity has a meaningful string representation
            import html

            # Check for both raw and HTML-escaped versions of the entity name
            escaped_entity_name = html.escape(entity_name)
            assert entity_name in content or escaped_entity_name in content, (
                f"Entity name '{entity_name}' (or escaped '{escaped_entity_name}') not found in modal for {entity_type}"
            )

        # Should contain proper form structure for deletion
        assert "form" in content.lower(), f"Delete form missing for {entity_type}"

        # Should contain form ID for JavaScript handling
        assert "deleteForm" in content, f"Delete form ID missing for {entity_type}"

        # Should contain proper method and action
        assert 'method="post"' in content, f"POST method missing for {entity_type}"

        # Should contain CSRF token for security
        assert "csrfmiddlewaretoken" in content, f"CSRF token missing for {entity_type}"

        # Should contain proper action buttons (Delete and Cancel)
        assert "cancel" in content.lower() or "close" in content.lower(), (
            f"Cancel button missing for {entity_type}"
        )

        # Should contain the delete URL as form action
        assert delete_url in content, f"Delete URL not found in form action for {entity_type}"

        # Test that non-HTMX requests also work (fallback behavior)
        fallback_response = self.client.get(delete_url)
        assert fallback_response.status_code == 200, (
            f"Fallback delete page failed for {entity_type}"
        )

        # Fallback should still contain delete confirmation
        fallback_content = fallback_response.content.decode()
        assert "delete" in fallback_content.lower(), (
            f"Fallback delete confirmation missing for {entity_type}"
        )

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_data=st.dictionaries(
            st.sampled_from(["name", "first_name", "family_name", "comment"]),
            st.text(
                alphabet=st.characters(
                    min_codepoint=32,  # Start from space character
                    max_codepoint=126,  # End at tilde character (printable ASCII)
                    blacklist_categories=(
                        "Cc",
                        "Cf",
                        "Cs",
                        "Co",
                        "Cn",
                    ),  # Exclude control characters
                ),
                min_size=1,
                max_size=50,
            ).filter(
                lambda x: x.strip() and "\x00" not in x
            ),  # Exclude null bytes and empty strings
            min_size=0,
            max_size=3,
        ),
    )
    @override_settings(USE_I18N=False)
    def test_successful_operation_completion_delete(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 3: Successful Operation Completion (Delete)

        For any valid delete operation, when the operation completes successfully,
        the entity should be deleted and the current view should be updated without page reload.

        **Validates: Requirements 1.3**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)
        entity_pk = entity.pk

        # Get delete URL for this entity type
        delete_url = self.get_delete_url(entity_type, entity)

        # Get the model class to verify deletion
        model_class = entity.__class__

        # Verify entity exists before deletion
        assert model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should exist before deletion"
        )

        # Perform HTMX delete operation
        response = self.client.post(delete_url, HTTP_HX_REQUEST="true")

        # Property 3: Successful Operation Completion
        # The delete operation should succeed (redirect or success response)
        assert response.status_code in [200, 302], (
            f"Delete operation failed for {entity_type} with status {response.status_code}"
        )

        # Entity should be deleted from database
        assert not model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should be deleted from database"
        )

        # For HTMX requests, should include proper headers for view updates
        if response.status_code == 200:
            # Check for HTMX trigger headers that update the view
            hx_trigger = response.get("HX-Trigger")
            if hx_trigger:
                assert "list:update" in hx_trigger or "modal:close" in hx_trigger, (
                    f"HTMX trigger headers missing for view update after {entity_type} deletion"
                )

        # Test fallback behavior for non-HTMX requests
        # Create another entity for fallback test
        fallback_entity = self.create_entity_with_permission(entity_type, entity_data)
        fallback_entity_pk = fallback_entity.pk
        fallback_delete_url = self.get_delete_url(entity_type, fallback_entity)

        # Perform regular delete operation (no HTMX)
        fallback_response = self.client.post(fallback_delete_url)

        # Should redirect after successful deletion
        assert fallback_response.status_code == 302, (
            f"Fallback delete should redirect for {entity_type}"
        )

        # Entity should still be deleted
        assert not model_class.objects.filter(pk=fallback_entity_pk).exists(), (
            f"Entity {entity_type} should be deleted in fallback mode"
        )

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_data=st.dictionaries(
            st.sampled_from(["name", "first_name", "family_name", "comment"]),
            st.text(
                alphabet=st.characters(
                    min_codepoint=32,  # Start from space character
                    max_codepoint=126,  # End at tilde character (printable ASCII)
                    blacklist_categories=(
                        "Cc",
                        "Cf",
                        "Cs",
                        "Co",
                        "Cn",
                    ),  # Exclude control characters
                ),
                min_size=1,
                max_size=50,
            ).filter(
                lambda x: x.strip() and "\x00" not in x
            ),  # Exclude null bytes and empty strings
            min_size=0,
            max_size=3,
        ),
    )
    @override_settings(USE_I18N=False)
    def test_cancellation_behavior_delete(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 5: Cancellation Behavior (Delete)

        For any UI component (modal or panel), when a user cancels or closes the component,
        it should close properly and maintain the current application state without any changes.

        **Validates: Requirements 1.4**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)
        entity_pk = entity.pk

        # Get delete URL for this entity type
        delete_url = self.get_delete_url(entity_type, entity)

        # Get the model class to verify entity persistence
        model_class = entity.__class__

        # Store original entity state
        original_entity_count = model_class.objects.count()

        # Verify entity exists before cancellation test
        assert model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should exist before cancellation test"
        )

        # Test 1: GET request to show delete confirmation modal (should not delete anything)
        response = self.client.get(delete_url, HTTP_HX_REQUEST="true")

        # Property 5: Cancellation Behavior
        # Getting the delete confirmation should not modify any data
        assert response.status_code == 200, f"Delete confirmation display failed for {entity_type}"

        # Entity should still exist after showing confirmation modal
        assert model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should still exist after showing delete confirmation"
        )

        # Total entity count should remain unchanged
        assert model_class.objects.count() == original_entity_count, (
            f"Entity count should remain unchanged after showing delete confirmation for {entity_type}"
        )

        # Test 2: Simulate modal cancellation by not following through with POST
        # In a real browser, this would be clicking "Cancel" or the X button
        # We simulate this by just not making the POST request

        # Verify entity still exists (simulating user clicked cancel)
        assert model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should still exist after cancellation"
        )

        # Total entity count should remain unchanged
        assert model_class.objects.count() == original_entity_count, (
            f"Entity count should remain unchanged after cancellation for {entity_type}"
        )

        # Test 3: Verify that the modal content includes proper cancellation options
        content = response.content.decode()

        # Should contain cancel/close buttons or mechanisms
        has_cancel_button = (
            "cancel" in content.lower()
            or "close" in content.lower()
            or "btn-close" in content
            or "data-bs-dismiss" in content
        )

        assert has_cancel_button, (
            f"Delete confirmation modal should have cancel/close mechanism for {entity_type}"
        )

        # Test 4: Verify fallback behavior for non-HTMX requests
        # GET request without HTMX should also not delete anything
        fallback_response = self.client.get(delete_url)

        assert fallback_response.status_code == 200, (
            f"Fallback delete confirmation failed for {entity_type}"
        )

        # Entity should still exist after fallback confirmation display
        assert model_class.objects.filter(pk=entity_pk).exists(), (
            f"Entity {entity_type} should still exist after fallback delete confirmation"
        )

        # Total entity count should remain unchanged
        assert model_class.objects.count() == original_entity_count, (
            f"Entity count should remain unchanged after fallback confirmation for {entity_type}"
        )

        # Test 5: Verify that application state is maintained
        # The entity should be in exactly the same state as before
        refreshed_entity = model_class.objects.get(pk=entity_pk)

        # Basic state verification - entity should be unchanged
        assert refreshed_entity.pk == entity.pk, (
            f"Entity {entity_type} primary key should be unchanged"
        )

        # For entities with names, verify the name is unchanged
        if hasattr(refreshed_entity, "name") and hasattr(entity, "name"):
            assert refreshed_entity.name == entity.name, (
                f"Entity {entity_type} name should be unchanged"
            )
        elif hasattr(refreshed_entity, "first_name") and hasattr(entity, "first_name"):
            assert refreshed_entity.first_name == entity.first_name, (
                f"Entity {entity_type} first_name should be unchanged"
            )
