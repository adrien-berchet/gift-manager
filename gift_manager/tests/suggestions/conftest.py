import pytest
from django.test import Client

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission


@pytest.fixture
def client(user):
    """A test client logged in as `user`."""
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def share():
    """Helper to grant a permission on an object to a user."""

    def _share(user, obj, level=PermissionLevel.EDITOR):
        return create_or_update_permission(user, obj, permission_level=level)

    return _share


@pytest.fixture
def status():
    """Helper to get or create a relation status by canonical English name."""

    def _status(name: str):
        instance, _ = RelationStatus.objects.get_or_create(
            status_en=name, defaults={"status": name}
        )
        return instance

    return _status
