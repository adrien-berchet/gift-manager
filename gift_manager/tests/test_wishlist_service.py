"""Service-level tests for wishes: claiming, planning, plan sync and privacy."""

import pytest
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.utils import timezone

from gift_manager import wishlist
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def _befriend(first, second):
    first.profile.friends.add(second.profile)


def _own(user, obj):
    PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


def _claim_directly(wish, user):
    Wish.objects.filter(pk=wish.pk).update(claimed_by=user, claimed_at=timezone.now())
    wish.refresh_from_db()


@pytest.fixture
def wisher():
    return UserFactory()


@pytest.fixture
def bob(wisher):
    user = UserFactory()
    _befriend(wisher, user)
    return user


@pytest.fixture
def carol(wisher):
    user = UserFactory()
    _befriend(wisher, user)
    return user


@pytest.fixture
def stranger():
    return UserFactory()


@pytest.fixture
def wish(wisher):
    return WishFactory(wisher=wisher)


@pytest.fixture
def wisher_person(wisher, bob):
    """The wisher's account as a person in Bob's address book."""
    person = PersonFactory(account=wisher)
    _own(bob, person)
    return person


# --- listing -----------------------------------------------------------------------------------


def test_get_wisher_wishes_hides_archived_by_default(wisher):
    active = WishFactory(wisher=wisher)
    WishFactory(wisher=wisher, is_archived=True)

    assert list(wishlist.get_wisher_wishes(wisher)) == [active]
    assert wishlist.get_wisher_wishes(wisher, include_archived=True).count() == 2


def test_get_friend_visible_wishes_requires_friendship(wisher, stranger, wish):
    with pytest.raises(PermissionDenied):
        wishlist.get_friend_visible_wishes(wisher, stranger)


def test_get_friend_visible_wishes_excludes_archived_unless_claimed(wisher, bob, carol):
    active = WishFactory(wisher=wisher)
    WishFactory(wisher=wisher, is_archived=True)
    kept = WishFactory(wisher=wisher, is_archived=True)
    _claim_directly(kept, bob)

    assert set(wishlist.get_friend_visible_wishes(wisher, bob)) == {active, kept}
    assert set(wishlist.get_friend_visible_wishes(wisher, carol)) == {active}


# --- claim -------------------------------------------------------------------------------------


def test_claim_wish_success(wish, bob):
    claimed = wishlist.claim_wish(wish, bob)

    assert claimed.claimed_by == bob
    assert claimed.claimed_at is not None
    wish.refresh_from_db()
    assert wish.claimed_by == bob


def test_claim_wish_is_idempotent_for_the_claimer(wish, bob):
    first = wishlist.claim_wish(wish, bob)
    second = wishlist.claim_wish(wish, bob)

    assert second.claimed_at == first.claimed_at


def test_claim_wish_rejects_wisher_self_claim(wish, wisher):
    with pytest.raises(PermissionDenied):
        wishlist.claim_wish(wish, wisher)


def test_claim_wish_rejects_non_friend(wish, stranger):
    with pytest.raises(PermissionDenied):
        wishlist.claim_wish(wish, stranger)


def test_claim_wish_rejects_already_claimed_by_another(wish, bob, carol):
    wishlist.claim_wish(wish, bob)

    with pytest.raises(ValidationError):
        wishlist.claim_wish(wish, carol)


@pytest.mark.parametrize("field", ["is_archived", "is_fulfilled"])
def test_claim_wish_rejects_closed_wish(wisher, bob, field):
    closed = WishFactory(wisher=wisher, **{field: True})

    with pytest.raises(ValidationError):
        wishlist.claim_wish(closed, bob)


def test_claim_wish_uses_fresh_database_state(wish, bob, carol):
    stale = Wish.objects.get(pk=wish.pk)
    wishlist.claim_wish(wish, bob)

    with pytest.raises(ValidationError):
        wishlist.claim_wish(stale, carol)


# --- release -----------------------------------------------------------------------------------


