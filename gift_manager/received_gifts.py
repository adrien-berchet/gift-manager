"""Service functions for received gifts (plan reveals and reaction feedback)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ngettext

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import ReceivedGift
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.services import PermissionService
from gift_manager.statuses import is_given_status
from gift_manager.validators import validate_http_url

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


def _active_friend_ids(actor: User) -> set[int]:
    """Return active user IDs confirmed as friends of ``actor``."""
    if not actor or not actor.is_authenticated:
        return set()
    try:
        friend_profiles = actor.profile.friends.all()
    except (AttributeError, ObjectDoesNotExist):
        return set()
    return set(
        User.objects.filter(profile__in=friend_profiles, is_active=True).values_list(
            "pk", flat=True
        )
    )


def reveal_target_ids_by_relation(
    relations: Iterable[Relation],
    actor: User,
) -> dict[int, set[int]]:
    """Return eligible recipient user IDs keyed by relation PK in bulk.

    Matches the exact rules of :func:`can_reveal_plan`:
    1. Relation is marked Given and has not been revealed yet.
    2. ``actor`` holds explicit OWNER permission on the relation.
    3. Recipient account (or non-owner group member account) is an active confirmed friend.
    """
    candidates = [r for r in relations if is_given_status(r.status) and r.revealed_at is None]
    if not candidates:
        return {}

    active_friend_ids = _active_friend_ids(actor)
    if not active_friend_ids:
        return {}

    candidate_pks = [r.pk for r in candidates]
    owners_by_relation: dict[int, set[int]] = {}
    for relation_id, user_id in RelationPermission.objects.filter(
        relation_id__in=candidate_pks,
        permission_type=PermissionLevel.OWNER,
    ).values_list("relation_id", "user_id"):
        owners_by_relation.setdefault(relation_id, set()).add(user_id)

    owned = [r for r in candidates if actor.pk in owners_by_relation.get(r.pk, ())]
    if not owned:
        return {}

    group_ids = {r.group_id for r in owned if r.person_id is None and r.group_id is not None}
    group_account_ids: dict[int, set[int]] = {}
    for group_id in group_ids:
        descendants = PersonGroup.hierarchy_subquery(
            PersonGroup.objects.filter(pk=group_id).values("pk"),
            include_start=True,
        )
        group_account_ids[group_id] = set(
            Person.objects.filter(
                groups__in=descendants,
                account_id__in=active_friend_ids,
            ).values_list("account_id", flat=True)
        )

    targets_by_relation: dict[int, set[int]] = {}
    for relation in owned:
        if relation.person_id is not None:
            raw_ids = (
                {relation.person.account_id} & active_friend_ids
                if relation.person.account_id is not None
                else set()
            )
        elif relation.group_id is not None:
            raw_ids = group_account_ids.get(relation.group_id, set())
        else:
            raw_ids = set()

        eligible_ids = raw_ids - owners_by_relation[relation.pk]
        if eligible_ids:
            targets_by_relation[relation.pk] = eligible_ids
    return targets_by_relation


def revealable_relation_pks(relations: Iterable[Relation], actor: User) -> set[int]:
    """Return the subset of relation PKs ``actor`` can currently reveal."""
    return set(reveal_target_ids_by_relation(relations, actor).keys())


def can_reveal_plan(relation: Relation, user: User) -> bool:
    """Return whether ``user`` can reveal ``relation`` to its recipient(s).

    Requires:
    1. The plan is marked Given.
    2. The plan has not already been revealed (relation.revealed_at is None).
    3. The user holds an explicit OWNER permission on the plan (not via superuser shortcut).
    4. There is at least one active recipient account.
    """
    return bool(reveal_target_ids_by_relation([relation], user))


def get_reveal_targets(relation: Relation, actor: User) -> list[User]:
    """Return confirmed-friend active users who are recipients of ``relation``."""
    target_ids = reveal_target_ids_by_relation([relation], actor).get(relation.pk)
    if not target_ids:
        return []
    return list(User.objects.filter(pk__in=target_ids))


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


class ShareReactionResult(str, Enum):
    """Outcome of sharing a recipient's reaction feedback with a source plan."""

    SHARED = "shared"
    NOTHING_NEW = "nothing_new"
    NOT_ALLOWED = "not_allowed"


