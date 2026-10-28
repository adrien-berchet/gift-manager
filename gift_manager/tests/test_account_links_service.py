"""Tests for person account linking service."""

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from gift_manager import account_links
from gift_manager.account_links import LinkRefused
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import RelationPermission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_owner_links_record_to_friend():
    """An owner can link a person record to a confirmed friend."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)
    person = PersonFactory(owner=bob)

    linked = account_links.link(person, alice, bob)
    assert linked.account == alice
    person.refresh_from_db()
    assert person.account == alice


def test_editor_links_when_an_owner_is_a_friend():
    """An editor can link a person if at least one owner is friends with the account."""
    bob = UserFactory()
    carol = UserFactory()
    alice = UserFactory()
    # Carol is editor, Bob is owner. Alice is friends with both.
    bob.profile.friends.add(alice.profile)
    carol.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob)
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.EDITOR
    )

    linked = account_links.link(person, alice, carol)
    assert linked.account == alice
    person.refresh_from_db()
    assert person.account == alice


def test_editor_refused_when_no_owner_is_a_friend():
    """An editor cannot link a person if no owner is friends with the target account."""
    bob = UserFactory()
    carol = UserFactory()
    alice = UserFactory()
    # Carol is editor and friends with Alice, but owner Bob is NOT friends with Alice
    carol.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob)
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.EDITOR
    )

    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(person, alice, carol)
    assert exc_info.value.code == "no_friend_owner"
    person.refresh_from_db()
    assert person.account is None


def test_viewer_refused():
    """A viewer on a person record gets PermissionDenied when attempting to link."""
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()
    bob.profile.friends.add(alice.profile)
    carol.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob)
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.VIEWER
    )

    with pytest.raises(PermissionDenied):
        account_links.link(person, alice, carol)

    # Viewer trying to self-link also gets PermissionDenied before LinkRefused
    with pytest.raises(PermissionDenied):
        account_links.link(person, carol, carol)


def test_refused_for_a_non_friend():
    """Linking to a user who is not a friend of the actor is refused."""
    bob = UserFactory()
    stranger = UserFactory()
    person = PersonFactory(owner=bob)

    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(person, stranger, bob)
    assert exc_info.value.code == "not_friend"


def test_self_link_needs_owner():
    """Only an owner can mark a record as themselves."""
    bob = UserFactory()
    carol = UserFactory()
    person = PersonFactory(owner=bob)
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.EDITOR
    )

    # Editor linking to self is refused
    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(person, carol, carol)
    assert exc_info.value.code == "self_needs_owner"

    # Owner linking to self succeeds
    account_links.link(person, bob, bob)
    person.refresh_from_db()
    assert person.account == bob


def test_duplicate_guard_friend():
    """An owner cannot have two person records linked to the same friend account."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p1 = PersonFactory(owner=bob, account=alice)
    p2 = PersonFactory(owner=bob)

    assert account_links.duplicate_conflicts(p2, alice) == [p1]

    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(p2, alice, bob)
    assert exc_info.value.code == "duplicate"


def test_duplicate_guard_self():
    """An owner cannot have two person records marked as themselves."""
    bob = UserFactory()
    p1 = PersonFactory(owner=bob, account=bob)
    p2 = PersonFactory(owner=bob)

    assert account_links.duplicate_conflicts(p2, bob) == [p1]

    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(p2, bob, bob)
    assert exc_info.value.code == "duplicate"


def test_self_link_duplicate_through_co_owner():
    """A self-link is refused if a co-owner already owns another record linked to that account."""
    bob = UserFactory()
    carol = UserFactory()
    p1 = PersonFactory(owner=bob)
    # Carol owns p2 linked to Bob
    p2 = PersonFactory(owner=carol, account=bob)

    # Carol becomes co-owner of p1
    PermissionService.create_or_update_permission(carol, p1, permission_level=PermissionLevel.OWNER)

    assert account_links.duplicate_conflicts(p1, bob) == [p2]

    with pytest.raises(LinkRefused) as exc_info:
        account_links.link(p1, bob, bob)
    assert exc_info.value.code == "duplicate"


