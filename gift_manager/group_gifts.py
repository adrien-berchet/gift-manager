"""Group gifts and collaborative contribution tally service layer."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationContribution
from gift_manager.models import SplitMode
from gift_manager.plan_coordination import is_recipient_of_plan
from gift_manager.plan_coordination import require_level
from gift_manager.services import PermissionService

MAX_CONTRIBUTION_AMOUNT = Decimal("100000000.00")  # max 8 integer digits (10^8)


def calculate_equal_shares(total_price: Decimal | None, contributor_count: int) -> list[Decimal]:
    """Divide total_price into contributor_count shares, spreading remainder cents by 1 cent each.

    Returns empty list if contributor_count <= 0.
    Returns list of 0.00 if total_price is None or <= 0.
    Sum of shares strictly equals round(total_price, 2).
    """
    if contributor_count <= 0:
        return []
    if total_price is None or total_price <= Decimal("0.00"):
        return [Decimal("0.00")] * contributor_count

    total_cents = int((total_price * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    base_cents, remainder_cents = divmod(total_cents, contributor_count)

    shares: list[Decimal] = []
    for i in range(contributor_count):
        cents = base_cents + (1 if i < remainder_cents else 0)
        shares.append((Decimal(cents) / 100).quantize(Decimal("0.01")))
    return shares


def _clean_amount(value: object) -> Decimal:
    """Validate and quantize a financial amount to two decimal places."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(gettext("Enter a valid amount.")) from None

    if not dec.is_finite() or dec < Decimal("0.00") or dec >= MAX_CONTRIBUTION_AMOUNT:
        raise ValidationError(
            gettext("Amount must be a non-negative finite value under 100,000,000.")
        )

    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_buyer(relation: Relation, contribution: RelationContribution) -> bool:
    """Return whether this contribution belongs to the designated buyer of the plan."""
    return relation.claimed_by_id is not None and contribution.user_id == relation.claimed_by_id


def _require_group_gift_access(
    relation: Relation, user: User, minimum_level: int = PermissionLevel.VIEWER
) -> int:
    """Validate user permission and assert user is not the recipient of the plan.

    Reuses plan_coordination.require_level to enforce hidden surprises.
    Raises PermissionDenied (HTTP 403) with generic message on failure.
    """
    level = require_level(relation, user, minimum_level)
    if is_recipient_of_plan(relation, user):
        raise PermissionDenied(gettext("You do not have permission to do this on this gift plan."))
    return level


def _resolve_currency(relation: Relation, viewer: User | None = None) -> str:
    """Resolve the display currency for the plan, using the first owner's currency."""
    owner_ids = [
        uid
        for uid, lvl in PermissionService.get_permission_map(relation).items()
        if lvl == PermissionLevel.OWNER
    ]
    owner = User.objects.filter(pk__in=owner_ids).select_related("profile").order_by("pk").first()
    if owner and getattr(owner, "profile", None) and owner.profile.currency:
        return owner.profile.currency
    if viewer and getattr(viewer, "profile", None) and viewer.profile.currency:
        return viewer.profile.currency
    return "EUR"


@dataclass(frozen=True)
class ContributorRow:
    contribution: RelationContribution
    display_name: str
    share_amount: Decimal
    is_buyer: bool
    is_paid: bool
    paid_at: datetime | None
    can_toggle_paid: bool
    can_remove: bool


@dataclass(frozen=True)
class GroupGiftSummary:
    is_group_gift: bool
    split_mode: str
    total_price: Decimal
    currency: str
    buyer: User | None
    contributor_count: int
    rows: tuple[ContributorRow, ...]
    total_allocated: Decimal
    total_collected: Decimal
    total_remaining: Decimal
    total_unallocated: Decimal
    owed_to_buyer: Decimal
    is_fully_paid: bool
    is_overfunded: bool
    can_manage: bool

    @property
    def percent_collected(self) -> int:
        """Percentage of total price collected, capped between 0 and 100."""
        if not self.total_price or self.total_price <= Decimal("0.00"):
            return 0
        ratio = (self.total_collected / self.total_price) * 100
        return min(100, max(0, int(ratio)))


