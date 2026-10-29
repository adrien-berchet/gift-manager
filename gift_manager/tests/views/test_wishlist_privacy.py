"""Privacy boundary and side-channel invariant tests for personal wishlists.

Verifies that the wisher never discovers whether a wish is claimed, who claimed it, or
whether a surprise gift plan has been created for it. All wisher-facing representations
must render identically whether a wish is unclaimed, claimed, planned, or fulfilled.

Design notes:
- Deleting an unclaimed wish hard-deletes the row; deleting a claimed wish marks it
  ``is_archived = True`` so that the giver's plan is not broken. Both disappear from the
  wisher's active list (``get_wisher_wishes(include_archived=False)``). However, if the wisher
  specifically views their archived list, a previously deleted claimed wish remains visible
  there as archived. A future improvement can introduce a separate soft-delete field.
- The contract tests for ``/profile/wishlist/`` (``test_wisher_views_render_identically_whether_claimed_or_not``
  and ``test_wisher_cannot_see_claim_status_via_api_or_html``) are marked with
  ``@pytest.mark.xfail(strict=True, raises=NoReverseMatch)`` because the wisher UI views are
  scheduled for Task 4. Once Task 4 registers ``gift_manager:wishlist_list``, the strict xfail
  will fail (XPASS), prompting the Task 4 implementer to remove the marker.
"""

import re
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import NoReverseMatch
from django.urls import reverse

from gift_manager import wishlist
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import Wish
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def _befriend(first, second):
    first.profile.friends.add(second.profile)


def _grant(user, obj, level=PermissionLevel.OWNER, attr=None):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


def _normalize_html(content: bytes | str) -> str:
    """Normalize dynamic values such as CSRF tokens for exact HTML comparison."""
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    # Replace CSRF token value
    return re.sub(
        r'name=["\']csrfmiddlewaretoken["\'] value=["\'][^"\']+["\']',
        'name="csrfmiddlewaretoken" value="NORMALIZED"',
        text,
    )


@pytest.fixture
def alice():
    """The wisher."""
    return UserFactory(username="alice")


@pytest.fixture
def bob(alice):
    """A friend of Alice who claims and plans gifts for her."""
    friend = UserFactory(username="bob")
    _befriend(alice, friend)
    return friend


@pytest.fixture
def carol(alice):
    """A friend of Alice who is not friends with Bob."""
    friend = UserFactory(username="carol")
    _befriend(alice, friend)
    return friend


@pytest.fixture
def stranger():
    """A user who is not friends with Alice."""
    return UserFactory(username="stranger")


@pytest.fixture
def wisher_person(alice, bob):
    """Alice's account represented as a Person in Bob's address book."""
    person = PersonFactory(account=alice)
    _grant(bob, person, PermissionLevel.OWNER)
    return person


@pytest.fixture
def wish(alice):
    """A sample wish owned by Alice."""
    return WishFactory(
        wisher=alice,
        title="Super Mario Odyssey Deluxe",
        url="https://example.com/games/mario",
        price_hint=Decimal("59.99"),
        notes="Physical game cartridge please",
    )


# --- 1. Service and Model Privacy Invariants --------------------------------------------------


def test_plan_wish_forces_surprise_flag_on_relation(wish, bob, wisher_person):
    """A gift plan created from a wish must always have is_surprise = True."""
    # Test planning without an event
    relation = wishlist.plan_wish(wish, bob, wisher_person, event=None)
    assert relation.is_surprise is True

    # Test planning with an event
    event = EventFactory()
    _grant(bob, event, PermissionLevel.OWNER)
    another_wish = WishFactory(wisher=wish.wisher)
    relation_with_event = wishlist.plan_wish(another_wish, bob, wisher_person, event=event)
    assert relation_with_event.is_surprise is True

    # Verify sync_wish_on_plan_change preserves the surprise flag
    wishlist.sync_wish_on_plan_change(relation)
    relation.refresh_from_db()
    assert relation.is_surprise is True


