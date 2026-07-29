from datetime import timedelta

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.views import RelationListView


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
        """Test that the comment column data is present in the template."""
        url = reverse("gift_manager:relations")

        factory = RequestFactory()
        request = factory.get(url)
        request.user = self.user

        view = RelationListView()
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

    def test_workspace_cards_render_with_advanced_grid_kept(self, event_factory, gift_tag_factory):
        """The gift-plan list opens on planning cards while preserving Grid.js mode."""
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
        assert 'id="gift-plan-advanced-list"' in content
        assert 'id="relation-grid"' in content

    def test_advanced_grid_status_controls_are_permission_aware(self):
        """The retained Grid.js status control should not invite viewer-only edits."""
        response = self.client.get(reverse("gift_manager:relations"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "const canEditStatus = permission >= editorPermission" in content
        assert 'disabled title="${statusReadonlyMessage}"' in content
        assert 'data-current-value="${statusPk}"' in content
        assert "{ columnSelector: 'th:nth-child(6)' },  // Status" in content
        assert "{ columnSelector: 'th:nth-child(3)', shift: true },  // Recipient" in content
        assert "{ columnSelector: 'th:nth-child(2)', shift: true }  // Gift" in content

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
        assert "gift-plan-card--no_date" not in content

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
