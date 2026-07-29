"""Tests for the deterministic seed data function.

Validates that :func:`gift_manager.seed_data.create_seed_data` produces
the expected object graph with correct counts, hierarchies, permissions,
encrypted emails, M2M relationships and relation links.
"""

import pytest
from django.contrib.auth.models import User

from gift_manager.email_encoding import decode_email
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import PersonGroupPermission
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.seed_data import SeedData
from gift_manager.services import PermissionService


@pytest.fixture
def data(db):
    """Create seed data once for this module's tests."""
    from gift_manager.seed_data import create_seed_data

    return create_seed_data()


# =====================================================================
# Object counts
# =====================================================================


class TestObjectCounts:
    """Verify that the seed creates the expected number of objects."""

    def test_user_count(self, data):
        assert User.objects.filter(username__in=["alice", "bob"]).count() == 2

    def test_status_count(self, data):
        assert len(data.statuses) == 5
        assert RelationStatus.objects.count() >= 5
        assert data.statuses["abandoned"].status_en == "Abandoned"
        assert data.statuses["abandoned"].status_fr == "Abandonné"

    def test_group_count(self, data):
        assert len(data.groups) == 3
        assert PersonGroup.objects.count() >= 3

    def test_person_count(self, data):
        assert len(data.persons) == 5
        assert Person.objects.count() >= 5

    def test_tag_count(self, data):
        assert len(data.tags) == 3
        assert GiftTag.objects.count() >= 3

    def test_gift_count(self, data):
        assert len(data.gifts) == 4
        assert Gift.objects.count() >= 4

    def test_event_count(self, data):
        assert len(data.events) == 3
        assert Event.objects.count() >= 3

    def test_relation_count(self, data):
        assert len(data.relations) == 4
        assert Relation.objects.count() >= 4


# =====================================================================
# Return type
# =====================================================================


class TestReturnType:
    """Verify the function returns a frozen SeedData dataclass."""

    def test_returns_seed_data(self, data):
        assert isinstance(data, SeedData)

    def test_frozen(self, data):
        with pytest.raises(AttributeError):
            data.alice = None  # type: ignore[misc]


# =====================================================================
# Hierarchies
# =====================================================================


class TestHierarchies:
    """Verify group and tag parent-child relationships."""

    def test_close_family_parent_is_family(self, data):
        close_family = data.groups["close_family"]
        assert data.groups["family"] in close_family.parent_groups.all()

    def test_gadgets_parent_is_electronics(self, data):
        gadgets = data.tags["gadgets"]
        assert data.tags["electronics"] in gadgets.parent_tags.all()

    def test_family_has_close_family_as_child(self, data):
        family = data.groups["family"]
        assert data.groups["close_family"] in family.child_groups.all()

    def test_electronics_has_gadgets_as_child(self, data):
        electronics = data.tags["electronics"]
        assert data.tags["gadgets"] in electronics.child_tags.all()


# =====================================================================
# Person group memberships
# =====================================================================


class TestPersonGroupMemberships:
    """Verify which persons belong to which groups."""

    def test_mom_in_family_and_close_family(self, data):
        mom_groups = set(data.persons["mom"].groups.all())
        assert data.groups["family"] in mom_groups
        assert data.groups["close_family"] in mom_groups

    def test_dad_in_family_and_close_family(self, data):
        dad_groups = set(data.persons["dad"].groups.all())
        assert data.groups["family"] in dad_groups
        assert data.groups["close_family"] in dad_groups

    def test_sister_in_family_only(self, data):
        sister_groups = list(data.persons["sister"].groups.all())
        assert sister_groups == [data.groups["family"]]

    def test_best_friend_in_friends(self, data):
        bf_groups = list(data.persons["best_friend"].groups.all())
        assert bf_groups == [data.groups["friends"]]

    def test_colleague_in_no_groups(self, data):
        assert data.persons["colleague"].groups.count() == 0


# =====================================================================
# Permissions - alice OWNER on all
# =====================================================================