def test_created_gift_from_wish_is_not_shared_with_wisher(wish, bob, wisher_person, alice):
    """The Gift and Relation created by plan_wish must never be accessible to the wisher."""
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    gift = relation.gift

    # Bob is the owner
    assert PermissionService.get_effective_permission(gift, bob) == PermissionLevel.OWNER
    assert PermissionService.get_effective_permission(relation, bob) == PermissionLevel.OWNER

    # Alice has NO permissions on the created gift or relation
    assert PermissionService.get_effective_permission(gift, alice) == PermissionLevel.NONE
    assert PermissionService.get_effective_permission(relation, alice) == PermissionLevel.NONE

    # Excluded from Alice's querysets
    assert not Gift.objects.accessible_by(alice).filter(pk=gift.pk).exists()
    assert not Relation.objects.accessible_by(alice).filter(pk=relation.pk).exists()

    # Even if Bob shares the recipient Person with Alice, the surprise plan remains hidden
    _grant(alice, wisher_person, PermissionLevel.VIEWER)
    assert not Relation.objects.accessible_by(alice).filter(pk=relation.pk).exists()


@pytest.mark.parametrize("state", ["unclaimed", "claimed", "planned"])
def test_wisher_cannot_claim_release_or_plan_own_wish(wish, bob, wisher_person, alice, state):
    """The wisher is rejected before inspecting claim state, guaranteeing identical errors."""
    if state == "claimed":
        wishlist.claim_wish(wish, bob)
    elif state == "planned":
        wishlist.plan_wish(wish, bob, wisher_person)

    with pytest.raises(PermissionDenied, match="You cannot claim your own wish"):
        wishlist.claim_wish(wish, alice)

    with pytest.raises(PermissionDenied, match="You cannot release claims on your own wish"):
        wishlist.release_wish_claim(wish, alice)

    # Creating a plan where wisher tries to plan their own wish
    alice_own_person = PersonFactory(account=alice)
    _grant(alice, alice_own_person, PermissionLevel.OWNER)
    with pytest.raises(PermissionDenied, match="You cannot claim your own wish"):
        wishlist.plan_wish(wish, alice, alice_own_person)


def test_wisher_updated_at_not_bumped_by_claim_or_plan(wish, bob, wisher_person):
    """Giver actions (claiming, planning) must not alter wisher_updated_at."""
    initial_updated_at = wish.wisher_updated_at

    wishlist.claim_wish(wish, bob)
    wish.refresh_from_db()
    assert wish.wisher_updated_at == initial_updated_at

    wishlist.plan_wish(wish, bob, wisher_person)
    wish.refresh_from_db()
    assert wish.wisher_updated_at == initial_updated_at


@pytest.mark.parametrize("state", ["unclaimed", "claimed", "planned", "fulfilled"])
def test_format_claimer_label_empty_for_wisher(wish, bob, wisher_person, alice, state):
    """format_claimer_label returns empty string for the wisher in every possible state."""
    if state == "claimed":
        wishlist.claim_wish(wish, bob)
    elif state == "planned":
        wishlist.plan_wish(wish, bob, wisher_person)
    elif state == "fulfilled":
        rel = wishlist.plan_wish(wish, bob, wisher_person)
        rel.status = RelationStatusFactory(status="Given")
        rel.save()
        wishlist.sync_wish_on_plan_change(rel)
        wish.refresh_from_db()
        assert wish.is_fulfilled is True

    # Regular wisher
    assert wishlist.format_claimer_label(wish, alice) == ""
    assert wishlist.format_claimer_label(wish, alice, viewer_friend_ids={bob.pk}) == ""

    # Even if wisher is a superuser
    alice.is_superuser = True
    assert wishlist.format_claimer_label(wish, alice) == ""


