"""Property-based tests for bulk operations support."""

import json

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
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestBulkOperationsProperty:
    """Property-based tests for bulk operations support."""

    ENTITY_UUID_FIELDS = {
        "person": "person_id",
        "gift": "gift_id",
        "event": "event_id",
        "relation": "relation_id",
        "persongroup": "group_id",
        "gifttag": "tag_id",
    }

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def get_entity_id(self, entity_type, entity):
        """Return the public UUID field used by bulk-operation requests."""
        return str(getattr(entity, self.ENTITY_UUID_FIELDS[entity_type.lower()]))

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

    def test_bulk_delete_keeps_last_owner_on_shared_object(self):
        """Bulk delete must not remove the final owner permission."""
        viewer = UserFactory()
        gift = GiftFactory()
        PermissionService.create_or_update_permission(
            self.user, gift, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            viewer, gift, permission_level=PermissionLevel.VIEWER
        )

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_delete",
                    "entity_type": "gift",
                    "entity_ids": [str(gift.gift_id)],
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is False
        assert str(gift.gift_id) in response_data["permission_denied"]
        assert PermissionService.get_permission(gift, self.user) == PermissionLevel.OWNER
        assert PermissionService.get_permission(gift, viewer) == PermissionLevel.VIEWER

    def test_bulk_delete_allows_non_owner_to_remove_own_share(self):
        """Bulk delete can remove current user's non-owner access to a shared object."""
        owner = UserFactory()
        gift = GiftFactory()
        PermissionService.create_or_update_permission(
            owner, gift, permission_level=PermissionLevel.OWNER
        )
        PermissionService.create_or_update_permission(
            self.user, gift, permission_level=PermissionLevel.EDITOR
        )

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_delete",
                    "entity_type": "gift",
                    "entity_ids": [str(gift.gift_id)],
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is True
        assert str(gift.gift_id) in response_data["shared_removed"]
        assert PermissionService.get_permission(gift, self.user) == PermissionLevel.NONE
        assert PermissionService.get_permission(gift, owner) == PermissionLevel.OWNER

    def test_bulk_delete_preserves_person_with_implicit_user_link_owner(self):
        """Bulk delete must preserve persons owned only through user_link."""
        linked_owner = UserFactory()
        person = PersonFactory(user_link=linked_owner)
        PermissionService.create_or_update_permission(
            self.user, person, permission_level=PermissionLevel.EDITOR
        )

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_delete",
                    "entity_type": "person",
                    "entity_ids": [str(person.person_id)],
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is True
        assert str(person.person_id) in response_data["shared_removed"]
        person.refresh_from_db()
        assert person.user_link == linked_owner
        assert PermissionService.get_permission(person, self.user) == PermissionLevel.NONE

    def test_bulk_update_status_updates_editor_relations_by_public_id(self):
        """Bulk status updates should update editable gift plans by relation_id."""
        new_status = RelationStatusFactory(status="Purchased")
        relations = self.create_entities("relation", 2)
        relation_ids = [self.get_entity_id("relation", relation) for relation in relations]

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_update_status",
                    "entity_type": "relation",
                    "entity_ids": relation_ids,
                    "new_status": new_status.pk,
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is True
        assert set(response_data["updated"]) == set(relation_ids)

        for relation in relations:
            relation.refresh_from_db()
            assert relation.status == new_status

    def test_bulk_update_status_skips_reader_relations(self):
        """Reader-shared gift plans should remain unchanged during bulk status updates."""
        new_status = RelationStatusFactory(status="Given")
        relation = self.create_entities("relation", 1)[0]
        original_status = relation.status
        PermissionService.create_or_update_permission(
            self.user,
            relation,
            permission_level=PermissionLevel.VIEWER,
        )
        relation_id = self.get_entity_id("relation", relation)

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_update_status",
                    "entity_type": "relation",
                    "entity_ids": [relation_id],
                    "new_status": new_status.pk,
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is False
        assert response_data["updated"] == []
        assert response_data["permission_denied"] == [relation_id]
        assert "error" in response_data

        relation.refresh_from_db()
        assert relation.status == original_status

    def test_bulk_update_status_partially_updates_mixed_selection(self):
        """Bulk status updates should update editable rows and report skipped rows."""
        new_status = RelationStatusFactory(status="Given")
        editable_relation = self.create_entities("relation", 1)[0]
        viewer_relation = self.create_entities("relation", 1)[0]
        inaccessible_relation = RelationFactory()
        viewer_original_status = viewer_relation.status
        inaccessible_original_status = inaccessible_relation.status
        PermissionService.create_or_update_permission(
            self.user,
            viewer_relation,
            permission_level=PermissionLevel.VIEWER,
        )

        editable_id = self.get_entity_id("relation", editable_relation)
        viewer_id = self.get_entity_id("relation", viewer_relation)
        inaccessible_id = self.get_entity_id("relation", inaccessible_relation)

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_update_status",
                    "entity_type": "relation",
                    "entity_ids": [editable_id, viewer_id, inaccessible_id],
                    "new_status": new_status.pk,
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 200
        assert response_data["success"] is True
        assert response_data["updated"] == [editable_id]
        assert response_data["permission_denied"] == [viewer_id]
        assert response_data["failed"][0]["id"] == inaccessible_id

        editable_relation.refresh_from_db()
        viewer_relation.refresh_from_db()
        inaccessible_relation.refresh_from_db()
        assert editable_relation.status == new_status
        assert viewer_relation.status == viewer_original_status
        assert inaccessible_relation.status == inaccessible_original_status

    def test_bulk_update_status_rejects_invalid_status(self):
        """Bulk status updates should reject missing or invalid statuses."""
        relation = self.create_entities("relation", 1)[0]

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_update_status",
                    "entity_type": "relation",
                    "entity_ids": [self.get_entity_id("relation", relation)],
                    "new_status": "not-a-status",
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 400
        assert response_data["success"] is False
        assert "error" in response_data

    def test_bulk_update_status_rejects_non_relation_entities(self):
        """Bulk status updates should be limited to gift plans."""
        person = PersonFactory()
        new_status = RelationStatusFactory(status="Given")
        PermissionService.create_or_update_permission(
            self.user,
            person,
            permission_level=PermissionLevel.EDITOR,
        )

        response = self.client.post(
            reverse("gift_manager:bulk_operations"),
            data=json.dumps(
                {
                    "action": "bulk_update_status",
                    "entity_type": "person",
                    "entity_ids": [self.get_entity_id("person", person)],
                    "new_status": new_status.pk,
                }
            ),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        response_data = json.loads(response.content)
        assert response.status_code == 400
        assert response_data["success"] is False
        assert "error" in response_data

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_count=st.integers(min_value=2, max_value=5),
    )
    def test_bulk_operations_support_property(self, entity_type, entity_count):
        """Feature: modern-ux-interface, Property 9: Bulk Operations Support

        For any entity list with multiple items selected, the system should provide
        bulk operation capabilities with appropriate confirmation dialogs and progress feedback.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        # Create test entities
        entities = self.create_entities(entity_type, entity_count)
        if not entities:
            pytest.skip(f"Could not create entities for type: {entity_type}")

        entity_ids = [self.get_entity_id(entity_type, entity) for entity in entities]

        # Property 9.1: Bulk delete confirmation should be available
        confirmation_url = reverse("gift_manager:bulk_delete_confirmation")
        confirmation_response = self.client.get(
            confirmation_url,
            {"entity_type": entity_type, "entity_ids": ",".join(entity_ids)},
            HTTP_HX_REQUEST="true",
        )

        assert confirmation_response.status_code == 200, (
            f"Bulk delete confirmation should be available for {entity_type}"
        )

        confirmation_content = confirmation_response.content.decode()
        assert "modal-header" in confirmation_content, "Confirmation should display as modal"
        assert "Confirm Bulk Delete" in confirmation_content, (
            "Confirmation should have appropriate title"
        )
        assert str(entity_count) in confirmation_content, (
            "Confirmation should show correct count of items"
        )

        # Property 9.2: Bulk delete operation should be available
        bulk_operations_url = reverse("gift_manager:bulk_operations")
        bulk_delete_data = {
            "action": "bulk_delete",
            "entity_type": entity_type,
            "entity_ids": entity_ids,
        }

        bulk_response = self.client.post(
            bulk_operations_url,
            data=json.dumps(bulk_delete_data),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert bulk_response.status_code == 200, (
            f"Bulk delete should be available for {entity_type}"
        )

        response_data = json.loads(bulk_response.content)
        assert response_data.get("success") is True, (
            f"Bulk delete should succeed: {response_data.get('error', 'Unknown error')}"
        )

        # Property 9.3: Results should provide appropriate feedback
        assert "deleted" in response_data or "shared_removed" in response_data, (
            "Bulk delete should provide feedback about processed items"
        )

        deleted_count = len(response_data.get("deleted", []))
        shared_removed_count = len(response_data.get("shared_removed", []))
        total_processed = deleted_count + shared_removed_count

        assert total_processed > 0, "Bulk delete should process at least some items"
        assert total_processed <= entity_count, (
            "Bulk delete should not process more items than selected"
        )

        # Property 9.4: Success message should be provided
        assert "message" in response_data, "Bulk delete should provide success message"
        assert len(response_data["message"]) > 0, "Success message should not be empty"

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        entity_count=st.integers(min_value=1, max_value=3),
    )
    def test_bulk_share_support_property(self, entity_type, entity_count):
        """Feature: modern-ux-interface, Property 9: Bulk Operations Support (Share)

        For any entity list with multiple items selected, the system should provide
        bulk share operation capabilities.

        **Validates: Requirements 6.1, 6.2**
        """
        # Create test entities
        entities = self.create_entities(entity_type, entity_count)
        if not entities:
            pytest.skip(f"Could not create entities for type: {entity_type}")

        entity_ids = [self.get_entity_id(entity_type, entity) for entity in entities]

        # Property 9: Bulk share operation should be available
        bulk_operations_url = reverse("gift_manager:bulk_operations")
        bulk_share_data = {
            "action": "bulk_share",
            "entity_type": entity_type,
            "entity_ids": entity_ids,
        }

        bulk_response = self.client.post(
            bulk_operations_url,
            data=json.dumps(bulk_share_data),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert bulk_response.status_code == 200, f"Bulk share should be available for {entity_type}"

        response_data = json.loads(bulk_response.content)
        assert response_data.get("success") is True, (
            f"Bulk share should succeed: {response_data.get('error', 'Unknown error')}"
        )

        # Property 9: Should provide redirect URL for share page
        assert "redirect_url" in response_data, "Bulk share should provide redirect URL"

        redirect_url = response_data["redirect_url"]
        assert "/share/" in redirect_url, "Redirect URL should point to share page"
        assert entity_type in redirect_url, "Redirect URL should include entity type"
        assert all(entity_id in redirect_url for entity_id in entity_ids), (
            "Redirect URL should include all selected entity IDs"
        )

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        ),
        permission_level=st.sampled_from([PermissionLevel.NONE, PermissionLevel.VIEWER]),
    )
    def test_bulk_operations_permission_property(self, entity_type, permission_level):
        """Feature: modern-ux-interface, Property 9: Bulk Operations Support (Permissions)

        For any entity list, bulk operations should respect user permissions.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        # Create test entities with limited permissions
        entities = self.create_entities(entity_type, 2)
        if not entities:
            pytest.skip(f"Could not create entities for type: {entity_type}")

        # Set limited permissions
        for entity in entities:
            if permission_level == PermissionLevel.NONE:
                PermissionService.delete_permission(self.user, entity)
            else:
                PermissionService.create_or_update_permission(
                    self.user, entity, permission_level=permission_level
                )

        entity_ids = [self.get_entity_id(entity_type, entity) for entity in entities]

        # Property 9: Bulk operations should respect permissions
        bulk_operations_url = reverse("gift_manager:bulk_operations")
        bulk_delete_data = {
            "action": "bulk_delete",
            "entity_type": entity_type,
            "entity_ids": entity_ids,
        }

        bulk_response = self.client.post(
            bulk_operations_url,
            data=json.dumps(bulk_delete_data),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        if permission_level < PermissionLevel.EDITOR:
            # Should fail or return empty results for insufficient permissions
            response_data = json.loads(bulk_response.content)

            # Either the operation fails entirely or no items are processed
            if response_data.get("success"):
                deleted_count = len(response_data.get("deleted", []))
                shared_removed_count = len(response_data.get("shared_removed", []))
                total_processed = deleted_count + shared_removed_count

                assert total_processed == 0, (
                    "Bulk operations should not process items without proper permissions"
                )
            else:
                assert "error" in response_data, (
                    "Failed bulk operation should provide error message"
                )

    @given(
        invalid_action=st.text().filter(
            lambda x: x not in ["bulk_delete", "bulk_share", "bulk_update_status"]
        )
    )
    def test_bulk_operations_invalid_action_property(self, invalid_action):
        """Feature: modern-ux-interface, Property 9: Bulk Operations Support (Error Handling)

        For any invalid bulk operation action, the system should provide appropriate error handling.

        **Validates: Requirements 6.3, 6.4**
        """
        # Create a test entity
        entities = self.create_entities("person", 1)
        entity_ids = [self.get_entity_id("person", entities[0])]

        # Property 9: Invalid actions should be handled gracefully
        bulk_operations_url = reverse("gift_manager:bulk_operations")
        invalid_data = {"action": invalid_action, "entity_type": "person", "entity_ids": entity_ids}

        bulk_response = self.client.post(
            bulk_operations_url,
            data=json.dumps(invalid_data),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        # Should return error response
        assert bulk_response.status_code == 400, "Invalid bulk action should return 400 status"

        response_data = json.loads(bulk_response.content)
        assert response_data.get("success") is False, "Invalid bulk action should not succeed"
        assert "error" in response_data, "Invalid bulk action should provide error message"
        assert len(response_data["error"]) > 0, "Error message should not be empty"

    @given(
        entity_type=st.sampled_from(
            ["person", "gift", "event", "relation", "persongroup", "gifttag"]
        )
    )
    def test_bulk_operations_empty_selection_property(self, entity_type):
        """Feature: modern-ux-interface, Property 9: Bulk Operations Support (Empty Selection)

        For any bulk operation with empty selection, the system should handle it gracefully.

        **Validates: Requirements 6.1, 6.2**
        """
        # Property 9: Empty selection should be handled gracefully
        bulk_operations_url = reverse("gift_manager:bulk_operations")
        empty_data = {"action": "bulk_delete", "entity_type": entity_type, "entity_ids": []}

        bulk_response = self.client.post(
            bulk_operations_url,
            data=json.dumps(empty_data),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        # Should return error response for empty selection
        assert bulk_response.status_code == 400, "Empty selection should return 400 status"

        response_data = json.loads(bulk_response.content)
        assert response_data.get("success") is False, "Empty selection should not succeed"
        assert "error" in response_data, "Empty selection should provide error message"
