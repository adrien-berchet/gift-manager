"""Service functions for received gifts (plan reveals and reaction feedback)."""

from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.plan_coordination import plan_recipient_account_ids
from gift_manager.services import PermissionService
from gift_manager.statuses import is_given_status

_REVEAL_OWNER_ONLY_ERROR = "Only plan owners can reveal a gift plan."
_REVEAL_GIVEN_ONLY_ERROR = "Only plans with status 'Given' can be revealed."
_RECEIVED_GIFT_OWNER_ONLY_ERROR = "You do not own this received gift."


@dataclass(frozen=True)
class _RevealSnapshot:
    """Precomputed snapshot attributes and giver details for a plan reveal."""

    title: str
    url: str
    received_on: date
    occasion_text: str
    giver_note: str
    owner_ids: set[int]
    owner_users: list[User]
    source_givers_text: str


def can_reveal_plan(relation: Relation, user: User) -> bool:
    """Return whether ``user`` can reveal ``relation`` to its recipient(s).

    Requires:
    1. The plan is marked Given.
    2. The plan has not already been revealed (relation.revealed_at is None).
    3. The user holds an explicit OWNER permission on the plan (not via superuser shortcut).
    4. There is at least one active recipient account.
    """
    if not is_given_status(relation.status) or relation.revealed_at is not None:
        return False
    if not user or not user.is_authenticated:
        return False
    permission_map = PermissionService.get_permission_map(relation)
    if permission_map.get(user.pk) != PermissionLevel.OWNER:
        return False
    return bool(get_reveal_targets(relation, user))


def get_reveal_targets(relation: Relation, actor: User) -> list[User]:
    """Return confirmed-friend active users who are recipients of ``relation``."""
    recipient_ids = plan_recipient_account_ids(relation)
    if not recipient_ids:
        return []
    candidates = User.objects.filter(pk__in=recipient_ids, is_active=True)
    # Check actor friendship with each candidate to prevent harassment
    return [c for c in candidates if PermissionService.users_are_friends(actor, c)]


def user_is_plan_owner(relation: Relation, user: User) -> bool:
    """Return whether ``user`` has explicit OWNER permission on ``relation``."""
    if not user or not user.is_authenticated:
        return False
    return PermissionService.get_permission_map(relation).get(user.pk) == PermissionLevel.OWNER


def _resolve_reveal_date(relation: Relation, received_on: date | None) -> date:
    """Return the reveal date, falling back to status change, due date, or today."""
    if received_on is not None:
        return received_on
    if relation.status_changed_at:
        return timezone.localdate(relation.status_changed_at)
    if relation.due_date:
        return relation.due_date
    return timezone.localdate()


def _build_reveal_snapshot(
    locked: Relation,
    *,
    title: str,
    url: str,
    received_on: date | None,
    occasion_text: str,
    giver_note: str,
) -> _RevealSnapshot:
    """Build immutable snapshot fields and owner attribution for revealing a plan."""
    snap_title = (title or (locked.gift.name if locked.gift else ""))[:255]
    snap_url = (url or locked.url or (locked.gift.url if locked.gift else ""))[:2000]
    snap_date = _resolve_reveal_date(locked, received_on)
    snap_occasion = (occasion_text or (locked.event.name[:100] if locked.event else ""))[:100]

    owner_ids = {
        user_id
        for user_id, level in PermissionService.get_permission_map(locked).items()
        if level == PermissionLevel.OWNER
    }
    owner_users = list(User.objects.filter(pk__in=owner_ids, is_active=True))
    owner_names = [u.get_full_name() or u.username for u in owner_users]
    source_givers_text = ", ".join(owner_names)[:255]

    return _RevealSnapshot(
        title=snap_title,
        url=snap_url,
        received_on=snap_date,
        occasion_text=snap_occasion,
        giver_note=giver_note,
        owner_ids=owner_ids,
        owner_users=owner_users,
        source_givers_text=source_givers_text,
    )


