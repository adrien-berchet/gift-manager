# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime

import pytest

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonPermission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.utils import requires_postgresql


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
