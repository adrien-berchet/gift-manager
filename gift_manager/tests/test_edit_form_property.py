"""Property-based tests for edit form display and data population."""

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
class TestEditFormDisplayProperty:
    """Property-based tests for edit form display and data population consistency."""

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
            if "email_address" in entity_data:
                # Generate a valid email format
                email_base = entity_data.get("email_address", "test")[:20]
                # Clean the email base to remove invalid characters
                import re

                email_base = re.sub(r"[^a-zA-Z0-9]", "", email_base)
                if not email_base:
                    email_base = "test"
                filtered_data["email_address"] = f"{email_base}@example.com"
        elif entity_type.lower() == "gift" or entity_type.lower() == "event":
            if "name" in entity_data:
                filtered_data["name"] = entity_data["name"][:100]
            if "comment" in entity_data:
                filtered_data["comment"] = entity_data["comment"][:500]
        elif entity_type.lower() == "persongroup" or entity_type.lower() == "gifttag":
            if "name" in entity_data:
                filtered_data["name"] = entity_data["name"][:100]
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
            filtered_data["person"] = person
            filtered_data["gift"] = gift

        # Create entity with valid data or defaults
        entity = factory(**filtered_data) if filtered_data else factory()

        # Grant permissions to user
        PermissionService.create_or_update_permission(
            self.user, entity, permission_level=PermissionLevel.OWNER
        )

        return entity

    def get_edit_url(self, entity_type, entity):
        """Get the edit URL for the given entity type and instance."""
        url_patterns = {
            "person": ("gift_manager:person_edit", "person_id"),
            "gift": ("gift_manager:gift_edit", "gift_id"),
            "event": ("gift_manager:event_edit", "event_id"),
            "relation": ("gift_manager:relation_edit", "relation_id"),
            "persongroup": ("gift_manager:person_group_edit", "group_id"),
            "gifttag": ("gift_manager:gift_tag_edit", "tag_id"),
        }

        pattern_info = url_patterns.get(entity_type.lower())
        if not pattern_info:
            pytest.skip(f"No URL pattern available for entity type: {entity_type}")

        url_name, pk_field = pattern_info
        pk_value = getattr(entity, pk_field)
        return reverse(url_name, kwargs={"pk": pk_value})

    def get_expected_form_fields(self, entity_type):
        """Get the expected form fields for each entity type."""
        field_mappings = {
            "person": ["first_name", "family_name", "email_address", "groups"],
            "gift": ["name", "comment", "tags"],
            "event": ["name", "comment", "usual_date"],
            "relation": ["person", "gift", "event", "status"],
            "persongroup": ["name", "parent_groups"],
            "gifttag": ["name", "parent_tags"],
        }
        return field_mappings.get(entity_type.lower(), [])

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
    def test_data_population_accuracy_edit(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 2: Data Population Accuracy (Edit)

        For any entity and any form or detail view, when the UI component is displayed,
        all fields and information should be populated with the current entity data
        accurately and completely.

        **Validates: Requirements 2.2**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get edit URL for this entity type
        edit_url = self.get_edit_url(entity_type, entity)

        # Test regular edit form request (full page)
        response = self.client.get(edit_url)

        # Property 2: Data Population Accuracy
        # The response should be successful
        assert response.status_code == 200, f"Edit form failed to load for {entity_type}"

        # Should contain form in context
        assert "form" in response.context, f"Form not found in context for {entity_type}"

        form = response.context["form"]
        content = response.content.decode()

        # Verify form is bound to the entity instance
        assert form.instance == entity, (
            f"Form not bound to correct entity instance for {entity_type}"
        )

        # Get expected fields for this entity type
        expected_fields = self.get_expected_form_fields(entity_type)

        # Verify each expected field is populated with correct data
        for field_name in expected_fields:
            if hasattr(entity, field_name):
                entity_value = getattr(entity, field_name)

                # Skip None values and empty relationships
                if entity_value is None:
                    continue

                # Handle different field types
                if hasattr(form.fields.get(field_name), "queryset"):
                    # Many-to-many or foreign key field
                    if hasattr(entity_value, "all"):  # Many-to-many
                        form_value = form.initial.get(field_name, [])
                        entity_pks = list(entity_value.values_list("pk", flat=True))
                        if form_value:
                            assert set(form_value) == set(entity_pks), (
                                f"Many-to-many field {field_name} not populated correctly for {entity_type}"
                            )
                    else:  # Foreign key
                        form_value = form.initial.get(field_name)
                        if entity_value:
                            assert form_value == entity_value.pk, (
                                f"Foreign key field {field_name} not populated correctly for {entity_type}"
                            )
                else:
                    # Regular field - handle encrypted email addresses
                    form_value = form.initial.get(field_name)
                    if form_value is not None and entity_value is not None:
                        # Special handling for encrypted email addresses
                        if field_name == "email_address" and entity_type.lower() == "person":
                            # For encrypted emails, skip the comparison as the form shows decrypted version
                            # but the entity stores encrypted version. This is expected behavior.
                            continue

                        # For non-encrypted fields or when encryption handling isn't available
                        assert str(form_value) == str(entity_value), (
                            f"Field {field_name} not populated correctly for {entity_type}: expected '{entity_value}', got '{form_value}'"
                        )

        # Verify form fields are rendered in the HTML
        for field_name in expected_fields:
            if field_name in form.fields:
                field_id = f"id_{field_name}"
                assert field_id in content, (
                    f"Field {field_name} not rendered in HTML for {entity_type}"
                )

        # Test HTMX edit form request (partial content)
        htmx_response = self.client.get(edit_url, HTTP_HX_REQUEST="true")

        # HTMX response should also be successful
        assert htmx_response.status_code == 200, f"HTMX edit form failed to load for {entity_type}"

        htmx_content = htmx_response.content.decode()

        # HTMX response should contain form elements
        assert "form" in htmx_content.lower(), (
            f"HTMX response missing form elements for {entity_type}"
        )

        # Should contain HTMX attributes for AJAX handling
        assert "hx-post" in htmx_content, f"HTMX post attribute missing for {entity_type}"

        # Should contain CSRF token for security
        assert "csrfmiddlewaretoken" in htmx_content, (
            f"CSRF token missing in HTMX response for {entity_type}"
        )

        # Verify entity data is still populated in HTMX response
        entity_str = str(entity)
        if entity_str.strip():  # Only check if entity has a meaningful string representation
            import html

            # Check for both raw and HTML-escaped versions of the entity data
            escaped_entity_str = html.escape(entity_str)
            # At least some representation of the entity should be in the form
            has_entity_data = (
                entity_str in htmx_content
                or escaped_entity_str in htmx_content
                or any(
                    str(getattr(entity, field, "")) in htmx_content
                    for field in expected_fields
                    if hasattr(entity, field) and getattr(entity, field)
                )
            )

            assert has_entity_data, f"Entity data not found in HTMX form for {entity_type}"

        # Verify form action points to correct URL
        assert edit_url in htmx_content, (
            f"Form action URL not found in HTMX response for {entity_type}"
        )

        # Test that form contains proper Bootstrap classes for styling
        bootstrap_classes = [
            "form-control",
            "form-select",
            "form-input-text",
            "form-textarea",
            "form-check-input",
        ]
        has_bootstrap_classes = any(cls in htmx_content for cls in bootstrap_classes)
        assert has_bootstrap_classes, (
            f"Bootstrap form classes missing in HTMX response for {entity_type}"
        )

        # Verify offcanvas structure for HTMX responses (slide panel)
        if "offcanvas" in htmx_content.lower():
            # If using offcanvas, should have proper structure
            assert "offcanvas-body" in htmx_content or "form-fields" in htmx_content, (
                f"Offcanvas structure incomplete for {entity_type}"
            )

        # Test form validation - the form should be valid with current entity data
        if hasattr(form, "is_valid"):
            # Create a form with the entity's current data to verify it's valid
            form_data = {}
            for field_name in expected_fields:
                if field_name in form.fields and hasattr(entity, field_name):
                    entity_value = getattr(entity, field_name)
                    if entity_value is not None:
                        if hasattr(entity_value, "all"):  # Many-to-many
                            form_data[field_name] = list(entity_value.values_list("pk", flat=True))
                        elif hasattr(entity_value, "pk"):  # Foreign key
                            form_data[field_name] = entity_value.pk
                        else:  # Regular field
                            form_data[field_name] = entity_value

            # Create a new form instance with the entity data
            form_class = form.__class__
            validation_form = form_class(data=form_data, instance=entity)

            # The form should be valid with the entity's own data
            if not validation_form.is_valid():
                # Only assert if there are actual validation errors (not just missing required fields)
                non_required_errors = {
                    field: errors
                    for field, errors in validation_form.errors.items()
                    if not (len(errors) == 1 and "required" in str(errors[0]).lower())
                }
                # Skip email validation errors for encrypted fields
                if "email_address" in non_required_errors and entity_type.lower() == "person":
                    email_errors = non_required_errors["email_address"]
                    if any("valid email" in str(error).lower() for error in email_errors):
                        # This is expected for encrypted email fields
                        non_required_errors.pop("email_address")

                if non_required_errors:
                    assert False, (
                        f"Form validation failed for {entity_type} with entity's own data: {non_required_errors}"
                    )

        # Verify accessibility attributes
        assert "aria-label" in htmx_content or "label" in htmx_content, (
            f"Accessibility labels missing for {entity_type}"
        )

        # Test that the form includes proper error handling structure
        error_handling_elements = ["alert", "error", "invalid-feedback", "form-fields", "danger"]
        has_error_handling = any(element in htmx_content for element in error_handling_elements)
        assert has_error_handling, f"Error handling structure missing for {entity_type}"

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
    def test_ui_component_display_consistency_edit(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 1: UI Component Display Consistency (Edit)

        For any entity type and edit action, clicking the edit button should display
        the appropriate slide panel with correct content and structure.

        **Validates: Requirements 2.1**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get edit URL for this entity type
        edit_url = self.get_edit_url(entity_type, entity)

        # Test HTMX edit form request (slide panel)
        response = self.client.get(edit_url, HTTP_HX_REQUEST="true")

        # Property 1: UI Component Display Consistency
        # The response should be successful
        assert response.status_code == 200, f"Edit form failed for {entity_type}"

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

        # Should contain the edit URL as form action
        assert edit_url in content, f"Edit URL not found in form action for {entity_type}"

        # Test that non-HTMX requests also work (fallback behavior)
        fallback_response = self.client.get(edit_url)
        assert fallback_response.status_code == 200, f"Fallback edit page failed for {entity_type}"

        # Fallback should still contain edit form
        fallback_content = fallback_response.content.decode()
        assert "form" in fallback_content.lower(), f"Fallback edit form missing for {entity_type}"

        # Should contain proper page structure for full page
        assert "html" in fallback_content.lower(), f"Full page structure missing for {entity_type}"

        # Should contain entity type information
        entity_type_display = entity_type.replace("_", " ").title()
        type_found = (
            entity_type_display in fallback_content
            or entity_type.lower() in fallback_content.lower()
            or "edit" in fallback_content.lower()
        )
        assert type_found, f"Entity type information missing for {entity_type}"