def test_sharing_as_owner_can_create_duplicates():
    """Sharing as owner does not run duplicate guard, but duplicate_conflicts detects it."""
    bob = UserFactory()
    carol = UserFactory()
    alice = UserFactory()

    p1 = PersonFactory(owner=bob, account=alice)
    p2 = PersonFactory(owner=carol, account=alice)

    # Bob shares p1 with Carol as OWNER
    PermissionService.create_or_update_permission(carol, p1, permission_level=PermissionLevel.OWNER)

    # Both p1 and p2 are now owned by Carol and linked to Alice
    conflicts = account_links.duplicate_conflicts(p1, alice)
    assert conflicts == [p2]


def test_relinking_same_account_is_a_noop():
    """Relinking a person to their current account is a no-op and does not raise duplicate."""
    bob = UserFactory()
    carol = UserFactory()
    alice = UserFactory()

    p1 = PersonFactory(owner=bob, account=alice)
    PersonFactory(owner=carol, account=alice)
    PermissionService.create_or_update_permission(carol, p1, permission_level=PermissionLevel.OWNER)

    # p1 already has duplicate conflict with p2, but relinking p1 to alice is a no-op
    res = account_links.link(p1, alice, bob)
    assert res.account == alice
    p1.refresh_from_db()
    assert p1.account == alice


def test_linking_replaces_another_link():
    """Linking a person already linked to another friend replaces the link."""
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()
    bob.profile.friends.add(alice.profile)
    bob.profile.friends.add(carol.profile)

    person = PersonFactory(owner=bob, account=alice)
    account_links.link(person, carol, bob)
    person.refresh_from_db()
    assert person.account == carol


def test_link_releases_claims_on_now_hidden_plans():
    """Linking releases claims the target account holds on surprise plans now hidden from them."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob)

    # Surprise plan for person, shared with Alice, claimed by Alice
    surprise_plan = RelationFactory(
        person=person,
        is_surprise=True,
        claimed_by=alice,
        claimed_at=timezone.now(),
    )
    RelationPermission.objects.create(
        user=bob, relation=surprise_plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=surprise_plan, permission_type=PermissionLevel.VIEWER
    )

    # Surprise plan claimed by Bob (claim isolation)
    bob_surprise = RelationFactory(
        person=person,
        is_surprise=True,
        claimed_by=bob,
        claimed_at=timezone.now(),
    )
    RelationPermission.objects.create(
        user=bob, relation=bob_surprise, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=bob_surprise, permission_type=PermissionLevel.VIEWER
    )

    # Non-surprise plan claimed by Alice
    normal_plan = RelationFactory(
        person=person,
        is_surprise=False,
        claimed_by=alice,
        claimed_at=timezone.now(),
    )
    RelationPermission.objects.create(
        user=bob, relation=normal_plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=normal_plan, permission_type=PermissionLevel.VIEWER
    )

    account_links.link(person, alice, bob)

    surprise_plan.refresh_from_db()
    assert surprise_plan.claimed_by is None
    assert surprise_plan.claimed_at is None

    bob_surprise.refresh_from_db()
    assert bob_surprise.claimed_by == bob

    normal_plan.refresh_from_db()
    assert normal_plan.claimed_by == alice


def test_link_releases_claims_on_group_surprises():
    """Linking releases claims the target account holds on group surprise plans."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    group = PersonGroupFactory()
    PermissionService.create_or_update_permission(
        bob, group, permission_level=PermissionLevel.OWNER
    )
    person = PersonFactory(owner=bob)
    person.groups.add(group)

    group_plan = GroupRelationFactory(
        group=group,
        is_surprise=True,
        claimed_by=alice,
        claimed_at=timezone.now(),
    )
    RelationPermission.objects.create(
        user=bob, relation=group_plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=group_plan, permission_type=PermissionLevel.VIEWER
    )

    account_links.link(person, alice, bob)

    group_plan.refresh_from_db()
    assert group_plan.claimed_by is None
    assert group_plan.claimed_at is None


