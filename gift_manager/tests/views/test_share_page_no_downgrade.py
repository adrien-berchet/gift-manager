"""The share page grants access and must never reduce anyone's existing access."""

from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

SHARE_URL = "gift_manager:share_objects"


def _grant(user, obj, level):
    create_or_update_permission(user, obj, permission_level=level)


@pytest.fixture
def actor():
    return UserFactory()


@pytest.fixture
def friend(actor):
    friend = UserFactory()
    actor.profile.friends.add(friend.profile)
    return friend


@pytest.fixture
def client_for(actor):
    client = Client()
    client.force_login(actor)
    return client


def _post_share(client, friends, level, **selection):
    data = {
        "friends": [user.id for user in friends],
        "permission_level": str(level),
    }
    for key, objects in selection.items():
        if key in {"share_group_persons", "share_child_groups"}:
            if objects:
                data[key] = "on"
            continue
        data[key] = [str(value) for value in objects]
    return client.post(reverse(SHARE_URL), data)


SIMPLE_OBJECTS = [
    ("persons", PersonFactory, "person_id"),
    ("gifts", GiftFactory, "gift_id"),
    ("events", EventFactory, "event_id"),
    ("person_groups", PersonGroupFactory, "group_id"),
]


@pytest.mark.parametrize(("field", "factory", "id_field"), SIMPLE_OBJECTS)
def test_share_page_does_not_demote_co_owner(actor, friend, client_for, field, factory, id_field):
    """Sharing as viewer with a co-owner must keep them owner."""
    obj = factory()
    _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, obj, PermissionLevel.OWNER)

    response = _post_share(
        client_for, [friend], PermissionLevel.VIEWER, **{field: [getattr(obj, id_field)]}
    )

    assert response.status_code == 302
    assert get_permission(obj, friend) == PermissionLevel.OWNER
    assert get_permission(obj, actor) == PermissionLevel.OWNER


@pytest.mark.parametrize(("field", "factory", "id_field"), SIMPLE_OBJECTS)
def test_share_page_does_not_downgrade_editor_to_viewer(
    actor, friend, client_for, field, factory, id_field
):
    """An existing editor stays editor when shared again as viewer."""
    obj = factory()
    _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, obj, PermissionLevel.EDITOR)

    response = _post_share(
        client_for, [friend], PermissionLevel.VIEWER, **{field: [getattr(obj, id_field)]}
    )

    assert response.status_code == 302
    assert get_permission(obj, friend) == PermissionLevel.EDITOR


@pytest.mark.parametrize(("field", "factory", "id_field"), SIMPLE_OBJECTS)
def test_share_page_upgrades_viewer_to_editor(actor, friend, client_for, field, factory, id_field):
    """Sharing at a higher level still raises an existing lower permission."""
    obj = factory()
    _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, obj, PermissionLevel.VIEWER)

    response = _post_share(
        client_for, [friend], PermissionLevel.EDITOR, **{field: [getattr(obj, id_field)]}
    )

    assert response.status_code == 302
    assert get_permission(obj, friend) == PermissionLevel.EDITOR


@pytest.mark.parametrize(("field", "factory", "id_field"), SIMPLE_OBJECTS)
def test_share_page_creates_new_share(actor, friend, client_for, field, factory, id_field):
    """A friend without access gets the requested level."""
    obj = factory()
    _grant(actor, obj, PermissionLevel.OWNER)

    response = _post_share(
        client_for, [friend], PermissionLevel.EDITOR, **{field: [getattr(obj, id_field)]}
    )

    assert response.status_code == 302
    assert get_permission(obj, friend) == PermissionLevel.EDITOR
    assert friend in obj.shared_with.all()


def test_share_page_raises_one_friend_and_keeps_another(actor, friend, client_for):
    """Per-friend decisions: a new friend is added while an existing owner is kept."""
    other_friend = UserFactory()
    actor.profile.friends.add(other_friend.profile)
    event = EventFactory()
    _grant(actor, event, PermissionLevel.OWNER)
    _grant(friend, event, PermissionLevel.OWNER)

    response = _post_share(
        client_for, [friend, other_friend], PermissionLevel.VIEWER, events=[event.event_id]
    )

    assert response.status_code == 302
    assert get_permission(event, friend) == PermissionLevel.OWNER
    assert get_permission(event, other_friend) == PermissionLevel.VIEWER


