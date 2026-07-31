import json
import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.statuses import relation_status_slug


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
class TestRelationQuickAction:
    """Tests for gift-plan card quick actions."""

    @pytest.fixture(autouse=True)
    def setup(self, user, person_relation, event_factory):
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        self.relation = person_relation
        self.relation.event = event_factory()
        self.relation.due_date = timezone.localdate() + timedelta(days=2)
        self.relation.status = RelationStatus.objects.get_or_create(status="Planned")[0]
        self.relation.save()

        for status in ("Purchased", "Given", "Abandoned"):
            RelationStatus.objects.get_or_create(status=status)

        create_or_update_permission(
            user,
            self.relation,
            permission_level=PermissionLevel.EDITOR,
        )

    def make_relation_idea(self):
        idea_status = RelationStatus.objects.get_or_create(status="Idea")[0]
        self.relation.status = idea_status
        self.relation.event = None
        self.relation.due_date = None
        self.relation.save(update_fields=["status", "event", "due_date"])

    @override_settings(USE_I18N=False)
    def test_status_quick_action_updates_relation_and_refreshes_cards(self):
        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {"action": "given"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert response["HX-Reswap"] == "none"
        triggers = json.loads(response["HX-Trigger"])
        assert "list:update" in triggers
        assert triggers["showNotification"]["type"] == "success"

        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "given"

    @override_settings(USE_I18N=False)
    def test_set_date_quick_action_updates_due_date(self):
        self.relation.due_date = None
        self.relation.save(update_fields=["due_date"])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {"action": "set_date", "due_date": "2026-08-15"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert "list:update" in json.loads(response["HX-Trigger"])

        self.relation.refresh_from_db()
        assert self.relation.due_date.isoformat() == "2026-08-15"

    @override_settings(USE_I18N=False)
    def test_plan_quick_action_sets_status_event_and_due_date(self, event_factory):
        self.make_relation_idea()
        event = event_factory(shared_with=[self.user])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {
                "action": "plan",
                "event": str(event.event_id),
                "due_date": "2026-08-15",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert "list:update" in json.loads(response["HX-Trigger"])

        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "planned"
        assert self.relation.event == event
        assert self.relation.due_date.isoformat() == "2026-08-15"

    def test_plan_quick_action_rejects_inaccessible_event(self, event_factory):
        self.make_relation_idea()
        private_event = event_factory()

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {
                "action": "plan",
                "event": str(private_event.event_id),
                "due_date": "2026-08-15",
            },
        )

        assert response.status_code == 400
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "idea"
        assert self.relation.event is None
        assert self.relation.due_date is None

    def test_plan_quick_action_rejects_missing_due_date(self, event_factory):
        self.make_relation_idea()
        event = event_factory(shared_with=[self.user])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {
                "action": "plan",
                "event": str(event.event_id),
                "due_date": "",
            },
        )

        assert response.status_code == 400
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "idea"
        assert self.relation.event is None
        assert self.relation.due_date is None

    def test_plan_quick_action_requires_edit_permission(self, event_factory):
        self.make_relation_idea()
        event = event_factory(shared_with=[self.user])
        create_or_update_permission(
            self.user,
            self.relation,
            permission_level=PermissionLevel.VIEWER,
        )

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {
                "action": "plan",
                "event": str(event.event_id),
                "due_date": "2026-08-15",
            },
        )

        assert response.status_code == 403
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "idea"

    def test_plan_quick_action_rejects_non_idea_relation(self, event_factory):
        self.relation.due_date = None
        self.relation.event = None
        self.relation.save(update_fields=["due_date", "event"])
        event = event_factory(shared_with=[self.user])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {
                "action": "plan",
                "event": str(event.event_id),
                "due_date": "2026-08-15",
            },
        )

        assert response.status_code == 400
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "planned"
        assert self.relation.event is None
        assert self.relation.due_date is None

    def test_set_date_quick_action_requires_csrf_token_in_middleware_flow(self):
        self.relation.due_date = None
        self.relation.save(update_fields=["due_date"])

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )

        response = csrf_client.post(
            url,
            {"action": "set_date", "due_date": "2026-08-15"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        self.relation.refresh_from_db()
        assert self.relation.due_date is None

        csrf_client.cookies[settings.CSRF_COOKIE_NAME] = "a" * 32
        response = csrf_client.post(
            url,
            {"action": "set_date", "due_date": "2026-08-15"},
            HTTP_HX_REQUEST="true",
            HTTP_X_CSRFTOKEN="a" * 32,
        )

        assert response.status_code == 200
        self.relation.refresh_from_db()
        assert self.relation.due_date.isoformat() == "2026-08-15"

    def test_quick_action_rejects_unavailable_action(self):
        self.relation.due_date = None
        self.relation.save(update_fields=["due_date"])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {"action": "purchased"},
        )

        assert response.status_code == 400
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "planned"

    def test_quick_action_requires_edit_permission(self):
        create_or_update_permission(
            self.user,
            self.relation,
            permission_level=PermissionLevel.VIEWER,
        )

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {"action": "given"},
        )

        assert response.status_code == 403
        self.relation.refresh_from_db()
        assert relation_status_slug(self.relation.status) == "planned"

    def test_quick_action_rejects_invalid_date(self):
        self.relation.due_date = None
        self.relation.save(update_fields=["due_date"])

        url = reverse(
            "gift_manager:relation_quick_action", kwargs={"pk": self.relation.relation_id}
        )
        response = self.client.post(
            url,
            {"action": "set_date", "due_date": "not-a-date"},
        )

        assert response.status_code == 400


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
