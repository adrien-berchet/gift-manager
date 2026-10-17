# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime

import pytest

from gift_manager.models import Gift
from gift_manager.models import GiftPermission
from gift_manager.models import PermissionLevel
from gift_manager.tests.utils import requires_postgresql


@pytest.mark.django_db
class TestGift:
    """Tests for the Gift model."""

    def test_gift_creation(self, gift):
        """Test creating a gift."""
        assert gift.name == "Smartphone"
        assert gift.comment == "Latest model"
        assert gift.gift_id is not None
        assert isinstance(gift.gift_id, uuid.UUID)
        assert isinstance(gift.creation_date, datetime)

    def test_gift_string_representation(self, gift):
        """Test the string representation of a gift."""
        assert str(gift) == "Smartphone"

    def test_gift_with_tags(self, gift, gift_tag):
        """Test adding tags to a gift."""
        gift.tags.add(gift_tag)
        assert gift_tag in gift.tags.all()

    def test_gift_permission(self, user, username, gift, gift_name):
        """Test adding a permission to a gift."""
        permission = GiftPermission.objects.create(
            user=user, gift=gift, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.gift == gift
        assert str(permission) == f"{username} - {gift_name} -> owner"
        assert user in gift.shared_with.all()


@pytest.mark.django_db
class TestGiftManagerMethods:
    """Tests for GiftManager query methods."""

    @requires_postgresql
    def test_with_tags_annotated(self, gift, gift_tag):
        """Test with_tags_annotated annotates gifts with tags info."""
        gift.tags.add(gift_tag)

        gifts = Gift.objects.with_tags_annotated().filter(pk=gift.pk)
        annotated_gift = gifts.first()

        assert hasattr(annotated_gift, "tags_info")
        tags_info = annotated_gift.tags_info
        assert tags_info is not None
        assert len(tags_info) == 1

    @requires_postgresql
    def test_for_list_display(self, user, gift, gift_tag):
        """Test for_list_display returns optimized queryset."""
        gift.tags.add(gift_tag)

        # Share gift with user
        GiftPermission.objects.create(user=user, gift=gift, permission_type=PermissionLevel.VIEWER)

        results = Gift.objects.for_list_display(user)
        assert len(results) == 1
        result = results[0]

        assert "gift_id" in result
        assert "name" in result
        assert "tags_info" in result
