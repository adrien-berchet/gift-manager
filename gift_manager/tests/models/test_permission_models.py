# pylint: disable=redefined-outer-name
import pytest

from gift_manager.models import EventPermission
from gift_manager.models import GiftPermission
from gift_manager.models import GiftTagPermission
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroupPermission
from gift_manager.models import PersonPermission
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestAccessibleByMethod:
    """Tests for the accessible_by query method."""

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

    def test_accessible_by_deduplicates_owned_person_with_multiple_permissions(self, user, person):
        """An owned person is returned once even when shared with another user."""
        friend = UserFactory(username="friend")
        person.account = user
        person.save(update_fields=["account"])
        PersonPermission.objects.create(
            user=user, person=person, permission_type=PermissionLevel.OWNER
        )
        PersonPermission.objects.create(
            user=friend, person=person, permission_type=PermissionLevel.VIEWER
        )

        accessible = Person.objects.accessible_by(user).filter(pk=person.pk)

        assert list(accessible) == [person]


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
