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


class FakeAIClient:
    """Fake AI client for unit and integration tests."""

    def __init__(self, canned_responses=None, error=None):
        self.canned_responses = list(canned_responses or [])
        self.error = error
        self.calls = []
        self.payload = None
        self.system = None
        self.schema = None

    def generate(self, *, system: str, payload: dict, schema: dict) -> str:
        import json

        self.calls.append({"system": system, "payload": payload, "schema": schema})
        self.payload = payload
        self.system = system
        self.schema = schema
        if self.error:
            raise self.error
        if self.canned_responses:
            res = self.canned_responses.pop(0)
            if isinstance(res, Exception):
                raise res
            if isinstance(res, str):
                return res
            return json.dumps(res)
        return json.dumps({"ideas": []})


@pytest.fixture
def fake_ai_client():
    return FakeAIClient()
