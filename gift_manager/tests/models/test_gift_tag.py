# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from gift_manager.models import Gift
from gift_manager.models import GiftPermission
from gift_manager.models import GiftTag
from gift_manager.models import GiftTagPermission
from gift_manager.models import PermissionLevel


@pytest.mark.django_db
class TestGiftTag:
    """Tests for the GiftTag model."""

    def test_gift_tag_creation(self, gift_tag, gift_tag_name):
        """Test creating a gift tag."""
        assert gift_tag.name == gift_tag_name
        assert gift_tag.tag_id is not None
        assert isinstance(gift_tag.tag_id, uuid.UUID)
        assert not gift_tag.parent_tags.exists()
        assert isinstance(gift_tag.creation_date, datetime)

    def test_gift_tag_string_representation(self, gift_tag, gift_tag_name):
        """Test the string representation of a gift tag."""
        assert str(gift_tag) == gift_tag_name

    def test_gift_tag_hierarchy(self, gift_tag):
        """Test creating a hierarchical structure of gift tags."""
        sub_tag = GiftTag.objects.create(name="Computers")
        sub_tag.parent_tags.add(gift_tag)
        assert list(sub_tag.parent_tags.all()) == [gift_tag]

    def test_gift_tag_permission(self, user, username, gift_tag, gift_tag_name):
        """Test adding a permission to a gift tag."""
        permission = GiftTagPermission.objects.create(
            user=user, gift_tag=gift_tag, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.gift_tag == gift_tag
        assert str(permission) == f"{username} - {gift_tag_name} -> owner"
        assert user in gift_tag.shared_with.all()

    def test_tag_get_children(self):
        """Test the get_children method."""
        parent_tag = GiftTag.objects.create(name="Electronics")
        child_tag1 = GiftTag.objects.create(name="Smartphones")
        child_tag2 = GiftTag.objects.create(name="Computers")

        child_tag1.parent_tags.add(parent_tag)
        child_tag2.parent_tags.add(parent_tag)

        children = parent_tag.get_children()
        assert len(children) == 2
        assert child_tag1 in children
        assert child_tag2 in children

    def test_tag_get_descendants(self):
        """Test the get_descendants method, including cycle prevention."""
        # Create a tag structure with a tag that will appear more than once in the traversal
        root_tag = GiftTag.objects.create(name="Electronics")

        # First level
        mid_tag1 = GiftTag.objects.create(name="Computers")
        mid_tag2 = GiftTag.objects.create(name="Phones")
        mid_tag1.parent_tags.add(root_tag)
        mid_tag2.parent_tags.add(root_tag)

        # Second level - diamond structure
        leaf_tag = GiftTag.objects.create(name="Devices")
        leaf_tag.parent_tags.add(mid_tag1)
        leaf_tag.parent_tags.add(mid_tag2)  # The same tag has 2 different parents

        # Third level
        bottom_tag = GiftTag.objects.create(name="Accessories")
        bottom_tag.parent_tags.add(leaf_tag)

        # Basic test: all descendants should be included
        descendants = root_tag.get_descendants()
        assert len(descendants) == 4  # mid_tag1, mid_tag2, leaf_tag, bottom_tag
        assert mid_tag1 in descendants
        assert mid_tag2 in descendants
        assert leaf_tag in descendants
        assert bottom_tag in descendants

        # Cycle test: leaf_tag will be encountered twice during traversal
        # (once via mid_tag1 and once via mid_tag2)
        # Test from an intermediate level to check that duplicates are handled correctly
        descendants_from_mid = mid_tag1.get_descendants()
        assert len(descendants_from_mid) == 2  # leaf_tag, bottom_tag
        assert leaf_tag in descendants_from_mid
        assert bottom_tag in descendants_from_mid

        # Create a complex structure with a tag that appears multiple times in different paths
        common_tag = GiftTag.objects.create(name="Common")
        branch1 = GiftTag.objects.create(name="Branch1")
        branch2 = GiftTag.objects.create(name="Branch2")

        branch1.parent_tags.add(root_tag)
        branch2.parent_tags.add(root_tag)
        common_tag.parent_tags.add(branch1)
        common_tag.parent_tags.add(branch2)
        common_tag.parent_tags.add(mid_tag1)  # The same tag appears in multiple paths

        # The common tag should only appear once in the descendants
        all_descendants = root_tag.get_descendants()
        # Count how many times common_tag appears in the results
        common_tag_count = sum(1 for tag in all_descendants if tag == common_tag)
        assert common_tag_count == 1  # Must appear only once

        # Check that all tags are included (without duplicates)
        expected_tags = {mid_tag1, mid_tag2, leaf_tag, bottom_tag, branch1, branch2, common_tag}
        assert set(all_descendants) == expected_tags
        assert len(all_descendants) == len(expected_tags)

    def test_tag_get_ancestors(self):  # pylint: disable=too-many-statements
        """Test the get_ancestors method, including with diamond structures."""
        # Basic hierarchical structure
        root_tag = GiftTag.objects.create(name="Electronics")
        mid_tag = GiftTag.objects.create(name="Computers")
        leaf_tag = GiftTag.objects.create(name="Laptops")

        mid_tag.parent_tags.add(root_tag)
        leaf_tag.parent_tags.add(mid_tag)

        # Basic test: verify all ancestors are included
        ancestors = leaf_tag.get_ancestors()
        assert len(ancestors) == 2
        assert root_tag in ancestors
        assert mid_tag in ancestors

        # Diamond structure: a tag with two paths to the root
        mid_tag1 = mid_tag  # Reuse existing variable for clarity
        mid_tag2 = GiftTag.objects.create(name="Mobile Devices")
        leaf_tag2 = GiftTag.objects.create(name="Tablets")

        # Create the diamond structure
        mid_tag2.parent_tags.add(root_tag)
        leaf_tag2.parent_tags.add(mid_tag1)
        leaf_tag2.parent_tags.add(mid_tag2)

        # Test with diamond structure: the tag should have both ancestor paths
        ancestors = leaf_tag2.get_ancestors()
        assert len(ancestors) == 3  # root_tag, mid_tag1, mid_tag2
        assert root_tag in ancestors
        assert mid_tag1 in ancestors
        assert mid_tag2 in ancestors

        # More complex structure with tags appearing multiple times
        # in different paths
        extra_root = GiftTag.objects.create(name="Extra Root")
        common_parent = GiftTag.objects.create(name="Common Parent")
        bottom_tag = GiftTag.objects.create(name="Bottom Tag")

        # Create two paths to common_parent
        common_parent.parent_tags.add(root_tag)
        common_parent.parent_tags.add(extra_root)

        # bottom_tag has common_parent as parent
        bottom_tag.parent_tags.add(common_parent)

        # Test that common_parent appears only once in bottom_tag's ancestors
        ancestors = bottom_tag.get_ancestors()
        common_parent_count = sum(1 for tag in ancestors if tag == common_parent)
        assert common_parent_count == 1

        # Verify that all ancestors are included (without duplicates)
        assert len(ancestors) == 3  # extra_root, root_tag, common_parent
        assert common_parent in ancestors
        assert root_tag in ancestors
        assert extra_root in ancestors

        # Create a structure that could cause infinite loop without processing IDs
        # Tag A and Tag B are mutually parents (allowed in DB but illogical)
        tag_a = GiftTag.objects.create(name="Tag A")
        tag_b = GiftTag.objects.create(name="Tag B")

        tag_b.parent_tags.add(tag_a)
        tag_a.parent_tags.add(tag_b)  # Create a circular reference

        # The get_ancestors code should avoid infinite loops
        ancestors_a = tag_a.get_ancestors()
        assert len(ancestors_a) == 1
        assert tag_b in ancestors_a

        ancestors_b = tag_b.get_ancestors()
        assert len(ancestors_b) == 1
        assert tag_a in ancestors_b

        # Test with a very deep tag to verify the method works
        # with many levels of nesting
        deep_tags = []
        previous_tag = root_tag
        # Create a chain of 10 tags
        for i in range(10):
            new_tag = GiftTag.objects.create(name=f"Deep Tag {i}")
            new_tag.parent_tags.add(previous_tag)
            deep_tags.append(new_tag)
            previous_tag = new_tag

        # The last tag should have all tags as ancestors
        deepest_tag = deep_tags[-1]
        ancestors = deepest_tag.get_ancestors()
        assert len(ancestors) == 10
        assert root_tag in ancestors
        for tag in deep_tags[:-1]:  # All except the last one
            assert tag in ancestors

    def test_tag_get_primary_ancestors_path(self):
        """Test the get_primary_ancestors_path method."""
        root_tag = GiftTag.objects.create(name="Electronics")
        mid_tag1 = GiftTag.objects.create(name="Computers")
        mid_tag2 = GiftTag.objects.create(name="Smartphones")
        leaf_tag = GiftTag.objects.create(name="Laptops")

        mid_tag1.parent_tags.add(root_tag)
        mid_tag2.parent_tags.add(root_tag)
        leaf_tag.parent_tags.add(mid_tag1)

        path = leaf_tag.get_primary_ancestors_path()
        assert len(path) == 2
        assert path[0] == root_tag
        assert path[1] == mid_tag1

    def test_tag_has_cycle_with(self):
        """Test the has_cycle_with method."""
        tag_a = GiftTag.objects.create(name="Tag A")
        tag_b = GiftTag.objects.create(name="Tag B")
        tag_c = GiftTag.objects.create(name="Tag C")

        # Create a chain: A -> B -> C
        tag_b.parent_tags.add(tag_a)
        tag_c.parent_tags.add(tag_b)

        # A cycle would be formed if C -> A
        assert tag_a.has_cycle_with(tag_c)
        assert not tag_c.has_cycle_with(tag_a)

        # Self-reference is a cycle
        assert tag_a.has_cycle_with(tag_a)

    def test_tag_get_all_gifts(self, gift):
        """Test the get_all_gifts method."""
        parent_tag = GiftTag.objects.create(name="Electronics")
        child_tag = GiftTag.objects.create(name="Smartphones")
        child_tag.parent_tags.add(parent_tag)

        # Associate gift with child tag
        gift.tags.add(child_tag)

        # Parent tag should return the gift via descendant relationship
        gifts = parent_tag.get_all_gifts()
        assert gift in gifts

        # Create another gift directly with parent tag
        gift2 = gift.__class__.objects.create(name="Computer", comment="Desktop")
        gift2.tags.add(parent_tag)

        gifts = parent_tag.get_all_gifts()
        assert len(gifts) == 2
        assert gift in gifts
        assert gift2 in gifts

    def test_tag_get_all_gifts_filters_by_user_access(self, user):
        """User-aware gift counts exclude inaccessible gifts."""
        tag = GiftTag.objects.create(name="Electronics")
        visible_gift = Gift.objects.create(name="Visible gift")
        private_gift = Gift.objects.create(name="Private gift")
        visible_gift.tags.add(tag)
        private_gift.tags.add(tag)

        GiftTagPermission.objects.create(
            user=user,
            gift_tag=tag,
            permission_type=PermissionLevel.VIEWER,
        )
        GiftPermission.objects.create(
            user=user,
            gift=visible_gift,
            permission_type=PermissionLevel.VIEWER,
        )

        gifts = tag.get_all_gifts(user=user)

        assert list(gifts) == [visible_gift]

    def test_tag_clean_with_cycle(self):
        """Test the clean method prevents cycles."""
        tag_a = GiftTag.objects.create(name="Tag A")
        tag_b = GiftTag.objects.create(name="Tag B")

        # B is a child of A
        tag_b.parent_tags.add(tag_a)

        # Trying to make A a child of B would create a cycle
        tag_a.parent_tags.add(tag_b)

        with pytest.raises(ValidationError):
            tag_a.clean()


@pytest.mark.django_db
class TestGiftTagManager:
    """Tests for the GiftTagManager."""

    @pytest.fixture
    def setup_tags_and_users(self, user, userpassword):
        """Set up tags and users for testing."""
        # Create another user
        user2 = User.objects.create_user(username="testuser2", password=userpassword)

        # Create public and private tags
        public_tag = GiftTag.objects.create(name="Public Tag", is_public=True)
        private_tag1 = GiftTag.objects.create(name="Private Tag 1")
        private_tag2 = GiftTag.objects.create(name="Private Tag 2")

        # Share private_tag1 with the first user
        GiftTagPermission.objects.create(
            user=user, gift_tag=private_tag1, permission_type=PermissionLevel.VIEWER
        )

        # Create tag hierarchy
        child_tag1 = GiftTag.objects.create(name="Child Tag 1", is_public=True)
        child_tag2 = GiftTag.objects.create(name="Child Tag 2")
        child_tag1.parent_tags.add(public_tag)
        child_tag2.parent_tags.add(private_tag1)

        # Share child_tag2 with the first user
        GiftTagPermission.objects.create(
            user=user, gift_tag=child_tag2, permission_type=PermissionLevel.VIEWER
        )

        return {
            "user": user,
            "user2": user2,
            "public_tag": public_tag,
            "private_tag1": private_tag1,
            "private_tag2": private_tag2,
            "child_tag1": child_tag1,
            "child_tag2": child_tag2,
        }

    def test_accessible_by(self, setup_tags_and_users):
        """Test the accessible_by method."""
        data = setup_tags_and_users

        # First user should see public tag and private tag shared with them
        tags = GiftTag.objects.accessible_by(data["user"])
        assert data["public_tag"] in tags
        assert data["private_tag1"] in tags
        assert data["private_tag2"] not in tags
        assert data["child_tag1"] in tags
        assert data["child_tag2"] in tags

        # Second user should only see public tags
        tags = GiftTag.objects.accessible_by(data["user2"])
        assert data["public_tag"] in tags
        assert data["private_tag1"] not in tags
        assert data["private_tag2"] not in tags
        assert data["child_tag1"] in tags
        assert data["child_tag2"] not in tags

    def test_root_tags_for_user(self, setup_tags_and_users):
        """Test the root_tags_for_user method."""
        data = setup_tags_and_users

        # Only root tags should be returned
        root_tags = GiftTag.objects.root_tags_for_user(data["user"])
        assert data["public_tag"] in root_tags
        assert data["private_tag1"] in root_tags
        assert data["private_tag2"] not in root_tags
        assert data["child_tag1"] not in root_tags
        assert data["child_tag2"] not in root_tags

    def test_children_for_user(self, setup_tags_and_users):
        """Test the children_for_user method."""
        data = setup_tags_and_users

        # Test children of public tag
        children = GiftTag.objects.children_for_user(data["public_tag"], data["user"])
        assert data["child_tag1"] in children
        assert data["child_tag2"] not in children

        # Test children of private tag shared with the user
        children = GiftTag.objects.children_for_user(data["private_tag1"], data["user"])
        assert data["child_tag2"] in children

        # Second user can only see children of public tags
        children = GiftTag.objects.children_for_user(data["public_tag"], data["user2"])
        assert data["child_tag1"] in children
        assert data["child_tag2"] not in children


@pytest.mark.django_db
class TestGiftTagManagerMethods:
    """Tests for GiftTagManager query methods."""

    def test_with_prefetched_relations(self):
        """Test with_prefetched_relations prefetches parent/child tags."""
        parent = GiftTag.objects.create(name="Electronics")
        child = GiftTag.objects.create(name="Phones")
        child.parent_tags.add(parent)

        # Query with prefetch
        tags = GiftTag.objects.with_prefetched_relations()
        fetched_parent = tags.get(pk=parent.pk)
        fetched_child = tags.get(pk=child.pk)

        # Should be able to access relations without additional queries
        assert child in fetched_parent.child_tags.all()
        assert parent in fetched_child.parent_tags.all()


@pytest.mark.django_db
class TestGiftTagBranches:
    """Tests for GiftTag branch coverage."""

    def test_get_primary_ancestors_path_no_prefetch(self):
        """Test get_primary_ancestors_path when _prefetched_objects_cache doesn't exist."""
        parent = GiftTag.objects.create(name="Parent")
        child = GiftTag.objects.create(name="Child")
        child.parent_tags.add(parent)

        # Fresh query without prefetch - exercises the prefetch branch
        fresh_child = GiftTag.objects.get(pk=child.pk)
        # Remove prefetch cache if it exists
        if hasattr(fresh_child, "_prefetched_objects_cache"):
            del fresh_child._prefetched_objects_cache

        path = fresh_child.get_primary_ancestors_path()
        assert len(path) == 1
        assert parent in path

    def test_get_primary_ancestors_path_with_prefetch(self):
        """Test get_primary_ancestors_path when prefetch exists."""
        parent = GiftTag.objects.create(name="Parent")
        child = GiftTag.objects.create(name="Child")
        child.parent_tags.add(parent)

        # Query with prefetch
        prefetched_child = GiftTag.objects.prefetch_related("parent_tags").get(pk=child.pk)
        path = prefetched_child.get_primary_ancestors_path()
        assert len(path) == 1
        assert parent in path

    def test_get_primary_ancestors_path_all_visited(self):
        """Test get_primary_ancestors_path when all parents are already visited."""
        # Create circular: A <-> B
        a = GiftTag.objects.create(name="A")
        b = GiftTag.objects.create(name="B")

        b.parent_tags.add(a)
        a.parent_tags.add(b)

        path = b.get_primary_ancestors_path()
        # Should have A, then stop
        assert len(path) == 1
        assert a in path

    def test_clean_no_pk(self):
        """Test clean method when pk is None (new unsaved tag)."""
        tag = GiftTag(name="New Tag")
        # Should not raise - pk is None so no cycle check
        tag.clean()

    def test_clean_no_parents(self):
        """Test clean method when tag has no parents."""
        tag = GiftTag.objects.create(name="Root Tag")
        # Should not raise - no parents to check
        tag.clean()

    def test_clean_with_cycle(self):
        """Test clean method raises ValidationError when cycle exists."""
        a = GiftTag.objects.create(name="A")
        b = GiftTag.objects.create(name="B")

        b.parent_tags.add(a)
        a.parent_tags.add(b)  # Create cycle

        with pytest.raises(ValidationError):
            a.clean()


@pytest.mark.django_db
class TestGiftTagHierarchyUpdates:
    """Tests that GiftTag hierarchy reads follow relationship changes."""

    def test_parent_removal_updates_hierarchy(self):
        """Removing a parent is reflected in tag descendants and ancestors."""
        parent = GiftTag.objects.create(name="Parent")
        child = GiftTag.objects.create(name="Child")
        child.parent_tags.add(parent)

        assert child in parent.get_descendants()
        assert parent in child.get_ancestors()

        child.parent_tags.remove(parent)

        assert child not in parent.get_descendants()
        assert parent not in child.get_ancestors()
