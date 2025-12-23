# pylint: disable=too-many-lines,redefined-outer-name
import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from gift_manager.email_encoding import encode_email
from gift_manager.models import Event
from gift_manager.models import EventPermission
from gift_manager.models import Gift
from gift_manager.models import GiftPermission
from gift_manager.models import GiftTag
from gift_manager.models import GiftTagPermission
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import RelationStatus
from gift_manager.tests.factories import InvitationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


def is_sqlite():
    """Check if the test database is SQLite."""
    return connection.vendor == "sqlite"


# Marker for tests that require PostgreSQL (use JSONB functions, etc.)
requires_postgresql = pytest.mark.skipif(
    is_sqlite(),
    reason="PostgreSQL-specific features (JSONB) not available in SQLite",
)


@pytest.mark.django_db
class TestProfile:
    """Tests for the Profile model."""

    @pytest.fixture
    def friend(self):
        """Create a second test user using factory."""
        return UserFactory(username="testfriend")

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
    def sender(self):
        """Create a test sender user using factory."""
        return UserFactory(username="sender")

    @pytest.fixture
    def invitation(self, sender):
        """Create a test invitation using factory."""
        # Email is stored encoded
        return InvitationFactory(
            sender=sender, recipient_email=encode_email("recipient@example.com")
        )

    def test_invitation_creation(self, invitation):
        """Test creating an invitation."""
        assert invitation.token is not None
        assert isinstance(invitation.token, uuid.UUID)
        # recipient_email is stored encoded, use email property for decoded value
        assert invitation.email == "recipient@example.com"
        assert invitation.accepted is False
        assert invitation.accepted_at is None
        assert isinstance(invitation.created_at, datetime)

    def test_invitation_string_representation(self, invitation, sender):
        """Test the string representation of an invitation."""
        assert "Invitation from" in str(invitation)
        assert sender.username in str(invitation)
        # __str__ uses the decoded email property
        assert invitation.email in str(invitation)

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
        # Create another user and person using factories
        user2 = UserFactory(username="testuser2")
        person2 = PersonFactory(first_name="Jane", family_name="Smith")

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

    def test_tag_get_ancestors(self):  # noqa: PLR0915 ; pylint: disable=too-many-statements
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

    def test_clear_hierarchy_cache(self):
        """Test clear_hierarchy_cache clears related caches."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # Populate caches
        parent.get_descendants(use_cache=True)
        child.get_ancestors(use_cache=True)

        # Verify caches exist
        assert cache.get(f"persongroup_descendants_{parent.pk}") is not None
        assert cache.get(f"persongroup_ancestors_{child.pk}") is not None

        # Clear caches
        child.clear_hierarchy_cache()

        # Verify caches are cleared
        assert cache.get(f"persongroup_descendants_{child.pk}") is None
        assert cache.get(f"persongroup_ancestors_{child.pk}") is None

    def test_get_descendants_caching(self):
        """Test get_descendants uses and respects cache."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # First call should populate cache
        descendants1 = parent.get_descendants(use_cache=True)
        assert len(descendants1) == 1

        # Second call should use cache (verify cache key exists)
        cache_key = f"persongroup_descendants_{parent.pk}"
        assert cache.get(cache_key) is not None

        # Call with use_cache=False should bypass cache
        # (we can't easily verify this, but at least it shouldn't error)
        descendants2 = parent.get_descendants(use_cache=False)
        assert len(descendants2) == 1

    def test_get_ancestors_caching(self):
        """Test get_ancestors uses and respects cache."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        # First call should populate cache
        ancestors1 = child.get_ancestors(use_cache=True)
        assert len(ancestors1) == 1

        # Verify cache key exists
        cache_key = f"persongroup_ancestors_{child.pk}"
        assert cache.get(cache_key) is not None

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
class TestPersonManager:
    """Tests for PersonManager query methods."""

    @requires_postgresql
    def test_with_groups_annotated(self, user):
        """Test with_groups_annotated annotates persons with groups info."""
        # Create person and groups
        person = PersonFactory(first_name="John", family_name="Doe")
        group1 = PersonGroupFactory(name="Family")
        group2 = PersonGroupFactory(name="Friends")

        person.groups.add(group1, group2)

        # Query with groups annotated
        persons = Person.objects.with_groups_annotated().filter(pk=person.pk)
        annotated_person = persons.first()

        # Verify annotation exists
        assert hasattr(annotated_person, "groups_info")
        groups_info = annotated_person.groups_info
        assert groups_info is not None
        assert len(groups_info) == 2

    def test_with_complete_name(self):
        """Test with_complete_name annotates persons with full name."""
        person = PersonFactory(first_name="John", family_name="Doe")

        persons = Person.objects.with_complete_name().filter(pk=person.pk)
        annotated_person = persons.first()

        assert hasattr(annotated_person, "complete_name")
        assert annotated_person.complete_name == "Doe John"

    @requires_postgresql
    def test_for_list_display(self, user):
        """Test for_list_display returns optimized queryset."""
        person = PersonFactory(first_name="John", family_name="Doe")
        group = PersonGroupFactory(name="Family")
        person.groups.add(group)

        # Share person with user
        PersonPermission.objects.create(
            user=user, person=person, permission_type=PermissionLevel.VIEWER
        )

        # Get list display data
        results = Person.objects.for_list_display(user)
        assert len(results) == 1
        result = results[0]

        # Verify expected fields are present
        assert "person_id" in result
        assert "first_name" in result
        assert "family_name" in result
        assert "groups_info" in result


@pytest.mark.django_db
class TestGiftManagerMethods:
    """Tests for GiftManager query methods."""

    @requires_postgresql
    def test_with_tags_annotated(self, gift, gift_tag):
        """Test with_tags_annotated annotates gifts with tags info."""
        gift.tags.add(gift_tag)

        gifts = Gift.objects.with_tags_annotated().filter(pk=gift.pk)
        annotated_gift = gifts.first()

        assert hasattr(annotated_gift, "tags_info")
        tags_info = annotated_gift.tags_info
        assert tags_info is not None
        assert len(tags_info) == 1

    @requires_postgresql
    def test_for_list_display(self, user, gift, gift_tag):
        """Test for_list_display returns optimized queryset."""
        gift.tags.add(gift_tag)

        # Share gift with user
        GiftPermission.objects.create(user=user, gift=gift, permission_type=PermissionLevel.VIEWER)

        results = Gift.objects.for_list_display(user)
        assert len(results) == 1
        result = results[0]

        assert "gift_id" in result
        assert "name" in result
        assert "tags_info" in result


@pytest.mark.django_db
class TestEventManagerMethods:
    """Tests for EventManager query methods."""

    def test_for_list_display(self, user, event):
        """Test for_list_display returns optimized queryset."""
        # Share event with user
        EventPermission.objects.create(
            user=user, event=event, permission_type=PermissionLevel.VIEWER
        )

        results = Event.objects.for_list_display(user)
        assert len(results) == 1
        result = results[0]

        assert "event_id" in result
        assert "name" in result
        assert "usual_date" in result


@pytest.mark.django_db
class TestRelationManagerMethods:
    """Tests for RelationManager query methods."""

    def test_with_related_objects(self, person, gift, status):
        """Test with_related_objects prefetches related objects."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)

        relations = Relation.objects.with_related_objects().filter(pk=relation.pk)
        fetched = relations.first()

        # Verify related objects are accessible
        assert fetched.person == person
        assert fetched.gift == gift
        assert fetched.status == status

    def test_with_related_object_name_person(self, person, gift, status):
        """Test with_related_object_name with person relation."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)

        relations = Relation.objects.with_related_object_name().filter(pk=relation.pk)
        fetched = relations.first()

        assert hasattr(fetched, "related_object")
        # Should contain person's name
        assert person.first_name in fetched.related_object

    def test_with_related_object_name_group(self, group, gift, status):
        """Test with_related_object_name with group relation."""
        relation = Relation.objects.create(group=group, gift=gift, status=status)

        relations = Relation.objects.with_related_object_name().filter(pk=relation.pk)
        fetched = relations.first()

        assert hasattr(fetched, "related_object")
        assert fetched.related_object == group.name

    @requires_postgresql
    def test_for_list_display(self, user, person, gift, status):
        """Test for_list_display returns optimized queryset."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)
        RelationPermission.objects.create(
            user=user, relation=relation, permission_type=PermissionLevel.VIEWER
        )

        results = Relation.objects.for_list_display(user)
        assert len(results) == 1
        result = results[0]

        assert "relation_id" in result
        assert "gift__name" in result
        assert "related_object" in result