def get_group_gift_summary(relation: Relation, viewer: User) -> GroupGiftSummary:
    """Build the read model financial summary and breakdown for a group gift."""
    viewer_level = _require_group_gift_access(relation, viewer, PermissionLevel.VIEWER)
    can_manage = viewer_level >= PermissionLevel.EDITOR
    buyer = relation.claimed_by
    currency = _resolve_currency(relation, viewer)
    total_price = relation.effective_price or Decimal("0.00")

    contributions = list(relation.contributions.select_related("user").order_by("created_at", "pk"))

    # In EQUAL mode, paid shares are frozen at contribution.amount.
    # Unpaid shares are rebalanced dynamically over max(0, total_price - sum_frozen).
    share_map: dict[int, Decimal] = {}
    if relation.split_mode == SplitMode.EQUAL:
        frozen_sum = sum(c.amount for c in contributions if c.is_paid)
        unpaid = [c for c in contributions if not c.is_paid]
        remaining_price = max(Decimal("0.00"), total_price - frozen_sum)
        unpaid_shares = calculate_equal_shares(remaining_price, len(unpaid))

        for c, share in zip(unpaid, unpaid_shares, strict=False):
            share_map[c.pk] = share
        for c in contributions:
            if c.is_paid:
                share_map[c.pk] = c.amount
    else:
        for c in contributions:
            share_map[c.pk] = c.amount

    rows: list[ContributorRow] = []
    for c in contributions:
        # Dynamic recipient protection: sanitize contributor row if linked person matches
        is_recip = c.user_id is not None and is_recipient_of_plan(relation, c.user)
        if is_recip:
            display_name = c.name
            is_buyer_row = False
        else:
            display_name = c.display_name
            is_buyer_row = _is_buyer(relation, c)

        is_paid = bool(is_buyer_row or c.is_paid)
        can_toggle_paid = (not is_buyer_row) and (
            can_manage or (buyer is not None and viewer.pk == buyer.pk)
        )
        can_remove = can_manage and (not is_buyer_row) and (not c.is_paid)
        share_amount = share_map.get(c.pk, Decimal("0.00"))

        rows.append(
            ContributorRow(
                contribution=c,
                display_name=display_name,
                share_amount=share_amount,
                is_buyer=is_buyer_row,
                is_paid=is_paid,
                paid_at=c.paid_at,
                can_toggle_paid=can_toggle_paid,
                can_remove=can_remove,
            )
        )

    total_allocated = sum(r.share_amount for r in rows)
    total_collected = sum(r.share_amount for r in rows if r.is_paid)
    total_remaining = max(Decimal("0.00"), total_price - total_collected)
    total_unallocated = max(Decimal("0.00"), total_price - total_allocated)
    owed_to_buyer = (
        sum(r.share_amount for r in rows if not r.is_buyer and not r.is_paid)
        if buyer
        else Decimal("0.00")
    )
    is_fully_paid = total_collected >= total_price > Decimal("0.00")
    is_overfunded = total_collected > total_price

    return GroupGiftSummary(
        is_group_gift=relation.is_group_gift,
        split_mode=relation.split_mode,
        total_price=total_price,
        currency=currency,
        buyer=buyer,
        contributor_count=len(rows),
        rows=tuple(rows),
        total_allocated=total_allocated,
        total_collected=total_collected,
        total_remaining=total_remaining,
        total_unallocated=total_unallocated,
        owed_to_buyer=owed_to_buyer,
        is_fully_paid=is_fully_paid,
        is_overfunded=is_overfunded,
        can_manage=can_manage,
    )


def enable_group_gift(
    relation: Relation, actor: User, split_mode: str = SplitMode.EQUAL
) -> Relation:
    """Enable collaborative group gifting on a gift plan."""
    _require_group_gift_access(relation, actor, PermissionLevel.EDITOR)
    if split_mode not in SplitMode.values:
        raise ValidationError(gettext("Invalid split mode."))

    with transaction.atomic():
        PermissionService.lock_object(relation)
        rel = Relation.objects.select_related("claimed_by", "person", "group").get(pk=relation.pk)
        rel.is_group_gift = True
        rel.split_mode = split_mode
        rel.save(update_fields=["is_group_gift", "split_mode"])

        if rel.claimed_by_id is not None and not is_recipient_of_plan(rel, rel.claimed_by):
            RelationContribution.objects.get_or_create(
                relation=rel,
                user=rel.claimed_by,
                defaults={"name": rel.claimed_by.username},
            )
    relation.refresh_from_db()
    return rel