def _resolve_snapshot_url(explicit_url: str, locked: Relation) -> str:
    """Validate explicit reveal URL or sanitize legacy fallback URLs."""
    if explicit_url:
        trimmed = explicit_url[:2000]
        validate_http_url(trimmed)
        return trimmed
    fallback = (locked.url or (locked.gift.url if locked.gift else ""))[:2000]
    if not fallback:
        return ""
    try:
        validate_http_url(fallback)
    except ValidationError:
        return ""
    return fallback


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
    snap_url = _resolve_snapshot_url(url, locked)
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

    # Link the target user's Person entries for the givers when available. The other owners stay
    # in giver_accounts: annotate_snapshot_givers names the target's friends and only counts the
    # rest, so co-owners the target does not know are never named to them.
    giver_persons = list(
        Person.objects.accessible_by(target).filter(account__in=snapshot.owner_ids)
    )
    linked_wish = (
        locked.wish
        if locked.wish_id
        and locked.wish.wisher_id == target.pk
        and not locked.wish.is_deleted_by_wisher
        else None
    )

    gift = ReceivedGift.objects.create(
        recipient_user=target,
        title=snapshot.title,
        url=snapshot.url,
        received_on=snapshot.received_on,
        occasion_text=snapshot.occasion_text,
        source_relation=locked,
        source_givers_text=snapshot.source_givers_text,
        giver_note=snapshot.giver_note,
        wish=linked_wish,
    )
    gift.giver_accounts.set(snapshot.owner_users)
    if giver_persons:
        gift.giver_persons.set(giver_persons)

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


def linkable_giver_ids(user: User, gifts: Iterable[ReceivedGift]) -> tuple[set[int], set[int]]:
    """Return the giver person and group PKs the user can still open.

    Givers are always displayed by name, but only linked to their detail page
    while the user has access to them (sharing may have been revoked since).
    """
    gifts_list = list(gifts)
    person_pks = {person.pk for gift in gifts_list for person in gift.giver_persons.all()}
    group_pks = {group.pk for gift in gifts_list for group in gift.giver_groups.all()}
    linkable_person_ids = (
        set(
            Person.objects.accessible_by(user)
            .filter(pk__in=person_pks)
            .values_list("pk", flat=True)
        )
        if person_pks
        else set()
    )
    linkable_group_ids = (
        set(
            PersonGroup.objects.accessible_by(user)
            .filter(pk__in=group_pks)
            .values_list("pk", flat=True)
        )
        if group_pks
        else set()
    )
    return linkable_person_ids, linkable_group_ids


def named_snapshot_givers(user: User) -> tuple[list[Person], list[tuple[str, str]]]:
    """Return the givers kept from revealed plans that ``user`` sees by name, for the giver filter.

    Follows ``annotate_snapshot_givers``: an account is named through ``user``'s contact for it,
    or as a confirmed friend; a typed giver label hides the kept givers. The result is the
    contacts, and the ``(username, display name)`` of the friends without a contact. Owners who
    are neither stay anonymous: they are never listed.
    """
    account_ids = set(
        ReceivedGift.objects.for_user(user)
        .filter(giver_label="", giver_accounts__isnull=False)
        .values_list("giver_accounts", flat=True)
    ) - {user.pk}
    if not account_ids:
        return [], []
    contacts = list(Person.objects.accessible_by(user).filter(account_id__in=account_ids))
    friend_ids = (account_ids & _active_friend_ids(user)) - {p.account_id for p in contacts}
    friends = sorted(
        (
            (account.username, _account_display_name(account))
            for account in User.objects.filter(pk__in=friend_ids)
        ),
        key=lambda friend: friend[1].lower(),
    )
    return contacts, friends


def snapshot_giver_account_q(user: User, account_id: int | None) -> Q:
    """Match the gifts whose kept giver ``account_id`` is shown by name to ``user``."""
    if account_id is None or account_id == user.pk:
        return Q(pk__in=[])
    return Q(giver_label="", giver_accounts=account_id)


def friend_giver_account_id(user: User, username: str) -> int | None:
    """Return the id of the confirmed friend of ``user`` named ``username``, if any."""
    return (
        User.objects.filter(username=username, pk__in=_active_friend_ids(user))
        .exclude(pk=user.pk)
        .values_list("pk", flat=True)
        .first()
    )


def _account_display_name(account: User) -> str:
    return account.get_full_name() or account.username


def _other_givers_label(count: int, *, after_named_givers: bool) -> str:
    if not count:
        return ""
    if after_named_givers:
        return ngettext("and %(count)d other", "and %(count)d others", count) % {"count": count}
    return ngettext("%(count)d other giver", "%(count)d other givers", count) % {"count": count}


