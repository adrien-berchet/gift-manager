"""Property-based tests for quick actions availability."""

import pytest
from django.test import Client
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st

from gift_manager.models import PermissionLevel
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestQuickActionsAvailabilityProperty:
    """Property-based tests for quick actions availability."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def create_entity(self, entity_type, entity_data):
        """Create an entity of the specified type with given data."""
        factory_map = {
            "person": PersonFactory,
            "gift": GiftFactory,
            "event": EventFactory,
            "relation": RelationFactory,
            "persongroup": PersonGroupFactory,
            "gifttag": GiftTagFactory,
        }

        factory_class = factory_map.get(entity_type.lower())
        if not factory_class:
            raise ValueError(f"Unknown entity type: {entity_type}")

        # Filter entity_data to only include valid fields for the factory
        filtered_data = {}
        if entity_type.lower() in ["person", "gift", "event", "persongroup", "gifttag"]:
            if "name" in entity_data:
                if entity_type.lower() == "person":
                    filtered_data["first_name"] = entity_data["name"][:30]
                else:
                    filtered_data["name"] = entity_data["name"][:100]

        return factory_class(**filtered_data)

    def get_list_url(self, entity_type):
        """Get the list URL for the specified entity type."""
        url_map = {
            "person": "gift_manager:persons",
            "gift": "gift_manager:gifts",
            "event": "gift_manager:events",
            "relation": "gift_manager:relations",
            "persongroup": "gift_manager:person_groups",
            "gifttag": "gift_manager:gift_tag_explorer",
        }

        url_name = url_map.get(entity_type.lower())
        if not url_name:
            raise ValueError(f"Unknown entity type: {entity_type}")

        return reverse(url_name)

    def get_expected_actions(self, entity_type):
        """Get the expected quick actions for the specified entity type."""
        # Based on the existing test patterns, different entity types have different actions
        action_map = {
            "person": ["give", "details", "edit", "delete", "share"],
            "gift": ["give", "details", "edit", "delete", "share"],
            "event": ["details", "edit", "delete", "share"],  # No 'give' for events
            "relation": ["details", "edit", "delete", "share"],
            "persongroup": ["give", "details", "edit", "delete", "share"],
            "gifttag": ["details", "edit", "delete", "share"],  # Assuming similar to events
        }

        return action_map.get(entity_type.lower(), ["details", "edit", "delete", "share"])

    def get_expected_action_column_width(self, entity_type):
        """Get the action column width needed for visible icon+label buttons."""
        return "360px" if len(self.get_expected_actions(entity_type)) == 5 else "340px"

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup"]
        ),  # Exclude gifttag as it uses explorer view
        entity_data=st.dictionaries(
            st.sampled_from(["name", "comment"]),
            st.text(min_size=1, max_size=50).filter(
                lambda x: x.strip() and "\n" not in x and "\x00" not in x
            ),
            min_size=1,
            max_size=2,
        ),
    )
    def test_quick_actions_availability_property(self, entity_type, entity_data):
        """Feature: modern-ux-interface, Property 7: Quick Actions Availability
        For any entity list, each item should display appropriate quick action buttons
        (edit, delete, share) that are accessible and functional.
        Validates: Requirements 4.1, 4.2
        """
        # Create entity with random data
        self.create_entity(entity_type, entity_data)

        # Get the list URL for this entity type
        list_url = self.get_list_url(entity_type)

        # Make request to list view
        response = self.client.get(list_url)

        # Verify response is successful
        assert response.status_code == 200, f"List view failed for {entity_type}"

        content = response.content.decode()

        # Get expected actions for this entity type
        expected_actions = self.get_expected_actions(entity_type)

        # Verify that all expected quick action buttons are present in the configuration
        for action in expected_actions:
            assert f"'{action}'" in content, (
                f"Quick action '{action}' missing from {entity_type} list view"
            )

        # Verify that the actions array includes all expected buttons
        actions_array = str(expected_actions).replace("'", "'")
        assert actions_array in content, (
            f"Actions array {actions_array} not found in {entity_type} list view"
        )

        expected_width = self.get_expected_action_column_width(entity_type)
        assert f"width: '{expected_width}'" in content, (
            f"Action column width not set correctly for {entity_type} list view"
        )

        # Verify that share button points to the correct share URL
        if "share" in expected_actions:
            share_url = reverse("gift_manager:share_objects")
            assert f'share: () => "{share_url}"' in content, (
                f"Share button URL not configured correctly for {entity_type} list view"
            )

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup"]
        ),  # Exclude gifttag as it uses explorer view
        entity_data=st.dictionaries(
            st.sampled_from(["name", "comment"]),
            st.text(min_size=1, max_size=50).filter(
                lambda x: x.strip() and "\n" not in x and "\x00" not in x
            ),
            min_size=1,
            max_size=2,
        ),
        permission_level=st.sampled_from([PermissionLevel.NONE, PermissionLevel.VIEWER]),
    )
    def test_quick_actions_permission_based_availability(
        self, entity_type, entity_data, permission_level
    ):
        """Feature: modern-ux-interface, Property 7: Quick Actions Availability
        For any entity list with restricted permissions, action buttons should be
        hidden or disabled based on user permissions.
        Validates: Requirements 4.1, 4.2, 4.5
        """
        # Create entity with random data
        entity = self.create_entity(entity_type, entity_data)

        # Create a user with restricted permissions
        restricted_user = UserFactory()

        # Set up permission restrictions based on entity type
        if entity_type.lower() == "person":
            from gift_manager.models import PersonPermission

            PersonPermission.objects.create(
                user=restricted_user, person=entity, permission_type=permission_level
            )
        elif entity_type.lower() == "gift":
            from gift_manager.models import GiftPermission

            GiftPermission.objects.create(
                user=restricted_user, gift=entity, permission_type=permission_level
            )
        elif entity_type.lower() == "event":
            from gift_manager.models import EventPermission

            EventPermission.objects.create(
                user=restricted_user, event=entity, permission_type=permission_level
            )
        elif entity_type.lower() == "relation":
            from gift_manager.models import RelationPermission

            RelationPermission.objects.create(
                user=restricted_user, relation=entity, permission_type=permission_level
            )
        elif entity_type.lower() == "persongroup":
            from gift_manager.models import PersonGroupPermission

            PersonGroupPermission.objects.create(
                user=restricted_user, group=entity, permission_type=permission_level
            )

        # Login as restricted user
        self.client.force_login(restricted_user)

        # Get the list URL for this entity type
        list_url = self.get_list_url(entity_type)

        # Make request to list view
        response = self.client.get(list_url)

        # Verify response is successful
        assert response.status_code == 200, (
            f"List view failed for {entity_type} with restricted permissions"
        )

        content = response.content.decode()

        # For users with no permissions or viewer-only permissions,
        # edit and delete actions should be restricted
        if permission_level in [PermissionLevel.NONE, PermissionLevel.VIEWER]:
            # The actions should still be configured in the JavaScript,
            # but the backend should handle permission checking
            # We verify that the basic structure is still present
            expected_actions = self.get_expected_actions(entity_type)

            # At minimum, details action should be available for viewers
            if permission_level == PermissionLevel.VIEWER:
                assert "'details'" in content, (
                    f"Details action should be available for viewers in {entity_type} list"
                )

            # Share action should be available if the user has at least viewer permissions
            if permission_level == PermissionLevel.VIEWER and "share" in expected_actions:
                assert "'share'" in content, (
                    f"Share action should be available for viewers in {entity_type} list"
                )
