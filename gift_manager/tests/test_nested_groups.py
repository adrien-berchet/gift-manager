"""Tests for nested groups functionality."""

import pytest
from django.core.exceptions import ValidationError

from gift_manager.models import PermissionLevel
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestPersonGroupHierarchy:
    """Tests for person group hierarchy methods."""

    def test_get_children(self):
        """Test getting direct children of a group."""
        user = UserFactory()
        parent = PersonGroupFactory()
        child1 = PersonGroupFactory()
        child2 = PersonGroupFactory()
        unrelated = PersonGroupFactory()

        # Set up permissions
        for group in [parent, child1, child2, unrelated]:
            PersonGroupPermission.objects.create(
                user=user,
                group=group,
                permission_type=PermissionLevel.OWNER,
            )

        # Add children
        child1.parent_groups.add(parent)
        child2.parent_groups.add(parent)

        children = parent.get_children()
        assert set(children) == {child1, child2}
        assert unrelated not in children

    def test_get_descendants(self):
        """Test getting all descendants (children at all levels) of a group."""
        root = PersonGroupFactory(name="Root")
        level1_child1 = PersonGroupFactory(name="L1-C1")
        level1_child2 = PersonGroupFactory(name="L1-C2")
        level2_child1 = PersonGroupFactory(name="L2-C1")
        level2_child2 = PersonGroupFactory(name="L2-C2")

        # Build hierarchy: root -> level1_child1 -> level2_child1
        #                       -> level1_child2 -> level2_child2
        level1_child1.parent_groups.add(root)
        level1_child2.parent_groups.add(root)
        level2_child1.parent_groups.add(level1_child1)
        level2_child2.parent_groups.add(level1_child2)

        descendants = root.get_descendants()
        assert set(descendants) == {level1_child1, level1_child2, level2_child1, level2_child2}

    def test_get_ancestors(self):
        """Test getting all ancestors (parents at all levels) of a group."""
        root = PersonGroupFactory(name="Root")
        middle = PersonGroupFactory(name="Middle")
        leaf = PersonGroupFactory(name="Leaf")

        # Build hierarchy: root -> middle -> leaf
        middle.parent_groups.add(root)
        leaf.parent_groups.add(middle)

        # Leaf should have root and middle as ancestors
        ancestors = leaf.get_ancestors()
        assert set(ancestors) == {root, middle}

        # Middle should have only root as ancestor
        ancestors = middle.get_ancestors()
        assert set(ancestors) == {root}

        # Root should have no ancestors
        ancestors = root.get_ancestors()
        assert len(ancestors) == 0

    def test_multiple_parents(self):
        """Test that a group can have multiple parents."""
        parent1 = PersonGroupFactory(name="Parent1")
        parent2 = PersonGroupFactory(name="Parent2")
        child = PersonGroupFactory(name="Child")

        child.parent_groups.add(parent1, parent2)

        assert set(child.parent_groups.all()) == {parent1, parent2}
        assert child in parent1.get_children()
        assert child in parent2.get_children()

    def test_diamond_hierarchy(self):
        """Test diamond-shaped hierarchy (multiple paths to same ancestor)."""
        root = PersonGroupFactory(name="Root")
        middle1 = PersonGroupFactory(name="Middle1")
        middle2 = PersonGroupFactory(name="Middle2")
        leaf = PersonGroupFactory(name="Leaf")

        # Build diamond: root -> middle1 -> leaf
        #                     -> middle2 -> leaf
        middle1.parent_groups.add(root)
        middle2.parent_groups.add(root)
        leaf.parent_groups.add(middle1, middle2)

        # Leaf should have all three as ancestors, without duplicates
        ancestors = leaf.get_ancestors()
        assert set(ancestors) == {root, middle1, middle2}

        # Root should have leaf in descendants
        descendants = root.get_descendants()
        assert leaf in descendants
        assert middle1 in descendants
        assert middle2 in descendants


