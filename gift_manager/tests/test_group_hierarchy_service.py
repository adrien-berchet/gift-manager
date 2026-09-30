"""Tests for group hierarchy and membership authority (GM-AUD-001)."""

import pytest
from django.core.exceptions import PermissionDenied

from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.models import PersonGroupPermission
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level, *, inherit=False):
    create_or_update_permission(user, obj, permission_level=level)
    if inherit:
        PersonGroupPermission.objects.filter(user=user, group=obj).update(inherit_permissions=True)


@pytest.fixture
def actor():
    return UserFactory()


@pytest.fixture
def other():
    return UserFactory()


class TestParentLinks:
    def test_editor_on_both_sides_can_link(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.EDITOR)

        GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert list(child.parent_groups.all()) == [parent]

    def test_viewer_only_parent_is_rejected(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.VIEWER)
        _grant(actor, child, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert not child.parent_groups.exists()

    def test_viewer_only_child_is_rejected_when_adding_child(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.VIEWER)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_children(actor, parent, add=[child])

        assert not parent.child_groups.exists()

    def test_removing_link_to_viewer_only_parent_is_rejected(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        child.parent_groups.add(parent)
        _grant(actor, parent, PermissionLevel.VIEWER)
        _grant(actor, child, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, remove=[parent])

        assert child.parent_groups.filter(pk=parent.pk).exists()

    def test_editor_cannot_expand_inherited_access(self, actor, other):
        """Editor of the child + editor of an inheritable parent must not share the child."""
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert not child.parent_groups.exists()

    def test_owner_can_expand_inherited_access(self, actor, other):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.OWNER)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert child.parent_groups.filter(pk=parent.pk).exists()

    def test_link_that_expands_nothing_is_allowed_for_editor(self, actor, other):
        """The inheritable grantee already holds equal access on the child."""
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)
        _grant(other, child, PermissionLevel.EDITOR)

        GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert child.parent_groups.filter(pk=parent.pk).exists()

    def test_editor_cannot_grant_self_owner_via_inheritable_parent(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.OWNER, inherit=True)
        _grant(actor, child, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[parent])

    def test_change_is_atomic(self, actor):
        allowed, denied, child = PersonGroupFactory(), PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, allowed, PermissionLevel.EDITOR)
        _grant(actor, denied, PermissionLevel.VIEWER)
        _grant(actor, child, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[allowed, denied])

        assert not child.parent_groups.exists()

    def test_new_group_is_treated_as_owned_by_actor(self, actor, other):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        GroupHierarchyService.change_parents(actor, child, add=[parent], group_is_new=True)

        assert child.parent_groups.filter(pk=parent.pk).exists()

    def test_new_group_still_requires_editor_on_the_other_side(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.VIEWER)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[parent], group_is_new=True)


class TestMembers:
    def test_editor_on_group_and_person_can_add(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, person, PermissionLevel.EDITOR)

        GroupHierarchyService.change_members(actor, group, add=[person])

        assert group.person_set.filter(pk=person.pk).exists()

    def test_viewer_only_person_cannot_be_added(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, person, PermissionLevel.VIEWER)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_members(actor, group, add=[person])

    def test_inaccessible_person_cannot_be_removed(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        person.groups.add(group)
        _grant(actor, group, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_members(actor, group, remove=[person])

        assert group.person_set.filter(pk=person.pk).exists()

    def test_viewer_of_group_cannot_change_members(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.VIEWER)
        _grant(actor, person, PermissionLevel.OWNER)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_members(actor, group, add=[person])


class TestEditableFilter:
    def test_editable_pks_excludes_viewer_only(self, actor):
        editable, viewer_only = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, editable, PermissionLevel.EDITOR)
        _grant(actor, viewer_only, PermissionLevel.VIEWER)

        pks = GroupHierarchyService.editable_pks(actor, [editable, viewer_only])

        assert pks == {editable.pk}


class TestDescendantExpansion:
    def test_owner_of_child_but_editor_of_descendant_cannot_expand(self, actor, other):
        parent, child, grandchild = (PersonGroupFactory() for _ in range(3))
        grandchild.parent_groups.add(child)
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.OWNER)
        _grant(actor, grandchild, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)
        _grant(other, child, PermissionLevel.EDITOR)  # child itself already covered

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_parents(actor, child, add=[parent])

    def test_owner_of_whole_subtree_can_expand(self, actor, other):
        parent, child, grandchild = (PersonGroupFactory() for _ in range(3))
        grandchild.parent_groups.add(child)
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.OWNER)
        _grant(actor, grandchild, PermissionLevel.OWNER)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        GroupHierarchyService.change_parents(actor, child, add=[parent])

        assert child.parent_groups.filter(pk=parent.pk).exists()


class TestPersonGroups:
    def test_viewer_only_group_is_rejected(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.VIEWER)
        _grant(actor, person, PermissionLevel.EDITOR)

        with pytest.raises(PermissionDenied):
            GroupHierarchyService.change_person_groups(actor, person, add=[group])

        assert not person.groups.exists()

    def test_new_person_needs_no_permission_yet(self, actor):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.EDITOR)

        GroupHierarchyService.change_person_groups(actor, person, add=[group], person_is_new=True)

        assert person.groups.filter(pk=group.pk).exists()


class TestEditablePksIsBulk:
    def test_query_count_does_not_grow_with_group_count(self, actor, django_assert_max_num_queries):
        groups = [PersonGroupFactory() for _ in range(25)]
        for group in groups:
            _grant(actor, group, PermissionLevel.EDITOR)

        with django_assert_max_num_queries(8):
            pks = GroupHierarchyService.editable_pks(actor, groups)

        assert pks == {g.pk for g in groups}

    def test_query_count_does_not_grow_with_person_count(
        self, actor, django_assert_max_num_queries
    ):
        persons = [PersonFactory() for _ in range(25)]
        for person in persons[:10]:
            _grant(actor, person, PermissionLevel.EDITOR)

        with django_assert_max_num_queries(4):
            pks = GroupHierarchyService.editable_pks(actor, persons)

        assert pks == {p.pk for p in persons[:10]}

    def test_inherited_editor_and_user_link_owner_count_as_editable(self, actor):
        parent, child, unrelated = (PersonGroupFactory() for _ in range(3))
        child.parent_groups.add(parent)
        _grant(actor, parent, PermissionLevel.EDITOR, inherit=True)
        own_person, other_person = PersonFactory(user_link=actor), PersonFactory()

        assert GroupHierarchyService.editable_pks(actor, [parent, child, unrelated]) == {
            parent.pk,
            child.pk,
        }
        assert GroupHierarchyService.editable_pks(actor, [own_person, other_person]) == {
            own_person.pk
        }

    def test_viewer_inherited_grant_is_not_editable(self, actor):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        child.parent_groups.add(parent)
        _grant(actor, parent, PermissionLevel.VIEWER, inherit=True)

        assert GroupHierarchyService.editable_pks(actor, [parent, child]) == set()

    def test_superuser_can_edit_everything(self):
        admin = UserFactory(is_superuser=True)
        groups = [PersonGroupFactory(), PersonGroupFactory()]

        assert GroupHierarchyService.editable_pks(admin, groups) == {g.pk for g in groups}