def annotate_snapshot_givers(
    user: User, gifts: Iterable[ReceivedGift], *, ignore_label: bool = False
) -> list[ReceivedGift]:
    """Set how the givers kept from a revealed plan are shown to ``user`` on each gift.

    A revealed gift keeps every plan owner in ``giver_accounts``. Owners already shown as one of
    the gift's giver contacts are skipped; the others are shown as ``user``'s contact for them
    when there is one (``snapshot_giver_persons``, e.g. added after the reveal), named when they
    are confirmed friends of ``user`` (``snapshot_giver_names``), and only counted otherwise
    (``other_givers_count`` and ``other_givers_label``, e.g. "and 1 other"). A free-text giver
    typed by the recipient replaces them unless ``ignore_label`` is set.
    Prefetch ``giver_persons``, ``giver_groups`` and ``giver_accounts``.
    """
    gifts_list = list(gifts)
    pending: list[tuple[ReceivedGift, list[User]]] = []
    for gift in gifts_list:
        gift.snapshot_giver_persons = []
        gift.snapshot_giver_names = []
        gift.other_givers_count = 0
        gift.other_givers_label = ""
        if gift.giver_label and not ignore_label:
            continue
        contact_account_ids = {p.account_id for p in gift.giver_persons.all() if p.account_id}
        accounts = [
            account
            for account in gift.giver_accounts.all()
            if account.pk not in contact_account_ids and account.pk != user.pk
        ]
        if accounts:
            pending.append((gift, accounts))
    if not pending:
        return gifts_list

    contacts_by_account: dict[int, Person] = {}
    for person in Person.objects.accessible_by(user).filter(
        account_id__in={account.pk for _gift, accounts in pending for account in accounts}
    ):
        contacts_by_account.setdefault(person.account_id, person)
    friend_ids = _active_friend_ids(user)
    for gift, accounts in pending:
        gift.snapshot_giver_persons = [
            contacts_by_account[account.pk]
            for account in accounts
            if account.pk in contacts_by_account
        ]
        unmatched = [account for account in accounts if account.pk not in contacts_by_account]
        known = [account for account in unmatched if account.pk in friend_ids]
        gift.snapshot_giver_names = sorted(_account_display_name(account) for account in known)
        gift.other_givers_count = len(unmatched) - len(known)
        after_named_givers = bool(
            gift.snapshot_giver_persons
            or gift.snapshot_giver_names
            or gift.giver_persons.all()
            or gift.giver_groups.all()
        )
        gift.other_givers_label = _other_givers_label(
            gift.other_givers_count, after_named_givers=after_named_givers
        )
    return gifts_list


def snapshot_givers_summary(gift: ReceivedGift) -> str:
    """One line listing the givers of an annotated gift, e.g. "Alice Smith, and 1 other"."""
    parts = [str(person) for person in gift.giver_persons.all()]
    parts += [group.name for group in gift.giver_groups.all()]
    parts += [str(person) for person in gift.snapshot_giver_persons]
    parts += gift.snapshot_giver_names
    if gift.other_givers_label:
        parts.append(gift.other_givers_label)
    return ", ".join(parts)


def shareable_reaction_fields(received_gift: ReceivedGift, plan: Relation) -> list[str]:
    """Return reaction fields that ``received_gift`` can still fill on ``plan``."""
    fields = []
    if plan.reaction_rating is None and received_gift.reaction_rating is not None:
        fields.append("reaction_rating")
    if (not plan.reaction_note) and received_gift.reaction_note:
        fields.append("reaction_note")
    return fields


def _actor_is_friends_with_plan_owner(plan: Relation, actor: User) -> bool:
    """Return whether ``actor`` is confirmed friends with at least one owner of ``plan``."""
    try:
        actor_friend_ids = set(actor.profile.friends.values_list("user_id", flat=True))
    except ObjectDoesNotExist:
        return False
    if not actor_friend_ids:
        return False
    owner_ids = set(
        RelationPermission.objects.filter(
            relation=plan, permission_type=PermissionLevel.OWNER
        ).values_list("user_id", flat=True)
    )
    return bool(owner_ids & actor_friend_ids)


def can_share_reaction(received_gift: ReceivedGift, actor: User) -> bool:
    """Return whether ``actor`` can share new reaction feedback from ``received_gift``."""
    if not actor or not actor.is_authenticated or received_gift.recipient_user_id != actor.pk:
        return False
    plan = received_gift.source_relation
    if plan is None or not is_given_status(plan.status):
        return False
    if not shareable_reaction_fields(received_gift, plan):
        return False
    return _actor_is_friends_with_plan_owner(plan, actor)


def share_reaction_feedback(received_gift: ReceivedGift, actor: User) -> ShareReactionResult:
    """Share recipient's reaction rating and note back to the source plan."""
    if received_gift.recipient_user_id != actor.pk:
        raise PermissionDenied(_RECEIVED_GIFT_OWNER_ONLY_ERROR)
    if received_gift.source_relation_id is None:
        return ShareReactionResult.NOT_ALLOWED

    with transaction.atomic():
        plan = (
            Relation.objects.select_for_update().filter(pk=received_gift.source_relation_id).first()
        )
        if plan is None or not is_given_status(plan.status):
            return ShareReactionResult.NOT_ALLOWED

        if not _actor_is_friends_with_plan_owner(plan, actor):
            return ShareReactionResult.NOT_ALLOWED

        plan_update_fields = shareable_reaction_fields(received_gift, plan)
        if not plan_update_fields:
            received_gift.source_relation = plan
            return ShareReactionResult.NOTHING_NEW

        for field_name in plan_update_fields:
            setattr(plan, field_name, getattr(received_gift, field_name))
        plan.save(update_fields=plan_update_fields)

        received_gift.reaction_shared_at = timezone.now()
        received_gift.save(update_fields=["reaction_shared_at"])
        received_gift.source_relation = plan
        return ShareReactionResult.SHARED