def _create_revealed_gift_for_target(
    locked: Relation,
    target: User,
    snapshot: _RevealSnapshot,
) -> ReceivedGift | None:
    """Create one snapshot ReceivedGift for ``target`` unless already created."""
    if ReceivedGift.objects.filter(recipient_user=target, source_relation=locked).exists():
        return None

    gift = ReceivedGift.objects.create(
        recipient_user=target,
        title=snapshot.title,
        url=snapshot.url,
        received_on=snapshot.received_on,
        occasion_text=snapshot.occasion_text,
        source_relation=locked,
        source_givers_text=snapshot.source_givers_text,
        giver_note=snapshot.giver_note,
    )
    gift.giver_accounts.set(snapshot.owner_users)

    # Link the target user's Person entries for the givers when available
    giver_persons = list(
        Person.objects.accessible_by(target).filter(account__in=snapshot.owner_ids)
    )
    if giver_persons:
        gift.giver_persons.set(giver_persons)
    else:
        gift.giver_label = snapshot.source_givers_text
        gift.save(update_fields=["giver_label"])

    if locked.wish_id and locked.wish.wisher_id == target.pk:
        gift.wish = locked.wish
        gift.save(update_fields=["wish"])

    return gift


def reveal_plan(
    relation: Relation,
    actor: User,
    *,
    title: str = "",
    url: str = "",
    received_on: date | None = None,
    occasion_text: str = "",
    giver_note: str = "",
) -> list[ReceivedGift]:
    """Reveal a Given plan to its recipient accounts by creating snapshot ReceivedGift entries.

    Returns the list of created ReceivedGift instances.
    """
    if not user_is_plan_owner(relation, actor):
        raise PermissionDenied(_REVEAL_OWNER_ONLY_ERROR)

    with transaction.atomic():
        locked = Relation.objects.select_for_update().get(pk=relation.pk)
        if not is_given_status(locked.status):
            raise PermissionDenied(_REVEAL_GIVEN_ONLY_ERROR)
        if locked.revealed_at is not None:
            return []  # Already revealed

        targets = get_reveal_targets(locked, actor)
        if not targets:
            return []

        snapshot = _build_reveal_snapshot(
            locked,
            title=title,
            url=url,
            received_on=received_on,
            occasion_text=occasion_text,
            giver_note=giver_note,
        )
        created_gifts = [
            gift
            for target in targets
            if (gift := _create_revealed_gift_for_target(locked, target, snapshot)) is not None
        ]

        if created_gifts:
            locked.revealed_at = timezone.now()
            locked.save(update_fields=["revealed_at"])
            relation.revealed_at = locked.revealed_at

        return created_gifts


def share_reaction_feedback(received_gift: ReceivedGift, actor: User) -> bool:
    """Share recipient's reaction rating and note back to the source plan."""
    if received_gift.recipient_user_id != actor.pk:
        raise PermissionDenied(_RECEIVED_GIFT_OWNER_ONLY_ERROR)
    if received_gift.source_relation_id is None:
        return False

    with transaction.atomic():
        plan = (
            Relation.objects.select_for_update().filter(pk=received_gift.source_relation_id).first()
        )
        if plan is None or not is_given_status(plan.status):
            return False

        # Verify actor is a friend of at least one owner
        owner_ids = set(
            RelationPermission.objects.filter(
                relation=plan, permission_type=PermissionLevel.OWNER
            ).values_list("user_id", flat=True)
        )
        actor_friend_ids = set(actor.profile.friends.values_list("user_id", flat=True))
        if not (owner_ids & actor_friend_ids):
            return False

        plan_update_fields = []
        if plan.reaction_rating is None and received_gift.reaction_rating is not None:
            plan.reaction_rating = received_gift.reaction_rating
            plan_update_fields.append("reaction_rating")

        if (not plan.reaction_note) and received_gift.reaction_note:
            plan.reaction_note = received_gift.reaction_note
            plan_update_fields.append("reaction_note")

        if plan_update_fields:
            plan.save(update_fields=plan_update_fields)

        received_gift.reaction_shared_at = timezone.now()
        received_gift.save(update_fields=["reaction_shared_at"])
        return True