def test_archiving_claimed_wish_preserves_claim_for_giver(wish, bob, carol, alice):
    """When Alice archives a claimed wish, Bob's claim is preserved; other friends do not see it."""
    wish = wishlist.claim_wish(wish, bob)
    claimed_at = wish.claimed_at

    # Alice archives her wish
    wish.is_archived = True
    wish.save(update_fields=["is_archived"])

    # Bob (the claimer) still sees the wish in friend-visible query
    bob_visible = list(wishlist.get_friend_visible_wishes(alice, bob))
    assert wish in bob_visible

    # Carol (a friend who is not the claimer) does NOT see the archived wish
    carol_visible = list(wishlist.get_friend_visible_wishes(alice, carol))
    assert wish not in carol_visible

    # Alice unarchives her wish
    wish.is_archived = False
    wish.save(update_fields=["is_archived"])

    # Claim and claimed_at are unchanged
    wish.refresh_from_db()
    assert wish.claimed_by == bob
    assert wish.claimed_at == claimed_at


def test_delete_claimed_wish_preserves_claim_and_plan(wish, bob, wisher_person, alice):
    """Deleting a claimed/planned wish archives it in DB so the giver's plan is not broken.

    Note on wisher visibility: The wish is removed from Alice's active wishes
    (get_wisher_wishes(include_archived=False)). If Alice checks her archived list,
    the wish will appear there because it was preserved rather than hard deleted.
    """
    plan = wishlist.plan_wish(wish, bob, wisher_person)

    # Alice deletes her claimed wish
    wishlist.delete_wish(wish, alice)

    # In DB, wish row is preserved with is_archived = True
    wish.refresh_from_db()
    assert wish.is_archived is True
    assert wish.claimed_by == bob

    # The fulfilling relation plan is NOT deleted or orphaned
    plan.refresh_from_db()
    assert plan.wish == wish
    assert Relation.objects.filter(pk=plan.pk).exists()

    # Active wisher list excludes it
    active_wishes = list(wishlist.get_wisher_wishes(alice, include_archived=False))
    assert wish not in active_wishes

    # Contrast with deleting an unclaimed wish, which is completely deleted
    unclaimed_wish = WishFactory(wisher=alice)
    wishlist.delete_wish(unclaimed_wish, alice)
    assert not Wish.objects.filter(pk=unclaimed_wish.pk).exists()


def test_unfriending_wisher_state_unchanged(wish, bob, wisher_person, alice):
    """Unfriending cleanly resets claim and plan links, leaving wisher state clean."""
    wishlist.plan_wish(wish, bob, wisher_person)

    wishlist.release_claims_after_unfriending(alice, bob)

    wish.refresh_from_db()
    assert wish.claimed_by is None
    assert wish.claimed_at is None

    # Alice's view of her wishes is equivalent to an unclaimed wish
    assert list(wishlist.get_wisher_wishes(alice)) == [wish]


# --- 2. Existing View Surfaces Invariant Tests ------------------------------------------------


@pytest.mark.parametrize("state", ["claimed", "planned"])
@pytest.mark.parametrize(
    "view_name",
    ["profile_detail", "gifts", "relations", "persons"],
)
def test_wisher_existing_surfaces_identical_across_states(
    client, alice, bob, wisher_person, wish, state, view_name
):
    """Existing surfaces viewed by Alice render identically regardless of claim/plan state."""
    client.force_login(alice)
    url = reverse(f"gift_manager:{view_name}")

    # Baseline response when wish is unclaimed
    res_unclaimed = client.get(url)
    assert res_unclaimed.status_code == 200
    norm_unclaimed = _normalize_html(res_unclaimed.content)

    # Transition wish to claimed or planned state
    if state == "claimed":
        wishlist.claim_wish(wish, bob)
    elif state == "planned":
        wishlist.plan_wish(wish, bob, wisher_person)

    # Re-fetch page as Alice
    res_tested = client.get(url)
    assert res_tested.status_code == 200
    norm_tested = _normalize_html(res_tested.content)

    # Content must be character-for-character identical across states
    assert norm_tested == norm_unclaimed

    # Claim indicators and secret plan details must not leak
    assert "Claimed" not in norm_tested
    assert "claimed" not in norm_tested
    assert "Reserved" not in norm_tested
    assert "reserved" not in norm_tested