def test_release_wish_claim_by_claimer(wish, bob):
    wishlist.claim_wish(wish, bob)

    released = wishlist.release_wish_claim(wish, bob)

    assert released.claimed_by is None
    assert released.claimed_at is None


def test_release_wish_claim_by_superuser(wish, bob):
    wishlist.claim_wish(wish, bob)
    admin = UserFactory(is_superuser=True)

    assert wishlist.release_wish_claim(wish, admin).claimed_by is None


def test_release_wish_claim_rejects_other_friend(wish, bob, carol):
    wishlist.claim_wish(wish, bob)

    with pytest.raises(PermissionDenied):
        wishlist.release_wish_claim(wish, carol)


def test_release_wish_claim_is_idempotent_when_unclaimed(wish, bob):
    assert wishlist.release_wish_claim(wish, bob).claimed_by is None


@pytest.mark.parametrize("claimed", [False, True])
def test_release_wish_claim_denies_wisher_whatever_the_claim_state(wish, wisher, bob, claimed):
    if claimed:
        wishlist.claim_wish(wish, bob)

    with pytest.raises(PermissionDenied):
        wishlist.release_wish_claim(wish, wisher)


@pytest.mark.parametrize("claimed", [False, True])
def test_release_wish_claim_denies_non_friend_whatever_the_claim_state(
    wish, bob, stranger, claimed
):
    if claimed:
        wishlist.claim_wish(wish, bob)

    with pytest.raises(PermissionDenied):
        wishlist.release_wish_claim(wish, stranger)


def test_release_wish_claim_requires_abandoning_the_active_plan(wish, bob, wisher_person):
    wishlist.plan_wish(wish, bob, wisher_person)

    with pytest.raises(ValidationError):
        wishlist.release_wish_claim(wish, bob)

    wish.refresh_from_db()
    assert wish.claimed_by == bob


# --- plan --------------------------------------------------------------------------------------


def test_plan_wish_creates_surprise_relation_and_claims_wish(wish, bob, wisher, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)

    assert relation.wish == wish
    assert relation.person == wisher_person
    assert relation.is_surprise is True
    assert relation.gift.name == wish.title
    assert relation.gift.url == wish.url
    assert relation.gift.comment == wish.notes
    wish.refresh_from_db()
    assert wish.claimed_by == bob
    assert PermissionService.get_permission(relation, bob) == PermissionLevel.OWNER
    assert PermissionService.get_permission(relation.gift, bob) == PermissionLevel.OWNER
    assert PermissionService.get_permission(relation, wisher) == PermissionLevel.NONE
    assert PermissionService.get_permission(relation.gift, wisher) == PermissionLevel.NONE


def test_plan_wish_is_idempotent_for_the_same_friend(wish, bob, wisher_person):
    first = wishlist.plan_wish(wish, bob, wisher_person)
    second = wishlist.plan_wish(wish, bob, wisher_person)

    assert first.pk == second.pk
    assert Gift.objects.count() == 1
    assert Relation.objects.filter(wish=wish).count() == 1


def test_plan_wish_rejects_person_not_linked_to_the_wisher(wish, bob):
    other_person = PersonFactory()
    _own(bob, other_person)

    with pytest.raises(ValidationError):
        wishlist.plan_wish(wish, bob, other_person)

    assert Relation.objects.count() == 0


def test_plan_wish_requires_edit_rights_on_the_person(wish, bob, wisher):
    person = PersonFactory(account=wisher)
    PermissionService.create_or_update_permission(
        bob, person, permission_level=PermissionLevel.VIEWER
    )

    with pytest.raises(PermissionDenied):
        wishlist.plan_wish(wish, bob, person)


def test_plan_wish_rejects_non_friend_and_leaves_no_trace(wish, stranger, wisher):
    person = PersonFactory(account=wisher)
    _own(stranger, person)

    with pytest.raises(PermissionDenied):
        wishlist.plan_wish(wish, stranger, person)

    assert Gift.objects.count() == 0


