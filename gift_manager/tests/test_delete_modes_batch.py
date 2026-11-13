"""PermissionService.delete_modes_for gives lists the delete mode of each row in few queries."""

import pytest

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level):
    PermissionService.create_or_update_permission(user, obj, permission_level=level)
    return obj


def _friend(user, label):
    friend = UserFactory(username=label)
    user.profile.friends.add(friend.profile)
    return friend


@pytest.fixture
def user():
    return UserFactory(username="me")


@pytest.fixture
def persons(user):
    """One person per situation the delete button has to tell apart."""
    friend = _friend(user, "friend")
    stranger = UserFactory(username="stranger")
    inactive = _friend(user, "inactive")
    inactive.is_active = False
    inactive.save()

    alone = _grant(user, PersonFactory(first_name="Alone"), PermissionLevel.OWNER)
    alone_editor = _grant(user, PersonFactory(first_name="AloneEditor"), PermissionLevel.EDITOR)
    alone_viewer = _grant(user, PersonFactory(first_name="AloneViewer"), PermissionLevel.VIEWER)

    viewer_of_shared = _grant(user, PersonFactory(first_name="Viewer"), PermissionLevel.VIEWER)
    _grant(stranger, viewer_of_shared, PermissionLevel.OWNER)

    editor_of_shared = _grant(user, PersonFactory(first_name="Editor"), PermissionLevel.EDITOR)
    _grant(stranger, editor_of_shared, PermissionLevel.OWNER)

    co_owner = _grant(user, PersonFactory(first_name="CoOwner"), PermissionLevel.OWNER)
    _grant(friend, co_owner, PermissionLevel.OWNER)

    sole_owner_with_friend = _grant(user, PersonFactory(first_name="Sole"), PermissionLevel.OWNER)
    _grant(friend, sole_owner_with_friend, PermissionLevel.VIEWER)

    sole_owner_no_friend = _grant(user, PersonFactory(first_name="Stuck"), PermissionLevel.OWNER)
    _grant(stranger, sole_owner_no_friend, PermissionLevel.EDITOR)

    other_owner_inactive = _grant(user, PersonFactory(first_name="Inactive"), PermissionLevel.OWNER)
    _grant(inactive, other_owner_inactive, PermissionLevel.OWNER)

    no_access = _grant(stranger, PersonFactory(first_name="NoAccess"), PermissionLevel.OWNER)

    return {
        "alone": alone,
        "alone_editor": alone_editor,
        "alone_viewer": alone_viewer,
        "viewer_of_shared": viewer_of_shared,
        "editor_of_shared": editor_of_shared,
        "co_owner": co_owner,
        "sole_owner_with_friend": sole_owner_with_friend,
        "sole_owner_no_friend": sole_owner_no_friend,
        "other_owner_inactive": other_owner_inactive,
        "no_access": no_access,
    }


def _batch(user, model, objects, id_field):
    ids = [getattr(obj, id_field) for obj in objects]
    return PermissionService.delete_modes_for(user, model, ids, id_field)


def test_modes_of_each_situation(user, persons):
    modes = _batch(user, Person, persons.values(), "person_id")
    by_name = {name: modes[str(person.person_id)] for name, person in persons.items()}
    assert by_name == {
        "alone": "delete",
        "alone_editor": "delete",
        "alone_viewer": "none",
        "viewer_of_shared": "leave",
        "editor_of_shared": "leave",
        "co_owner": "leave",
        "sole_owner_with_friend": "handover",
        "sole_owner_no_friend": "none",
        "other_owner_inactive": "none",
        "no_access": "none",
    }


def _states(user, model, objects, id_field):
    ids = [getattr(obj, id_field) for obj in objects]
    return PermissionService.delete_states_for(user, model, ids, id_field)


