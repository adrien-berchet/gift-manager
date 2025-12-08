import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.models import GiftTag

@pytest.mark.django_db
class TestGiftTagDetail:
    """Tests for GiftTag Detail view."""

    @pytest.fixture
    def other_user(self):
        return User.objects.create_user(username="other", password="password", email="other@example.com")

    def test_mro(self):
        from gift_manager.views import GiftTagDetailView
        print(f"MRO: {GiftTagDetailView.mro()}")

    def test_gift_tag_detail_shared_users(self, client, user, other_user, gift_tag):
        """Test accessing gift tag detail when shared with other users."""

        # Share with current user (so they can access it)
        create_or_update_permission(user, gift_tag, permission_level=PermissionLevel.EDITOR)

        # Share with other user (to trigger the loop in SharedUsersMixin)
        create_or_update_permission(other_user, gift_tag, permission_level=PermissionLevel.VIEWER)

        client.force_login(user)
        url = reverse("gift_manager:gift_tag_detail", kwargs={"pk": gift_tag.tag_id})

        response = client.get(url)

        if response.status_code == 404:
            print(f"Tag ID: {gift_tag.tag_id}")
            print(f"User ID: {user.id}")
            print(f"Shared with: {list(gift_tag.shared_with.all())}")
            print(f"Is public: {gift_tag.is_public}")
            print(f"Queryset count: {GiftTag.objects.filter(shared_with=user).count()}")

        assert response.status_code == 200
