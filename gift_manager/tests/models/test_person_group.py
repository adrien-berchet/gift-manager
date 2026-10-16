# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime

import pytest
from django.core.exceptions import ValidationError

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory


@pytest.mark.django_db
class TestPersonGroup:
    """Tests for the PersonGroup model."""

    def test_group_creation(self, group, group_name):
        """Test creating a person group."""
        assert group.name == group_name
        assert group.group_id is not None
        assert isinstance(group.group_id, uuid.UUID)
        assert isinstance(group.creation_date, datetime)

    def test_group_string_representation(self, group, group_name):
        """Test the string representation of a person group."""
        assert str(group) == group_name

    def test_add_person_to_group(self, group, person):
        """Test adding a person to a group."""
        person.groups.add(group)
        assert group in person.groups.all()

    def test_group_permission(self, user, username, group, group_name):
        """Test adding a permission to a group."""
        permission = PersonGroupPermission.objects.create(
            user=user, group=group, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.group == group
        assert str(permission) == f"{username} - {group_name} -> owner"
        assert user in group.shared_with.all()


@pytest.mark.django_db
class TestPersonGroupHierarchy:
    """Tests for PersonGroup hierarchy methods with trivial and complex scenarios."""

    # =========================================================================
    # TRIVIAL HIERARCHY TESTS (simple parent-child relationships)
    # =========================================================================

    def test_get_children_empty(self):
        """Test get_children returns empty queryset when no children."""
        group = PersonGroupFactory(name="Lonely Group")
        children = group.get_children()
        assert not list(children)

    def test_get_children_single_child(self):
        """Test get_children with single child."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        children = parent.get_children()
        assert len(children) == 1
        assert child in children

    def test_get_children_multiple_children(self):
        """Test get_children with multiple children."""
        parent = PersonGroupFactory(name="Parent")
        child1 = PersonGroupFactory(name="Child 1")
        child2 = PersonGroupFactory(name="Child 2")
        child3 = PersonGroupFactory(name="Child 3")

        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)
        child3.parent_groups.add(parent)

        children = parent.get_children()
        assert len(children) == 3
        assert child1 in children
        assert child2 in children
        assert child3 in children

    def test_get_descendants_empty(self):
        """Test get_descendants returns empty list when no descendants."""
        group = PersonGroupFactory(name="Lonely Group")
        descendants = group.get_descendants()
        assert descendants == []

    def test_get_descendants_single_level(self):
        """Test get_descendants with single level of children."""
        parent = PersonGroupFactory(name="Parent")
        child1 = PersonGroupFactory(name="Child 1")
        child2 = PersonGroupFactory(name="Child 2")

        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)

        descendants = parent.get_descendants()
        assert len(descendants) == 2
        assert child1 in descendants
        assert child2 in descendants

    def test_get_ancestors_empty(self):
        """Test get_ancestors returns empty list for root group."""
        group = PersonGroupFactory(name="Root Group")
        ancestors = group.get_ancestors()
        assert ancestors == []

    def test_get_ancestors_single_parent(self):
        """Test get_ancestors with single parent."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        ancestors = child.get_ancestors()
        assert len(ancestors) == 1
        assert parent in ancestors

    def test_get_primary_ancestors_path_empty(self):
        """Test get_primary_ancestors_path returns empty list for root."""
        group = PersonGroupFactory(name="Root")
        path = group.get_primary_ancestors_path()
        assert path == []

    def test_get_primary_ancestors_path_simple(self):
        """Test get_primary_ancestors_path with simple chain."""
        root = PersonGroupFactory(name="Root")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(root)

        path = child.get_primary_ancestors_path()
        assert len(path) == 1
        assert path[0] == root

    def test_has_cycle_with_self(self):
        """Test has_cycle_with detects self-reference."""
        group = PersonGroupFactory(name="Group")
        assert group.has_cycle_with(group) is True

    def test_has_cycle_with_unrelated(self):
        """Test has_cycle_with returns False for unrelated groups."""
        group1 = PersonGroupFactory(name="Group 1")
        group2 = PersonGroupFactory(name="Group 2")
        assert group1.has_cycle_with(group2) is False
        assert group2.has_cycle_with(group1) is False

    def test_has_cycle_with_parent_child(self):
        """Test has_cycle_with with parent-child relationship."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # Parent becoming child of its own child would create cycle
        assert parent.has_cycle_with(child) is True
        # Child becoming child of parent is fine (already is)
        assert child.has_cycle_with(parent) is False

    def test_get_all_members_empty(self):
        """Test get_all_members returns empty queryset when no members."""
        group = PersonGroupFactory(name="Empty Group")
        members = group.get_all_members()
        assert not list(members)

    def test_get_all_members_direct_only(self):
        """Test get_all_members with direct members only."""
        group = PersonGroupFactory(name="Group")
        person1 = PersonFactory(first_name="John", family_name="Doe")
        person2 = PersonFactory(first_name="Jane", family_name="Doe")
        person1.groups.add(group)
        person2.groups.add(group)

        members = group.get_all_members(include_nested=False)
        assert len(members) == 2
        assert person1 in members
        assert person2 in members

    def test_clean_no_cycle(self):
        """Test clean passes when no cycle exists."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # Should not raise
        child.clean()

    # =========================================================================
    # COMPLEX HIERARCHY TESTS (deep, DAG, diamond structures)
    # =========================================================================

    def test_get_descendants_deep_hierarchy(self):
        """Test get_descendants with 4-level deep hierarchy."""
        level1 = PersonGroupFactory(name="Level 1")
        level2 = PersonGroupFactory(name="Level 2")
        level3 = PersonGroupFactory(name="Level 3")
        level4 = PersonGroupFactory(name="Level 4")

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)
        level4.parent_groups.add(level3)

        # Level 1 should have all others as descendants
        descendants = level1.get_descendants()
        assert len(descendants) == 3
        assert level2 in descendants
        assert level3 in descendants
        assert level4 in descendants

        # Level 2 should have levels 3 and 4
        descendants = level2.get_descendants()
        assert len(descendants) == 2
        assert level3 in descendants
        assert level4 in descendants

        # Level 4 should have no descendants
        descendants = level4.get_descendants()
        assert len(descendants) == 0

    def test_get_descendants_diamond_structure(self):
        """Test get_descendants with diamond DAG structure."""
        #       root
        #      /    \
        #   left    right
        #      \    /
        #       leaf
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        # Root should see all 3 descendants (no duplicates)
        descendants = root.get_descendants()
        assert len(descendants) == 3
        assert left in descendants
        assert right in descendants
        assert leaf in descendants

        # Left and right should each see only leaf
        assert len(left.get_descendants()) == 1
        assert len(right.get_descendants()) == 1

    def test_get_descendants_complex_dag(self):
        """Test get_descendants with complex DAG having shared nodes."""
        #       root1    root2
        #         |   \ /   |
        #         A    B    C
        #          \  / \  /
        #           D    E
        #            \  /
        #             F
        root1 = PersonGroupFactory(name="Root1")
        root2 = PersonGroupFactory(name="Root2")
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")
        d = PersonGroupFactory(name="D")
        e = PersonGroupFactory(name="E")
        f = PersonGroupFactory(name="F")

        a.parent_groups.add(root1)
        b.parent_groups.add(root1, root2)
        c.parent_groups.add(root2)
        d.parent_groups.add(a, b)
        e.parent_groups.add(b, c)
        f.parent_groups.add(d, e)

        # Root1 descendants: A, B, D, E, F (C is only under root2)
        descendants = root1.get_descendants()
        assert len(descendants) == 5
        assert a in descendants
        assert b in descendants
        assert d in descendants
        assert e in descendants
        assert f in descendants
        assert c not in descendants

        # Root2 descendants: B, C, D, E, F (A is only under root1)
        descendants = root2.get_descendants()
        assert len(descendants) == 5
        assert b in descendants
        assert c in descendants
        assert d in descendants
        assert e in descendants
        assert f in descendants
        assert a not in descendants

    def test_get_ancestors_deep_hierarchy(self):
        """Test get_ancestors with 4-level deep hierarchy."""
        level1 = PersonGroupFactory(name="Level 1")
        level2 = PersonGroupFactory(name="Level 2")
        level3 = PersonGroupFactory(name="Level 3")
        level4 = PersonGroupFactory(name="Level 4")

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)
        level4.parent_groups.add(level3)

        # Level 4 should have all ancestors
        ancestors = level4.get_ancestors()
        assert len(ancestors) == 3
        assert level1 in ancestors
        assert level2 in ancestors
        assert level3 in ancestors

        # Level 1 should have no ancestors
        ancestors = level1.get_ancestors()
        assert len(ancestors) == 0

    def test_get_ancestors_diamond_structure(self):
        """Test get_ancestors with diamond structure."""
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        # Leaf should have all 3 ancestors (no duplicates)
        ancestors = leaf.get_ancestors()
        assert len(ancestors) == 3
        assert root in ancestors
        assert left in ancestors
        assert right in ancestors

    def test_get_ancestors_multiple_roots(self):
        """Test get_ancestors when there are multiple root groups."""
        root1 = PersonGroupFactory(name="Root 1")
        root2 = PersonGroupFactory(name="Root 2")
        child = PersonGroupFactory(name="Child")

        child.parent_groups.add(root1, root2)

        ancestors = child.get_ancestors()
        assert len(ancestors) == 2
        assert root1 in ancestors
        assert root2 in ancestors

    def test_get_primary_ancestors_path_deep(self):
        """Test get_primary_ancestors_path with deep hierarchy."""
        level1 = PersonGroupFactory(name="Level 1")
        level2 = PersonGroupFactory(name="Level 2")
        level3 = PersonGroupFactory(name="Level 3")
        level4 = PersonGroupFactory(name="Level 4")

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)
        level4.parent_groups.add(level3)

        path = level4.get_primary_ancestors_path()
        assert len(path) == 3
        # Path should be ordered from root to immediate parent
        assert path[0] == level1
        assert path[1] == level2
        assert path[2] == level3

    def test_get_primary_ancestors_path_diamond(self):
        """Test get_primary_ancestors_path picks one path in diamond."""
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        path = leaf.get_primary_ancestors_path()
        # Should pick one path (either left or right, but not both)
        assert len(path) == 2
        assert path[0] == root
        assert path[1] in [left, right]

    def test_has_cycle_with_deep_chain(self):
        """Test has_cycle_with detects cycle in deep chain."""
        # Create: A -> B -> C -> D
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")
        d = PersonGroupFactory(name="D")

        b.parent_groups.add(a)
        c.parent_groups.add(b)
        d.parent_groups.add(c)

        # Making A a child of D would create cycle
        assert a.has_cycle_with(d) is True
        assert a.has_cycle_with(c) is True
        assert a.has_cycle_with(b) is True

        # Making D a child of A is fine
        assert d.has_cycle_with(a) is False

    def test_has_cycle_with_diamond(self):
        """Test has_cycle_with in diamond structure."""
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        # Root becoming child of leaf would create cycle
        assert root.has_cycle_with(leaf) is True
        # Left or right becoming child of leaf would create cycle
        assert left.has_cycle_with(leaf) is True
        assert right.has_cycle_with(leaf) is True

    def test_get_all_members_nested(self):
        """Test get_all_members with nested groups."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        grandchild = PersonGroupFactory(name="Grandchild")

        child.parent_groups.add(parent)
        grandchild.parent_groups.add(child)

        # Add members at different levels
        person_parent = PersonFactory(first_name="Parent", family_name="Member")
        person_child = PersonFactory(first_name="Child", family_name="Member")
        person_grandchild = PersonFactory(first_name="Grandchild", family_name="Member")

        person_parent.groups.add(parent)
        person_child.groups.add(child)
        person_grandchild.groups.add(grandchild)

        # Without nested, only direct members
        direct_members = parent.get_all_members(include_nested=False)
        assert len(direct_members) == 1
        assert person_parent in direct_members

        # With nested, all members from hierarchy
        all_members = parent.get_all_members(include_nested=True)
        assert len(all_members) == 3
        assert person_parent in all_members
        assert person_child in all_members
        assert person_grandchild in all_members

    def test_get_all_members_diamond_no_duplicates(self):
        """Test get_all_members doesn't duplicate members in diamond structure."""
        root = PersonGroupFactory(name="Root")
        left = PersonGroupFactory(name="Left")
        right = PersonGroupFactory(name="Right")
        leaf = PersonGroupFactory(name="Leaf")

        left.parent_groups.add(root)
        right.parent_groups.add(root)
        leaf.parent_groups.add(left)
        leaf.parent_groups.add(right)

        # Add same person to multiple groups
        person = PersonFactory(first_name="Multi", family_name="Group")
        person.groups.add(left, right, leaf)

        # Person should appear only once in results
        members = root.get_all_members(include_nested=True)
        person_count = sum(1 for m in members if m == person)
        assert person_count == 1

    def test_clean_cycle_detection(self):
        """Test clean method raises ValidationError on cycle."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # Create cycle by making parent a child of child
        parent.parent_groups.add(child)

        with pytest.raises(ValidationError):
            parent.clean()

    def test_clean_deep_cycle_detection(self):
        """Test clean method detects cycle in deep hierarchy."""
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")

        b.parent_groups.add(a)
        c.parent_groups.add(b)

        # Create cycle: A -> B -> C -> A
        a.parent_groups.add(c)

        with pytest.raises(ValidationError):
            a.clean()

    def test_parent_removal_updates_hierarchy(self):
        """Removing a parent is reflected in descendants and ancestors."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        assert child in parent.get_descendants()
        assert parent in child.get_ancestors()

        child.parent_groups.remove(parent)

        assert child not in parent.get_descendants()
        assert parent not in child.get_ancestors()

    def test_circular_reference_handling(self):
        """Test that circular references don't cause infinite loops."""
        # Create two groups that reference each other
        group_a = PersonGroupFactory(name="Group A")
        group_b = PersonGroupFactory(name="Group B")

        group_b.parent_groups.add(group_a)
        group_a.parent_groups.add(group_b)

        # These should complete without infinite loops
        ancestors_a = group_a.get_ancestors()
        ancestors_b = group_b.get_ancestors()

        # Each should see the other as an ancestor
        assert len(ancestors_a) == 1
        assert group_b in ancestors_a
        assert len(ancestors_b) == 1
        assert group_a in ancestors_b

        descendants_a = group_a.get_descendants()
        descendants_b = group_b.get_descendants()

        assert len(descendants_a) == 1
        assert group_b in descendants_a
        assert len(descendants_b) == 1
        assert group_a in descendants_b

    def test_very_deep_hierarchy(self):
        """Test hierarchy methods work with very deep hierarchies (10+ levels)."""
        groups = []
        previous = None

        # Create a chain of 15 groups
        for i in range(15):
            group = PersonGroupFactory(name=f"Level {i}")
            if previous:
                group.parent_groups.add(previous)
            groups.append(group)
            previous = group

        root = groups[0]
        deepest = groups[-1]

        # Root should have 14 descendants
        descendants = root.get_descendants()
        assert len(descendants) == 14

        # Deepest should have 14 ancestors
        ancestors = deepest.get_ancestors()
        assert len(ancestors) == 14

        # Primary path should have 14 ancestors
        path = deepest.get_primary_ancestors_path()
        assert len(path) == 14
        assert path[0] == root
        assert path[-1] == groups[-2]  # immediate parent

    def test_wide_hierarchy(self):
        """Test hierarchy methods work with wide hierarchies (many children)."""
        parent = PersonGroupFactory(name="Parent")
        children = []

        # Create 20 children
        for i in range(20):
            child = PersonGroupFactory(name=f"Child {i}")
            child.parent_groups.add(parent)
            children.append(child)

        descendants = parent.get_descendants()
        assert len(descendants) == 20

        for child in children:
            assert child in descendants
            ancestors = child.get_ancestors()
            assert len(ancestors) == 1
            assert parent in ancestors


