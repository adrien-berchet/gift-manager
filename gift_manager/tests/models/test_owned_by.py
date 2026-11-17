"""Tests for the ``owned_by`` queryset helper of permissioned models."""

import pytest

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory


@pytest.mark.django_db
class TestOwnedBy:
    """``owned_by(user)`` returns only objects the user owns."""

    def test_returns_owned_person_only(self, user_factory):
        """A person only shared with the user is not owned by them."""
        alice, bob = user_factory(), user_factory()
        owned = PersonFactory(owner=alice)
        shared = PersonFactory(owner=bob, shared_with=[alice])

        assert list(Person.objects.owned_by(alice)) == [owned]
        assert shared not in Person.objects.owned_by(alice)

    @pytest.mark.parametrize("level", [PermissionLevel.VIEWER, PermissionLevel.EDITOR])
    def test_non_owner_levels_excluded(self, user_factory, level):
        """Viewer and editor permissions do not make the user an owner."""
        alice, bob = user_factory(), user_factory()
        gift = GiftFactory()
        create_or_update_permission(bob, gift, permission_level=PermissionLevel.OWNER)
        create_or_update_permission(alice, gift, permission_level=level)

        assert gift not in Gift.objects.owned_by(alice)
        assert gift in Gift.objects.owned_by(bob)

    def test_works_for_groups_gifts_and_plans(self, user_factory):
        """The helper is available on every permissioned model."""
        alice = user_factory()
        group = PersonGroupFactory()
        gift = GiftFactory()
        plan = RelationFactory()
        for obj in (group, gift, plan):
            create_or_update_permission(alice, obj, permission_level=PermissionLevel.OWNER)

        assert list(PersonGroup.objects.owned_by(alice)) == [group]
        assert list(Gift.objects.owned_by(alice)) == [gift]
        assert list(Relation.objects.owned_by(alice)) == [plan]

    def test_owner_and_other_rows_do_not_combine(self, user_factory):
        """An owner row of another user and a viewer row of this user do not match."""
        alice, bob = user_factory(), user_factory()
        person = PersonFactory(owner=bob, shared_with=[alice])

        assert person not in Person.objects.owned_by(alice)