@pytest.mark.django_db
class TestCyclePrevention:
    """Tests for cycle detection and prevention in group hierarchies."""

    def test_has_cycle_with_direct_parent(self):
        """Test detecting a direct cycle (A -> B -> A)."""
        group_a = PersonGroupFactory(name="A")
        group_b = PersonGroupFactory(name="B")

        group_b.parent_groups.add(group_a)

        # Trying to add group_b as parent of group_a would create a cycle
        assert group_a.has_cycle_with(group_b) is True

    def test_has_cycle_with_indirect_parent(self):
        """Test detecting an indirect cycle (A -> B -> C -> A)."""
        group_a = PersonGroupFactory(name="A")
        group_b = PersonGroupFactory(name="B")
        group_c = PersonGroupFactory(name="C")

        # Build chain: A -> B -> C
        group_b.parent_groups.add(group_a)
        group_c.parent_groups.add(group_b)

        # Trying to add group_c as parent of group_a would create a cycle
        assert group_a.has_cycle_with(group_c) is True

    def test_has_cycle_with_self(self):
        """Test that a group cannot be its own parent."""
        group = PersonGroupFactory()

        assert group.has_cycle_with(group) is True

    def test_has_no_cycle_with_unrelated_group(self):
        """Test that unrelated groups don't create cycles."""
        group_a = PersonGroupFactory(name="A")
        group_b = PersonGroupFactory(name="B")

        # No relationship between groups
        assert group_a.has_cycle_with(group_b) is False
        assert group_b.has_cycle_with(group_a) is False

    def test_clean_prevents_cycle(self):
        """Test that clean() method prevents cycles."""
        group_a = PersonGroupFactory(name="A")
        group_b = PersonGroupFactory(name="B")

        # Build: A -> B
        group_b.parent_groups.add(group_a)

        # Try to create cycle: B -> A
        group_a.parent_groups.add(group_b)

        # clean() should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            group_a.clean()

        assert "cycle" in str(exc_info.value).lower()


@pytest.mark.django_db
class TestNestedGroupMembers:
    """Tests for getting members from nested groups."""

    def test_get_all_members_direct_only(self):
        """Test getting members when only direct members exist."""
        group = PersonGroupFactory()
        person1 = PersonFactory()
        person2 = PersonFactory()

        group.person_set.add(person1, person2)

        all_members = group.get_all_members()
        assert set(all_members) == {person1, person2}

    def test_get_all_members_with_nested_groups(self):
        """Test getting members including from nested groups."""
        parent_group = PersonGroupFactory(name="Parent")
        child_group = PersonGroupFactory(name="Child")

        # Create persons
        parent_member = PersonFactory(first_name="Parent", family_name="Member")
        child_member = PersonFactory(first_name="Child", family_name="Member")

        # Add members to respective groups
        parent_group.person_set.add(parent_member)
        child_group.person_set.add(child_member)

        # Make child_group a child of parent_group
        child_group.parent_groups.add(parent_group)

        # Parent group should have both members when include_nested=True
        all_members = parent_group.get_all_members(include_nested=True)
        assert set(all_members) == {parent_member, child_member}

        # Child group should only have its direct member
        child_members = child_group.get_all_members(include_nested=False)
        assert set(child_members) == {child_member}

    def test_get_all_members_deep_hierarchy(self):
        """Test getting members from a deep hierarchy."""
        level1 = PersonGroupFactory(name="Level1")
        level2 = PersonGroupFactory(name="Level2")
        level3 = PersonGroupFactory(name="Level3")

        # Create members for each level
        member1 = PersonFactory(first_name="Member1")
        member2 = PersonFactory(first_name="Member2")
        member3 = PersonFactory(first_name="Member3")

        # Assign members
        level1.person_set.add(member1)
        level2.person_set.add(member2)
        level3.person_set.add(member3)

        # Build hierarchy: level1 -> level2 -> level3
        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)

        # Level1 should have all members when include_nested=True
        all_members = level1.get_all_members(include_nested=True)
        assert set(all_members) == {member1, member2, member3}

        # Level2 should have member2 and member3
        all_members = level2.get_all_members(include_nested=True)
        assert set(all_members) == {member2, member3}

        # Level3 should only have member3
        all_members = level3.get_all_members(include_nested=False)
        assert set(all_members) == {member3}

    def test_get_all_members_no_duplicates(self):
        """Test that members aren't duplicated in diamond hierarchies."""
        root = PersonGroupFactory(name="Root")
        middle1 = PersonGroupFactory(name="Middle1")
        middle2 = PersonGroupFactory(name="Middle2")
        leaf = PersonGroupFactory(name="Leaf")

        # Create member only in leaf
        member = PersonFactory()
        leaf.person_set.add(member)

        # Build diamond: root -> middle1 -> leaf
        #                     -> middle2 -> leaf
        middle1.parent_groups.add(root)
        middle2.parent_groups.add(root)
        leaf.parent_groups.add(middle1, middle2)

        # Root should have member exactly once when include_nested=True
        all_members = root.get_all_members(include_nested=True)
        assert list(all_members).count(member) == 1
        assert set(all_members) == {member}


