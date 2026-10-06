"""Rules of claiming, commenting and the surprise flag (``gift_manager.plan_coordination``)."""

import pytest
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.utils import translation

from gift_manager import plan_coordination
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationComment
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _share(relation, user, level):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


@pytest.fixture
def relation():
    return RelationFactory()


@pytest.fixture
def owner(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.OWNER)
    return user


@pytest.fixture
def editor(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.EDITOR)
    return user


@pytest.fixture
def viewer(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.VIEWER)
    return user


@pytest.fixture
def stranger():
    return UserFactory()


# --- claim -------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["viewer", "editor", "owner"])
def test_every_collaborator_can_claim_a_free_plan(request, relation, role):
    user = request.getfixturevalue(role)

    plan_coordination.claim(relation, user)

    relation.refresh_from_db()
    assert relation.claimed_by == user
    assert relation.claimed_at is not None


def test_stranger_cannot_claim(relation, stranger):
    with pytest.raises(PermissionDenied):
        plan_coordination.claim(relation, stranger)


def test_claiming_twice_by_the_same_user_changes_nothing(relation, viewer):
    plan_coordination.claim(relation, viewer)
    relation.refresh_from_db()
    first_claimed_at = relation.claimed_at

    plan_coordination.claim(relation, viewer)

    relation.refresh_from_db()
    assert relation.claimed_at == first_claimed_at


def test_claim_is_refused_while_someone_else_holds_it(relation, viewer, editor):
    plan_coordination.claim(relation, viewer)

    with pytest.raises(plan_coordination.AlreadyClaimed) as raised:
        plan_coordination.claim(relation, editor)

    assert raised.value.claimed_by == viewer
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


def test_a_stale_copy_of_the_plan_cannot_override_a_claim(relation, viewer, editor):
    stale_copy = Relation.objects.get(pk=relation.pk)
    plan_coordination.claim(relation, viewer)

    with pytest.raises(plan_coordination.AlreadyClaimed):
        plan_coordination.claim(stale_copy, editor)

    assert Relation.objects.get(pk=relation.pk).claimed_by == viewer


# --- release -----------------------------------------------------------------------------


def test_claimer_can_release(relation, viewer):
    plan_coordination.claim(relation, viewer)

    plan_coordination.release(relation, viewer)

    relation.refresh_from_db()
    assert relation.claimed_by is None
    assert relation.claimed_at is None


def test_owner_can_release_anyones_claim(relation, viewer, owner):
    plan_coordination.claim(relation, viewer)

    plan_coordination.release(relation, owner)

    relation.refresh_from_db()
    assert relation.claimed_by is None


def test_editor_cannot_release_someone_elses_claim(relation, viewer, editor):
    plan_coordination.claim(relation, viewer)

    with pytest.raises(PermissionDenied):
        plan_coordination.release(relation, editor)

    relation.refresh_from_db()
    assert relation.claimed_by == viewer


def test_releasing_an_unclaimed_plan_is_a_no_op(relation, viewer):
    plan_coordination.release(relation, viewer)

    relation.refresh_from_db()
    assert relation.claimed_by is None


# --- comments ----------------------------------------------------------------------------


def test_viewer_can_comment_and_the_text_is_stripped(relation, viewer):
    comment = plan_coordination.add_comment(relation, viewer, "  I can pick it up  ")

    assert comment.author == viewer
    assert comment.relation == relation
    assert comment.text == "I can pick it up"


def test_stranger_cannot_comment(relation, stranger):
    with pytest.raises(PermissionDenied):
        plan_coordination.add_comment(relation, stranger, "hello")

    assert RelationComment.objects.count() == 0


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_comment_is_rejected(relation, viewer, text):
    with pytest.raises(ValidationError):
        plan_coordination.add_comment(relation, viewer, text)

    assert RelationComment.objects.count() == 0


def test_comment_length_limit(relation, viewer):
    limit = plan_coordination.MAX_COMMENT_LENGTH
    assert limit == 2000

    plan_coordination.add_comment(relation, viewer, "a" * limit)
    with pytest.raises(ValidationError):
        plan_coordination.add_comment(relation, viewer, "a" * (limit + 1))