class TestAliceOwnerPermissions:
    """Alice should be OWNER on every entity."""

    @pytest.mark.parametrize(
        "collection",
        ["groups", "persons", "tags", "gifts", "events"],
    )
    def test_alice_owner_on_dict_collections(self, data, collection):
        for obj in getattr(data, collection).values():
            perm = PermissionService.get_permission(obj, data.alice)
            assert perm == PermissionLevel.OWNER, f"alice should be OWNER on {obj!r}, got {perm}"

    def test_alice_owner_on_relations(self, data):
        for rel in data.relations:
            perm = PermissionService.get_permission(rel, data.alice)
            assert perm == PermissionLevel.OWNER


# =====================================================================
# Permissions - bob mixed access
# =====================================================================


class TestBobPermissions:
    """Bob's permissions match the permission matrix."""

    # Groups
    def test_bob_viewer_family(self, data):
        assert (
            PermissionService.get_permission(data.groups["family"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_none_close_family(self, data):
        assert (
            PermissionService.get_permission(data.groups["close_family"], data.bob)
            == PermissionLevel.NONE
        )

    def test_bob_editor_friends(self, data):
        assert (
            PermissionService.get_permission(data.groups["friends"], data.bob)
            == PermissionLevel.EDITOR
        )

    # Persons
    def test_bob_viewer_mom(self, data):
        assert (
            PermissionService.get_permission(data.persons["mom"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_viewer_dad(self, data):
        assert (
            PermissionService.get_permission(data.persons["dad"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_none_sister(self, data):
        assert (
            PermissionService.get_permission(data.persons["sister"], data.bob)
            == PermissionLevel.NONE
        )

    def test_bob_editor_best_friend(self, data):
        assert (
            PermissionService.get_permission(data.persons["best_friend"], data.bob)
            == PermissionLevel.EDITOR
        )

    def test_bob_none_colleague(self, data):
        assert (
            PermissionService.get_permission(data.persons["colleague"], data.bob)
            == PermissionLevel.NONE
        )

    # Tags
    def test_bob_viewer_electronics(self, data):
        assert (
            PermissionService.get_permission(data.tags["electronics"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_none_gadgets(self, data):
        assert (
            PermissionService.get_permission(data.tags["gadgets"], data.bob) == PermissionLevel.NONE
        )

    def test_bob_editor_books(self, data):
        assert (
            PermissionService.get_permission(data.tags["books"], data.bob) == PermissionLevel.EDITOR
        )

    # Gifts
    def test_bob_viewer_smartphone(self, data):
        assert (
            PermissionService.get_permission(data.gifts["smartphone"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_viewer_novel(self, data):
        assert (
            PermissionService.get_permission(data.gifts["novel"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_editor_watch(self, data):
        assert (
            PermissionService.get_permission(data.gifts["watch"], data.bob)
            == PermissionLevel.EDITOR
        )

    def test_bob_none_scarf(self, data):
        assert (
            PermissionService.get_permission(data.gifts["scarf"], data.bob) == PermissionLevel.NONE
        )

    # Events
    def test_bob_viewer_christmas(self, data):
        assert (
            PermissionService.get_permission(data.events["christmas"], data.bob)
            == PermissionLevel.VIEWER
        )

    def test_bob_none_mom_birthday(self, data):
        assert (
            PermissionService.get_permission(data.events["mom_birthday"], data.bob)
            == PermissionLevel.NONE
        )

    def test_bob_editor_graduation(self, data):
        assert (
            PermissionService.get_permission(data.events["graduation"], data.bob)
            == PermissionLevel.EDITOR
        )

    # Relations
    def test_bob_viewer_relation_0(self, data):
        assert (
            PermissionService.get_permission(data.relations[0], data.bob) == PermissionLevel.VIEWER
        )

    def test_bob_none_relation_1(self, data):
        assert PermissionService.get_permission(data.relations[1], data.bob) == PermissionLevel.NONE

    def test_bob_editor_relation_2(self, data):
        assert (
            PermissionService.get_permission(data.relations[2], data.bob) == PermissionLevel.EDITOR
        )

    def test_bob_none_relation_3(self, data):
        assert PermissionService.get_permission(data.relations[3], data.bob) == PermissionLevel.NONE


# =====================================================================
# Cascade inheritance
# =====================================================================


class TestCascadeInheritance:
    """Verify permission inheritance through the group hierarchy."""

    def test_alice_inherits_owner_on_close_family(self, data):
        """Alice has no direct permission on close_family but inherits OWNER from Family."""
        # Alice has OWNER + inherit=True on Family → should cascade to Close Family.
        perm = PermissionService.get_effective_permission_for_group(
            data.groups["close_family"],
            data.alice,
        )
        assert perm == PermissionLevel.OWNER

    def test_family_permission_has_inherit_flag(self, data):
        pgp = PersonGroupPermission.objects.get(user=data.alice, group=data.groups["family"])
        assert pgp.inherit_permissions is True


# =====================================================================
# Encrypted emails
# =====================================================================


class TestEncryptedEmails:
    """Verify that person emails are stored encrypted and decode correctly."""

    def test_raw_email_is_not_plaintext(self, data):
        mom = Person.objects.get(pk=data.persons["mom"].pk)
        assert mom.email_address != "mom@example.com"
        assert mom.email_address  # not None / empty

    def test_decode_email_returns_correct_value(self, data):
        mom = Person.objects.get(pk=data.persons["mom"].pk)
        assert decode_email(mom.email_address) == "mom@example.com"

    def test_colleague_has_no_email(self, data):
        colleague = Person.objects.get(pk=data.persons["colleague"].pk)
        assert not colleague.email_address

    def test_user_email_is_encrypted(self, data):
        alice = User.objects.get(pk=data.alice.pk)
        assert alice.email != "alice@example.com"
        assert decode_email(alice.email) == "alice@example.com"


# =====================================================================
# Gift-tag M2M
# =====================================================================


class TestGiftTagM2M:
    """Verify gift ↔ tag many-to-many relationships."""

    def test_smartphone_has_electronics_and_gadgets(self, data):
        tags = set(data.gifts["smartphone"].tags.all())
        assert data.tags["electronics"] in tags
        assert data.tags["gadgets"] in tags
        assert len(tags) == 2

    def test_novel_has_books(self, data):
        tags = list(data.gifts["novel"].tags.all())
        assert tags == [data.tags["books"]]

    def test_watch_has_gadgets(self, data):
        tags = list(data.gifts["watch"].tags.all())
        assert tags == [data.tags["gadgets"]]

    def test_scarf_has_no_tags(self, data):
        assert data.gifts["scarf"].tags.count() == 0


# =====================================================================
# Relations
# =====================================================================


class TestRelations:
    """Verify relation links (person/group, gift, event, status)."""

    def test_relation_0_mom_smartphone_christmas_idea(self, data):
        r = data.relations[0]
        assert r.person == data.persons["mom"]
        assert r.gift == data.gifts["smartphone"]
        assert r.event == data.events["christmas"]
        assert r.status == data.statuses["idea"]

    def test_relation_1_dad_novel_mom_birthday_planned(self, data):
        r = data.relations[1]
        assert r.person == data.persons["dad"]
        assert r.gift == data.gifts["novel"]
        assert r.event == data.events["mom_birthday"]
        assert r.status == data.statuses["planned"]

    def test_relation_2_bestfriend_watch_graduation_purchased(self, data):
        r = data.relations[2]
        assert r.person == data.persons["best_friend"]
        assert r.gift == data.gifts["watch"]
        assert r.event == data.events["graduation"]
        assert r.status == data.statuses["purchased"]

    def test_relation_3_group_scarf_christmas_given(self, data):
        r = data.relations[3]
        assert r.person is None
        assert r.group == data.groups["family"]
        assert r.gift == data.gifts["scarf"]
        assert r.event == data.events["christmas"]
        assert r.status == data.statuses["given"]