def disable_group_gift(relation: Relation, actor: User) -> Relation:
    """Disable collaborative group gifting, preserving existing contribution rows."""
    _require_group_gift_access(relation, actor, PermissionLevel.EDITOR)
    with transaction.atomic():
        PermissionService.lock_object(relation)
        rel = Relation.objects.get(pk=relation.pk)
        if rel.contributions.filter(is_paid=True).exists():
            raise ValidationError(gettext("Cannot disable a group gift with recorded payments."))
        rel.is_group_gift = False
        rel.save(update_fields=["is_group_gift"])
    relation.refresh_from_db()
    return rel


def set_split_mode(relation: Relation, actor: User, split_mode: str) -> Relation:
    """Switch cost split mode between EQUAL and CUSTOM."""
    _require_group_gift_access(relation, actor, PermissionLevel.EDITOR)
    if split_mode not in SplitMode.values:
        raise ValidationError(gettext("Invalid split mode."))

    with transaction.atomic():
        PermissionService.lock_object(relation)
        rel = Relation.objects.select_related("claimed_by", "person", "group").get(pk=relation.pk)
        if not rel.is_group_gift:
            raise ValidationError(gettext("Group gift is not enabled on this plan."))

        if rel.split_mode == split_mode:
            return rel

        if split_mode == SplitMode.CUSTOM:
            # Switching EQUAL -> CUSTOM: freeze current equal dynamic shares
            summary = get_group_gift_summary(rel, actor)
            for row in summary.rows:
                if not row.contribution.is_paid:
                    RelationContribution.objects.filter(pk=row.contribution.pk).update(
                        amount=row.share_amount
                    )
        elif split_mode == SplitMode.EQUAL:
            # Switching CUSTOM -> EQUAL: reset unpaid contributions to 0.00
            rel.contributions.filter(is_paid=False).update(amount=Decimal("0.00"))

        rel.split_mode = split_mode
        rel.save(update_fields=["split_mode"])
    relation.refresh_from_db()
    return rel


def add_contributor(
    relation: Relation,
    actor: User,
    user: User | None = None,
    name: str = "",
    amount: Decimal = Decimal("0.00"),
) -> RelationContribution:
    """Add a registered collaborator or external individual as a contributor."""
    _require_group_gift_access(relation, actor, PermissionLevel.EDITOR)
    cleaned_amount = _clean_amount(amount)
    name = (name or "").strip()

    with transaction.atomic():
        PermissionService.lock_object(relation)
        rel = Relation.objects.select_related("person", "group").get(pk=relation.pk)
        if not rel.is_group_gift:
            raise ValidationError(gettext("Group gift is not enabled on this plan."))

        if user is not None:
            if is_recipient_of_plan(rel, user):
                raise ValidationError(
                    gettext("The recipient cannot be a contributor to their own gift.")
                )
            if PermissionService.get_effective_permission(rel, user) < PermissionLevel.VIEWER:
                raise ValidationError(gettext("User must have access to the gift plan."))
            if Relation.objects.hidden_surprises_for(user).filter(pk=rel.pk).exists():
                raise ValidationError(gettext("User cannot access this surprise gift plan."))
            if rel.contributions.filter(user=user).exists():
                raise ValidationError(gettext("This user is already a contributor."))
            name = user.username
        elif not name or len(name) > 150:
            raise ValidationError(gettext("Contributor name must be between 1 and 150 characters."))

        actual_amount = cleaned_amount if rel.split_mode == SplitMode.CUSTOM else Decimal("0.00")
        return RelationContribution.objects.create(
            relation=rel,
            user=user,
            name=name,
            amount=actual_amount,
        )


