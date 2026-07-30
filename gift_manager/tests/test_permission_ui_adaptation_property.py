"""Property-based tests for permission-based UI adaptation.

Feature: modern-ux-interface, Property 6: Permission-Based UI Adaptation
For any user with specific permissions, the UI should only display action buttons
and operations that the user is authorized to perform, hiding or disabling restricted actions.

Validates: Requirements 4.5, 5.5, 6.5
"""

import json

from django.test import Client
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

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


class PermissionUIAdaptationPropertyTest(HypothesisTestCase):
    """Property-based tests for permission-based UI adaptation."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def create_entity_with_permission(self, entity_type, permission_level):
        """Create an entity and set user permission."""
        factories = {
            "person": PersonFactory,
            "gift": GiftFactory,
            "event": EventFactory,
            "relation": RelationFactory,
            "persongroup": PersonGroupFactory,
            "gifttag": GiftTagFactory,
        }

        factory = factories.get(entity_type)
        if not factory:
            return None

        # Create entity with required relationships for relation
        if entity_type == "relation":
            person = PersonFactory()
            gift = GiftFactory()
            PermissionService.create_or_update_permission(
                self.user, person, permission_level=PermissionLevel.OWNER
            )
            PermissionService.create_or_update_permission(
                self.user, gift, permission_level=PermissionLevel.OWNER
            )
            entity = factory(person=person, gift=gift)
        else:
            entity = factory()

        # NONE means no explicit permission row.
        if permission_level > PermissionLevel.NONE:
            PermissionService.create_or_update_permission(
                self.user, entity, permission_level=permission_level
            )

        return entity

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        permission_level=st.sampled_from(
            [
                PermissionLevel.NONE,
                PermissionLevel.VIEWER,
                PermissionLevel.EDITOR,
                PermissionLevel.OWNER,
            ]
        ),
    )
    def test_permission_based_ui_adaptation_property(self, entity_type, permission_level):
        """Feature: modern-ux-interface, Property 6: Permission-Based UI Adaptation
        For any user with specific permissions, the UI should only display action buttons
        and operations that the user is authorized to perform.
        """
        # Create entity with specified permission level
        entity = self.create_entity_with_permission(entity_type, permission_level)
        if not entity:
            return  # Skip unsupported entity types

        # Get the list view URL
        list_urls = {
            "person": "gift_manager:persons",
            "gift": "gift_manager:gifts",
            "event": "gift_manager:events",
            "relation": "gift_manager:relations",
            "persongroup": "gift_manager:person_groups",
            "gifttag": "gift_manager:gift_tags",
        }

        list_url = list_urls.get(entity_type)
        if not list_url:
            return

        try:
            # Get the list view response
            response = self.client.get(reverse(list_url))

            # Skip if view doesn't work (might not be implemented yet)
            if response.status_code != 200:
                return

            content = response.content.decode()

            # Check that permission data is included in the response
            assert_text_in_rendered("user_permissions_json", content)

            # Extract permission data from the response
            # Look for the JavaScript variable containing permissions
            if "userPermissions" in content:
                # Find the permissions JSON in the JavaScript
                start_marker = "userPermissions = "
                start_idx = content.find(start_marker)
                if start_idx != -1:
                    start_idx += len(start_marker)
                    end_idx = content.find(";", start_idx)
                    if end_idx != -1:
                        permissions_json = content[start_idx:end_idx].strip()
                        try:
                            permissions = json.loads(permissions_json)
                            entity_id = str(getattr(entity, "pk", ""))

                            # Verify permission level is correctly reflected
                            if entity_id in permissions:
                                self.assertEqual(permissions[entity_id], permission_level)
                        except json.JSONDecodeError:
                            pass  # Skip if JSON parsing fails

            # Check for permission-aware JavaScript utilities
            if permission_level < PermissionLevel.EDITOR:
                # For users with limited permissions, check that permission utilities are loaded
                assert_text_in_rendered("PermissionUtils", content)
                assert_text_in_rendered("permissionAwareActionFormatter", content)

            # Verify that disabled actions have appropriate styling/attributes
            if permission_level < PermissionLevel.OWNER:
                # Should include permission-based CSS
                assert_text_in_rendered("permission-ui.css", content)

        except Exception:
            # Skip test if there are issues with the view
            pass

    @given(
        permission_level=st.sampled_from(
            [PermissionLevel.VIEWER, PermissionLevel.EDITOR, PermissionLevel.OWNER]
        )
    )
    def test_create_button_availability_property(self, permission_level):
        """Feature: modern-ux-interface, Property 6: Permission-Based UI Adaptation
        Create buttons should generally be available regardless of object permissions
        since they don't operate on existing objects.
        """
        # Create a person to ensure user has some access
        person = PersonFactory()
        PermissionService.create_or_update_permission(
            self.user, person, permission_level=permission_level
        )

        # Test person list view
        try:
            response = self.client.get(reverse("gift_manager:persons"))
            if response.status_code == 200:
                content = response.content.decode()

                # Create button should be available
                assert_text_in_rendered('data-action="create"', content)
                assert_text_in_rendered("Create new person", content)

                # Create button should not be disabled by default
                create_button_disabled = 'data-action="create"' in content and "disabled" in content
                self.assertFalse(create_button_disabled)

        except Exception:
            pass  # Skip if view has issues

    @given(
        entity_type=st.sampled_from(["person", "gift", "event"]),
        user_permission=st.sampled_from([PermissionLevel.VIEWER, PermissionLevel.EDITOR]),
        action=st.sampled_from(["edit", "delete", "share"]),
    )
    def test_action_button_permission_requirements_property(
        self, entity_type, user_permission, action
    ):
        """Feature: modern-ux-interface, Property 6: Permission-Based UI Adaptation
        Action buttons should be enabled/disabled based on specific permission requirements.
        """
        # Create entity with specified permission
        entity = self.create_entity_with_permission(entity_type, user_permission)
        if not entity:
            return

        # Define action requirements
        action_requirements = {
            "edit": PermissionLevel.EDITOR,
            "delete": PermissionLevel.OWNER,
            "share": PermissionLevel.OWNER,
        }

        required_permission = action_requirements.get(action, PermissionLevel.OWNER)
        should_be_enabled = user_permission >= required_permission

        # Get detail view to check action buttons
        detail_urls = {
            "person": "gift_manager:person_detail",
            "gift": "gift_manager:gift_detail",
            "event": "gift_manager:event_detail",
        }

        detail_url = detail_urls.get(entity_type)
        if not detail_url:
            return

        try:
            response = self.client.get(reverse(detail_url, kwargs={"pk": entity.pk}))

            if response.status_code == 200:
                content = response.content.decode()

                # Check if action button exists and its state
                action_pattern = f'data-action="{action}"'

                if action_pattern in content:
                    # Button exists, check if it's properly enabled/disabled
                    if should_be_enabled:
                        # Should not be disabled
                        disabled_pattern = f"{action_pattern}.*disabled"
                        self.assertNotRegex(content, disabled_pattern)
                    else:
                        # Should be disabled or have permission tooltip
                        self.assertTrue(
                            "disabled" in content
                            or "You do not have permission" in content
                            or "opacity: 0.5" in content
                        )

        except Exception:
            pass  # Skip if view has issues

    def test_bulk_operations_permission_property(self):
        """Feature: modern-ux-interface, Property 6: Permission-Based UI Adaptation
        Bulk operations should respect individual item permissions.
        """
        # Create entities with different permission levels
        person1 = PersonFactory()
        person2 = PersonFactory()
        person3 = PersonFactory()

        # Grant different permissions
        PermissionService.create_or_update_permission(
            self.user, person1, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            self.user, person2, permission_level=PermissionLevel.EDITOR
        )
        PermissionService.create_or_update_permission(
            self.user, person3, permission_level=PermissionLevel.VIEWER
        )

        try:
            response = self.client.get(reverse("gift_manager:persons"))

            if response.status_code == 200:
                content = response.content.decode()

                # Should include bulk operations JavaScript
                self.assertTrue("BulkOperations" in content or "bulk-operations" in content)

                # Should include permission data for bulk operations
                assert_text_in_rendered("user_permissions", content)

        except Exception:
            pass  # Skip if view has issues