def test_plan_wish_rolls_back_when_claimed_by_another(wish, bob, carol, wisher_person):
    wishlist.claim_wish(wish, carol)

    with pytest.raises(ValidationError):
        wishlist.plan_wish(wish, bob, wisher_person)

    assert Gift.objects.count() == 0
    assert Relation.objects.count() == 0


def test_plan_wish_rejects_inaccessible_event(wish, bob, wisher_person):
    from gift_manager.tests.factories import EventFactory

    event = EventFactory()

    with pytest.raises(PermissionDenied):
        wishlist.plan_wish(wish, bob, wisher_person, event=event)


# --- sync --------------------------------------------------------------------------------------


def _set_status(relation, name):
    relation.status = RelationStatusFactory(status=name)
    relation.save()


def test_abandoning_the_fulfilling_plan_releases_the_claim(wish, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)

    _set_status(relation, "Abandoned")

    wish.refresh_from_db()
    assert wish.claimed_by is None
    assert wish.claimed_at is None


def test_deleting_the_fulfilling_plan_releases_the_claim(wish, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)

    relation.delete()

    wish.refresh_from_db()
    assert wish.claimed_by is None


def test_giving_the_plan_marks_the_wish_fulfilled_and_keeps_the_claim(wish, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)

    _set_status(relation, "Given")

    wish.refresh_from_db()
    assert wish.is_fulfilled is True
    assert wish.claimed_by == bob


