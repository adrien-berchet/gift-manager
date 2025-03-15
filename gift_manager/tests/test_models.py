import uuid
from datetime import date
from datetime import datetime

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from gift_manager.models import Event
from gift_manager.models import EventPermission
from gift_manager.models import Gift
from gift_manager.models import GiftPermission
from gift_manager.models import GiftTag
from gift_manager.models import GiftTagPermission
from gift_manager.models import Invitation
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import RelationStatus


@pytest.fixture
def username():
    """Create a test username."""
    return "testuser"


@pytest.fixture
def userpassword():
    """Create a test user password."""
    return "password123"


@pytest.fixture
def user(username, userpassword):
    """Create a test user."""
    return User.objects.create_user(username=username, password=userpassword)


@pytest.fixture
def person_first_name():
    """Create a test person first name."""
    return "John"


@pytest.fixture
def person_family_name():
    """Create a test person family name."""
    return "Doe"


@pytest.fixture
def person(person_first_name, person_family_name):
    """Create a test person."""
    return Person.objects.create(first_name=person_first_name, family_name=person_family_name)


@pytest.fixture
def group_name():
    """Create a test person group name."""
    return "Family"


@pytest.fixture
def group(group_name):
    """Create a test person group."""
    return PersonGroup.objects.create(name=group_name)


@pytest.fixture
def gift_tag_name():
    """Create a test gift tag name."""
    return "Electronics"


@pytest.fixture
def gift_tag(gift_tag_name):
    """Create a test gift tag."""
    return GiftTag.objects.create(name=gift_tag_name)


@pytest.fixture
def gift_name():
    """Create a test gift name."""
    return "Smartphone"


@pytest.fixture
def gift_comment():
    """Create a test gift comment."""
    return "Latest model"


@pytest.fixture
def gift(gift_name, gift_comment):
    """Create a test gift."""
    return Gift.objects.create(name=gift_name, comment=gift_comment)


@pytest.fixture
def event_name():
    """Create a test event name."""
    return "Birthday"


@pytest.fixture
def event_comment():
    """Create a test event comment."""
    return "Annual celebration"


@pytest.fixture
def event_usual_date():
    """Create a test event usual date."""
    return date(2000, 5, 15)


@pytest.fixture
def event_recurrence():
    """Create a test event recurrence."""
    return "yearly"


@pytest.fixture
def event(event_name, event_comment, event_usual_date, event_recurrence):
    """Create a test event."""
    return Event.objects.create(
        name=event_name,
        comment=event_comment,
        usual_date=event_usual_date,
        recurrence=event_recurrence,
    )


@pytest.fixture
def status():
    """Create a test relation status."""
    return RelationStatus.objects.create(status="Idea")


@pytest.mark.django_db
class TestProfile:
    """Tests for the Profile model."""

    @pytest.fixture
    def friend(self, userpassword):
        """Create a second test user."""
        return User.objects.create_user(username="testfriend", password=userpassword)

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
        assert gift_tag.parent_tag is None
        assert isinstance(gift_tag.creation_date, datetime)

    def test_gift_tag_string_representation(self, gift_tag, gift_tag_name):
        """Test the string representation of a gift tag."""
        assert str(gift_tag) == gift_tag_name

    def test_gift_tag_hierarchy(self, gift_tag):
        """Test creating a hierarchical structure of gift tags."""
        sub_tag = GiftTag.objects.create(name="Computers", parent_tag=gift_tag)
        assert sub_tag.parent_tag == gift_tag

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
