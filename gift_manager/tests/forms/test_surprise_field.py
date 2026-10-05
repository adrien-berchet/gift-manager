"""The surprise checkbox of the gift plan forms: default, who sees it, what is saved."""

import pytest

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.models import PermissionLevel
from gift_manager.plan_repeat import duplicate_initial
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _share(obj, user, level, attr=None):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


@pytest.fixture
def creator():
    return UserFactory()


@pytest.fixture
def gift(creator):
    return GiftFactory(shared_with=[creator])


def _data(gift, **overrides):
    data = {
        "gift": str(gift.pk),
        "comment": "",
        "event": "",
        "status": str(RelationStatusFactory(status="Idea").pk),
        "due_date": "",
    }
    data.update(overrides)
    return data


# --- defaults on creation ------------------------------------------------------------------


def test_default_is_on_for_a_person_linked_to_another_user(creator):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])

    form = RelationForm(initial={"recipient": f"person:{person.person_id}"}, user=creator)

    assert form["is_surprise"].value() is True


def test_default_is_off_for_an_unlinked_person(creator):
    person = PersonFactory(shared_with=[creator])

    form = RelationForm(initial={"recipient": f"person:{person.person_id}"}, user=creator)

    assert form["is_surprise"].value() is False


def test_default_is_on_for_a_group_with_a_linked_member(creator):
    group = PersonGroupFactory(shared_with=[creator])
    PersonFactory(user_link=UserFactory(), groups=[group])

    form = RelationForm(initial={"recipient": f"group:{group.group_id}"}, user=creator)

    assert form["is_surprise"].value() is True


def test_default_is_off_for_a_group_whose_only_linked_member_is_the_creator(creator):
    group = PersonGroupFactory(shared_with=[creator])
    PersonFactory(user_link=creator, groups=[group])

    form = RelationForm(initial={"recipient": f"group:{group.group_id}"}, user=creator)

    assert "is_surprise" in form.fields
    assert form["is_surprise"].value() is False


def test_person_and_group_create_forms_apply_the_same_default(creator):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])
    group = PersonGroupFactory(shared_with=[creator])
    PersonFactory(user_link=UserFactory(), groups=[group])

    person_form = PersonRelationForm(person_id=person.person_id, user=creator)
    group_form = PersonGroupRelationForm(group_id=group.group_id, user=creator)

    assert person_form["is_surprise"].value() is True
    assert group_form["is_surprise"].value() is True


def test_gift_create_form_uses_its_initial_recipient(creator, gift):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])

    form = GiftRelationForm(
        gift_id=gift.gift_id, initial={"recipient": f"person:{person.person_id}"}, user=creator
    )

    assert form["is_surprise"].value() is True


def test_duplicating_a_surprise_plan_keeps_the_flag_whatever_the_default(creator):
    source = RelationFactory(is_surprise=True)
    initial = duplicate_initial(source)
    assert initial["is_surprise"] is True

    form = RelationForm(initial=initial, user=creator)

    assert form["is_surprise"].value() is True


# --- the recipient is the creator ---------------------------------------------------------


def test_field_is_absent_when_the_recipient_is_the_creators_own_person(creator):
    person = PersonFactory(user_link=creator)

    form = RelationForm(initial={"recipient": f"person:{person.person_id}"}, user=creator)

    assert "is_surprise" not in form.fields


def test_posting_the_flag_for_the_creators_own_person_saves_false(creator, gift):
    person = PersonFactory(user_link=creator)

    form = RelationForm(
        data=_data(gift, recipient=f"person:{person.person_id}", is_surprise="on"), user=creator
    )

    assert form.is_valid(), form.errors
    assert form.save().is_surprise is False


# --- saving ---------------------------------------------------------------------------------


def test_the_checkbox_is_saved_when_ticked_and_when_cleared(creator, gift):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])
    recipient = f"person:{person.person_id}"

    ticked = RelationForm(data=_data(gift, recipient=recipient, is_surprise="on"), user=creator)
    cleared = RelationForm(data=_data(gift, recipient=recipient), user=creator)

    assert ticked.is_valid(), ticked.errors
    assert ticked.save().is_surprise is True
    assert cleared.is_valid(), cleared.errors
    assert cleared.save().is_surprise is False


# --- editing --------------------------------------------------------------------------------


@pytest.mark.parametrize("level", [PermissionLevel.EDITOR, PermissionLevel.OWNER])
def test_editors_and_owners_see_the_field_on_edit(creator, level):
    relation = RelationFactory(person=PersonFactory(user_link=UserFactory()))
    _share(relation, creator, level, "relation")

    form = RelationForm(instance=relation, user=creator)

    assert "is_surprise" in form.fields


def test_viewers_do_not_get_the_field_and_cannot_change_the_flag(creator, gift):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])
    relation = RelationFactory(person=person, gift=gift, is_surprise=True)
    _share(relation, creator, PermissionLevel.VIEWER, "relation")

    form = RelationForm(
        instance=relation,
        data=_data(gift, recipient=f"person:{person.person_id}", status=str(relation.status_id)),
        user=creator,
    )

    assert "is_surprise" not in form.fields
    assert form.is_valid(), form.errors
    assert form.save().is_surprise is True


def test_editing_a_plan_keeps_the_flag_when_the_field_is_left_ticked(creator, gift):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])
    relation = RelationFactory(person=person, gift=gift, is_surprise=True)
    _share(relation, creator, PermissionLevel.OWNER, "relation")
    data = _data(
        gift,
        recipient=f"person:{person.person_id}",
        status=str(relation.status_id),
        is_surprise="on",
    )

    form = RelationForm(instance=relation, data=data, user=creator)

    assert form.is_valid(), form.errors
    assert form.save().is_surprise is True


def test_field_is_absent_and_flag_forced_off_when_the_recipient_owns_the_plan(creator, gift):
    recipient_user = UserFactory()
    person = PersonFactory(user_link=recipient_user, shared_with=[creator])
    relation = RelationFactory(person=person, gift=gift, is_surprise=True)
    _share(relation, recipient_user, PermissionLevel.OWNER, "relation")
    _share(relation, creator, PermissionLevel.EDITOR, "relation")
    data = _data(
        gift,
        recipient=f"person:{person.person_id}",
        status=str(relation.status_id),
        is_surprise="on",
    )

    form = RelationForm(instance=relation, data=data, user=creator)

    assert "is_surprise" not in form.fields
    assert form.is_valid(), form.errors
    assert form.save().is_surprise is False


def test_group_plan_edit_keeps_the_field_even_if_an_owner_is_a_member(creator, gift):
    group = PersonGroupFactory(shared_with=[creator])
    PersonFactory(user_link=creator, groups=[group])
    relation = GroupRelationFactory(group=group, gift=gift)
    _share(relation, creator, PermissionLevel.OWNER, "relation")

    form = RelationForm(instance=relation, user=creator)

    assert "is_surprise" in form.fields
