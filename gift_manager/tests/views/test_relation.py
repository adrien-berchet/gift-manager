import json
import uuid

import pytest
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission


@pytest.mark.django_db
class TestUpdateRelationStatus:
    """Tests for update_relation_status view."""

    @pytest.fixture(autouse=True)
    def setup(self, user, person_relation):
        """Setup test fixtures."""
        self.user = user
        self.client = Client()
        self.client.force_login(user)

        # Create a test status
        self.new_status = RelationStatus.objects.create(status="Testing")

        # Create a test relation
        self.relation = person_relation
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.OWNER)

    @override_settings(USE_I18N=False)
    def test_update_relation_status_success(self):
        """Test updating a relation status successfully via HTMX."""
        url = reverse("gift_manager:relation_status_update")
        data = {
            "relation_id": self.relation.relation_id,
            "new_status": self.new_status.pk,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 200
        # The response is HTML (HTMX partial), not JSON
        content = response.content.decode("utf-8")
        assert "status-form-" in content
        assert "gift-plan-status-form" in content
        assert "gift-plan-status-select gift-plan-status--testing" in content
        assert f'value="{self.new_status.pk}"' in content
        assert f'data-current-value="{self.new_status.pk}"' in content
        assert "selected" in content

        # Check database
        self.relation.refresh_from_db()
        assert self.relation.status == self.new_status

    @override_settings(USE_I18N=False)
    def test_update_relation_status_not_found(self):
        """Test updating a non-existent relation status."""
        import json

        url = reverse("gift_manager:relation_status_update")
        fake_uuid = str(uuid.uuid4())
        data = {
            "relation_id": fake_uuid,
            "new_status": self.new_status.pk,
        }

        # Act
        response = self.client.post(url, data)

        # Assert
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert "error" in response_data

    @override_settings(USE_I18N=False)
    def test_update_relation_status_requires_edit_permission(self):
        """Viewers can see a gift plan but cannot update its status."""
        create_or_update_permission(
            self.user,
            self.relation,
            permission_level=PermissionLevel.VIEWER,
        )

        response = self.client.post(
            reverse("gift_manager:relation_status_update"),
            {
                "relation_id": self.relation.relation_id,
                "new_status": self.new_status.pk,
            },
        )

        assert response.status_code == 403
        self.relation.refresh_from_db()
        assert self.relation.status != self.new_status


@pytest.mark.django_db
class TestRelationUpdateView:
    """Tests for editing gift plans."""

    @pytest.fixture(autouse=True)
    def setup(self, client, user, person_relation):
        self.client = client
        self.client.force_login(user)
        self.user = user
        self.relation = person_relation
        self.new_status = RelationStatus.objects.create(status="Planned")

        create_or_update_permission(
            user, self.relation.person, permission_level=PermissionLevel.OWNER
        )
        create_or_update_permission(
            user, self.relation.gift, permission_level=PermissionLevel.OWNER
        )
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.OWNER)

    @override_settings(USE_I18N=False)
    def test_htmx_relation_edit_closes_panel_and_refreshes_cards(self):
        """Successful offcanvas saves should close the panel and refresh live card lists."""
        response = self.client.post(
            reverse("gift_manager:relation_edit", kwargs={"pk": self.relation.relation_id}),
            {
                "recipient": self.relation.recipient_key,
                "gift": self.relation.gift.pk,
                "comment": "Updated from the edit panel",
                "event": "",
                "status": self.new_status.pk,
                "due_date": "2026-08-15",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert response["HX-Reswap"] == "none"
        triggers = json.loads(response["HX-Trigger"])
        assert "list:update" in triggers
        assert "offcanvas:close" in triggers
        assert triggers["showNotification"]["type"] == "success"

        self.relation.refresh_from_db()
        assert self.relation.comment == "Updated from the edit panel"
        assert self.relation.status == self.new_status