def test_group_share_does_not_downgrade_members_or_child_groups(actor, friend, client_for):
    """Cascaded members and descendant groups are only raised, never lowered."""
    parent = PersonGroupFactory()
    child = PersonGroupFactory()
    child.parent_groups.add(parent)
    owned_member = PersonFactory()
    editor_member = PersonFactory()
    new_member = PersonFactory()
    for person in (owned_member, editor_member, new_member):
        person.groups.add(parent)
    child_member = PersonFactory()
    child_member.groups.add(child)

    for obj in (parent, child, owned_member, editor_member, new_member, child_member):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, parent, PermissionLevel.EDITOR)
    _grant(friend, child, PermissionLevel.OWNER)
    _grant(friend, owned_member, PermissionLevel.OWNER)
    _grant(friend, editor_member, PermissionLevel.EDITOR)
    _grant(friend, child_member, PermissionLevel.EDITOR)

    response = _post_share(
        client_for,
        [friend],
        PermissionLevel.VIEWER,
        person_groups=[parent.group_id],
        share_group_persons=True,
        share_child_groups=True,
    )

    assert response.status_code == 302
    assert get_permission(parent, friend) == PermissionLevel.EDITOR
    assert get_permission(child, friend) == PermissionLevel.OWNER
    assert get_permission(owned_member, friend) == PermissionLevel.OWNER
    assert get_permission(editor_member, friend) == PermissionLevel.EDITOR
    assert get_permission(child_member, friend) == PermissionLevel.EDITOR
    assert get_permission(new_member, friend) == PermissionLevel.VIEWER


def test_group_share_raises_members_and_child_groups(actor, friend, client_for):
    """Cascaded members and descendant groups with lower access are raised."""
    parent = PersonGroupFactory()
    child = PersonGroupFactory()
    child.parent_groups.add(parent)
    member = PersonFactory()
    member.groups.add(parent)

    for obj in (parent, child, member):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, child, PermissionLevel.VIEWER)
    _grant(friend, member, PermissionLevel.VIEWER)

    response = _post_share(
        client_for,
        [friend],
        PermissionLevel.EDITOR,
        person_groups=[parent.group_id],
        share_group_persons=True,
        share_child_groups=True,
    )

    assert response.status_code == 302
    assert get_permission(parent, friend) == PermissionLevel.EDITOR
    assert get_permission(child, friend) == PermissionLevel.EDITOR
    assert get_permission(member, friend) == PermissionLevel.EDITOR


def test_relation_share_does_not_downgrade_relation_or_related_objects(actor, friend, client_for):
    """Sharing a gift plan as viewer keeps the friend's higher access on it and its objects."""
    relation = RelationFactory()
    for obj in (relation, relation.gift, relation.person, relation.event):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, relation, PermissionLevel.OWNER)
    _grant(friend, relation.gift, PermissionLevel.EDITOR)
    _grant(friend, relation.person, PermissionLevel.OWNER)

    response = _post_share(
        client_for, [friend], PermissionLevel.VIEWER, relations=[relation.relation_id]
    )

    assert response.status_code == 302
    assert get_permission(relation, friend) == PermissionLevel.OWNER
    assert get_permission(relation.gift, friend) == PermissionLevel.EDITOR
    assert get_permission(relation.person, friend) == PermissionLevel.OWNER
    assert get_permission(relation.event, friend) == PermissionLevel.VIEWER


def test_relation_share_upgrades_relation(actor, friend, client_for):
    """Sharing a gift plan at a higher level raises the friend's access."""
    relation = RelationFactory()
    for obj in (relation, relation.gift, relation.person, relation.event):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, relation, PermissionLevel.VIEWER)

    response = _post_share(
        client_for, [friend], PermissionLevel.EDITOR, relations=[relation.relation_id]
    )

    assert response.status_code == 302
    assert get_permission(relation, friend) == PermissionLevel.EDITOR
    assert get_permission(relation.gift, friend) == PermissionLevel.EDITOR


def test_share_page_locks_each_object_before_writing(actor, friend, client_for):
    """Permission writes are serialized with the edit pages through the object row lock."""
    event = EventFactory()
    gift = GiftFactory()
    for obj in (event, gift):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, gift, PermissionLevel.OWNER)

    with patch.object(
        PermissionService, "lock_object", wraps=PermissionService.lock_object
    ) as lock_object:
        response = _post_share(
            client_for,
            [friend],
            PermissionLevel.VIEWER,
            events=[event.event_id],
            gifts=[gift.gift_id],
        )

    assert response.status_code == 302
    locked = {(type(call.args[0]), call.args[0].pk) for call in lock_object.call_args_list}
    assert (type(event), event.pk) in locked
    assert (type(gift), gift.pk) in locked


@override_settings(USE_I18N=False)
def test_share_page_reports_kept_permissions(actor, friend, client_for):
    """The user is told when existing equal or higher access was kept."""
    event = EventFactory()
    gift = GiftFactory()
    for obj in (event, gift):
        _grant(actor, obj, PermissionLevel.OWNER)
    _grant(friend, event, PermissionLevel.OWNER)

    response = _post_share(
        client_for,
        [friend],
        PermissionLevel.VIEWER,
        events=[event.event_id],
        gifts=[gift.gift_id],
    )

    texts = [str(message) for message in get_messages(response.wsgi_request)]
    assert any("Successfully shared" in text for text in texts)
    assert any("1 existing permission was" in text for text in texts)


@override_settings(USE_I18N=False)
def test_share_page_has_no_kept_message_for_new_shares(actor, friend, client_for):
    """No extra message when every permission was created or raised."""
    event = EventFactory()
    _grant(actor, event, PermissionLevel.OWNER)

    response = _post_share(client_for, [friend], PermissionLevel.VIEWER, events=[event.event_id])

    texts = [str(message) for message in get_messages(response.wsgi_request)]
    assert not any("existing permission" in text for text in texts)