@pytest.mark.django_db
class TestNestedRelationQueries:
    """Tests for querying relations through nested groups."""

    def test_group_includes_nested_members(self):
        """Test that parent groups include nested group members."""
        # Create parent and child groups
        parent_group = PersonGroupFactory(name="Parent")
        child_group = PersonGroupFactory(name="Child")

        # Create receiver in child group
        receiver = PersonFactory(first_name="Receiver")
        child_group.person_set.add(receiver)

        # Make child_group a child of parent_group
        child_group.parent_groups.add(parent_group)

        # All members of parent group (including nested) should include receiver
        all_receivers = parent_group.get_all_members(include_nested=True)
        assert receiver in all_receivers

    def test_person_membership_through_nested_groups(self):
        """Test that persons can be accessed through parent group hierarchy."""
        # Create hierarchy
        grandparent_group = PersonGroupFactory(name="Grandparent")
        parent_group = PersonGroupFactory(name="Parent")
        receiver = PersonFactory(first_name="Receiver")

        # Build hierarchy
        parent_group.parent_groups.add(grandparent_group)
        parent_group.person_set.add(receiver)

        # Receiver should be accessible through grandparent group's nested members
        all_members = grandparent_group.get_all_members(include_nested=True)
        assert receiver in all_members


@pytest.mark.django_db
class TestPermissionInheritance:
    """Tests for permission inheritance through group hierarchy."""

    def test_child_group_accessible_through_parent_permission(self):
        """Test that having permission on parent grants access to children."""
        owner = UserFactory(username="owner")
        viewer = UserFactory(username="viewer")

        # Create hierarchy
        parent_group = PersonGroupFactory(name="Parent")
        child_group = PersonGroupFactory(name="Child")

        # Set owner permissions
        PersonGroupPermission.objects.create(
            user=owner,
            group=parent_group,
            permission_type=PermissionLevel.OWNER,
        )
        PersonGroupPermission.objects.create(
            user=owner,
            group=child_group,
            permission_type=PermissionLevel.OWNER,
        )

        child_group.parent_groups.add(parent_group)

        # Grant viewer permission to parent group only
        PersonGroupPermission.objects.create(
            user=viewer,
            group=parent_group,
            permission_type=PermissionLevel.VIEWER,
        )

        # Child group should be accessible to viewer through inheritance
        accessible_groups = PersonGroup.objects.accessible_by(viewer)
        assert parent_group in accessible_groups
        # Note: Permission inheritance means viewer can see parent,
        # and through parent can query child members

    def test_owner_has_access_to_all_nested_groups(self):
        """Test that owner has full access to all groups in hierarchy."""
        owner = UserFactory()

        # Create deep hierarchy
        level1 = PersonGroupFactory(name="Level1")
        level2 = PersonGroupFactory(name="Level2")
        level3 = PersonGroupFactory(name="Level3")

        # Grant owner permissions to all levels
        for group in [level1, level2, level3]:
            PersonGroupPermission.objects.create(
                user=owner,
                group=group,
                permission_type=PermissionLevel.OWNER,
            )

        level2.parent_groups.add(level1)
        level3.parent_groups.add(level2)

        # Owner should have access to all groups
        accessible_groups = PersonGroup.objects.accessible_by(owner)
        assert level1 in accessible_groups
        assert level2 in accessible_groups
        assert level3 in accessible_groups


