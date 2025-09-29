import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone

from gift_manager.models import EventPermission
from gift_manager.models import GiftPermission
from gift_manager.models import GiftTag
from gift_manager.models import GiftTagPermission
from gift_manager.models import Invitation
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import RelationStatus


@pytest.mark.django_db
class TestProfile:
    """Tests for the Profile model."""

    @pytest.fixture
    def friend(self, userpassword):
        """Create a second test user."""
        return User.objects.create_user(username="testfriend", password=userpassword)

    def test_save_user_profile_with_existing_profile(self, user):
        """Test saving a user that already has a profile."""
        # Get the initial profile
        initial_profile = user.profile

        # Modify the user and save it
        user.username = "modified_username"
        user.save()

        # Check that the same profile instance was saved, not a new one created
        assert user.profile == initial_profile
        assert Profile.objects.filter(user=user).count() == 1

    def test_save_user_profile_without_existing_profile(self, user):
        """Test saving a user that doesn't have a profile."""
        # Delete the profile manually to simulate a user without profile
        Profile.objects.filter(user=user).delete()

        # Reload user from database to clear the profile attribute
        user = User.objects.get(pk=user.pk)

        # Verify the profile is gone
        assert not hasattr(user, "profile")
        assert Profile.objects.filter(user=user).count() == 0

        # Save the user to trigger the signal
        user.username = "another_username"
        user.save()

        # Verify a new profile was created
        assert hasattr(user, "profile")
        assert Profile.objects.filter(user=user).count() == 1
        assert user.profile is not None
        assert isinstance(user.profile, Profile)

    def test_profile_creation(self, user):
        """Test that a profile is automatically created when a user is created."""
        assert hasattr(user, "profile")
        assert user.profile is not None
        assert isinstance(user.profile, Profile)

    def test_profile_string_representation(self, user):
        """Test the string representation of a profile."""
        assert "Profile of" in str(user.profile)
        assert user.username in str(user.profile)

    def test_profile_friends(self, user, friend):
        """Test adding friends to a profile."""
        user.profile.friends.add(friend.profile)
        assert friend.profile in user.profile.friends.all()
        # Test symmetry
        assert user.profile in friend.profile.friends.all()


@pytest.mark.django_db
class TestInvitation:
    """Tests for the Invitation model."""

    @pytest.fixture
    def sender(self, userpassword):
        """Create a test sender user."""
        return User.objects.create_user(username="sender", password=userpassword)

    @pytest.fixture
    def invitation(self, sender):
        """Create a test invitation."""
        return Invitation.objects.create(
            sender=sender,
            recipient_email="recipient@example.com",
        )

    def test_invitation_creation(self, invitation):
        """Test creating an invitation."""
        assert invitation.token is not None
        assert isinstance(invitation.token, uuid.UUID)
        assert invitation.recipient_email == "recipient@example.com"
        assert invitation.accepted is False
        assert invitation.accepted_at is None
        assert isinstance(invitation.created_at, datetime)

    def test_invitation_string_representation(self, invitation, sender):
        """Test the string representation of an invitation."""
        assert "Invitation from" in str(invitation)
        assert sender.username in str(invitation)
        assert invitation.recipient_email in str(invitation)

    @override_settings(INVITATION_EXPIRY_DAYS=7)
    def test_invitation_is_expired_with_setting(self, invitation):
        """Test is_expired method with expiry setting configured."""
        # Test non-expired invitation
        assert invitation.is_expired() is False

        # Test expired invitation
        invitation.created_at = timezone.now() - timedelta(days=8)
        invitation.save()
        assert invitation.is_expired() is True

        # Test invitation on the edge (exactly 7 days)
        invitation.created_at = timezone.now() - timedelta(days=7)
        invitation.save()
        assert invitation.is_expired() is True

    def test_invitation_is_expired_without_setting(self, invitation):
        """Test is_expired method without expiry setting configured."""
        # Remove the setting if it exists
        if hasattr(settings, "INVITATION_EXPIRY_DAYS"):
            del settings.INVITATION_EXPIRY_DAYS

        # Test old invitation without setting (should not expire)
        invitation.created_at = timezone.now() - timedelta(days=365)
        invitation.save()
        assert invitation.is_expired() is False

    @override_settings(INVITATION_EXPIRY_DAYS=30)
    def test_invitation_is_expired_different_expiry_days(self, invitation):
        """Test is_expired method with different expiry days setting."""
        # Test with 30 days setting
        invitation.created_at = timezone.now() - timedelta(days=29)
        invitation.save()
        assert invitation.is_expired() is False

        invitation.created_at = timezone.now() - timedelta(days=31)
        invitation.save()
        assert invitation.is_expired() is True


@pytest.mark.django_db
class TestUserPermissionManager:
    """Tests for the UserPermissionManager."""

    def test_accessible_by_for_person(self, user, person):
        """Test the accessible_by method for Person model."""
        # Create another user and person
        user2 = User.objects.create_user(username="testuser2", password="password")
        person2 = Person.objects.create(first_name="Jane", family_name="Smith")

        # Share person with user
        PersonPermission.objects.create(
            user=user, person=person, permission_type=PermissionLevel.VIEWER
        )

        # User should see person but not person2
        accessible = Person.objects.accessible_by(user)
        assert person in accessible
        assert person2 not in accessible

        # User2 shouldn't see any persons yet
        accessible = Person.objects.accessible_by(user2)
        assert person not in accessible
        assert person2 not in accessible

        # Share person2 with user2
        PersonPermission.objects.create(
            user=user2, person=person2, permission_type=PermissionLevel.VIEWER
        )

        # Now user2 should see person2
        accessible = Person.objects.accessible_by(user2)
        assert person not in accessible
        assert person2 in accessible