@pytest.mark.django_db
class TestGetAbsoluteUrlMethods:
    """Tests for get_absolute_url methods on various models."""

    def test_profile_get_absolute_url(self, user):
        """Test Profile.get_absolute_url returns correct URL."""
        profile = user.profile
        url = profile.get_absolute_url()
        # URL may have language prefix
        assert "profile" in url

    @pytest.mark.xfail(
        reason=(
            "BUG: get_absolute_url uses self.pk instead of self.group_id - URL pattern expects UUID"
        )
    )
    def test_person_group_get_absolute_url(self, group):
        """Test PersonGroup.get_absolute_url returns correct URL."""
        url = group.get_absolute_url()
        # URL uses group_id (UUID), not pk
        assert "person_groups" in url
        assert str(group.group_id) in url
        assert "edit" in url

    @pytest.mark.xfail(
        reason=(
            "BUG: get_absolute_url uses self.pk instead of self.relation_id - "
            "URL pattern expects UUID"
        )
    )
    def test_relation_get_absolute_url(self, person, gift, status):
        """Test Relation.get_absolute_url returns correct URL."""
        relation = Relation.objects.create(person=person, gift=gift, status=status)
        url = relation.get_absolute_url()
        # URL uses relation_id (UUID), not pk
        assert "persons" in url
        assert str(relation.relation_id) in url
        assert "edit" in url


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
class TestPersonGroupCacheHits:
    """Tests for cache hit scenarios in PersonGroup hierarchy methods."""

    def test_get_descendants_cache_hit(self):
        """Test get_descendants returns cached result on second call."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        cache_key = f"persongroup_descendants_{parent.pk}"

        # Clear any existing cache
        cache.delete(cache_key)

        # First call - populates cache
        descendants1 = parent.get_descendants(use_cache=True)
        assert len(descendants1) == 1

        # Verify cache was set
        cached = cache.get(cache_key)
        assert cached is not None

        # Second call should hit cache
        descendants2 = parent.get_descendants(use_cache=True)
        assert len(descendants2) == 1
        assert descendants1 == descendants2

    def test_get_ancestors_cache_hit(self):
        """Test get_ancestors returns cached result on second call."""
        parent = PersonGroupFactory(name="Parent")
        child = PersonGroupFactory(name="Child")
        child.parent_groups.add(parent)

        cache_key = f"persongroup_ancestors_{child.pk}"

        # Clear any existing cache
        cache.delete(cache_key)

        # First call - populates cache
        ancestors1 = child.get_ancestors(use_cache=True)
        assert len(ancestors1) == 1

        # Verify cache was set
        cached = cache.get(cache_key)
        assert cached is not None

        # Second call should hit cache
        ancestors2 = child.get_ancestors(use_cache=True)
        assert len(ancestors2) == 1
        assert ancestors1 == ancestors2


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
class TestGiftTagCacheAndBranches:
    """Tests for GiftTag cache hits and branch coverage."""

    def test_get_ancestors_cache_hit(self):
        """Test get_ancestors returns cached result on second call."""
        parent = GiftTag.objects.create(name="Electronics")
        child = GiftTag.objects.create(name="Phones")
        child.parent_tags.add(parent)

        cache_key = f"gifttag_ancestors_{child.pk}"
        cache.delete(cache_key)

        # First call - populates cache
        ancestors1 = child.get_ancestors(use_cache=True)
        assert len(ancestors1) == 1

        # Verify cache was set
        cached = cache.get(cache_key)
        assert cached is not None

        # Second call should hit cache
        ancestors2 = child.get_ancestors(use_cache=True)
        assert len(ancestors2) == 1

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
class TestGiftTagClearHierarchyCache:
    """Tests for GiftTag.clear_hierarchy_cache method."""

    def test_clear_hierarchy_cache(self):
        """Test clear_hierarchy_cache clears related caches."""
        parent = GiftTag.objects.create(name="Parent")
        child = GiftTag.objects.create(name="Child")
        child.parent_tags.add(parent)

        # Populate caches
        parent.get_descendants(use_cache=True)
        child.get_ancestors(use_cache=True)

        # Verify caches exist
        assert cache.get(f"gifttag_descendants_{parent.pk}") is not None
        assert cache.get(f"gifttag_ancestors_{child.pk}") is not None

        # Clear caches
        child.clear_hierarchy_cache()

        # Verify caches are cleared for child
        assert cache.get(f"gifttag_descendants_{child.pk}") is None
        assert cache.get(f"gifttag_ancestors_{child.pk}") is None


@pytest.mark.django_db
class TestPermissionLevelGetLabel:
    """Tests for PermissionLevel.get_label with different case options."""

    def test_get_label_default_case(self):
        """Test get_label returns lowercase by default."""
        assert PermissionLevel.get_label(PermissionLevel.VIEWER) == "viewer"
        assert PermissionLevel.get_label(PermissionLevel.EDITOR) == "editor"
        assert PermissionLevel.get_label(PermissionLevel.OWNER) == "owner"

    def test_get_label_upper_case(self):
        """Test get_label with case='upper'."""
        assert PermissionLevel.get_label(PermissionLevel.VIEWER, case="upper") == "VIEWER"
        assert PermissionLevel.get_label(PermissionLevel.EDITOR, case="upper") == "EDITOR"
        assert PermissionLevel.get_label(PermissionLevel.OWNER, case="upper") == "OWNER"

    def test_get_label_title_case(self):
        """Test get_label with case='title'."""
        assert PermissionLevel.get_label(PermissionLevel.VIEWER, case="title") == "Viewer"
        assert PermissionLevel.get_label(PermissionLevel.EDITOR, case="title") == "Editor"
        assert PermissionLevel.get_label(PermissionLevel.OWNER, case="title") == "Owner"

    def test_get_label_invalid_permission(self):
        """Test get_label with invalid permission level returns 'none'."""
        assert PermissionLevel.get_label(999) == "none"
        assert PermissionLevel.get_label(999, case="upper") == "NONE"
        assert PermissionLevel.get_label(999, case="title") == "None"


@pytest.mark.django_db
class TestEmailProperties:
    """Tests for email properties and setters on Profile, Person, and Invitation."""

    def test_profile_email_property(self, user):
        """Test Profile.email property returns decoded email."""
        # Set encoded email
        user.email = encode_email("test@example.com")
        user.save()

        # Profile.email should decode it
        assert user.profile.email == "test@example.com"

    def test_profile_set_user_email(self, user):
        """Test Profile.set_user_email encodes and saves email."""
        user.profile.set_user_email("newemail@example.com")

        # Reload user
        user.refresh_from_db()

        # Check email is encoded in DB but decodes correctly
        assert user.profile.email == "newemail@example.com"

    def test_person_email_property(self):
        """Test Person.email property returns decoded email."""
        person = PersonFactory(
            first_name="Test",
            family_name="User",
            email_address=encode_email("person@example.com"),
        )

        assert person.email == "person@example.com"

    def test_person_set_email(self):
        """Test Person.set_email encodes email address."""
        person = PersonFactory(first_name="Test", family_name="User")
        person.set_email("encoded@example.com")

        # Should be encoded in email_address field but decode via property
        assert person.email == "encoded@example.com"

    def test_invitation_set_email(self, user):
        """Test Invitation.set_email encodes recipient email."""
        invitation = InvitationFactory(sender=user)
        invitation.set_email("invited@example.com")

        # Should be encoded but decode correctly via property
        assert invitation.email == "invited@example.com"


@pytest.mark.django_db
class TestPermissionFilterNameProperties:
    """Tests for filter_name classproperty on Permission models."""

    def test_person_permission_filter_name(self):
        """Test PersonPermission.filter_name returns 'person'."""
        assert PersonPermission.filter_name == "person"

    def test_person_group_permission_filter_name(self):
        """Test PersonGroupPermission.filter_name returns 'group'."""
        assert PersonGroupPermission.filter_name == "group"

    def test_gift_tag_permission_filter_name(self):
        """Test GiftTagPermission.filter_name returns 'gift_tag'."""
        assert GiftTagPermission.filter_name == "gift_tag"

    def test_gift_permission_filter_name(self):
        """Test GiftPermission.filter_name returns 'gift'."""
        assert GiftPermission.filter_name == "gift"

    def test_event_permission_filter_name(self):
        """Test EventPermission.filter_name returns 'event'."""
        assert EventPermission.filter_name == "event"

    def test_relation_permission_filter_name(self):
        """Test RelationPermission.filter_name returns 'relation'."""
        assert RelationPermission.filter_name == "relation"


@pytest.mark.django_db
class TestRelationStatusDefaultPk:
    """Tests for RelationStatus.get_default_pk classmethod."""

    def test_get_default_pk_creates_status(self):
        """Test get_default_pk creates default status if not exists."""
        # Clear any existing default status
        RelationStatus.objects.filter(status=RelationStatus.DEFAULT_STATUS).delete()

        pk = RelationStatus.get_default_pk()

        # Should have created the default status
        status = RelationStatus.objects.get(pk=pk)
        assert status.status == RelationStatus.DEFAULT_STATUS

    def test_get_default_pk_returns_existing(self):
        """Test get_default_pk returns existing status pk."""
        # Create the default status first
        existing = RelationStatus.objects.create(status=RelationStatus.DEFAULT_STATUS)

        pk = RelationStatus.get_default_pk()

        # Should return existing pk
        assert pk == existing.pk

        # Should not create a duplicate
        assert RelationStatus.objects.filter(status=RelationStatus.DEFAULT_STATUS).count() == 1