def test_wisher_search_never_exposes_surprise_plan_or_gift(client, alice, bob, wisher_person, wish):
    """Alice searching for the secret gift title returns 0 results, while Bob sees it."""
    relation = wishlist.plan_wish(wish, bob, wisher_person)
    search_url = reverse("gift_manager:global_search")

    # Alice searches for the wish/gift title
    client.force_login(alice)
    res_alice = client.get(search_url, {"q": wish.title})
    assert res_alice.status_code == 200
    alice_data = res_alice.json()
    assert alice_data.get("results") == []

    # Bob searches for the same title and sees his gift plan
    client.force_login(bob)
    res_bob = client.get(search_url, {"q": wish.title})
    assert res_bob.status_code == 200
    bob_data = res_bob.json()
    bob_results = bob_data.get("results", [])
    assert any(relation.gift.name in r.get("title", "") for r in bob_results)


# --- 3. Wisher Wishlist View Contract Tests (Strict XFail for Task 4) -------------------------


@pytest.mark.xfail(
    strict=True,
    raises=NoReverseMatch,
    reason="Task 4 adds /profile/wishlist/ (reverse: gift_manager:wishlist_list)",
)
def test_wisher_views_render_identically_whether_claimed_or_not(client, alice, bob, wisher_person):
    """Alice's wishlist page HTML and context are identical when unclaimed, claimed, or planned."""
    url = reverse("gift_manager:wishlist_list")
    client.force_login(alice)

    # 1. Unclaimed wish
    wish = WishFactory(wisher=alice, title="Unique Nintendo Switch Game")
    res_unclaimed = client.get(url)
    assert res_unclaimed.status_code == 200
    norm_unclaimed = _normalize_html(res_unclaimed.content)

    # 2. Claimed wish
    wishlist.claim_wish(wish, bob)
    res_claimed = client.get(url)
    assert res_claimed.status_code == 200
    norm_claimed = _normalize_html(res_claimed.content)
    assert norm_claimed == norm_unclaimed

    # 3. Planned wish
    wishlist.plan_wish(wish, bob, wisher_person)
    res_planned = client.get(url)
    assert res_planned.status_code == 200
    norm_planned = _normalize_html(res_planned.content)
    assert norm_planned == norm_unclaimed

    # 4. Fulfilled wish
    rel = Relation.objects.filter(wish=wish).first()
    rel.status = RelationStatusFactory(status="Given")
    rel.save()
    wishlist.sync_wish_on_plan_change(rel)
    res_fulfilled = client.get(url)
    assert res_fulfilled.status_code == 200
    norm_fulfilled = _normalize_html(res_fulfilled.content)
    assert norm_fulfilled == norm_unclaimed


@pytest.mark.xfail(
    strict=True,
    raises=NoReverseMatch,
    reason="Task 4 adds /profile/wishlist/ (reverse: gift_manager:wishlist_list)",
)
def test_wisher_cannot_see_claim_status_via_api_or_html(client, alice, bob, wisher_person):
    """Wisher payload and context never expose claimer name, claim status, or fulfilling plan."""
    url = reverse("gift_manager:wishlist_list")
    wish = WishFactory(wisher=alice, title="Secret Robot Toy")
    wishlist.plan_wish(wish, bob, wisher_person)

    client.force_login(alice)
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Sensitive claim/plan information must not appear in HTML
    assert bob.username not in content
    assert "Claimed" not in content
    assert "claimed" not in content
    assert "Reserved" not in content
    assert "reserved" not in content

    # Template context must not expose sensitive keys
    if hasattr(response, "context") and response.context is not None:
        for ctx in response.context:
            for forbidden_key in ("claimed_by", "claimed_at", "fulfilling_plans"):
                assert forbidden_key not in ctx