def test_link_clears_dismissed_suggestion():
    """Linking clears link_suggestion_dismissed_account on the person record."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob, link_suggestion_dismissed_account=alice)
    assert person.link_suggestion_dismissed_account == alice

    account_links.link(person, alice, bob)
    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account is None


def test_revealed_surprise_count():
    """revealed_surprise_count counts surprise plans that would become visible upon unlinking."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p1 = PersonFactory(owner=bob, account=alice)
    p2 = PersonFactory(owner=bob, account=alice)

    # 2 surprise plans for p1 shared with Alice (revealed if p1 unlinked)
    plan1 = RelationFactory(person=p1, is_surprise=True)
    RelationPermission.objects.create(
        user=bob, relation=plan1, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=plan1, permission_type=PermissionLevel.VIEWER
    )

    plan2 = RelationFactory(person=p1, is_surprise=True)
    RelationPermission.objects.create(
        user=bob, relation=plan2, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=plan2, permission_type=PermissionLevel.VIEWER
    )

    # 1 surprise plan for p2 shared with Alice (NOT revealed if p1 unlinked)
    plan3 = RelationFactory(person=p2, is_surprise=True)
    RelationPermission.objects.create(
        user=bob, relation=plan3, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=plan3, permission_type=PermissionLevel.VIEWER
    )

    # 1 surprise plan for p1 NOT shared with Alice (Alice cannot see it anyway)
    plan4 = RelationFactory(person=p1, is_surprise=True)
    RelationPermission.objects.create(
        user=bob, relation=plan4, permission_type=PermissionLevel.OWNER
    )

    # 1 surprise plan for p1 owned by Alice (never hidden from Alice)
    plan5 = RelationFactory(person=p1, is_surprise=True)
    RelationPermission.objects.create(
        user=alice, relation=plan5, permission_type=PermissionLevel.OWNER
    )

    assert account_links.revealed_surprise_count(p1) == 2
    assert account_links.revealed_surprise_count(p2) == 1

    # Unlinked person returns 0
    unlinked = PersonFactory(owner=bob)
    assert account_links.revealed_surprise_count(unlinked) == 0


def test_revealed_surprise_count_group_surprises():
    """revealed_surprise_count properly accounts for group surprise plans."""
    bob = UserFactory()
    alice = UserFactory()

    parent_group = PersonGroupFactory()
    PermissionService.create_or_update_permission(
        bob, parent_group, permission_level=PermissionLevel.OWNER
    )
    child_group = PersonGroupFactory()
    child_group.parent_groups.add(parent_group)
    PermissionService.create_or_update_permission(
        bob, child_group, permission_level=PermissionLevel.OWNER
    )

    p1 = PersonFactory(owner=bob, account=alice)
    p1.groups.add(child_group)

    # Surprise plan on parent group shared with Alice
    plan = GroupRelationFactory(group=parent_group, is_surprise=True)
    RelationPermission.objects.create(
        user=bob, relation=plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=alice, relation=plan, permission_type=PermissionLevel.VIEWER
    )

    assert account_links.revealed_surprise_count(p1) == 1

    # If another linked person p2 is also in child_group, unlinking p1 leaves the plan hidden
    p2 = PersonFactory(owner=bob, account=alice)
    p2.groups.add(child_group)
    assert account_links.revealed_surprise_count(p1) == 0


def test_unlink_needs_editor():
    """Unlinking requires at least EDITOR permission; unlinked record is a no-op."""
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()
    bob.profile.friends.add(alice.profile)

    person = PersonFactory(owner=bob, account=alice)
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.VIEWER
    )

    # Viewer gets PermissionDenied
    with pytest.raises(PermissionDenied):
        account_links.unlink(person, carol)

    # Editor succeeds
    PermissionService.create_or_update_permission(
        carol, person, permission_level=PermissionLevel.EDITOR
    )
    account_links.unlink(person, carol)
    person.refresh_from_db()
    assert person.account is None

    # Unlinking an already unlinked person is a no-op
    account_links.unlink(person, carol)
    person.refresh_from_db()
    assert person.account is None