def test_html_in_a_comment_is_stored_verbatim(relation, viewer):
    comment = plan_coordination.add_comment(relation, viewer, "<b>x</b>")

    assert comment.text == "<b>x</b>"


def test_author_and_owner_can_delete_a_comment(relation, viewer, owner):
    own = plan_coordination.add_comment(relation, viewer, "mine")
    other = plan_coordination.add_comment(relation, viewer, "theirs")

    plan_coordination.delete_comment(own, viewer)
    plan_coordination.delete_comment(other, owner)

    assert RelationComment.objects.count() == 0


def test_other_editor_cannot_delete_a_comment(relation, viewer, editor):
    comment = plan_coordination.add_comment(relation, viewer, "mine")

    with pytest.raises(PermissionDenied):
        plan_coordination.delete_comment(comment, editor)

    assert RelationComment.objects.count() == 1


# --- surprise flag -----------------------------------------------------------------------


def test_viewer_cannot_change_the_surprise_flag(relation, viewer):
    with pytest.raises(PermissionDenied):
        plan_coordination.set_surprise(relation, viewer, value=True)


@pytest.mark.parametrize("role", ["editor", "owner"])
def test_editor_and_owner_can_set_and_clear_the_surprise_flag(request, relation, role):
    user = request.getfixturevalue(role)

    plan_coordination.set_surprise(relation, user, value=True)
    relation.refresh_from_db()
    assert relation.is_surprise is True

    plan_coordination.set_surprise(relation, user, value=False)
    relation.refresh_from_db()
    assert relation.is_surprise is False


def test_surprise_is_stored_as_false_when_the_recipient_owns_the_plan(editor):
    recipient = UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient))
    _share(relation, recipient, PermissionLevel.OWNER)
    _share(relation, editor, PermissionLevel.EDITOR)

    plan_coordination.set_surprise(relation, editor, value=True)

    relation.refresh_from_db()
    assert relation.is_surprise is False


def test_the_hidden_recipient_cannot_claim_or_comment(editor):
    recipient = UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=True)
    _share(relation, recipient, PermissionLevel.EDITOR)

    with pytest.raises(PermissionDenied):
        plan_coordination.claim(relation, recipient)
    with pytest.raises(PermissionDenied):
        plan_coordination.add_comment(relation, recipient, "hi")


def test_can_be_surprise_is_false_when_the_recipient_owns_the_plan():
    recipient = UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient))
    _share(relation, recipient, PermissionLevel.OWNER)

    assert plan_coordination.can_be_surprise(relation) is False


def test_can_be_surprise_is_true_for_a_linked_recipient_who_is_not_an_owner(owner):
    relation = RelationFactory(person=PersonFactory(user_link=UserFactory()))
    _share(relation, owner, PermissionLevel.OWNER)

    assert plan_coordination.can_be_surprise(relation) is True


def test_can_be_surprise_is_true_for_any_group(owner):
    group = PersonGroupFactory()
    PersonFactory(user_link=owner, groups=[group])
    relation = GroupRelationFactory(group=group)
    _share(relation, owner, PermissionLevel.OWNER)

    assert plan_coordination.can_be_surprise(relation) is True


# --- default for new plans ---------------------------------------------------------------


def test_default_is_on_for_a_person_linked_to_another_user():
    person = PersonFactory(user_link=UserFactory())

    assert plan_coordination.default_surprise_for(person, UserFactory()) is True


def test_default_is_off_for_the_creators_own_person():
    creator = UserFactory()

    assert (
        plan_coordination.default_surprise_for(PersonFactory(user_link=creator), creator) is False
    )


def test_default_is_off_for_an_unlinked_person_and_for_no_recipient():
    assert plan_coordination.default_surprise_for(PersonFactory(), UserFactory()) is False
    assert plan_coordination.default_surprise_for(None, UserFactory()) is False


