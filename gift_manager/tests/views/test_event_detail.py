import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.views import EventDetailView


@pytest.mark.django_db
class TestEventDetail:
    """Tests for Event Detail view."""

    @pytest.fixture(autouse=True)
    def setup(self, client, user, event, person_relation):
        self.client = client
        self.client.force_login(user)
        self.user = user
        self.event = event
        # Ensure relation is linked to the event
        self.relation = person_relation
        self.relation.event = event
        self.relation.comment = "Test Relation Comment"
        self.relation.save()

        # Grant access
        create_or_update_permission(user, event, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.VIEWER)

    def test_actions_column_presence(self):
        """Test that the actions column data is present in the template."""
        url = reverse("gift_manager:event_detail", kwargs={"pk": self.event.event_id})

        # Use manual view instantiation to avoid 404 issues

        factory = RequestFactory()
        request = factory.get(url)
        request.user = self.user

        view = EventDetailView()
        view.request = request
        view.kwargs = {"pk": self.event.event_id}
        view.object = self.event

        context = view.get_context_data()
        content = render_to_string("gift_manager/event_detail.html", context, request=request)

        # Check for the presence of action URLs in the grid data
        # We expect to see relation_detail, relation_edit, relation_delete URLs
        detail_url = reverse(
            "gift_manager:relation_detail", kwargs={"pk": self.relation.relation_id}
        )
        edit_url = reverse("gift_manager:relation_edit", kwargs={"pk": self.relation.relation_id})
        delete_url = reverse(
            "gift_manager:relation_delete", kwargs={"pk": self.relation.relation_id}
        )

        assert detail_url in content
        assert edit_url in content
        assert delete_url in content

        # The modern detail page uses card actions instead of a Grid.js Actions column.
        assert "detail-page-shell" in content
        assert "relation-actions" in content

        # Check for the Comment column
        assert "Comment" in content
        # Check for the relation comment itself
        assert self.relation.comment in content