def test_batch_matches_the_per_object_rule_and_its_reason(user, persons):
    states = _states(user, Person, persons.values(), "person_id")
    for name, person in persons.items():
        assert states[str(person.person_id)] == PermissionService.delete_mode_for(user, person), (
            name
        )


def test_batch_matches_the_per_object_rule_for_a_superuser(persons):
    admin = UserFactory(username="admin", is_superuser=True)
    states = _states(admin, Person, persons.values(), "person_id")
    for name, person in persons.items():
        assert states[str(person.person_id)] == PermissionService.delete_mode_for(admin, person), (
            name
        )


def test_a_blocked_delete_says_why(user, persons):
    states = _states(user, Person, persons.values(), "person_id")
    assert states[str(persons["sole_owner_no_friend"].person_id)] == (
        "none",
        "At least one owner is required.",
    )
    assert states[str(persons["alone_viewer"].person_id)] == (
        "none",
        "You do not have permission to delete this object.",
    )


def test_public_tags_and_global_events_can_be_neither_deleted_nor_left(user):
    public_tag = _grant(user, GiftTagFactory(name="Public", is_public=True), PermissionLevel.OWNER)
    own_tag = _grant(user, GiftTagFactory(name="Own"), PermissionLevel.OWNER)
    tag_states = _states(user, GiftTag, [public_tag, own_tag], "tag_id")
    assert tag_states[str(public_tag.tag_id)] == PermissionService.delete_mode_for(user, public_tag)
    tag_modes = _batch(user, GiftTag, [public_tag, own_tag], "tag_id")
    assert tag_modes == {str(public_tag.tag_id): "none", str(own_tag.tag_id): "delete"}

    birthday = Event.objects.get_birthday_event()
    own_event = _grant(user, EventFactory(name="Party"), PermissionLevel.OWNER)
    event_states = _states(user, Event, [birthday, own_event], "event_id")
    assert event_states[str(birthday.event_id)] == PermissionService.delete_mode_for(user, birthday)
    event_modes = _batch(user, Event, [birthday, own_event], "event_id")
    assert event_modes == {str(birthday.event_id): "none", str(own_event.event_id): "delete"}


def test_groups_follow_inherited_permissions(user):
    owner = UserFactory(username="group-owner")
    parent = _grant(owner, PersonGroupFactory(name="Parent"), PermissionLevel.OWNER)
    child = _grant(owner, PersonGroupFactory(name="Child"), PermissionLevel.OWNER)
    child.parent_groups.add(parent)
    PersonGroupPermission.objects.create(
        group=parent, user=user, permission_type=PermissionLevel.VIEWER, inherit_permissions=True
    )
    own = _grant(user, PersonGroupFactory(name="Own"), PermissionLevel.OWNER)

    modes = _batch(user, PersonGroup, [parent, child, own], "group_id")

    states = _states(user, PersonGroup, [parent, child, own], "group_id")
    for group in (parent, child, own):
        assert states[str(group.group_id)] == PermissionService.delete_mode_for(user, group)
    assert modes[str(own.group_id)] == "delete"
    assert modes[str(parent.group_id)] == "leave"
    # Access to the child only comes from the parent: there is no permission of its own to remove
    assert modes[str(child.group_id)] == "none"


def test_batch_uses_a_constant_number_of_queries(user, django_assert_max_num_queries):
    gifts = [_grant(user, GiftFactory(name=f"Gift {i}"), PermissionLevel.OWNER) for i in range(12)]
    friend = _friend(user, "friend")
    for gift in gifts[:6]:
        _grant(friend, gift, PermissionLevel.VIEWER)
    ids = [gift.gift_id for gift in gifts]

    with django_assert_max_num_queries(5):
        modes = PermissionService.delete_modes_for(user, Gift, ids, "gift_id")

    assert len(modes) == 12
    assert set(modes.values()) == {"delete", "handover"}


def test_empty_list_needs_no_query(user, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert PermissionService.delete_modes_for(user, Person, [], "person_id") == {}
