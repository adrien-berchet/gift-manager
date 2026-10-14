"""Hierarchy-dependent paths follow the live group tree, in a constant number of queries.

Each test poisons the hierarchy cache with a stale value: the code under test must ignore it
and resolve the tree with a recursive query instead of one query per group.
"""

import pytest
from django.core.cache import cache
from django.urls import reverse

from gift_manager.gift_history import group_history_queryset
from gift_manager.gift_history import person_history_queryset
from gift_manager.group_hierarchy_service import GroupHierarchyService
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _child_of(parent, **kwargs):
    child = PersonGroupFactory(**kwargs)
    child.parent_groups.add(parent)
    return child


def _poison(kind, node):
    """Store a stale (empty) hierarchy for ``node`` in the cache."""
    cache.set(f"{node._meta.model_name}_{kind}_{node.pk}", [], 3600)


def _tag_child_of(parent, **kwargs):
    child = GiftTagFactory(**kwargs)
    child.parent_tags.add(parent)
    return child


def _tag_tree(user):
    """Return a tag, a visible grandchild and a private child, with one gift on each."""
    root = GiftTagFactory(shared_with=[user])
    grandchild = _tag_child_of(_tag_child_of(root, shared_with=[user]), shared_with=[user])
    private = _tag_child_of(root, shared_with=[UserFactory()])
    gifts = {}
    for name, tag in (("root", root), ("grandchild", grandchild), ("private", private)):
        gifts[name] = GiftFactory(name=f"Gift on {name}", shared_with=[user])
        gifts[name].tags.add(tag)
    _poison("descendants", root)
    return root, gifts


def _grant(user, group, level, *, inherit=False):
    PersonGroupPermission.objects.update_or_create(
        user=user,
        group=group,
        defaults={"permission_type": level, "inherit_permissions": inherit},
    )


class TestHierarchySubqueryStart:
    def test_accepts_nodes_and_an_empty_start(self):
        root = PersonGroupFactory()
        child = _child_of(root)
        grandchild = _child_of(child)

        from_nodes = PersonGroup.objects.filter(pk__in=PersonGroup.hierarchy_subquery([root]))
        from_empty = PersonGroup.objects.filter(pk__in=PersonGroup.hierarchy_subquery([]))

        assert set(from_nodes) == {child, grandchild}
        assert not from_empty.exists()


class TestPersonHistory:
    def test_includes_plans_of_ancestor_groups_in_one_query(self, django_assert_num_queries):
        user = UserFactory()
        root = PersonGroupFactory()
        first = _child_of(_child_of(root))
        second = PersonGroupFactory()
        person = PersonFactory(groups=[first, second])
        plans = [GroupRelationFactory(group=group, shared_with=[user]) for group in (root, second)]
        _poison("ancestors", first)

        with django_assert_num_queries(1):
            history = set(person_history_queryset(user, person))

        assert history == set(plans)


class TestEditableGroups:
    def test_cascading_editor_permission_opens_descendants_in_one_query(
        self, django_assert_num_queries
    ):
        actor = UserFactory()
        root = PersonGroupFactory()
        child = _child_of(root)
        grandchild = _child_of(child)
        viewer_only = _child_of(PersonGroupFactory())
        _grant(actor, root, PermissionLevel.EDITOR, inherit=True)
        _grant(actor, viewer_only.parent_groups.get(), PermissionLevel.VIEWER, inherit=True)
        _poison("descendants", root)

        with django_assert_num_queries(1):
            editable = GroupHierarchyService.editable_pks(
                actor, [root, child, grandchild, viewer_only]
            )

        assert editable == {root.pk, child.pk, grandchild.pk}


class TestEffectiveGroupPermission:
    def test_inherited_permission_follows_the_live_tree_in_one_query(
        self, django_assert_num_queries
    ):
        user = UserFactory()
        root = PersonGroupFactory()
        child = _child_of(_child_of(root))
        _grant(user, root, PermissionLevel.OWNER, inherit=True)
        _grant(user, child, PermissionLevel.VIEWER)
        _poison("ancestors", child)

        with django_assert_num_queries(1):
            level = PermissionService.get_effective_permission_for_group(child, user)

        assert level == PermissionLevel.OWNER

    def test_non_cascading_ancestor_permission_is_ignored(self):
        user = UserFactory()
        root = PersonGroupFactory()
        child = _child_of(root)
        _grant(user, root, PermissionLevel.OWNER)

        assert (
            PermissionService.get_effective_permission_for_group(child, user)
            == PermissionLevel.NONE
        )


