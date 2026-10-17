# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction

from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.models import RelationStatus
from gift_manager.tests.utils import requires_postgresql


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

    def test_relation_database_rejects_missing_recipient(self, gift, status):
        """The database enforces that a relation has exactly one recipient."""
        with pytest.raises(IntegrityError), transaction.atomic():
            Relation.objects.create(gift=gift, status=status)

    def test_relation_database_rejects_two_recipients(self, person, group, gift, status):
        """The database rejects rows with both person and group recipients."""
        with pytest.raises(IntegrityError), transaction.atomic():
            Relation.objects.create(person=person, group=group, gift=gift, status=status)

    def test_relation_recipient_database_constraint(self, person, group, gift, status):
        """The database rejects rows without exactly one recipient."""
        with pytest.raises(IntegrityError), transaction.atomic():
            Relation.objects.create(gift=gift, status=status)

        with pytest.raises(IntegrityError), transaction.atomic():
            Relation.objects.create(person=person, group=group, gift=gift, status=status)

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