def test_default_is_on_for_a_group_with_a_linked_member():
    group = PersonGroupFactory()
    PersonFactory(user_link=UserFactory(), groups=[group])

    assert plan_coordination.default_surprise_for(group, UserFactory()) is True


def test_default_is_on_when_the_linked_member_is_in_a_nested_group():
    group, child = PersonGroupFactory(), PersonGroupFactory()
    child.parent_groups.add(group)
    PersonFactory(user_link=UserFactory(), groups=[child])

    assert plan_coordination.default_surprise_for(group, UserFactory()) is True


def test_default_is_off_for_a_group_whose_only_linked_member_is_the_creator():
    creator = UserFactory()
    group = PersonGroupFactory()
    PersonFactory(user_link=creator, groups=[group])
    PersonFactory(groups=[group])

    assert plan_coordination.default_surprise_for(group, creator) is False


# --- sharing a surprise plan with someone who cannot see it ----------------------------------


def test_hidden_recipient_ids_for_a_person_recipient_and_the_owner_exemption():
    recipient, owner = UserFactory(), UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=True)
    _share(relation, owner, PermissionLevel.OWNER)

    assert plan_coordination.hidden_recipient_ids(relation) == {recipient.pk}

    _share(relation, recipient, PermissionLevel.OWNER)
    assert plan_coordination.hidden_recipient_ids(relation) == set()


def test_hidden_recipient_ids_for_a_group_include_nested_members():
    direct, nested, parent_member = UserFactory(), UserFactory(), UserFactory()
    group, child, parent = PersonGroupFactory(), PersonGroupFactory(), PersonGroupFactory()
    child.parent_groups.add(group)
    group.parent_groups.add(parent)
    PersonFactory(user_link=direct, groups=[group])
    PersonFactory(user_link=nested, groups=[child])
    PersonFactory(user_link=parent_member, groups=[parent])
    PersonFactory(groups=[group])
    relation = GroupRelationFactory(group=group, is_surprise=True)

    assert plan_coordination.hidden_recipient_ids(relation) == {direct.pk, nested.pk}


def test_hidden_recipient_ids_is_empty_when_the_plan_is_not_a_surprise():
    relation = RelationFactory(person=PersonFactory(user_link=UserFactory()), is_surprise=False)

    assert plan_coordination.hidden_recipient_ids(relation) == set()


def test_hidden_recipient_ids_agrees_with_hidden_surprises_for():
    users = [UserFactory() for _ in range(3)]
    group = PersonGroupFactory()
    PersonFactory(user_link=users[0], groups=[group])
    relation = GroupRelationFactory(group=group, is_surprise=True)

    hidden = plan_coordination.hidden_recipient_ids(relation)

    for user in users:
        in_queryset = Relation.objects.hidden_surprises_for(user).filter(pk=relation.pk).exists()
        assert (user.pk in hidden) is in_queryset


def test_sharing_warning_names_only_the_people_who_cannot_see_the_plan():
    recipient, other = UserFactory(), UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=True)

    warning = plan_coordination.surprise_sharing_warning(relation, [recipient, other])

    assert recipient.username in warning
    assert other.username not in warning
    assert str(relation.gift.name) in warning
    assert plan_coordination.surprise_sharing_warning(relation, [other]) == ""


def test_sharing_warning_is_translated_and_agrees_in_number():
    first, second = UserFactory(username="anna"), UserFactory(username="ben")
    group = PersonGroupFactory()
    PersonFactory(user_link=first, groups=[group])
    PersonFactory(user_link=second, groups=[group])
    relation = GroupRelationFactory(group=group, is_surprise=True)

    with translation.override("fr"):
        one = plan_coordination.surprise_sharing_warning(relation, [first])
        two = plan_coordination.surprise_sharing_warning(relation, [first, second])

    assert "anna ne pourra pas voir" in one
    assert "anna, ben ne pourront pas voir" in two


def test_hidden_recipient_ids_of_a_plan_without_a_recipient_is_empty():
    assert plan_coordination.hidden_recipient_ids(Relation(is_surprise=True)) == set()
