from datetime import timedelta

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.views import RelationAdvancedListView


@pytest.mark.django_db
class TestRelationList:
    """Tests for Relation List view."""

    @pytest.fixture(autouse=True)
    def setup(self, client, user, person_relation):
        self.client = client
        self.client.force_login(user)
        self.user = user
        self.relation = person_relation
        self.relation.comment = "Unique Comment for Testing"
        self.relation.save()

        # Grant access
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.VIEWER)

    def test_comment_column_presence(self):
        """Test that the comment column data is present in the advanced list template."""
        url = reverse("gift_manager:relation_advanced_list")

        factory = RequestFactory()
        request = factory.get(url)
        request.user = self.user

        view = RelationAdvancedListView()
        view.request = request
        view.kwargs = {}

        # We need to set the object list for the view context manually if we bypass setup() of
        # generic view
        # But BaseListView should handle get_queryset in get_context_data if structured correctly?
        # Actually BaseListView usually puts object_list in context.
        # Let's call get(request) to get full response or render manually.
        # Since we want to check rendered string (including JS loop), manual render is safer
        # to inspect context + template logic.

        view.object_list = view.get_queryset()
        context = view.get_context_data(object_list=view.object_list)
        content = render_to_string("gift_manager/relation_list.html", context, request=request)

        # Check for the Comment column header
        assert "Comment" in content

        # Check for the relation comment itself
        assert "Unique Comment for Testing" in content

    def test_workspace_cards_render_without_advanced_grid(self, event_factory, gift_tag_factory):
        """The gift-plan list opens on planning cards without the advanced Grid.js mode."""
        create_or_update_permission(
            self.user,
            self.relation,
            permission_level=PermissionLevel.EDITOR,
        )
        event = event_factory(name="Birthday")
        tag = gift_tag_factory(name="Books")
        self.relation.event = event
        self.relation.due_date = timezone.localdate() - timedelta(days=1)
        self.relation.gift.tags.add(tag)
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="gift-plan-workspace"' in content
        assert "gift-plan-urgency-section--overdue" in content
        assert "gift-plan-card--overdue" in content
        assert "gift-plan-status-badge gift-plan-status--idea" in content
        assert "gift-plan-due-badge gift-plan-due-badge--overdue" in content
        assert self.relation.gift.name in content
        assert self.relation.recipient_name in content
        assert "Birthday" in content
        assert "Books" in content
        assert "Unique Comment for Testing" in content
        assert 'data-action="detail"' in content
        assert 'data-action="edit"' in content
        assert "/relations/advanced/" in content
        assert "Advanced List" in content
        assert 'id="gift-plan-advanced-list"' not in content
        assert 'id="relation-grid"' not in content

    def test_advanced_grid_status_controls_are_permission_aware(self):
        """The retained Grid.js status control should not invite viewer-only edits."""
        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="gift-plan-workspace"' not in content
        assert 'id="gift-plan-advanced-list"' in content
        assert 'id="relation-grid"' in content
        assert "Advanced Gift Plans List" in content
        assert "/relations/" in content
        assert "Workspace" in content
        assert "const canEditStatus = permission >= editorPermission" in content
        assert 'disabled title="${statusReadonlyMessage}"' in content
        assert 'data-current-value="${statusPk}"' in content
        assert "inline-edit:success" in content
        assert "event.detail?.fieldName === 'due_date'" in content
        assert "{ columnSelector: 'th:nth-child(6)' },  // Status" in content
        assert "{ columnSelector: 'th:nth-child(3)', shift: true },  // Recipient" in content
        assert "{ columnSelector: 'th:nth-child(2)', shift: true }  // Gift" in content

    def test_advanced_grid_marks_overdue_rows_as_needing_attention(self):
        """The advanced list exposes row metadata for overdue attention styling."""
        self.relation.due_date = timezone.localdate() - timedelta(days=1)
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        content = response.content.decode()
        assert row["urgency_key"] == "overdue"
        assert row["needs_attention"] is True
        assert row["attention_label"] == "Overdue"
        assert 'urgencyKey: "overdue"' in content
        assert "needsAttention: true" in content
        assert "data-grid-row-state" in content
        assert "rowStateMarkers" in content

    def test_advanced_grid_does_not_mark_open_ideas_without_due_date(self):
        """Open-ended ideas without due dates should stay unmarked in the advanced list."""
        idea_status = self.relation.status.__class__.objects.get(status_en="Idea")
        self.relation.status = idea_status
        self.relation.due_date = None
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        content = response.content.decode()
        assert row["urgency_key"] == "ideas"
        assert row["needs_attention"] is False
        assert row["attention_label"] == ""
        assert row["has_missing_data"] is False
        assert row["missing_data_label"] == ""
        assert row["has_missing_due_date"] is False
        assert row["missing_due_date_label"] == ""
        assert row["has_missing_event"] is False
        assert row["missing_event_label"] == ""
        assert 'urgencyKey: "ideas"' in content
        assert "needsAttention: false" in content
        assert "missingData: false" in content

    def test_workspace_separates_open_ideas_from_needs_details(self, event_factory, gift_factory):
        """Open-ended ideas should not appear in the actionable details bucket."""
        planned_status, _ = self.relation.status.__class__.objects.get_or_create(status="Planned")
        self.relation.status = self.relation.status.__class__.objects.get(status_en="Idea")
        self.relation.due_date = None
        self.relation.event = None
        self.relation.save()

        planned_relation = self.relation.__class__.objects.create(
            person=self.relation.person,
            gift=gift_factory(name="Deadline Needed Gift"),
            event=event_factory(name="Birthday"),
            status=planned_status,
            due_date=None,
        )
        create_or_update_permission(
            self.user,
            planned_relation,
            permission_level=PermissionLevel.VIEWER,
        )

        response = self.client.get(reverse("gift_manager:relations"))

        assert response.status_code == 200
        groups_by_key = {group["key"]: group for group in response.context["workspace_groups"]}
        assert self.relation in [card["relation"] for card in groups_by_key["ideas"]["cards"]]
        assert planned_relation in [
            card["relation"] for card in groups_by_key["needs_details"]["cards"]
        ]
        assert response.context["workspace_summary"]["needs_details"] == 1
        assert response.context["workspace_summary"]["ideas"] == 1
        content = response.content.decode()
        assert "gift-plan-urgency-section--ideas" in content
        assert "gift-plan-urgency-section--needs_details" in content
        assert "Deadline Needed Gift" in content

    def test_advanced_grid_marks_planned_rows_without_due_date_as_missing_data(self, event_factory):
        """Active gift plans without due dates should show missing-data metadata."""
        planned_status, _ = self.relation.status.__class__.objects.get_or_create(status="Planned")
        self.relation.status = planned_status
        self.relation.due_date = None
        self.relation.event = event_factory()
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        content = response.content.decode()
        assert row["urgency_key"] == "needs_details"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is True
        assert row["missing_data_label"] == "Missing due date"
        assert row["has_missing_due_date"] is True
        assert row["missing_due_date_label"] == "Missing due date"
        assert row["has_missing_event"] is False
        assert row["missing_event_label"] == ""
        assert "missingData: true" in content
        assert 'missingDataLabel: "Missing due date"' in content
        assert "missingDueDate: true" in content
        assert "missingEvent: false" in content
        assert "gift-plan-missing-data-badge" in content
        assert "fa-triangle-exclamation" in content

    def test_advanced_grid_marks_purchased_rows_without_due_date_as_missing_data(
        self, event_factory
    ):
        """Purchased gift plans should still expose missing due-date data."""
        purchased_status, _ = self.relation.status.__class__.objects.get_or_create(
            status="Purchased"
        )
        self.relation.status = purchased_status
        self.relation.due_date = None
        self.relation.event = event_factory()
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        assert row["urgency_key"] == "needs_details"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is True
        assert row["has_missing_due_date"] is True
        assert row["has_missing_event"] is False
        assert row["missing_due_date_label"] == "Missing due date"
        assert row["missing_event_label"] == ""

    def test_advanced_grid_marks_active_rows_with_due_date_and_event_missing_data(self):
        """Rows missing both due date and event should expose both column warnings."""
        planned_status, _ = self.relation.status.__class__.objects.get_or_create(status="Planned")
        self.relation.status = planned_status
        self.relation.due_date = None
        self.relation.event = None
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        content = response.content.decode()
        assert row["urgency_key"] == "needs_details"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is True
        assert row["missing_data_label"] == "Missing due date, Missing event"
        assert row["has_missing_due_date"] is True
        assert row["missing_due_date_label"] == "Missing due date"
        assert row["has_missing_event"] is True
        assert row["missing_event_label"] == "Missing event"
        assert "missingDueDate: true" in content
        assert "missingEvent: true" in content
        assert 'missingEventLabel: "Missing event"' in content

    def test_advanced_grid_marks_planned_rows_without_event_as_missing_data(self):
        """Active gift plans with due dates should still show missing event data."""
        planned_status, _ = self.relation.status.__class__.objects.get_or_create(status="Planned")
        self.relation.status = planned_status
        self.relation.due_date = timezone.localdate() + timedelta(days=20)
        self.relation.event = None
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        content = response.content.decode()
        assert row["urgency_key"] == "needs_details"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is True
        assert row["missing_data_label"] == "Missing event"
        assert row["has_missing_due_date"] is False
        assert row["missing_due_date_label"] == ""
        assert row["has_missing_event"] is True
        assert row["missing_event_label"] == "Missing event"
        assert "missingDueDate: false" in content
        assert "missingEvent: true" in content
        assert 'missingEventLabel: "Missing event"' in content

    def test_advanced_grid_does_not_mark_terminal_rows_without_due_date(self):
        """Terminal gift plans should not ask for a due date."""
        given_status, _ = self.relation.status.__class__.objects.get_or_create(status="Given")
        self.relation.status = given_status
        self.relation.due_date = None
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        assert row["urgency_key"] == "completed"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is False
        assert row["missing_data_label"] == ""
        assert row["has_missing_due_date"] is False
        assert row["has_missing_event"] is False

    def test_advanced_grid_does_not_mark_active_rows_with_due_date_and_event_as_missing_data(
        self, event_factory
    ):
        """Active gift plans with due date and event should not show a missing-data warning."""
        planned_status, _ = self.relation.status.__class__.objects.get_or_create(status="Planned")
        self.relation.status = planned_status
        self.relation.due_date = timezone.localdate() + timedelta(days=20)
        self.relation.event = event_factory()
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relation_advanced_list"))

        assert response.status_code == 200
        row = response.context["data"][0]
        assert row["urgency_key"] == "later"
        assert row["needs_attention"] is False
        assert row["has_missing_data"] is False
        assert row["missing_data_label"] == ""
        assert row["has_missing_due_date"] is False
        assert row["has_missing_event"] is False

    def test_completed_workspace_group_wins_over_overdue_due_date(self):
        """Completed statuses should not stay in the attention bucket."""
        completed_status = self.relation.status.__class__.objects.create(status="Given")
        self.relation.status = completed_status
        self.relation.due_date = timezone.localdate() - timedelta(days=3)
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relations"))

        assert response.status_code == 200
        workspace_groups = response.context["workspace_groups"]
        assert [group["key"] for group in workspace_groups] == ["completed"]
        content = response.content.decode()
        assert "gift-plan-urgency-section--completed" in content
        assert "gift-plan-card--completed" in content

    def test_abandoned_workspace_group_wins_over_missing_due_date(self):
        """Abandoned ideas should stay visible without requiring attention."""
        abandoned_status = self.relation.status.__class__.objects.get(status_en="Abandoned")
        self.relation.status = abandoned_status
        self.relation.due_date = None
        self.relation.save()

        response = self.client.get(reverse("gift_manager:relations"))

        assert response.status_code == 200
        workspace_groups = response.context["workspace_groups"]
        assert [group["key"] for group in workspace_groups] == ["completed"]
        content = response.content.decode()
        assert "gift-plan-urgency-section--completed" in content
        assert "gift-plan-card--completed" in content
        assert "gift-plan-card--needs_details" not in content

    def test_detail_panel_uses_shared_status_and_due_badges(self):
        """Quick details should match the workspace card visual language."""
        self.relation.due_date = timezone.localdate() + timedelta(days=2)
        self.relation.save()

        response = self.client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": self.relation.relation_id}),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "gift-plan-status-badge gift-plan-status--idea" in content
        assert "gift-plan-due-badge gift-plan-due-badge--due_soon" in content
        assert 'data-action="edit"' not in content
        assert 'data-action="delete"' not in content
        assert "You do not have permission to edit this object" in content