class TestShareChildGroups:
    def test_sharing_with_children_reaches_the_live_descendants(self, client):
        owner = UserFactory()
        friend = UserFactory()
        owner.profile.friends.add(friend.profile)
        root = PersonGroupFactory()
        grandchild = _child_of(_child_of(root))
        for group in PersonGroup.objects.all():
            create_or_update_permission(
                owner, group, permission_level=PermissionLevel.OWNER, object_attr="group"
            )
        _poison("descendants", root)
        client.force_login(owner)

        response = client.post(
            reverse("gift_manager:share_objects"),
            {
                "person_groups": [root.group_id],
                "friends": [friend.id],
                "permission_level": PermissionLevel.VIEWER,
                "share_child_groups": "on",
            },
        )

        assert response.status_code == 302
        assert get_permission(grandchild, friend, "group") == PermissionLevel.VIEWER


class TestPersonDetailAncestors:
    def test_shows_live_ancestor_groups_and_their_plans(self, client):
        viewer = UserFactory()
        root = PersonGroupFactory(name="RootAncestorXyz", shared_with=[viewer])
        group = _child_of(root, shared_with=[viewer])
        person = PersonFactory(groups=[group], shared_with=[viewer])
        plan = GroupRelationFactory(group=root, shared_with=[viewer])
        _poison("ancestors", group)
        client.force_login(viewer)

        response = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert response.status_code == 200
        assert [g.pk for g in response.context["ancestor_groups"]] == [root.pk]
        assert plan in response.context["relations"]


class TestGroupHistory:
    def test_includes_plans_of_members_of_descendant_groups(self):
        user = UserFactory()
        root = PersonGroupFactory()
        member = PersonFactory(groups=[_child_of(_child_of(root))])
        plan = RelationFactory(person=member, shared_with=[user])
        _poison("descendants", root)

        assert plan in group_history_queryset(user, root)


class TestTagGifts:
    def test_all_gifts_follow_the_live_tree_and_skip_private_tags(self, django_assert_num_queries):
        user = UserFactory()
        root, gifts = _tag_tree(user)

        with django_assert_num_queries(2):
            for_user = set(root.get_all_gifts(user))

        assert for_user == {gifts["root"], gifts["grandchild"]}
        assert set(root.get_all_gifts()) == set(gifts.values())

    def test_explorer_lists_gifts_of_live_descendants(self, client):
        user = UserFactory()
        root, gifts = _tag_tree(user)
        client.force_login(user)

        response = client.get(
            reverse("gift_manager:gift_tag_explorer_with_tag", args=[root.tag_id])
        )

        assert response.status_code == 200
        assert set(response.context["gifts"]) == {gifts["root"], gifts["grandchild"]}


class TestGroupDetailNestedContent:
    def test_shows_members_and_plans_of_live_accessible_descendants(self, client):
        viewer = UserFactory()
        root = PersonGroupFactory(shared_with=[viewer])
        grandchild = _child_of(_child_of(root, shared_with=[viewer]), shared_with=[viewer])
        private = _child_of(root, shared_with=[UserFactory()])
        member = PersonFactory(groups=[grandchild], shared_with=[viewer])
        plans = {
            name: GroupRelationFactory(group=group, shared_with=[viewer])
            for name, group in (("grandchild", grandchild), ("private", private))
        }
        _poison("descendants", root)
        client.force_login(viewer)

        response = client.get(reverse("gift_manager:person_group_detail", args=[root.group_id]))

        assert response.status_code == 200
        assert member in response.context["nested_members"]
        assert plans["grandchild"] in response.context["nested_gifts"]
        assert plans["private"] not in response.context["nested_gifts"]