def remove_contributor(contribution: RelationContribution, actor: User) -> None:
    """Remove a contributor from the group gift."""
    _require_group_gift_access(contribution.relation, actor, PermissionLevel.EDITOR)
    with transaction.atomic():
        PermissionService.lock_object(contribution.relation)
        rel = Relation.objects.select_related("claimed_by").get(pk=contribution.relation_id)
        contrib = RelationContribution.objects.select_related("relation").get(pk=contribution.pk)

        if not rel.is_group_gift:
            raise ValidationError(gettext("Group gift is not enabled on this plan."))
        if _is_buyer(rel, contrib):
            raise ValidationError(gettext("Cannot remove the designated buyer from contributors."))
        if contrib.is_paid:
            raise ValidationError(
                gettext(
                    "Cannot remove a contributor with a recorded payment; unmark payment first."
                )
            )

        contrib.delete()


def toggle_contribution_paid(
    contribution: RelationContribution, actor: User
) -> RelationContribution:
    """Toggle a contributor's share between paid and unpaid."""
    _require_group_gift_access(contribution.relation, actor, PermissionLevel.VIEWER)
    with transaction.atomic():
        PermissionService.lock_object(contribution.relation)
        rel = Relation.objects.select_related("claimed_by", "person", "group").get(
            pk=contribution.relation_id
        )
        contrib = RelationContribution.objects.select_related("relation", "user").get(
            pk=contribution.pk
        )

        if not rel.is_group_gift:
            raise ValidationError(gettext("Group gift is not enabled on this plan."))

        actor_level = PermissionService.get_effective_permission(rel, actor)
        is_actor_buyer = rel.claimed_by_id is not None and actor.pk == rel.claimed_by_id
        if actor_level < PermissionLevel.EDITOR and not is_actor_buyer:
            raise PermissionDenied(
                gettext("Only editors, owners, or the buyer can update payment status.")
            )

        if _is_buyer(rel, contrib):
            raise ValidationError(gettext("The buyer's share is settled by definition."))

        if contrib.is_paid:
            contrib.is_paid = False
            contrib.paid_at = None
            if rel.split_mode == SplitMode.EQUAL:
                contrib.amount = Decimal("0.00")
            contrib.save(update_fields=["is_paid", "paid_at", "amount"])
            return contrib

        # Marking as paid
        if rel.split_mode == SplitMode.CUSTOM:
            if contrib.amount <= Decimal("0.00"):
                raise ValidationError(gettext("Cannot mark a zero-amount share as paid."))
            contrib.is_paid = True
            contrib.paid_at = timezone.now()
            contrib.save(update_fields=["is_paid", "paid_at"])
            return contrib

        # EQUAL mode: derive current dynamic share
        summary = get_group_gift_summary(rel, actor)
        row = next((r for r in summary.rows if r.contribution.pk == contrib.pk), None)
        dynamic_share = row.share_amount if row else Decimal("0.00")
        if dynamic_share <= Decimal("0.00"):
            raise ValidationError(gettext("Cannot mark a zero-amount share as paid."))

        contrib.amount = dynamic_share
        contrib.is_paid = True
        contrib.paid_at = timezone.now()
        contrib.save(update_fields=["is_paid", "paid_at", "amount"])
        return contrib


def update_contribution_amount(
    contribution: RelationContribution, actor: User, amount: Decimal
) -> RelationContribution:
    """Update custom share amount for a contributor in custom split mode."""
    _require_group_gift_access(contribution.relation, actor, PermissionLevel.EDITOR)
    cleaned_amount = _clean_amount(amount)

    with transaction.atomic():
        PermissionService.lock_object(contribution.relation)
        rel = Relation.objects.get(pk=contribution.relation_id)
        contrib = RelationContribution.objects.select_related("relation").get(pk=contribution.pk)

        if not rel.is_group_gift:
            raise ValidationError(gettext("Group gift is not enabled on this plan."))
        if rel.split_mode != SplitMode.CUSTOM:
            raise ValidationError(
                gettext("Share amounts can only be updated in custom split mode.")
            )
        if contrib.is_paid:
            raise ValidationError(
                gettext("Cannot update amount for a contribution that is already marked as paid.")
            )

        contrib.amount = cleaned_amount
        contrib.save(update_fields=["amount"])
        return contrib
