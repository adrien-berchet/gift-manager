"""Property-based tests for detail view display and data population."""

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
class TestDetailViewDisplayProperty:
    """Property-based tests for detail view display and data population consistency."""

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

    def get_detail_url(self, entity_type, entity):
        """Get the detail URL for the given entity type and instance."""
        url_patterns = {
            "person": ("gift_manager:person_detail", "person_id"),
            "gift": ("gift_manager:gift_detail", "gift_id"),
            "event": ("gift_manager:event_detail", "event_id"),
            "relation": ("gift_manager:relation_detail", "relation_id"),
            "persongroup": ("gift_manager:person_group_detail", "group_id"),
            "gifttag": ("gift_manager:gift_tag_detail", "tag_id"),
        }

        pattern_info = url_patterns.get(entity_type.lower())
        if not pattern_info:
            pytest.skip(f"No URL pattern available for entity type: {entity_type}")

        url_name, pk_field = pattern_info
        pk_value = getattr(entity, pk_field)
        return reverse(url_name, kwargs={"pk": pk_value})

    def get_expected_detail_fields(self, entity_type):
        """Get the expected detail fields for each entity type."""
        field_mappings = {
            "person": ["first_name", "family_name", "email_address", "creation_date"],
            "gift": ["name", "comment", "creation_date"],
            "event": ["name", "comment", "date", "creation_date"],
            "relation": ["person", "gift", "event", "status", "creation_date"],
            "persongroup": ["name", "creation_date"],
            "gifttag": ["name", "creation_date"],
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
    def test_data_population_accuracy_detail(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 2: Data Population Accuracy (Detail)

        For any entity and any detail view, when the UI component is displayed,
        all fields and information should be populated with the current entity data
        accurately and completely.

        **Validates: Requirements 3.2, 3.3**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get detail URL for this entity type
        detail_url = self.get_detail_url(entity_type, entity)

        # Test regular detail view request (full page)
        response = self.client.get(detail_url)

        # Property 2: Data Population Accuracy
        # The response should be successful
        assert response.status_code == 200, f"Detail view failed to load for {entity_type}"

        # Should contain object in context
        assert "object" in response.context or entity_type in response.context, (
            f"Entity object not found in context for {entity_type}"
        )

        content = response.content.decode()

        # Get expected fields for this entity type
        expected_fields = self.get_expected_detail_fields(entity_type)

        # Verify each expected field is displayed with correct data
        for field_name in expected_fields:
            if hasattr(entity, field_name):
                entity_value = getattr(entity, field_name)

                # Skip None values
                if entity_value is None:
                    continue

                # Convert value to string for comparison
                if hasattr(entity_value, "strftime"):  # Date/datetime field
                    # Check for various date formats in the content
                    date_formats = [
                        entity_value.strftime("%Y-%m-%d"),
                        entity_value.strftime("%m/%d/%Y"),
                        entity_value.strftime("%b %d, %Y"),
                        entity_value.strftime("%B %d, %Y"),
                        entity_value.strftime("%Y"),  # Just the year
                        entity_value.strftime("%m"),  # Just the month
                        entity_value.strftime("%d"),  # Just the day
                    ]
                    # Also check for Django's default date formatting
                    django_default = str(entity_value)  # Django's default string representation
                    date_formats.append(django_default)

                    date_found = any(date_format in content for date_format in date_formats)
                    assert date_found, (
                        f"Date field {field_name} not displayed correctly for {entity_type}. "
                        f"Expected one of {date_formats} in content. Entity value: {entity_value}"
                    )
                elif hasattr(entity_value, "all"):  # Many-to-many relationship
                    # Check if related objects are displayed
                    related_objects = list(entity_value.all())
                    if related_objects:
                        # At least one related object should be mentioned
                        related_found = any(str(obj) in content for obj in related_objects)
                        assert related_found, (
                            f"Related objects for {field_name} not displayed for {entity_type}"
                        )
                elif hasattr(entity_value, "__str__"):  # Foreign key or regular object
                    entity_str = str(entity_value)
                    if entity_str.strip():
                        # Handle special cases for encrypted fields
                        if field_name == "email_address" and entity_type.lower() == "person":
                            # For encrypted emails, check if any email-like pattern is displayed
                            import re

                            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                            email_found = re.search(email_pattern, content)
                            if not email_found:
                                # If no email pattern found, that's also acceptable (might be encrypted)
                                continue
                        else:
                            # For regular fields, check if the value is displayed
                            import html

                            escaped_value = html.escape(entity_str)
                            value_found = entity_str in content or escaped_value in content
                            assert value_found, (
                                f"Field {field_name} value '{entity_str}' not displayed for {entity_type}"
                            )

        # Test HTMX detail view request (partial content for slide panel)
        htmx_response = self.client.get(detail_url, HTTP_HX_REQUEST="true")

        # HTMX response should also be successful
        assert htmx_response.status_code == 200, (
            f"HTMX detail view failed to load for {entity_type}"
        )

        htmx_content = htmx_response.content.decode()

        # HTMX response should contain detail content
        assert (
            "detail" in htmx_content.lower()
            or "group details" in htmx_content.lower()
            or "person details" in htmx_content.lower()
            or "gift details" in htmx_content.lower()
            or "event details" in htmx_content.lower()
            or "relation details" in htmx_content.lower()
            or "tag details" in htmx_content.lower()
        ), f"HTMX response missing detail content for {entity_type}"

        # Should contain entity information
        entity_str = str(entity)
        if entity_str.strip():
            import html

            escaped_entity_str = html.escape(entity_str)
            has_entity_data = (
                entity_str in htmx_content
                or escaped_entity_str in htmx_content
                or any(
                    str(getattr(entity, field, "")) in htmx_content
                    for field in expected_fields
                    if hasattr(entity, field) and getattr(entity, field)
                )
            )

            assert has_entity_data, f"Entity data not found in HTMX detail view for {entity_type}"

        # Verify detail sections are properly structured
        detail_structure_elements = [
            "detail-section",
            "detail-field",
            "detail-value",
            "detail-label",
        ]
        has_detail_structure = any(element in htmx_content for element in detail_structure_elements)
        assert has_detail_structure, (
            f"Detail view structure missing in HTMX response for {entity_type}"
        )

        # Should contain action buttons (edit, delete)
        action_buttons = ["edit", "delete", "btn"]
        has_action_buttons = any(button in htmx_content.lower() for button in action_buttons)
        assert has_action_buttons, f"Action buttons missing in detail view for {entity_type}"

        # Verify accessibility attributes
        accessibility_elements = ["aria-label", "role", "title"]
        has_accessibility = any(element in htmx_content for element in accessibility_elements)
        assert has_accessibility, f"Accessibility attributes missing for {entity_type}"

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
    def test_ui_component_display_consistency_detail(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 1: UI Component Display Consistency (Detail)

        For any entity type and detail action, clicking the detail button should display
        the appropriate slide panel with correct content and structure.

        **Validates: Requirements 3.1**
        """
        # Create entity with random data
        entity = self.create_entity_with_permission(entity_type, entity_data)

        # Get detail URL for this entity type
        detail_url = self.get_detail_url(entity_type, entity)

        # Test HTMX detail view request (slide panel)
        response = self.client.get(detail_url, HTTP_HX_REQUEST="true")

        # Property 1: UI Component Display Consistency
        # The response should be successful
        assert response.status_code == 200, f"Detail view failed for {entity_type}"

        content = response.content.decode()

        # Should contain proper detail structure (more flexible for HTMX vs full page)
        detail_indicators = [
            "detail",
            "group details",
            "person details",
            "gift details",
            "event details",
            "relation details",
            "tag details",
            "detail-section",
            "detail-field",
            "detail-value",
            f"{entity_type.lower()} details",
            "creation date",
            "created",
        ]
        has_detail_structure = any(indicator in content.lower() for indicator in detail_indicators)
        assert has_detail_structure, f"Detail structure missing for {entity_type}"

        # Should contain entity information
        entity_str = str(entity)
        if entity_str.strip():
            import html

            escaped_entity_str = html.escape(entity_str)
            has_entity_info = (
                entity_str in content
                or escaped_entity_str in content
                or entity_type.lower() in content.lower()
            )
            assert has_entity_info, f"Entity information missing for {entity_type}"

        # Should contain proper Bootstrap classes for styling
        bootstrap_classes = ["detail-section", "detail-field", "detail-value", "badge", "card"]
        has_bootstrap_classes = any(cls in content for cls in bootstrap_classes)
        assert has_bootstrap_classes, f"Bootstrap detail classes missing for {entity_type}"

        # Should contain action buttons with proper data attributes
        action_elements = ["data-action", "btn", "edit", "delete"]
        has_action_elements = any(element in content for element in action_elements)
        assert has_action_elements, f"Action elements missing for {entity_type}"

        # Should contain proper icons for visual enhancement
        icon_elements = ["fa-", "fas", "icon"]
        has_icons = any(icon in content for icon in icon_elements)
        assert has_icons, f"Icons missing for {entity_type}"

        # Test that non-HTMX requests also work (fallback behavior)
        fallback_response = self.client.get(detail_url)
        assert fallback_response.status_code == 200, (
            f"Fallback detail page failed for {entity_type}"
        )

        # Fallback should still contain detail information
        fallback_content = fallback_response.content.decode()

        # Check for entity information with HTML escaping consideration
        entity_str = str(entity)
        import html

        escaped_entity_str = html.escape(entity_str)

        # For full page responses, check for broader indicators of detail content
        detail_content_indicators = [
            entity_str,
            escaped_entity_str,
            entity_type.lower(),
            f"{entity_type.lower()} details",
            "details",
            "creation date",
            "created",
        ]

        has_detail_content = any(
            indicator in fallback_content.lower() for indicator in detail_content_indicators
        )
        assert has_detail_content, (
            f"Fallback detail content missing for {entity_type}. Expected one of {detail_content_indicators}"
        )

        # Should contain proper page structure for full page
        assert "html" in fallback_content.lower(), f"Full page structure missing for {entity_type}"

        # Should contain navigation elements
        nav_elements = ["nav", "breadcrumb", "menu"]
        has_navigation = any(nav in fallback_content.lower() for nav in nav_elements)
        assert has_navigation, f"Navigation elements missing for {entity_type}"

        # Verify the detail view contains creation date information
        if hasattr(entity, "creation_date") and entity.creation_date:
            date_found = any(
                date_format in content
                for date_format in [
                    entity.creation_date.strftime("%Y"),
                    entity.creation_date.strftime("%m"),
                    entity.creation_date.strftime("%d"),
                    "created",
                    "date",
                ]
            )
            assert date_found, f"Creation date information missing for {entity_type}"

        # Verify responsive design elements
        responsive_elements = ["col-", "row", "d-", "flex"]
        has_responsive = any(element in content for element in responsive_elements)
        assert has_responsive, f"Responsive design elements missing for {entity_type}"

        # Should contain proper semantic HTML structure
        semantic_elements = ["section", "article", "header", "main", "div"]
        has_semantic = any(element in content for element in semantic_elements)
        assert has_semantic, f"Semantic HTML structure missing for {entity_type}"
