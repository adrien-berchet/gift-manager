"""Lists tell their rows what "Delete" does for the user: delete, leave or nothing (Q1)."""

import json
import re

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level):
    PermissionService.create_or_update_permission(user, obj, permission_level=level)
    return obj


def _delete_modes(response) -> dict:
    match = re.search(
        r'<script id="user-delete-modes" type="application/json">(.*?)</script>',
        response.content.decode(),
        re.DOTALL,
    )
    assert match, "the page has no user-delete-modes data"
    return json.loads(match.group(1))


@pytest.fixture
def owner():
    return UserFactory(username="owner")


@pytest.fixture
def viewer(client, owner):
    user = UserFactory(username="viewer")
    owner.profile.friends.add(user.profile)
    client.force_login(user)
    return user


@pytest.mark.parametrize(
    "factory, url_name, query, id_field",
    [
        (PersonFactory, "persons", "", "person_id"),
        (PersonFactory, "recipients", "?view=people", "person_id"),
        (GiftFactory, "gifts", "", "gift_id"),
        (EventFactory, "events", "", "event_id"),
        (PersonGroupFactory, "person_groups", "", "group_id"),
        (PersonGroupFactory, "recipients", "?view=groups", "group_id"),
    ],
)
def test_list_pages_give_the_delete_mode_of_each_row(
    client, owner, viewer, factory, url_name, query, id_field
):
    shared = _grant(viewer, _grant(owner, factory(), PermissionLevel.OWNER), PermissionLevel.VIEWER)
    own = _grant(viewer, factory(), PermissionLevel.OWNER)

    response = client.get(reverse(f"gift_manager:{url_name}") + query)

    assert response.status_code == 200
    modes = _delete_modes(response)
    assert modes[str(getattr(shared, id_field))] == "leave"
    assert modes[str(getattr(own, id_field))] == "delete"


def test_list_pages_say_why_a_row_cannot_be_deleted(client, owner, viewer):
    """The only owner of a shared object with no friend to hand it to learns why."""
    stranger = UserFactory(username="stranger")
    stuck = _grant(viewer, GiftFactory(name="Stuck"), PermissionLevel.OWNER)
    _grant(stranger, stuck, PermissionLevel.VIEWER)
    own = _grant(viewer, GiftFactory(name="Own"), PermissionLevel.OWNER)

    response = client.get(reverse("gift_manager:gifts"))

    assert _delete_modes(response)[str(stuck.gift_id)] == "none"
    assert response.context["user_delete_reasons"] == {
        str(stuck.gift_id): "At least one owner is required."
    }
    assert str(own.gift_id) not in response.context["user_delete_reasons"]
    assert '<script id="user-delete-reasons" type="application/json">' in response.content.decode()


def _plan(user, level, *, other=None):
    relation = RelationFactory(
        person=PersonFactory(shared_with=[user]),
        gift=GiftFactory(name="Book", shared_with=[user]),
        status=RelationStatusFactory(status="Planned"),
    )
    if other is not None:
        _grant(other, relation, PermissionLevel.OWNER)
    return _grant(user, relation, level)


def test_advanced_plan_list_gives_the_delete_mode_of_each_row(client, owner, viewer):
    shared = _plan(viewer, PermissionLevel.VIEWER, other=owner)
    own = _plan(viewer, PermissionLevel.OWNER)

    modes = _delete_modes(client.get(reverse("gift_manager:relation_advanced_list")))

    assert modes[str(shared.relation_id)] == "leave"
    assert modes[str(own.relation_id)] == "delete"


def test_status_page_grid_follows_the_rights_on_each_plan(client, owner, viewer):
    shared = _plan(viewer, PermissionLevel.VIEWER, other=owner)
    own = RelationFactory(
        person=PersonFactory(shared_with=[viewer]),
        gift=GiftFactory(name="Pen", shared_with=[viewer]),
        status=shared.status,
    )
    _grant(viewer, own, PermissionLevel.OWNER)

    response = client.get(reverse("gift_manager:relation_status_detail", args=[shared.status.pk]))

    assert _delete_modes(response) == {
        str(shared.relation_id): "leave",
        str(own.relation_id): "delete",
    }
    assert response.context["user_permissions"] == {
        str(shared.relation_id): PermissionLevel.VIEWER,
        str(own.relation_id): PermissionLevel.OWNER,
    }
    assert "permissionAwareActionFormatter" in response.content.decode()
    # Group plans follow the same delete modes as the others
    assert "canDelete" not in response.content.decode()


def test_gift_page_offers_to_leave_a_plan_the_user_cannot_delete(client, owner, viewer):
    gift = _grant(viewer, GiftFactory(name="Book"), PermissionLevel.OWNER)
    person = PersonFactory(shared_with=[viewer])
    status = RelationStatusFactory(status="Planned")
    shared = RelationFactory(person=person, gift=gift, status=status)
    _grant(owner, shared, PermissionLevel.OWNER)
    _grant(viewer, shared, PermissionLevel.VIEWER)
    own = _grant(
        viewer, RelationFactory(person=person, gift=gift, status=status), PermissionLevel.OWNER
    )

    content = client.get(reverse("gift_manager:gift_detail", args=[gift.gift_id])).content.decode()

    shared_delete = reverse("gift_manager:relation_delete", args=[shared.relation_id])
    own_delete = reverse("gift_manager:relation_delete", args=[own.relation_id])
    assert f'href="{shared_delete}?intent=leave_access"' in content
    assert f'href="{shared_delete}"' not in content
    assert f'href="{own_delete}"' in content


def test_group_tree_view_only_offers_what_the_user_may_do(client, owner, viewer):
    parent = _grant(owner, PersonGroupFactory(name="Parent"), PermissionLevel.OWNER)
    child = _grant(owner, PersonGroupFactory(name="Child"), PermissionLevel.OWNER)
    child.parent_groups.add(parent)
    _grant(viewer, parent, PermissionLevel.VIEWER)
    _grant(viewer, child, PermissionLevel.VIEWER)

    content = client.get(reverse("gift_manager:person_groups")).content.decode()

    assert "tree-view-container" in content
    edit_url = reverse("gift_manager:person_group_edit", args=[parent.group_id])
    delete_url = reverse("gift_manager:person_group_delete", args=[parent.group_id])
    assert f'href="{edit_url}"' not in content
    assert f'href="{delete_url}"' not in content
    assert f'href="{delete_url}?intent=leave_access"' in content
    tree = content.split('class="tree-view-container')[1].split('id="groupMoveModal"')[0]
    assert tree.count('class="tree-node"') == 2
    assert 'draggable="true"' not in tree
    assert "tree-move-btn" not in tree
    assert "drag-handle" not in tree