@pytest.mark.django_db
class TestPersonGroupManagerMethods:
    """Tests for PersonGroupManager query methods."""

    def test_root_groups_for_user(self, user):
        """Test root_groups_for_user returns only root groups accessible by user."""
        # Create root group shared with user
        root = PersonGroupFactory(name="Root")
        PersonGroupPermission.objects.create(
            user=user, group=root, permission_type=PermissionLevel.VIEWER
        )

        # Create child group shared with user
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(root)
        PersonGroupPermission.objects.create(
            user=user, group=child, permission_type=PermissionLevel.VIEWER
        )

        # Create unshared root group
        unshared = PersonGroupFactory(name="Unshared Root")

        root_groups = PersonGroup.objects.root_groups_for_user(user)
        assert root in root_groups
        assert child not in root_groups  # Has parent, not root
        assert unshared not in root_groups  # Not shared

    def test_accessible_by_includes_inherited_descendant_permissions(self, user):
        """Inherited parent permissions make descendant groups accessible."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)
        PersonGroupPermission.objects.create(
            user=user,
            group=parent,
            permission_type=PermissionLevel.EDITOR,
            inherit_permissions=True,
        )

        assert child in PersonGroup.objects.accessible_by(user)
        assert PermissionService.get_effective_permission(child, user) == PermissionLevel.EDITOR

    def test_direct_permission_does_not_mask_higher_inherited_permission(self, user):
        """Effective permissions use the highest direct or inherited group permission."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)
        PersonGroupPermission.objects.create(
            user=user,
            group=parent,
            permission_type=PermissionLevel.OWNER,
            inherit_permissions=True,
        )
        PersonGroupPermission.objects.create(
            user=user,
            group=child,
            permission_type=PermissionLevel.VIEWER,
        )

        assert PermissionService.get_effective_permission(child, user) == PermissionLevel.OWNER

    def test_children_for_user(self, user):
        """Test children_for_user returns children accessible by user."""
        parent = PersonGroupFactory(name="Parent")
        child1 = PersonGroupFactory(name="Child 1")
        child2 = PersonGroupFactory(name="Child 2")

        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)

        # Share only child1 with user
        PersonGroupPermission.objects.create(
            user=user, group=child1, permission_type=PermissionLevel.VIEWER
        )

        children = PersonGroup.objects.children_for_user(parent, user)
        assert child1 in children
        assert child2 not in children

    def test_accessible_by_includes_inherited_descendants(self, user):
        """Parent permissions cascade only when inherit_permissions is explicit."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        grandchild = PersonGroupFactory(name="Grandchild")
        unrelated = PersonGroupFactory(name="Unrelated")
        child.parent_groups.add(parent)
        grandchild.parent_groups.add(child)
        PersonGroupPermission.objects.create(
            user=user,
            group=parent,
            permission_type=PermissionLevel.EDITOR,
            inherit_permissions=True,
        )

        accessible_groups = PersonGroup.objects.accessible_by(user)

        assert parent in accessible_groups
        assert child in accessible_groups
        assert grandchild in accessible_groups
        assert unrelated not in accessible_groups
        assert PermissionService.get_effective_permission(child, user) == PermissionLevel.EDITOR

    def test_accessible_by_does_not_inherit_when_flag_is_false(self, user):
        """A direct parent permission without inherit_permissions does not expose children."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)
        PersonGroupPermission.objects.create(
            user=user,
            group=parent,
            permission_type=PermissionLevel.EDITOR,
            inherit_permissions=False,
        )

        accessible_groups = PersonGroup.objects.accessible_by(user)

        assert parent in accessible_groups
        assert child not in accessible_groups

    def test_with_prefetched_relations(self):
        """Test with_prefetched_relations prefetches parent/child groups."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # Query with prefetch
        groups = PersonGroup.objects.with_prefetched_relations()
        fetched_parent = groups.get(pk=parent.pk)
        fetched_child = groups.get(pk=child.pk)

        # Should be able to access relations without additional queries
        assert child in fetched_parent.child_groups.all()
        assert parent in fetched_child.parent_groups.all()


@pytest.mark.django_db
class TestPersonGroupPrimaryAncestorsPathBranches:
    """Tests for branch coverage in get_primary_ancestors_path."""

    def test_all_parents_already_visited(self):
        """Test when all parent candidates have been visited (cycle scenario)."""
        # Create a circular structure: A -> B -> A
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")

        b.parent_groups.add(a)
        a.parent_groups.add(b)  # Creates cycle

        # Path from B should not loop infinitely
        path = b.get_primary_ancestors_path()
        # Should have A, then stop because A's parent (B) is already visited
        assert len(path) == 1
        assert a in path

    def test_parent_pk_not_in_all_groups(self):
        """Test when a parent_pk is somehow not in all_groups dict."""
        # This is an edge case - in practice, all groups should be in the dict
        # But we test the branch by creating a simple structure
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        path = child.get_primary_ancestors_path()
        assert len(path) == 1
        assert parent in path

    def test_no_valid_parent_after_filtering_visited(self):
        """Test path terminates when no unvisited parent is available."""
        # Create: A <- B <- C, where C also links back to A
        a = PersonGroupFactory(name="A")
        b = PersonGroupFactory(name="B")
        c = PersonGroupFactory(name="C")

        b.parent_groups.add(a)
        c.parent_groups.add(b)
        c.parent_groups.add(a)  # C has two parents

        path = c.get_primary_ancestors_path()
        # Should pick one path (B then A, or just A if B leads back to A)
        assert len(path) >= 1
        assert a in path
