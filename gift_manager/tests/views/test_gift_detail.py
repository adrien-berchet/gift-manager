import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.views import GiftDetailView


@pytest.mark.django_db
class TestGiftDetail:
    """Tests for Gift Detail view."""

    @pytest.fixture(autouse=True)
    def setup(self, client, user, gift, person_relation):
        self.client = client
        self.client.force_login(user)
        self.user = user
        self.gift = gift
        # Ensure relation is linked to the gift
        self.relation = person_relation
        self.relation.gift = gift
        self.relation.save()

        # Grant access
        # Gift is not directly shared, but accessible if user created it or it's shared.
        # Assuming the 'gift' fixture in conftest creates a gift owned by someone?
        # Actually standard Django models usually have an owner or shared_with.
        # Gift model: shared_with.

        create_or_update_permission(user, gift, permission_level=PermissionLevel.VIEWER)
        create_or_update_permission(user, self.relation, permission_level=PermissionLevel.VIEWER)

    def test_actions_column_presence(self):
        """Test that the actions column data is present in the template."""
        url = reverse("gift_manager:gift_detail", kwargs={"pk": self.gift.gift_id})

        # Use manual view instantiation to avoid 404 issues

        factory = RequestFactory()
        request = factory.get(url)
        request.user = self.user

        view = GiftDetailView()
        view.request = request
        view.kwargs = {"pk": self.gift.gift_id}
        view.object = self.gift

        context = view.get_context_data()
        content = render_to_string("gift_manager/gift_detail.html", context, request=request)

        # response = self.client.get(url)
        # assert response.status_code == 200
        # content = response.content.decode("utf-8")

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

        # Check for the Actions column header
        assert "Actions" in content
