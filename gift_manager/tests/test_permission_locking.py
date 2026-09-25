"""Owner-affecting permission changes are serialized per object (GM-AUD-007)."""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Row locks need PostgreSQL"
)


@pytest.fixture
def owners():
    first, second = UserFactory(), UserFactory()
    first.profile.friends.add(second.profile)
    gift = GiftFactory()
    create_or_update_permission(first, gift, permission_level=PermissionLevel.OWNER)
    create_or_update_permission(second, gift, permission_level=PermissionLevel.OWNER)
    return first, second, gift


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _edit_url(gift):
    return reverse("gift_manager:gift_edit", kwargs={"pk": gift.gift_id})


def _locked(queries) -> bool:
    return any("FOR UPDATE" in query["sql"] for query in queries)


def test_locked_context_manager_runs_inside_a_transaction(owners):
    _first, _second, gift = owners

    with PermissionService.locked_for_permission_change(gift):
        assert connection.in_atomic_block


@postgres_only
def test_locked_context_manager_locks_the_object_row(owners):
    _first, _second, gift = owners

    with (
        CaptureQueriesContext(connection) as queries,
        PermissionService.locked_for_permission_change(gift),
    ):
        pass

    assert _locked(queries)


@postgres_only
@pytest.mark.parametrize(
    "payload",
    [
        {"update_permission": "1", "permission": str(PermissionLevel.VIEWER)},
        {"remove_share": "1"},
        {"share_with": "1", "permission": str(PermissionLevel.VIEWER)},
    ],
    ids=["update", "remove", "share_with"],
)
def test_detail_page_permission_actions_take_the_row_lock(owners, payload):
    first, second, gift = owners

    with CaptureQueriesContext(connection) as queries:
        _client(first).post(_edit_url(gift), {**payload, "user_id": second.id})

    assert _locked(queries)


@postgres_only
def test_edit_form_permission_fields_take_the_row_lock(owners):
    first, second, gift = owners

    with CaptureQueriesContext(connection) as queries:
        _client(first).post(
            _edit_url(gift),
            {"name": gift.name, f"permission_{second.id}": str(PermissionLevel.VIEWER)},
        )

    assert _locked(queries)


def test_last_owner_cannot_be_demoted(owners):
    first, second, gift = owners
    _client(first).post(
        _edit_url(gift),
        {"update_permission": "1", "user_id": second.id, "permission": PermissionLevel.VIEWER},
    )

    # second is now a viewer: first is the only owner and cannot demote themselves
    _client(first).post(
        _edit_url(gift),
        {"update_permission": "1", "user_id": first.id, "permission": PermissionLevel.VIEWER},
    )

    assert get_permission(gift, first) == PermissionLevel.OWNER
    assert get_permission(gift, second) == PermissionLevel.VIEWER


def test_owner_cannot_demote_after_the_other_owner_already_did(owners):
    """Sequential outcome of the race: the second demotion must be rejected."""
    first, second, gift = owners
    _client(first).post(
        _edit_url(gift),
        {"update_permission": "1", "user_id": second.id, "permission": PermissionLevel.VIEWER},
    )

    response = _client(second).post(
        _edit_url(gift),
        {"update_permission": "1", "user_id": first.id, "permission": PermissionLevel.VIEWER},
    )

    assert response.status_code == 403
    assert get_permission(gift, first) == PermissionLevel.OWNER
