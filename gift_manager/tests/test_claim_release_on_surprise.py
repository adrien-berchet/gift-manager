"""A claim is released when its holder can no longer see the plan (it became a surprise for them)."""

import pytest
from django.utils import timezone

from gift_manager import plan_coordination
from gift_manager.forms import RelationForm
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _share(relation, user, level=PermissionLevel.EDITOR):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


def _claim(relation, user):
    Relation.objects.filter(pk=relation.pk).update(claimed_by=user, claimed_at=timezone.now())
    relation.refresh_from_db()


@pytest.fixture
def claimer():
    return UserFactory()


@pytest.fixture
def owner():
    return UserFactory()


def test_ticking_surprise_releases_the_claim_of_the_person_recipient(claimer, owner):
    relation = RelationFactory(person=PersonFactory(user_link=claimer))
    _share(relation, owner, PermissionLevel.OWNER)
    _share(relation, claimer)
    _claim(relation, claimer)

    plan_coordination.set_surprise(relation, owner, value=True)

    relation.refresh_from_db()
    assert relation.claimed_by is None
    assert relation.claimed_at is None
    assert relation.is_surprise is True


def test_ticking_surprise_releases_the_claim_of_a_group_member(claimer, owner):
    group = PersonGroupFactory()
    PersonFactory(user_link=claimer, groups=[group])
    relation = GroupRelationFactory(group=group)
    _share(relation, owner, PermissionLevel.OWNER)
    _share(relation, claimer)
    _claim(relation, claimer)

    plan_coordination.set_surprise(relation, owner, value=True)

    relation.refresh_from_db()
    assert relation.claimed_by is None


def test_a_claim_held_by_someone_who_is_not_a_recipient_is_kept(claimer, owner):
    relation = RelationFactory(person=PersonFactory(user_link=UserFactory()))
    _share(relation, owner, PermissionLevel.OWNER)
    _share(relation, claimer)
    _claim(relation, claimer)

    plan_coordination.set_surprise(relation, owner, value=True)

    relation.refresh_from_db()
    assert relation.claimed_by == claimer


def test_an_owner_who_is_a_recipient_keeps_their_claim(claimer):
    group = PersonGroupFactory()
    PersonFactory(user_link=claimer, groups=[group])
    relation = GroupRelationFactory(group=group)
    _share(relation, claimer, PermissionLevel.OWNER)
    _claim(relation, claimer)

    plan_coordination.set_surprise(relation, claimer, value=True)

    relation.refresh_from_db()
    assert relation.claimed_by == claimer


def test_changing_the_recipient_of_a_surprise_plan_releases_the_claim(claimer, owner):
    relation = RelationFactory(person=PersonFactory(), is_surprise=True)
    _share(relation, owner, PermissionLevel.OWNER)
    _share(relation, claimer)
    _claim(relation, claimer)

    relation.person = PersonFactory(user_link=claimer)
    relation.save()

    relation.refresh_from_db()
    assert relation.claimed_by is None


def test_ticking_the_checkbox_in_the_plan_form_releases_the_claim(claimer, owner):
    person = PersonFactory(user_link=claimer, shared_with=[owner])
    gift = GiftFactory(shared_with=[owner])
    relation = RelationFactory(person=person, gift=gift, event=None)
    _share(relation, owner, PermissionLevel.OWNER)
    _share(relation, claimer)
    _claim(relation, claimer)
    data = {
        "recipient": f"person:{person.person_id}",
        "gift": str(gift.pk),
        "comment": "",
        "event": "",
        "status": str(relation.status_id),
        "due_date": "",
        "is_surprise": "on",
    }

    form = RelationForm(instance=relation, data=data, user=owner)

    assert form.is_valid(), form.errors
    form.save()
    relation.refresh_from_db()
    assert (relation.is_surprise, relation.claimed_by) == (True, None)


def test_creating_a_plan_does_not_touch_anything(claimer):
    relation = RelationFactory(person=PersonFactory(user_link=claimer), is_surprise=True)

    assert relation.claimed_by is None
