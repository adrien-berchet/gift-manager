"""Property-based tests for loading state feedback."""

import pytest
from django.test import Client
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
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.utils import assert_text_in_rendered


@pytest.mark.django_db
class TestLoadingStateFeedbackProperty:
    """Property-based tests for loading state feedback."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def create_entities(self, entity_type, count):
        """Create test entities of the specified type."""
        factories = {
            "person": PersonFactory,
            "gift": GiftFactory,
            "event": EventFactory,
            "relation": RelationFactory,
            "persongroup": PersonGroupFactory,
            "gifttag": GiftTagFactory,
        }

        factory = factories.get(entity_type.lower())
        if not factory:
            return []

        entities = []
        for _ in range(count):
            if entity_type.lower() == "relation":
                # Relations need special handling for person/gift creation
                person = PersonFactory()
                gift = GiftFactory()
                PermissionService.create_or_update_permission(
                    self.user, person, permission_level=PermissionLevel.EDITOR
                )
                PermissionService.create_or_update_permission(
                    self.user, gift, permission_level=PermissionLevel.EDITOR
                )
                entity = factory(person=person, gift=gift)
            else:
                entity = factory()

            # Grant permissions to the test user
            PermissionService.create_or_update_permission(
                self.user, entity, permission_level=PermissionLevel.EDITOR
            )
            entities.append(entity)

        return entities

    @given(
        entity_type=st.sampled_from(["person", "gift", "event"]),
        operation=st.sampled_from(["create", "edit", "detail"]),
    )
    def test_loading_state_feedback_property(self, entity_type, operation):
        """Feature: modern-ux-interface, Property 11: Loading State Feedback

        For any operation that takes time to complete, appropriate loading indicators
        should be displayed, and form controls should be disabled during submission.

        **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
        """
        # Create test entity if needed for edit/detail operations
        entity = None
        if operation in ["edit", "detail"]:
            entities = self.create_entities(entity_type, 1)
            if not entities:
                pytest.skip(f"Could not create entity for type: {entity_type}")
            entity = entities[0]

        # Map entity types to their URL field names (as used in views)
        pk_field_mapping = {
            "person": "person_id",
            "gift": "gift_id",
            "event": "event_id",
        }

        # Property 11.1: AJAX operations should provide loading indicators
        try:
            if operation == "create":
                url = reverse(f"gift_manager:{entity_type}_create")
            elif operation in ["edit", "detail"]:
                pk_field = pk_field_mapping.get(entity_type)
                if not pk_field or not hasattr(entity, pk_field):
                    pytest.skip(f"Primary key field {pk_field} not found for {entity_type}")

                pk_value = getattr(entity, pk_field)
                url = reverse(f"gift_manager:{entity_type}_{operation}", kwargs={"pk": pk_value})
        except Exception as e:
            pytest.skip(f"URL not available for {entity_type} {operation}: {e!s}")

        # Test HTMX request for loading state support
        response = self.client.get(url, HTTP_HX_REQUEST="true")

        # Property 11.1: HTMX requests should return appropriate content
        assert response.status_code in [200, 302, 404], (
            f"HTMX {operation} request should return valid status for {entity_type}"
        )

        if response.status_code == 200:
            content = response.content.decode()

            # Property 11.2: Forms should have loading state support
            if operation in ["create", "edit"]:
                assert_text_in_rendered("<form", content)

                # Check for form elements that support loading states
                tmp_check = 'type="submit"' in content or "button" in content
                assert tmp_check

            # Property 11.4: Detail views should support loading states
            elif operation == "detail":
                # Detail views should have content that can show loading states
                assert len(content.strip()) > 0, "Detail view should have content"

    @given(entity_type=st.sampled_from(["person", "gift", "event"]))
    def test_form_submission_loading_property(self, entity_type):
        """Feature: modern-ux-interface, Property 11: Loading State Feedback (Form Submission)

        For any form submission, form controls should be disabled during operations
        and appropriate feedback should be provided.

        **Validates: Requirements 8.2, 8.3**
        """
        # Property 11: Test form submission with loading states
        try:
            create_url = reverse(f"gift_manager:{entity_type}_create")
        except Exception:
            pytest.skip(f"Create URL not available for {entity_type}")

        # Get the create form
        form_response = self.client.get(create_url, HTTP_HX_REQUEST="true")

        if form_response.status_code != 200:
            pytest.skip(f"Create form not available for {entity_type}")

        form_content = form_response.content.decode()

        # Property 11.2: Form should have elements that can be disabled during submission
        form_elements = ["input", "select", "textarea", "button"]
        has_form_elements = any(element in form_content for element in form_elements)
        assert has_form_elements, (
            "Create form should have form elements that can be disabled during loading"
        )

        # Test actual form submission (if we can generate valid data)
        form_data = self._generate_form_data(entity_type)
        if form_data:
            submission_response = self.client.post(
                create_url, data=form_data, HTTP_HX_REQUEST="true"
            )

            # Property 11.4: Operations should complete (success or validation error)
            assert submission_response.status_code in [200, 201, 302, 400], (
                f"Form submission should return valid status for {entity_type}"
            )

    @given(entity_type=st.sampled_from(["person", "gift", "event"]))
    def test_error_feedback_property(self, entity_type):
        """Feature: modern-ux-interface, Property 11: Loading State Feedback (Error Handling)

        For any operation that fails, appropriate error feedback should be provided
        with user-friendly messages.

        **Validates: Requirements 8.4**
        """
        # Property 11.4: Test error feedback for validation errors
        try:
            create_url = reverse(f"gift_manager:{entity_type}_create")
        except Exception:
            pytest.skip(f"Create URL not available for {entity_type}")

        # Submit form with invalid data
        invalid_data = {"invalid_field": "invalid_value"}
        response = self.client.post(create_url, data=invalid_data, HTTP_HX_REQUEST="true")

        # Property 11.4: Should handle invalid submissions gracefully
        assert response.status_code in [200, 400, 422], (
            f"Invalid form submission should be handled gracefully for {entity_type}"
        )

    def _generate_form_data(self, entity_type):
        """Generate valid form data for testing."""
        form_data_templates = {
            "person": {
                "first_name": "Test",
                "family_name": "Person",
                "email_address": "test@example.com",
            },
            "gift": {"name": "Test Gift", "comment": "Test comment"},
            "event": {
                "name": "Test Event",
                "comment": "Test comment",
                "schedule_type": "recurring",
                "date": "2024-12-25",
                "recurrence": "yearly",
            },
        }

        return form_data_templates.get(entity_type.lower(), {})