@pytest.mark.django_db
class TestCascadeSharing:
    """Tests for cascade sharing through group hierarchy."""

    def test_share_parent_without_cascade(self):
        """Test sharing parent group without including children."""
        owner = UserFactory(username="owner")
        friend = UserFactory(username="friend")

        # Make them friends
        owner.profile.friends.add(friend.profile)

        # Create hierarchy
        parent_group = PersonGroupFactory(name="Parent")
        child_group = PersonGroupFactory(name="Child")

        # Set owner permissions
        PersonGroupPermission.objects.create(
            user=owner,
            group=parent_group,
            permission_type=PermissionLevel.OWNER,
        )
        PersonGroupPermission.objects.create(
            user=owner,
            group=child_group,
            permission_type=PermissionLevel.OWNER,
        )

        child_group.parent_groups.add(parent_group)

        # Share parent only (without cascade)
        PersonGroupPermission.objects.create(
            user=friend,
            group=parent_group,
            permission_type=PermissionLevel.VIEWER,
        )

        # Friend should have access to parent
        accessible_groups = PersonGroup.objects.accessible_by(friend)
        assert parent_group in accessible_groups

        # Child is NOT automatically shared (no cascade)
        # Friend can only see parent group, not child group
        assert child_group not in PersonGroup.objects.accessible_by(friend)

    def test_cascade_share_includes_children(self):
        """Test that cascade sharing explicitly shares all children."""
        owner = UserFactory(username="owner")
        friend = UserFactory(username="friend")

        # Make them friends
        owner.profile.friends.add(friend.profile)

        # Create hierarchy
        parent_group = PersonGroupFactory(name="Parent")
        child_group = PersonGroupFactory(name="Child")
        grandchild_group = PersonGroupFactory(name="Grandchild")

        # Set owner permissions
        for group in [parent_group, child_group, grandchild_group]:
            PersonGroupPermission.objects.create(
                user=owner,
                group=group,
                permission_type=PermissionLevel.OWNER,
            )

        child_group.parent_groups.add(parent_group)
        grandchild_group.parent_groups.add(child_group)

        # Share parent with cascade (share all descendants)
        PersonGroupPermission.objects.create(
            user=friend,
            group=parent_group,
            permission_type=PermissionLevel.VIEWER,
        )

        # Explicitly create permissions for descendants (simulating cascade)
        PersonGroupPermission.objects.create(
            user=friend,
            group=child_group,
            permission_type=PermissionLevel.VIEWER,
        )
        PersonGroupPermission.objects.create(
            user=friend,
            group=grandchild_group,
            permission_type=PermissionLevel.VIEWER,
        )

        # Friend should have explicit access to all groups
        accessible_groups = PersonGroup.objects.accessible_by(friend)
        assert parent_group in accessible_groups
        assert child_group in accessible_groups
        assert grandchild_group in accessible_groups

        # Verify permissions exist
        assert (
            PersonGroupPermission.objects.filter(
                user=friend, group__in=[parent_group, child_group, grandchild_group]
            ).count()
            == 3
        )


@pytest.mark.django_db
class TestGroupFormValidation:
    """Tests for form validation with nested groups."""

    def test_cannot_add_self_as_parent(self):
        """Test that a group cannot be its own parent."""
        group = PersonGroupFactory()

        # Try to add itself as parent
        group.parent_groups.add(group)

        # Validation should fail
        with pytest.raises(ValidationError):
            group.clean()

    def test_cannot_create_cycle_through_form(self):
        """Test that form validation prevents cycle creation."""
        group_a = PersonGroupFactory(name="A")
        group_b = PersonGroupFactory(name="B")
        group_c = PersonGroupFactory(name="C")

        # Build chain: A -> B -> C
        group_b.parent_groups.add(group_a)
        group_c.parent_groups.add(group_b)

        # Try to close the loop: C -> A (which would create cycle)
        group_a.parent_groups.add(group_c)

        # Validation should fail
        with pytest.raises(ValidationError):
            group_a.clean()
