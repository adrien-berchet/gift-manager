import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

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
