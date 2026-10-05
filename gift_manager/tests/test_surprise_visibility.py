"""Surprise plans are hidden from their recipient inside ``Relation.objects.accessible_by``."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _share(relation, user, level=PermissionLevel.VIEWER):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


def _visible(relation, user) -> bool:
    return Relation.objects.accessible_by(user).filter(pk=relation.pk).exists()


@pytest.fixture
def recipient():
    return UserFactory()


@pytest.fixture
def collaborator():
    return UserFactory()


def _surprise_for_person(recipient, collaborator, **kwargs):
    person = PersonFactory(user_link=recipient)
    relation = RelationFactory(person=person, is_surprise=True, **kwargs)
    _share(relation, recipient)
    _share(relation, collaborator)
    return relation


def test_person_recipient_is_hidden_but_collaborator_still_sees_it(recipient, collaborator):
    relation = _surprise_for_person(recipient, collaborator)

    assert not _visible(relation, recipient)
    assert _visible(relation, collaborator)


def test_plan_that_is_not_a_surprise_stays_visible_to_the_recipient(recipient, collaborator):
    person = PersonFactory(user_link=recipient)
    relation = RelationFactory(person=person, is_surprise=False)
    _share(relation, recipient)

    assert _visible(relation, recipient)


def test_direct_group_member_is_hidden(recipient, collaborator):
    group = PersonGroupFactory()
    PersonFactory(user_link=recipient, groups=[group])
    relation = GroupRelationFactory(group=group, is_surprise=True)
    _share(relation, recipient)
    _share(relation, collaborator)

    assert not _visible(relation, recipient)
    assert _visible(relation, collaborator)


def test_member_of_a_nested_child_group_is_hidden(recipient):
    target = PersonGroupFactory()
    child = PersonGroupFactory()
    child.parent_groups.add(target)
    PersonFactory(user_link=recipient, groups=[child])
    relation = GroupRelationFactory(group=target, is_surprise=True)
    _share(relation, recipient)

    assert not _visible(relation, recipient)


def test_member_of_the_parent_of_the_target_group_still_sees_the_plan(recipient):
    parent = PersonGroupFactory()
    target = PersonGroupFactory()
    target.parent_groups.add(parent)
    PersonFactory(user_link=recipient, groups=[parent])
    relation = GroupRelationFactory(group=target, is_surprise=True)
    _share(relation, recipient)

    assert _visible(relation, recipient)


def test_recipient_who_owns_the_plan_is_never_hidden(recipient):
    person = PersonFactory(user_link=recipient)
    relation = RelationFactory(person=person, is_surprise=True)
    _share(relation, recipient, PermissionLevel.OWNER)

    assert _visible(relation, recipient)


def test_group_whose_only_linked_member_is_the_owner_stays_visible_to_them():
    owner = UserFactory()
    group = PersonGroupFactory()
    PersonFactory(user_link=owner, groups=[group])
    relation = GroupRelationFactory(group=group, is_surprise=True)
    _share(relation, owner, PermissionLevel.OWNER)

    assert _visible(relation, owner)


def test_hidden_surprises_for_lists_hidden_rows_even_when_not_shared(recipient, collaborator):
    hidden = _surprise_for_person(recipient, collaborator)
    unshared = RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=True)
    RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=False)
    RelationFactory(is_surprise=True)

    assert set(Relation.objects.hidden_surprises_for(recipient)) == {hidden, unshared}


def test_number_of_queries_does_not_grow_with_hidden_plans(recipient, collaborator):
    def count_queries():
        with CaptureQueriesContext(connection) as context:
            list(Relation.objects.accessible_by(recipient))
        return len(context)

    _surprise_for_person(recipient, collaborator)
    one_plan = count_queries()
    for _ in range(4):
        _surprise_for_person(recipient, collaborator)

    assert count_queries() == one_plan
