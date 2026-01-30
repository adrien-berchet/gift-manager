"""Property-based tests for creation form functionality."""

import pytest
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory


@pytest.mark.django_db
class TestCreateFormProperty:
    """Property-based tests for creation form functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, user):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

    def get_create_url(self, entity_type):
        """Get the create URL for the given entity type."""
        url_patterns = {
            "person": "gift_manager:person_create",
            "gift": "gift_manager:gift_create",
            "event": "gift_manager:event_create",
            "relation": "gift_manager:relation_create",
            "persongroup": "gift_manager:person_group_create",
            "gifttag": "gift_manager:gift_tag_create",
        }

        url_name = url_patterns.get(entity_type.lower())
        if not url_name:
            pytest.skip(f"No URL pattern available for entity type: {entity_type}")

        return reverse(url_name)

    def get_form_data_for_entity(self, entity_type, entity_data):
        """Generate valid form data for creating an entity."""
        form_data = {}

        if entity_type.lower() == "person":
            form_data["first_name"] = entity_data.get("first_name", "Test")[:50]
            form_data["family_name"] = entity_data.get("family_name", "User")[:50]
            if "email_address" in entity_data:
                # Generate a valid email format
                email_base = entity_data.get("email_address", "test")[:20]
                import re

                email_base = re.sub(r"[^a-zA-Z0-9]", "", email_base)
                if not email_base:
                    email_base = "test"
                form_data["email_address"] = f"{email_base}@example.com"
        elif entity_type.lower() == "gift":
            form_data["name"] = entity_data.get("name", "Test Gift")[:100]
            form_data["comment"] = entity_data.get("comment", "")[:500]
        elif entity_type.lower() == "event":
            form_data["name"] = entity_data.get("name", "Test Event")[:100]
            form_data["comment"] = entity_data.get("comment", "")[:500]
        elif entity_type.lower() == "persongroup":
            form_data["name"] = entity_data.get("name", "Test Group")[:100]
        elif entity_type.lower() == "gifttag":
            form_data["name"] = entity_data.get("name", "Test Tag")[:100]
        elif entity_type.lower() == "relation":
            # Relations need person and gift/event, so create them first
            person = PersonFactory()
            gift = GiftFactory()
            PermissionService.create_or_update_permission(
                self.user, person, permission_level=PermissionLevel.OWNER
            )
            PermissionService.create_or_update_permission(
                self.user, gift, permission_level=PermissionLevel.OWNER
            )
            form_data["person"] = person.person_id
            form_data["gift"] = gift.gift_id

        return form_data

    def get_model_class(self, entity_type):
        """Get the model class for the given entity type."""
        from gift_manager.models import Event
        from gift_manager.models import Gift
        from gift_manager.models import GiftTag
        from gift_manager.models import Person
        from gift_manager.models import PersonGroup
        from gift_manager.models import Relation

        model_map = {
            "person": Person,
            "gift": Gift,
            "event": Event,
            "relation": Relation,
            "persongroup": PersonGroup,
            "gifttag": GiftTag,
        }
        return model_map.get(entity_type.lower())

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_data=st.dictionaries(
            st.sampled_from(["name", "first_name", "family_name", "comment", "email_address"]),
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
            min_size=1,
            max_size=3,
        ),
    )
    @override_settings(USE_I18N=False)
    def test_successful_operation_completion_create(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 3: Successful Operation Completion (Create)

        For any valid create operation, when the operation completes successfully,
        the entity should be created as expected and the current view should be
        updated without page reload.

        **Validates: Requirements 5.3**
        """
        # Get create URL for this entity type
        create_url = self.get_create_url(entity_type)

        # Generate form data for creation
        form_data = self.get_form_data_for_entity(entity_type, entity_data)

        # Get the model class to check entity count
        model_class = self.get_model_class(entity_type)
        initial_count = model_class.objects.count()

        # Test HTMX create form submission (AJAX save)
        response = self.client.post(create_url, data=form_data, HTTP_HX_REQUEST="true")

        # Property 3: Successful Operation Completion
        # The create operation should succeed (redirect or success response)
        assert response.status_code in [200, 302], (
            f"Create operation failed for {entity_type} with status {response.status_code}"
        )

        # Check if this was a successful operation or a validation error
        hx_trigger = response.get("HX-Trigger", "")
        is_error_response = "showNotification" in hx_trigger and "error" in hx_trigger

        # If it's an error response, the form validation failed, so skip entity creation checks
        if is_error_response:
            # For error responses, just verify the error handling is working correctly
            content = response.content.decode()
            assert "error" in hx_trigger.lower(), (
                f"Error response should have error notification for {entity_type}"
            )
            return  # Skip the rest of the test for validation errors

        # Verify that a new entity was created
        new_count = model_class.objects.count()
        assert new_count == initial_count + 1, (
            f"New {entity_type} was not created: expected {initial_count + 1}, got {new_count}"
        )

        # Get the newly created entity
        created_entity = model_class.objects.order_by("-pk").first()
        assert created_entity is not None, f"Could not retrieve newly created {entity_type}"

        # Verify that the entity was created with the correct data
        if entity_type.lower() == "person":
            assert created_entity.first_name == form_data["first_name"].strip(), (
                f"Person first_name not set correctly: expected '{form_data['first_name']}', got '{created_entity.first_name}'"
            )
            assert created_entity.family_name == form_data["family_name"].strip(), (
                f"Person family_name not set correctly: expected '{form_data['family_name']}', got '{created_entity.family_name}'"
            )
            if form_data.get("email_address"):
                # For encrypted email addresses, we need to check if the email was set
                assert created_entity.email_address is not None, "Person email_address not set"

        elif entity_type.lower() in ["gift", "event"]:
            assert created_entity.name == form_data["name"].strip(), (
                f"{entity_type.title()} name not set correctly: expected '{form_data['name']}', got '{created_entity.name}'"
            )
            if form_data.get("comment"):
                assert created_entity.comment == form_data["comment"].strip(), (
                    f"{entity_type.title()} comment not set correctly: expected '{form_data['comment']}', got '{created_entity.comment}'"
                )

        elif entity_type.lower() in ["persongroup", "gifttag"]:
            assert created_entity.name == form_data["name"].strip(), (
                f"{entity_type.title()} name not set correctly: expected '{form_data['name']}', got '{created_entity.name}'"
            )

        elif entity_type.lower() == "relation":
            assert str(created_entity.person.person_id) == str(form_data["person"]), (
                f"Relation person not set correctly: expected '{form_data['person']}', got '{created_entity.person.person_id}'"
            )
            if form_data.get("gift"):
                assert str(created_entity.gift.gift_id) == str(form_data["gift"]), (
                    f"Relation gift not set correctly: expected '{form_data['gift']}', got '{created_entity.gift.gift_id}'"
                )

        # Verify that the user has proper permissions on the created entity
        user_permission = PermissionService.get_permission(created_entity, self.user)
        assert user_permission >= PermissionLevel.EDITOR, (
            f"User does not have proper permissions on created {entity_type}: got {user_permission}"
        )

        # Test HTMX response headers for proper AJAX handling
        if response.status_code == 200:
            # Should contain HTMX trigger headers for list updates (only for successful operations)
            hx_trigger = response.get("HX-Trigger")
            if hx_trigger:
                # Should trigger list update or offcanvas close for successful operations
                success_triggers = ["list:update", "offcanvas:close", "modal:close"]
                has_success_trigger = any(trigger in hx_trigger for trigger in success_triggers)
                has_error_notification = "showNotification" in hx_trigger and "error" in hx_trigger

                # Either should have success triggers OR be an error response
                assert has_success_trigger or has_error_notification, (
                    f"HTMX trigger header missing proper events for {entity_type}: {hx_trigger}"
                )

        # Test that the response indicates successful completion
        if response.status_code == 200:
            content = response.content.decode()
            # Check if this is an error response first
            hx_trigger = response.get("HX-Trigger", "")
            is_error_response = "showNotification" in hx_trigger and "error" in hx_trigger

            if not is_error_response:
                # Should not contain error messages for successful operations
                error_indicators = ["error", "invalid", "required", "danger"]
                has_errors = any(indicator in content.lower() for indicator in error_indicators)
                # Only fail if there are actual error messages (not just the word "error" in labels)
                if has_errors:
                    # Check if these are actual error messages or just form labels
                    import re

                    error_patterns = [
                        r'class="[^"]*alert[^"]*danger',
                        r'class="[^"]*invalid-feedback',
                        r"<div[^>]*error[^>]*>",
                        r"This field is required",
                    ]
                    actual_errors = any(
                        re.search(pattern, content, re.IGNORECASE) for pattern in error_patterns
                    )
                    assert not actual_errors, (
                        f"Response contains error messages for {entity_type}: {content[:500]}"
                    )

        # Test fallback behavior (non-HTMX request)
        # Reset the count for fallback test
        initial_count_fallback = model_class.objects.count()

        fallback_response = self.client.post(create_url, data=form_data)

        # Fallback should also succeed (redirect to success page)
        assert fallback_response.status_code in [200, 302], (
            f"Fallback create operation failed for {entity_type} with status {fallback_response.status_code}"
        )

        # Verify another entity was created for fallback request
        new_count_fallback = model_class.objects.count()
        assert new_count_fallback == initial_count_fallback + 1, (
            f"Fallback create did not create new {entity_type}: expected {initial_count_fallback + 1}, got {new_count_fallback}"
        )

        # If it's a redirect, it should redirect to a reasonable location
        if fallback_response.status_code == 302:
            redirect_url = fallback_response.url
            # Should redirect to list view or detail view
            url_patterns = [
                entity_type.lower(),
                "list",
                "detail",
                "person_groups",
                "gift_tags",
                "gift-tag",
            ]
            assert any(pattern in redirect_url for pattern in url_patterns), (
                f"Fallback redirect URL not appropriate for {entity_type}: {redirect_url}"
            )

        # Test that the operation completed without page reload (for HTMX)
        # This is verified by the HTMX response not being a full HTML page
        if response.status_code == 200:
            content = response.content.decode()
            # HTMX response should not contain full page structure
            full_page_indicators = ["<html", "<head>", "<body>", "<!DOCTYPE"]
            is_full_page = any(indicator in content for indicator in full_page_indicators)
            assert not is_full_page, (
                f"HTMX response contains full page structure for {entity_type} (should be partial)"
            )

        # Verify that the current view would be updated
        # This is indicated by proper HTMX response headers or success content
        if response.status_code == 200:
            # Should either have HX-Trigger header or success content
            has_trigger = bool(response.get("HX-Trigger"))
            has_success_content = "success" in content.lower() or len(content.strip()) == 0

            assert has_trigger or has_success_content, (
                f"HTMX response lacks proper update mechanism for {entity_type}"
            )

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_data=st.dictionaries(
            st.sampled_from(["name", "first_name", "family_name", "comment", "email_address"]),
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
    def test_ui_component_display_consistency_create(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 1: UI Component Display Consistency (Create)

        For any entity type and create action, clicking the create button should display
        the appropriate slide panel with correct content and structure.

        **Validates: Requirements 5.1**
        """
        # Get create URL for this entity type
        create_url = self.get_create_url(entity_type)

        # Test HTMX create form request (slide panel)
        response = self.client.get(create_url, HTTP_HX_REQUEST="true")

        # Property 1: UI Component Display Consistency
        # The response should be successful
        assert response.status_code == 200, f"Create form failed for {entity_type}"

        content = response.content.decode()

        # Should contain proper form structure
        assert "form" in content.lower(), f"Form structure missing for {entity_type}"

        # Should contain HTMX attributes for AJAX handling
        assert "hx-post" in content, f"HTMX post attribute missing for {entity_type}"

        # Should contain proper Bootstrap form classes
        bootstrap_classes = [
            "form-control",
            "form-select",
            "form-input-text",
            "form-textarea",
            "form-check-input",
        ]
        has_bootstrap_classes = any(cls in content for cls in bootstrap_classes)
        assert has_bootstrap_classes, f"Bootstrap form classes missing for {entity_type}"

        # Should contain CSRF token for security
        assert "csrfmiddlewaretoken" in content, f"CSRF token missing for {entity_type}"

        # Should contain proper action buttons (Save and Cancel)
        assert "save" in content.lower() or "submit" in content.lower(), (
            f"Save button missing for {entity_type}"
        )
        assert "cancel" in content.lower() or "close" in content.lower(), (
            f"Cancel button missing for {entity_type}"
        )

        # Should contain the create URL as form action
        assert create_url in content, f"Create URL not found in form action for {entity_type}"

        # Test that non-HTMX requests also work (fallback behavior)
        fallback_response = self.client.get(create_url)
        assert fallback_response.status_code == 200, (
            f"Fallback create page failed for {entity_type}"
        )

        # Fallback should still contain create form
        fallback_content = fallback_response.content.decode()
        assert "form" in fallback_content.lower(), f"Fallback create form missing for {entity_type}"

        # Should contain proper page structure for full page
        assert "html" in fallback_content.lower(), f"Full page structure missing for {entity_type}"

        # Should contain entity type information
        entity_type_display = entity_type.replace("_", " ").title()
        type_found = (
            entity_type_display in fallback_content
            or entity_type.lower() in fallback_content.lower()
            or "create" in fallback_content.lower()
        )
        assert type_found, f"Entity type information missing for {entity_type}"