def test_refresh_from_db_on_stale_instance():
    """Link and unlink refresh stale in-memory person instances from the database."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p_in_memory = PersonFactory(owner=bob)
    # Another transaction links person to alice
    Person.objects.filter(pk=p_in_memory.pk).update(account=alice)

    # Calling link with stale p_in_memory (where .account is None) recognizes it is already alice
    res = account_links.link(p_in_memory, alice, bob)
    assert res.account == alice

    # Calling unlink with stale instance that has account=alice in DB
    p_stale = Person.objects.get(pk=p_in_memory.pk)
    Person.objects.filter(pk=p_in_memory.pk).update(account=None)
    account_links.unlink(p_stale, bob)
    p_stale.refresh_from_db()
    assert p_stale.account is None


def test_owned_persons():
    """owned_persons returns query of persons where user has OWNER permission."""
    bob = UserFactory()
    carol = UserFactory()
    p1 = PersonFactory(owner=bob)
    p2 = PersonFactory(owner=bob)
    p3 = PersonFactory(owner=carol)
    PermissionService.create_or_update_permission(bob, p3, permission_level=PermissionLevel.EDITOR)

    owned = account_links.owned_persons(bob)
    assert set(owned) == {p1, p2}


def test_unfriending_removes_links_without_friend_owner():
    """Unfriending removes links where no remaining owner is friends with the account."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p = PersonFactory(owner=bob, account=alice)

    # Unfriend bob and alice
    bob.profile.friends.remove(alice.profile)
    alice.profile.friends.remove(bob.profile)

    removed = account_links.remove_links_after_unfriending(bob, alice)
    assert removed == 1
    p.refresh_from_db()
    assert p.account is None


def test_unfriending_in_both_directions():
    """Unfriending initiated by the linked account removes links on the former friend's records."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p = PersonFactory(owner=bob, account=alice)

    # Alice initiates unfriending
    alice.profile.friends.remove(bob.profile)
    bob.profile.friends.remove(alice.profile)

    removed = account_links.remove_links_after_unfriending(alice, bob)
    assert removed == 1
    p.refresh_from_db()
    assert p.account is None


def test_unfriending_keeps_link_when_another_owner_is_friend():
    """Unfriending preserves the link when another owner remains friends with the account."""
    bob = UserFactory()
    carol = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)
    carol.profile.friends.add(alice.profile)

    p = PersonFactory(owner=bob, account=alice)
    PermissionService.create_or_update_permission(carol, p, permission_level=PermissionLevel.OWNER)

    # Bob unfriends Alice, but Carol remains friends with Alice
    bob.profile.friends.remove(alice.profile)
    alice.profile.friends.remove(bob.profile)

    removed = account_links.remove_links_after_unfriending(bob, alice)
    assert removed == 0
    p.refresh_from_db()
    assert p.account == alice


def test_unfriending_never_removes_self_links():
    """Unfriending never removes self-links."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    # Bob has a self-link
    bob_self = PersonFactory(owner=bob, account=bob)
    # Alice has a self-link
    alice_self = PersonFactory(owner=alice, account=alice)

    bob.profile.friends.remove(alice.profile)
    alice.profile.friends.remove(bob.profile)

    removed = account_links.remove_links_after_unfriending(bob, alice)
    assert removed == 0
    bob_self.refresh_from_db()
    alice_self.refresh_from_db()
    assert bob_self.account == bob
    assert alice_self.account == alice


def test_unfriending_scope_isolation():
    """Unfriending only affects records linked between former friends."""
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()
    dan = UserFactory()

    bob.profile.friends.add(alice.profile)
    bob.profile.friends.add(carol.profile)
    dan.profile.friends.add(alice.profile)

    # Bob's record linked to Carol (third party)
    bob_carol = PersonFactory(owner=bob, account=carol)
    # Dan's record linked to Alice (Bob is not an owner)
    dan_alice = PersonFactory(owner=dan, account=alice)

    bob.profile.friends.remove(alice.profile)
    alice.profile.friends.remove(bob.profile)

    removed = account_links.remove_links_after_unfriending(bob, alice)
    assert removed == 0
    bob_carol.refresh_from_db()
    dan_alice.refresh_from_db()
    assert bob_carol.account == carol
    assert dan_alice.account == alice


def test_remove_friend_view_unlinks(client):
    """POST to remove_friend unlinks non-self-linked person records."""
    bob = UserFactory()
    alice = UserFactory()
    bob.profile.friends.add(alice.profile)

    p = PersonFactory(owner=bob, account=alice)
    client.force_login(bob)

    url = reverse("gift_manager:remove_friend", kwargs={"friend_id": alice.profile.pk})
    response = client.post(url)
    assert response.status_code == 302

    p.refresh_from_db()
    assert p.account is None