@pytest.mark.django_db
class TestPerson:
    """Tests for the Person model."""

    def test_person_creation(self, person):
        """Test creating a person."""
        assert person.first_name == "John"
        assert person.family_name == "Doe"
        assert person.person_id is not None
        assert isinstance(person.person_id, uuid.UUID)
        assert person.email_address is None
        assert isinstance(person.creation_date, datetime)

    def test_person_string_representation(self, person):
        """Test the string representation of a person."""
        assert str(person) == "John Doe"

        # Test with only first name
        person2 = Person.objects.create(first_name="Jane")
        assert str(person2) == "Jane"

    def test_person_user_link(self, person, user):
        """Test linking a person to a user."""
        person.user_link = user
        person.save()
        assert person.user_link == user

    def test_person_permission(self, user, username, person, person_first_name, person_family_name):
        """Test adding a permission to a person."""
        permission = PersonPermission.objects.create(
            user=user, person=person, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.person == person
        assert str(permission) == f"{username} - {person_first_name} {person_family_name} -> owner"
        assert user in person.shared_with.all()


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

    def test_tag_get_ancestors(self):  # noqa: PLR0915
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
        assert len(ancestors_a) == 2
        assert tag_b in ancestors_a

        ancestors_b = tag_b.get_ancestors()
        assert len(ancestors_b) == 2
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
class TestGift:
    """Tests for the Gift model."""

    def test_gift_creation(self, gift):
        """Test creating a gift."""
        assert gift.name == "Smartphone"
        assert gift.comment == "Latest model"
        assert gift.gift_id is not None
        assert isinstance(gift.gift_id, uuid.UUID)
        assert isinstance(gift.creation_date, datetime)

    def test_gift_string_representation(self, gift):
        """Test the string representation of a gift."""
        assert str(gift) == "Smartphone"

    def test_gift_with_tags(self, gift, gift_tag):
        """Test adding tags to a gift."""
        gift.tags.add(gift_tag)
        assert gift_tag in gift.tags.all()

    def test_gift_permission(self, user, username, gift, gift_name):
        """Test adding a permission to a gift."""
        permission = GiftPermission.objects.create(
            user=user, gift=gift, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.gift == gift
        assert str(permission) == f"{username} - {gift_name} -> owner"
        assert user in gift.shared_with.all()


@pytest.mark.django_db
class TestEvent:
    """Tests for the Event model."""

    def test_event_creation(self, event, event_name, event_comment, event_usual_date):
        """Test creating an event."""
        assert event.name == event_name
        assert event.comment == event_comment
        assert event.usual_date == event_usual_date
        assert event.absolute_date is None
        assert event.recurrence == "yearly"
        assert event.event_id is not None
        assert isinstance(event.event_id, uuid.UUID)
        assert isinstance(event.creation_date, datetime)

    def test_event_string_representation(self, event, event_name):
        """Test the string representation of an event."""
        assert str(event) == event_name

    def test_event_permission(self, user, username, event, event_name):
        """Test adding a permission to an event."""
        permission = EventPermission.objects.create(
            user=user, event=event, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.event == event
        assert str(permission) == f"{username} - {event_name} -> owner"
        assert user in event.shared_with.all()


@pytest.mark.django_db
class TestRelation:
    """Tests for the Relation model."""

    def test_relation_creation_with_person(self, person, gift, status):
        """Test creating a relation with a person."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)
        assert relation.person == person
        assert relation.group is None
        assert relation.gift == gift
        assert relation.status == status
        assert relation.relation_id is not None
        assert isinstance(relation.relation_id, uuid.UUID)
        assert isinstance(relation.creation_date, datetime)

    def test_relation_creation_with_group(self, group, gift, status):
        """Test creating a relation with a group."""
        relation = Relation.objects.create(group=group, gift=gift, status=status)
        assert relation.group == group
        assert relation.person is None
        assert relation.gift == gift
        assert relation.status == status

    def test_relation_with_event(self, person, gift, event, status):
        """Test creating a relation with an event."""
        relation = Relation.objects.create(person=person, gift=gift, event=event, status=status)
        assert relation.event == event

    def test_relation_string_representation(self, person, gift, status):
        """Test the string representation of a relation."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)
        expected = f"{person} - {gift} ({status})"
        assert str(relation) == expected

    def test_relation_validation_error(self, person, group, gift, status):
        """Test that validation error is raised when both person and group are None or not None."""
        # Both None
        relation = Relation(gift=gift, status=status)
        with pytest.raises(ValidationError):
            relation.clean()

        # Both set
        relation = Relation(person=person, group=group, gift=gift, status=status)
        with pytest.raises(ValidationError):
            relation.clean()

    def test_relation_permission(self, user, username, person, gift, status):
        """Test adding a permission to a relation."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)
        permission = RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.relation == relation
        assert str(permission) == f"{username} - {person} - {gift} ({status}) -> owner"
        assert user in relation.shared_with.all()


@pytest.mark.django_db
class TestRelationStatus:
    """Tests for the RelationStatus model."""

    def test_relation_status_creation(self):
        """Test creating a relation status."""
        status = RelationStatus.objects.create(status="Purchased")
        assert status.status == "Purchased"

    def test_relation_status_string_representation(self):
        """Test the string representation of a relation status."""
        status = RelationStatus.objects.create(status="Purchased")
        assert str(status) == "Purchased"

    def test_relation_status_uniqueness(self):
        """Test that relation status must be unique."""
        RelationStatus.objects.create(status="Purchased")
        with pytest.raises(IntegrityError):
            RelationStatus.objects.create(status="Purchased")
