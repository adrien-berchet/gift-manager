"""Tests for group gifts service layer (gift_manager.group_gifts)."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st

from gift_manager import plan_coordination
from gift_manager.group_gifts import _clean_amount
from gift_manager.group_gifts import _is_buyer
from gift_manager.group_gifts import _require_group_gift_access
from gift_manager.group_gifts import _resolve_currency
from gift_manager.group_gifts import add_contributor
from gift_manager.group_gifts import calculate_equal_shares
from gift_manager.group_gifts import disable_group_gift
from gift_manager.group_gifts import enable_group_gift
from gift_manager.group_gifts import get_group_gift_summary
from gift_manager.group_gifts import is_recipient_of_plan
from gift_manager.group_gifts import remove_contributor
from gift_manager.group_gifts import set_split_mode
from gift_manager.group_gifts import toggle_contribution_paid
from gift_manager.group_gifts import update_contribution_amount
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationContributionFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Row locks need PostgreSQL"
)


def _share(relation, user, level):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


# --- 1. Mathematics & Penny Rounding (DB-free) --------------------------------


@pytest.mark.django_db(transaction=False)
class TestCalculateEqualShares:
    def test_calculate_equal_shares_divmod_penny_distribution(self):
        # 100.00 split 3 ways -> 33.34, 33.33, 33.33
        shares = calculate_equal_shares(Decimal("100.00"), 3)
        assert shares == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
        assert sum(shares) == Decimal("100.00")

        # 0.07 split 4 ways -> 0.02, 0.02, 0.02, 0.01
        shares = calculate_equal_shares(Decimal("0.07"), 4)
        assert shares == [Decimal("0.02"), Decimal("0.02"), Decimal("0.02"), Decimal("0.01")]
        assert sum(shares) == Decimal("0.07")

        # 0.01 split 3 ways -> 0.01, 0.00, 0.00
        shares = calculate_equal_shares(Decimal("0.01"), 3)
        assert shares == [Decimal("0.01"), Decimal("0.00"), Decimal("0.00")]
        assert sum(shares) == Decimal("0.01")

        # 10.03 split 5 ways -> 2.01, 2.01, 2.01, 2.00, 2.00
        shares = calculate_equal_shares(Decimal("10.03"), 5)
        assert shares == [
            Decimal("2.01"),
            Decimal("2.01"),
            Decimal("2.01"),
            Decimal("2.00"),
            Decimal("2.00"),
        ]
        assert sum(shares) == Decimal("10.03")

    def test_calculate_equal_shares_edge_cases(self):
        assert calculate_equal_shares(Decimal("50.00"), 0) == []
        assert calculate_equal_shares(Decimal("50.00"), -2) == []
        assert calculate_equal_shares(None, 3) == [
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
        ]
        assert calculate_equal_shares(Decimal("0.00"), 2) == [Decimal("0.00"), Decimal("0.00")]
        assert calculate_equal_shares(Decimal("-10.00"), 2) == [Decimal("0.00"), Decimal("0.00")]

    @settings(deadline=None, max_examples=50)
    @given(
        total_price=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        count=st.integers(min_value=1, max_value=200),
    )
    def test_calculate_equal_shares_hypothesis_property(self, total_price, count):
        shares = calculate_equal_shares(total_price, count)

        assert len(shares) == count
        assert sum(shares) == total_price
        assert max(shares) - min(shares) <= Decimal("0.01")
        assert shares == sorted(shares, reverse=True)
        assert all(share >= Decimal("0.00") for share in shares)
        assert all(share.as_tuple().exponent == -2 for share in shares)


# --- 2. Helper Functions & Access Guards --------------------------------------


class TestGroupGiftHelpersAndGuards:
    def test_is_buyer_handles_none_match(self):
        relation = RelationFactory()
        assert relation.claimed_by is None

        # External contributor on unclaimed plan has user=None. None == None must NOT make them buyer!
        ext_contrib = RelationContributionFactory(relation=relation, user=None, name="Aunt Jane")
        assert _is_buyer(relation, ext_contrib) is False

        # Claim the plan
        buyer = UserFactory()
        relation.claimed_by = buyer
        relation.claimed_at = timezone.now()
        relation.save()

        # External contributor on claimed plan is not buyer
        assert _is_buyer(relation, ext_contrib) is False

        # Contributor with buyer account is buyer
        buyer_contrib = RelationContributionFactory(relation=relation, user=buyer)
        assert _is_buyer(relation, buyer_contrib) is True

        # Another collaborator is not buyer
        other_user = UserFactory()
        other_contrib = RelationContributionFactory(relation=relation, user=other_user)
        assert _is_buyer(relation, other_contrib) is False

    def test_clean_amount(self):
        assert _clean_amount("42.50") == Decimal("42.50")
        assert _clean_amount(Decimal(10)) == Decimal("10.00")
        assert _clean_amount(0) == Decimal("0.00")

        with pytest.raises(ValidationError):
            _clean_amount("-0.01")
        with pytest.raises(ValidationError):
            _clean_amount("NaN")
        with pytest.raises(ValidationError):
            _clean_amount("Infinity")
        with pytest.raises(ValidationError):
            _clean_amount("100000000.00")  # max 8 integer digits (10^8)

    def test_is_recipient_of_plan_person_recipient(self):
        account = UserFactory()
        person = PersonFactory(account=account)
        relation = RelationFactory(person=person)

        # Recipient account is recipient
        assert is_recipient_of_plan(relation, account) is True

        # Even if recipient is an OWNER or superuser on the plan, they remain the recipient!
        _share(relation, account, PermissionLevel.OWNER)
        assert is_recipient_of_plan(relation, account) is True

        account.is_superuser = True
        account.save()
        assert is_recipient_of_plan(relation, account) is True

        # Other user is not recipient
        other = UserFactory()
        assert is_recipient_of_plan(relation, other) is False

    def test_is_recipient_of_plan_group_recipient(self):
        group = PersonGroupFactory()
        member_user = UserFactory()
        group_person = PersonFactory(account=member_user)
        group_person.groups.add(group)

        relation = GroupRelationFactory(group=group)

        # Member with VIEWER permission is recipient (blocked)
        _share(relation, member_user, PermissionLevel.VIEWER)
        assert is_recipient_of_plan(relation, member_user) is True

        # Member with EDITOR permission is recipient (blocked)
        _share(relation, member_user, PermissionLevel.EDITOR)
        assert is_recipient_of_plan(relation, member_user) is True

        # Member who is OWNER of the plan is NOT blocked (owner exemption)
        _share(relation, member_user, PermissionLevel.OWNER)
        assert is_recipient_of_plan(relation, member_user) is False

        # Non-member user is not recipient
        non_member = UserFactory()
        assert is_recipient_of_plan(relation, non_member) is False

    def test_require_group_gift_access_enforces_permissions_and_recipient(self):
        owner = UserFactory()
        recipient_user = UserFactory()
        person = PersonFactory(account=recipient_user)
        relation = RelationFactory(person=person)
        _share(relation, owner, PermissionLevel.OWNER)

        # Owner has access
        assert (
            _require_group_gift_access(relation, owner, PermissionLevel.VIEWER)
            == PermissionLevel.OWNER
        )

        # Stranger gets PermissionDenied
        stranger = UserFactory()
        with pytest.raises(PermissionDenied):
            _require_group_gift_access(relation, stranger, PermissionLevel.VIEWER)

        # Recipient gets PermissionDenied even with share
        _share(relation, recipient_user, PermissionLevel.VIEWER)
        with pytest.raises(PermissionDenied):
            _require_group_gift_access(relation, recipient_user, PermissionLevel.VIEWER)

    def test_require_group_gift_access_blocks_hidden_surprises(self):
        owner = UserFactory()
        wisher = UserFactory()
        person = PersonFactory(account=wisher)
        relation = RelationFactory(person=person, is_surprise=True)
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, wisher, PermissionLevel.EDITOR)

        # Surprise plan is hidden for the recipient wisher
        with pytest.raises(PermissionDenied):
            _require_group_gift_access(relation, wisher, PermissionLevel.VIEWER)

    def test_resolve_currency_uses_owner_currency(self):
        owner = UserFactory()
        owner.profile.currency = "USD"
        owner.profile.save()

        viewer = UserFactory()
        viewer.profile.currency = "GBP"
        viewer.profile.save()

        relation = RelationFactory()
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, viewer, PermissionLevel.VIEWER)

        assert _resolve_currency(relation, viewer) == "USD"


# --- 3. Group Gift Summary ----------------------------------------------------


class TestGroupGiftSummary:
    def test_get_group_gift_summary_equal_mode(self):
        owner = UserFactory()
        buyer = UserFactory()
        collab = UserFactory()
        relation = RelationFactory(
            price=Decimal("90.00"),
            claimed_by=buyer,
            claimed_at=timezone.now(),
            is_group_gift=True,
        )
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.EDITOR)
        _share(relation, collab, PermissionLevel.VIEWER)

        # Add contributions for buyer, collab, and an external friend
        c_buyer = RelationContributionFactory(relation=relation, user=buyer)
        c_collab = RelationContributionFactory(relation=relation, user=collab)
        c_ext = RelationContributionFactory(relation=relation, user=None, name="Dave")

        summary = get_group_gift_summary(relation, owner)

        assert summary.is_group_gift is True
        assert summary.split_mode == SplitMode.EQUAL
        assert summary.total_price == Decimal("90.00")
        assert summary.buyer == buyer
        assert summary.contributor_count == 3
        assert len(summary.rows) == 3

        # Dynamic shares: 90 / 3 = 30.00 each
        assert summary.rows[0].contribution == c_buyer
        assert summary.rows[0].share_amount == Decimal("30.00")
        assert summary.rows[0].is_buyer is True
        assert summary.rows[0].is_paid is True
        assert summary.rows[0].can_toggle_paid is False
        assert summary.rows[0].can_remove is False

        assert summary.rows[1].contribution == c_collab
        assert summary.rows[1].share_amount == Decimal("30.00")
        assert summary.rows[1].is_buyer is False
        assert summary.rows[1].is_paid is False
        assert summary.rows[1].can_toggle_paid is True
        assert summary.rows[1].can_remove is True

        assert summary.rows[2].contribution == c_ext
        assert summary.rows[2].share_amount == Decimal("30.00")
        assert summary.rows[2].is_buyer is False
        assert summary.rows[2].is_paid is False
        assert summary.rows[2].can_toggle_paid is True
        assert summary.rows[2].can_remove is True

        # Financial tallies
        assert summary.total_allocated == Decimal("90.00")
        assert summary.total_collected == Decimal("30.00")  # buyer is collected by definition
        assert summary.total_remaining == Decimal("60.00")
        assert summary.owed_to_buyer == Decimal("60.00")
        assert summary.is_fully_paid is False
        assert summary.is_overfunded is False
        assert summary.total_unallocated == Decimal("0.00")

    def test_get_group_gift_summary_custom_mode(self):
        owner = UserFactory()
        relation = RelationFactory(
            price=Decimal("100.00"),
            claimed_by=None,
            is_group_gift=True,
            split_mode=SplitMode.CUSTOM,
        )
        _share(relation, owner, PermissionLevel.OWNER)

        RelationContributionFactory(relation=relation, user=owner, amount=Decimal("60.00"))
        RelationContributionFactory(
            relation=relation, user=None, name="Dave", amount=Decimal("20.00")
        )

        summary = get_group_gift_summary(relation, owner)

        assert summary.split_mode == SplitMode.CUSTOM
        assert summary.total_allocated == Decimal("80.00")
        assert summary.total_unallocated == Decimal("20.00")
        assert summary.total_remaining == Decimal("100.00")
        assert summary.owed_to_buyer == Decimal("0.00")  # no buyer claimed


# --- 4. Service Operations & Mutations ----------------------------------------


class TestGroupGiftOperations:
    def test_enable_group_gift_adds_buyer_get_or_create(self):
        owner = UserFactory()
        buyer = UserFactory()
        relation = RelationFactory(claimed_by=buyer, claimed_at=timezone.now())
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.EDITOR)

        assert relation.is_group_gift is False
        assert relation.contributions.count() == 0

        # Enable group gift
        updated = enable_group_gift(relation, owner, split_mode=SplitMode.EQUAL)
        assert updated.is_group_gift is True
        assert updated.split_mode == SplitMode.EQUAL

        # Buyer is automatically added as a contributor
        assert updated.contributions.count() == 1
        buyer_contrib = updated.contributions.first()
        assert buyer_contrib.user == buyer
        assert buyer_contrib.name == buyer.username

        # Re-enabling is idempotent and does not duplicate
        updated = enable_group_gift(relation, owner)
        assert updated.contributions.count() == 1

    def test_disable_group_gift_preserves_rows_and_refuses_when_paid(self):
        owner = UserFactory()
        relation = RelationFactory(is_group_gift=True)
        _share(relation, owner, PermissionLevel.OWNER)

        RelationContributionFactory(relation=relation, user=None, name="Friend 1")
        c2 = RelationContributionFactory(relation=relation, user=None, name="Friend 2")

        # Mark c2 as paid
        c2.is_paid = True
        c2.paid_at = timezone.now()
        c2.amount = Decimal("25.00")
        c2.save()

        # Cannot disable with paid contributions
        with pytest.raises(ValidationError) as exc:
            disable_group_gift(relation, owner)
        assert "recorded payments" in str(exc.value)

        # Unmark c2
        c2.is_paid = False
        c2.paid_at = None
        c2.save()

        # Now disabling succeeds and preserves rows
        updated = disable_group_gift(relation, owner)
        assert updated.is_group_gift is False
        assert updated.contributions.count() == 2

    def test_set_split_mode_freezes_and_resets(self):
        owner = UserFactory()
        relation = RelationFactory(
            price=Decimal("100.00"), is_group_gift=True, split_mode=SplitMode.EQUAL
        )
        _share(relation, owner, PermissionLevel.OWNER)

        c1 = RelationContributionFactory(relation=relation, user=None, name="A")
        c2 = RelationContributionFactory(relation=relation, user=None, name="B")

        # Switching to CUSTOM freezes current equal shares (50.00 each)
        set_split_mode(relation, owner, SplitMode.CUSTOM)
        relation.refresh_from_db()
        c1.refresh_from_db()
        c2.refresh_from_db()

        assert relation.split_mode == SplitMode.CUSTOM
        assert c1.amount == Decimal("50.00")
        assert c2.amount == Decimal("50.00")

        # Mark c1 as paid at 50.00
        c1.is_paid = True
        c1.paid_at = timezone.now()
        c1.save()

        # Change c2 custom amount to 70.00
        c2.amount = Decimal("70.00")
        c2.save()

        # Switch back to EQUAL: unpaid c2 resets to 0.00, paid c1 remains 50.00
        set_split_mode(relation, owner, SplitMode.EQUAL)
        relation.refresh_from_db()
        c1.refresh_from_db()
        c2.refresh_from_db()

        assert relation.split_mode == SplitMode.EQUAL
        assert c1.amount == Decimal("50.00")
        assert c2.amount == Decimal("0.00")

    def test_add_contributor_validations(self):
        owner = UserFactory()
        collab = UserFactory()
        recipient_user = UserFactory()
        person = PersonFactory(account=recipient_user)
        relation = RelationFactory(person=person, is_group_gift=True)
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, collab, PermissionLevel.VIEWER)

        # Rejects whitespace or empty name
        with pytest.raises(ValidationError):
            add_contributor(relation, owner, name="   ")
        with pytest.raises(ValidationError):
            add_contributor(relation, owner, name="")

        # Rejects recipient user
        with pytest.raises(ValidationError) as exc:
            add_contributor(relation, owner, user=recipient_user)
        assert "recipient" in str(exc.value).lower()

        # Rejects user without permission
        stranger = UserFactory()
        with pytest.raises(ValidationError):
            add_contributor(relation, owner, user=stranger)

        # Rejects duplicate user with ValidationError
        c = add_contributor(relation, owner, user=collab)
        assert c.user == collab
        assert c.name == collab.username

        with pytest.raises(ValidationError) as exc:
            add_contributor(relation, owner, user=collab)
        assert "already" in str(exc.value).lower()

        # Adds external contributor
        ext = add_contributor(relation, owner, name="Uncle Bob")
        assert ext.user is None
        assert ext.name == "Uncle Bob"

    def test_remove_contributor_refuses_buyer_or_paid(self):
        owner = UserFactory()
        buyer = UserFactory()
        relation = RelationFactory(claimed_by=buyer, claimed_at=timezone.now(), is_group_gift=True)
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.EDITOR)

        buyer_contrib = RelationContributionFactory(relation=relation, user=buyer)
        friend = RelationContributionFactory(relation=relation, user=None, name="Friend")

        # Rejects removing claimed buyer
        with pytest.raises(ValidationError) as exc:
            remove_contributor(buyer_contrib, owner)
        assert "buyer" in str(exc.value).lower()

        # Rejects removing paid contributor
        friend.is_paid = True
        friend.paid_at = timezone.now()
        friend.amount = Decimal("30.00")
        friend.save()

        with pytest.raises(ValidationError) as exc:
            remove_contributor(friend, owner)
        assert "payment" in str(exc.value).lower()

        # Successfully removes unpaid contributor
        friend.is_paid = False
        friend.paid_at = None
        friend.save()

        remove_contributor(friend, owner)
        assert RelationContribution.objects.filter(pk=friend.pk).exists() is False

    def test_toggle_contribution_paid_freezes_amount_in_equal_mode(self):
        owner = UserFactory()
        buyer = UserFactory()
        collab = UserFactory()
        relation = RelationFactory(
            price=Decimal("90.00"),
            claimed_by=buyer,
            claimed_at=timezone.now(),
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.EDITOR)
        _share(relation, collab, PermissionLevel.VIEWER)

        buyer_contrib = RelationContributionFactory(relation=relation, user=buyer)
        collab_contrib = RelationContributionFactory(relation=relation, user=collab)
        RelationContributionFactory(relation=relation, user=None, name="Dave")

        # Buyer toggle is rejected
        with pytest.raises(ValidationError) as exc:
            toggle_contribution_paid(buyer_contrib, owner)
        assert "buyer" in str(exc.value).lower()

        # Toggle collab paid: dynamic share is 30.00 -> frozen at 30.00
        updated = toggle_contribution_paid(collab_contrib, owner)
        assert updated.is_paid is True
        assert updated.paid_at is not None
        assert updated.amount == Decimal("30.00")

        # Unmark collab: amount resets to 0.00 in equal mode
        updated = toggle_contribution_paid(collab_contrib, owner)
        assert updated.is_paid is False
        assert updated.paid_at is None
        assert updated.amount == Decimal("0.00")

    def test_rebalancing_with_paid_freeze(self):
        owner = UserFactory()
        buyer = UserFactory()
        collab = UserFactory()
        relation = RelationFactory(
            price=Decimal("90.00"),
            claimed_by=buyer,
            claimed_at=timezone.now(),
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.EDITOR)
        _share(relation, collab, PermissionLevel.VIEWER)

        buyer_contrib = RelationContributionFactory(relation=relation, user=buyer)
        collab_contrib = RelationContributionFactory(relation=relation, user=collab)
        ext_contrib = RelationContributionFactory(relation=relation, user=None, name="Dave")

        # Collab pays 30.00
        toggle_contribution_paid(collab_contrib, owner)

        # Price increases from 90 to 110
        relation.price = Decimal("110.00")
        relation.save()

        # Dynamic shares for remaining unpaid (buyer + Dave = 2):
        # remaining = 110 - 30 = 80. 80 / 2 = 40.00 each
        summary = get_group_gift_summary(relation, owner)
        row_buyer = next(r for r in summary.rows if r.is_buyer)
        row_collab = next(r for r in summary.rows if r.contribution.pk == collab_contrib.pk)
        row_dave = next(r for r in summary.rows if r.contribution.pk == ext_contrib.pk)

        assert row_buyer.contribution.pk == buyer_contrib.pk

        assert row_collab.share_amount == Decimal("30.00")
        assert row_buyer.share_amount == Decimal("40.00")
        assert row_dave.share_amount == Decimal("40.00")
        assert summary.total_collected == Decimal("70.00")  # buyer 40 + collab 30

    def test_overfunded_state_when_price_drops(self):
        owner = UserFactory()
        relation = RelationFactory(
            price=Decimal("100.00"),
            claimed_by=None,
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
        _share(relation, owner, PermissionLevel.OWNER)

        c1 = RelationContributionFactory(relation=relation, user=None, name="A")
        c2 = RelationContributionFactory(relation=relation, user=None, name="B")
        c3 = RelationContributionFactory(relation=relation, user=None, name="C")

        # Mark c1 and c2 as paid (33.34 and 33.33)
        toggle_contribution_paid(c1, owner)
        toggle_contribution_paid(c2, owner)

        # Frozen sum is 66.67. Now price drops to 50.00
        relation.price = Decimal("50.00")
        relation.save()

        summary = get_group_gift_summary(relation, owner)
        assert summary.is_overfunded is True
        assert summary.total_collected == Decimal("66.67")
        assert summary.total_remaining == Decimal("0.00")

        # Unpaid c3 share is 0.00
        row_c3 = next(r for r in summary.rows if r.contribution.pk == c3.pk)
        assert row_c3.share_amount == Decimal("0.00")

        # Cannot mark zero-amount share as paid
        with pytest.raises(ValidationError) as exc:
            toggle_contribution_paid(c3, owner)
        assert "zero" in str(exc.value).lower()

    def test_update_contribution_amount(self):
        owner = UserFactory()
        relation = RelationFactory(
            price=Decimal("100.00"),
            is_group_gift=True,
            split_mode=SplitMode.CUSTOM,
        )
        _share(relation, owner, PermissionLevel.OWNER)

        contrib = RelationContributionFactory(
            relation=relation, user=None, name="A", amount=Decimal("20.00")
        )

        # Update amount
        updated = update_contribution_amount(contrib, owner, Decimal("45.00"))
        assert updated.amount == Decimal("45.00")

        # Cannot update in equal mode
        relation.split_mode = SplitMode.EQUAL
        relation.save()
        with pytest.raises(ValidationError):
            update_contribution_amount(contrib, owner, Decimal("50.00"))

        # Cannot update when paid
        relation.split_mode = SplitMode.CUSTOM
        relation.save()
        contrib.is_paid = True
        contrib.paid_at = timezone.now()
        contrib.save()

        with pytest.raises(ValidationError):
            update_contribution_amount(contrib, owner, Decimal("60.00"))

    def test_recipient_guard_owner_exemption_matrix(self):
        # 1. Person recipient: strictly blocked, even if OWNER or superuser
        recip_user = UserFactory(is_superuser=True)
        recip_person = PersonFactory(account=recip_user)
        person_plan = RelationFactory(person=recip_person)
        _share(person_plan, recip_user, PermissionLevel.OWNER)

        assert is_recipient_of_plan(person_plan, recip_user) is True
        with pytest.raises(PermissionDenied):
            _require_group_gift_access(person_plan, recip_user, PermissionLevel.VIEWER)

        # 2. Group recipient: non-owner member is blocked
        group = PersonGroupFactory()
        member_user = UserFactory()
        member_person = PersonFactory(account=member_user)
        member_person.groups.add(group)
        group_plan = GroupRelationFactory(group=group)
        _share(group_plan, member_user, PermissionLevel.EDITOR)

        assert is_recipient_of_plan(group_plan, member_user) is True
        with pytest.raises(PermissionDenied):
            _require_group_gift_access(group_plan, member_user, PermissionLevel.VIEWER)

        # 3. Group recipient: OWNER member is allowed (organizing/funding co-giver exemption)
        _share(group_plan, member_user, PermissionLevel.OWNER)
        assert is_recipient_of_plan(group_plan, member_user) is False
        assert (
            _require_group_gift_access(group_plan, member_user, PermissionLevel.VIEWER)
            == PermissionLevel.OWNER
        )

    def test_toggle_paid_unpaid_is_idempotent_no_op(self):
        owner = UserFactory()
        relation = RelationFactory(
            price=Decimal("60.00"),
            is_group_gift=True,
            split_mode=SplitMode.EQUAL,
        )
        _share(relation, owner, PermissionLevel.OWNER)

        c1 = RelationContributionFactory(relation=relation, user=None, name="Alice")
        c2 = RelationContributionFactory(relation=relation, user=None, name="Bob")

        summary_before = get_group_gift_summary(relation, owner)
        assert summary_before.rows[0].share_amount == Decimal("30.00")
        assert summary_before.rows[1].share_amount == Decimal("30.00")

        # Mark c1 as paid, then unpaid
        toggle_contribution_paid(c1, owner)
        c1.refresh_from_db()
        assert c1.is_paid is True
        assert c1.amount == Decimal("30.00")

        toggle_contribution_paid(c1, owner)
        c1.refresh_from_db()
        assert c1.is_paid is False
        assert c1.amount == Decimal("0.00")

        summary_after = get_group_gift_summary(relation, owner)
        assert summary_after.rows[0].share_amount == Decimal("30.00")
        assert summary_after.rows[1].share_amount == Decimal("30.00")
        assert summary_after.rows[1].contribution.pk == c2.pk
        assert summary_after.total_collected == Decimal("0.00")
        assert summary_after.total_remaining == Decimal("60.00")

    @postgres_only
    def test_concurrency_locking_takes_row_lock(self):
        owner = UserFactory()
        relation = RelationFactory(is_group_gift=True)
        _share(relation, owner, PermissionLevel.OWNER)

        def _locked(queries) -> bool:
            return any("FOR UPDATE" in query["sql"] for query in queries)

        with CaptureQueriesContext(connection) as queries:
            add_contributor(relation, owner, name="Concurrent Contributor")

        assert _locked(queries)

    def test_claim_integration_adds_contributor_row(self):
        owner = UserFactory()
        buyer = UserFactory()
        relation = RelationFactory(is_group_gift=True, claimed_by=None)
        _share(relation, owner, PermissionLevel.OWNER)
        _share(relation, buyer, PermissionLevel.VIEWER)

        assert relation.contributions.count() == 0

        # Buyer claims the plan
        plan_coordination.claim(relation, buyer)
        relation.refresh_from_db()

        assert relation.claimed_by == buyer
        assert relation.contributions.filter(user=buyer).exists()

        # Idempotent re-claim doesn't create duplicate
        plan_coordination.claim(relation, buyer)
        assert relation.contributions.filter(user=buyer).count() == 1