def test_ungiving_the_plan_clears_fulfilled(wish, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    _set_status(relation, "Given")

    _set_status(relation, "Planned")

    wish.refresh_from_db()
    assert wish.is_fulfilled is False


def test_reviving_an_abandoned_plan_reclaims_the_wish_for_its_owner(wish, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    _set_status(relation, "Abandoned")

    _set_status(relation, "Idea")

    wish.refresh_from_db()
    assert wish.claimed_by == bob


def test_reviving_does_not_steal_a_claim_taken_by_another_friend(wish, bob, carol, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    _set_status(relation, "Abandoned")
    wishlist.claim_wish(wish, carol)

    _set_status(relation, "Idea")

    wish.refresh_from_db()
    assert wish.claimed_by == carol


def test_abandoned_plan_of_another_friend_keeps_a_bare_claim(wish, bob, carol, wisher_person):
    old_plan = wishlist.plan_wish(wish, carol, _own_person(carol, wisher_person))
    _set_status(old_plan, "Abandoned")
    wishlist.claim_wish(wish, bob)

    _set_status(old_plan, "Abandoned")
    old_plan.delete()

    wish.refresh_from_db()
    assert wish.claimed_by == bob


def _own_person(user, person):
    _own(user, person)
    return person


def test_abandoning_one_of_two_active_plans_keeps_the_claim(wish, bob, wisher_person):
    first = wishlist.plan_wish(wish, bob, wisher_person)
    RelationFactory(person=wisher_person, wish=wish)

    _set_status(first, "Abandoned")

    wish.refresh_from_db()
    assert wish.claimed_by == bob


def test_sync_ignores_relations_without_a_wish():
    relation = RelationFactory()

    wishlist.sync_wish_on_plan_change(relation)


# --- unfriending -------------------------------------------------------------------------------


def test_release_claims_after_unfriending_clears_claims_both_ways(wisher, bob):
    mine = WishFactory(wisher=wisher)
    theirs = WishFactory(wisher=bob)
    _claim_directly(mine, bob)
    _claim_directly(theirs, wisher)

    wishlist.release_claims_after_unfriending(wisher, bob)

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.claimed_by is None
    assert theirs.claimed_by is None


def test_release_claims_after_unfriending_keeps_other_friends_claims(wish, bob, carol, wisher):
    _claim_directly(wish, carol)

    wishlist.release_claims_after_unfriending(wisher, bob)

    wish.refresh_from_db()
    assert wish.claimed_by == carol


def test_release_claims_after_unfriending_unlinks_plans_owned_by_the_former_friend(
    wish, bob, carol, wisher, wisher_person
):
    plan = wishlist.plan_wish(wish, bob, wisher_person)
    co_giver_plan = RelationFactory(person=wisher_person, wish=wish)
    PermissionService.create_or_update_permission(
        carol, co_giver_plan, permission_level=PermissionLevel.VIEWER, object_attr="relation"
    )

    wishlist.release_claims_after_unfriending(wisher, bob)
    wishlist.release_claims_after_unfriending(wisher, carol)

    plan.refresh_from_db()
    co_giver_plan.refresh_from_db()
    assert plan.wish is None
    assert co_giver_plan.wish == wish


# --- label -------------------------------------------------------------------------------------


@pytest.mark.parametrize("claimed", [False, True])
def test_label_is_identical_for_the_wisher_whatever_the_claim_state(wish, wisher, bob, claimed):
    if claimed:
        _claim_directly(wish, bob)

    assert wishlist.format_claimer_label(wish, wisher) == ""


def test_label_is_empty_for_non_friends(wish, stranger, bob):
    _claim_directly(wish, bob)

    assert wishlist.format_claimer_label(wish, stranger) == ""


def test_label_available(wish, bob):
    assert wishlist.format_claimer_label(wish, bob) == "Available"


def test_label_claimed_by_you(wish, bob):
    _claim_directly(wish, bob)

    assert wishlist.format_claimer_label(wish, bob) == "Claimed by you"


def test_label_masks_non_friend_username(wish, bob, carol):
    _claim_directly(wish, bob)

    assert wishlist.format_claimer_label(wish, carol) == "Claimed by a friend"
    _befriend(carol, bob)
    assert wishlist.format_claimer_label(wish, carol) == f"Claimed by @{bob.username}"


def test_label_uses_precomputed_friend_ids_without_queries(
    wish, bob, carol, django_assert_num_queries
):
    _befriend(carol, bob)
    _claim_directly(wish, bob)
    wish = Wish.objects.select_related("wisher", "claimed_by").get(pk=wish.pk)

    with django_assert_num_queries(0):
        label = wishlist.format_claimer_label(
            wish, carol, viewer_friend_ids={wish.wisher_id, bob.pk}
        )

    assert label == f"Claimed by @{bob.username}"


# --- delete ------------------------------------------------------------------------------------


def test_delete_wish_removes_an_unused_wish(wish, wisher):
    wishlist.delete_wish(wish, wisher)

    assert not Wish.objects.filter(pk=wish.pk).exists()


def test_delete_wish_archives_a_claimed_wish(wish, wisher, bob):
    wishlist.claim_wish(wish, bob)

    wishlist.delete_wish(wish, wisher)

    wish.refresh_from_db()
    assert wish.is_archived is True
    assert wish.claimed_by == bob


def test_delete_wish_archives_a_wish_with_plans(wish, wisher, bob, wisher_person):
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    _set_status(relation, "Abandoned")

    wishlist.delete_wish(wish, wisher)

    assert Wish.objects.filter(pk=wish.pk, is_archived=True).exists()


def test_delete_wish_rejects_other_users(wish, bob):
    with pytest.raises(PermissionDenied):
        wishlist.delete_wish(wish, bob)


# --- unfriend view -----------------------------------------------------------------------------


def test_remove_friend_view_releases_wish_claims_and_unlinks_plans(
    client, wish, wisher, bob, wisher_person
):
    from django.urls import reverse

    plan = wishlist.plan_wish(wish, bob, wisher_person)
    client.force_login(wisher)

    response = client.post(
        reverse("gift_manager:remove_friend", kwargs={"friend_id": bob.profile.pk})
    )

    assert response.status_code == 302
    wish.refresh_from_db()
    plan.refresh_from_db()
    assert wish.claimed_by is None
    assert plan.wish is None
