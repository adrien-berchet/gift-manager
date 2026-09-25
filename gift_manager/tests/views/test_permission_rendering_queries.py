"""Detail and edit pages must not query permissions once per shared user (GM-AUD-016)."""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _gift_with_collaborators(owner, count, *, friends=True):
    gift = GiftFactory()
    create_or_update_permission(owner, gift, permission_level=PermissionLevel.OWNER)
    for _ in range(count):
        other = UserFactory()
        if friends:
            owner.profile.friends.add(other.profile)
        create_or_update_permission(other, gift, permission_level=PermissionLevel.VIEWER)
    return gift


def _count_queries(user, url) -> int:
    client = Client()
    client.force_login(user)
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    return len(queries)


@pytest.mark.parametrize("route", ["gift_detail", "gift_edit"])
def test_query_count_does_not_grow_with_the_number_of_shared_users(route):
    small_owner, large_owner = UserFactory(), UserFactory()
    small = _gift_with_collaborators(small_owner, 1)
    large = _gift_with_collaborators(large_owner, 8)

    small_count = _count_queries(
        small_owner, reverse(f"gift_manager:{route}", kwargs={"pk": small.gift_id})
    )
    large_count = _count_queries(
        large_owner, reverse(f"gift_manager:{route}", kwargs={"pk": large.gift_id})
    )

    assert large_count == small_count


def test_permission_map_returns_direct_levels_in_one_query():
    owner, viewer, editor = UserFactory(), UserFactory(), UserFactory()
    gift = GiftFactory()
    create_or_update_permission(owner, gift, permission_level=PermissionLevel.OWNER)
    create_or_update_permission(viewer, gift, permission_level=PermissionLevel.VIEWER)
    create_or_update_permission(editor, gift, permission_level=PermissionLevel.EDITOR)

    with CaptureQueriesContext(connection) as queries:
        permissions = PermissionService.get_permission_map(gift)

    assert permissions == {
        owner.id: PermissionLevel.OWNER,
        viewer.id: PermissionLevel.VIEWER,
        editor.id: PermissionLevel.EDITOR,
    }
    assert len(queries) == 1


def test_shared_users_context_lists_everyone_but_the_viewer_with_their_levels():
    owner, viewer, editor = (
        UserFactory(username="zed"),
        UserFactory(username="amy"),
        UserFactory(username="bob"),
    )
    gift = GiftFactory()
    create_or_update_permission(owner, gift, permission_level=PermissionLevel.OWNER)
    create_or_update_permission(viewer, gift, permission_level=PermissionLevel.VIEWER)
    create_or_update_permission(editor, gift, permission_level=PermissionLevel.EDITOR)
    client = Client()
    client.force_login(owner)

    response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id}))

    shared = response.context["shared_users"]
    assert [(entry["user"].username, entry["permission"]) for entry in shared] == [
        ("amy", PermissionLevel.VIEWER),
        ("bob", PermissionLevel.EDITOR),
    ]
