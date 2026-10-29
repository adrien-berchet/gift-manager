"""Recipient history builder for gift suggestions."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Prefetch
from django.db.models import Q

from gift_manager.gift_history import group_history_queryset
from gift_manager.gift_history import person_history_queryset
from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import relation_status_slug


@dataclass(frozen=True)
class HistoryItem:
    """One past gift plan in the recipient's history."""

    relation_id: int
    gift_id: int
    gift_name: str
    tag_ids: frozenset[int]  # visible tags, ancestors included
    status_slug: str
    rating: int | None  # only when relation.has_visible_reaction
    note: str  # reaction note, only when rating is visible
    comment: str
    is_direct: bool  # plan targets the recipient itself
    person_id: int | None
    group_id: int | None
    created: datetime
    event_name: str = ""
    price: float | None = None
    direct_tag_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class RecipientHistory:
    """The complete accessible history and context for a recipient."""

    recipient: Person | PersonGroup
    items: tuple[HistoryItem, ...]
    planned_gift_ids: frozenset[int]
    interest_tag_ids: frozenset[int]
    ancestors: dict[int, frozenset[int]]
    public_interest_tag_ids: frozenset[int] = frozenset()


def tag_ancestor_map(tag_ids: set[int]) -> dict[int, frozenset[int]]:
    """Return each tag mapped to itself plus all its ancestors, restricted to tag_ids.

    Walks the GiftTag.parent_tags through table with a visited set so stored
    cycles terminate without error.
    """
    if not tag_ids:
        return {}

    parents_by_child: dict[int, set[int]] = defaultdict(set)
    edges = GiftTag.parent_tags.through.objects.filter(
        from_gifttag_id__in=tag_ids, to_gifttag_id__in=tag_ids
    ).values_list("from_gifttag_id", "to_gifttag_id")
    for child_id, parent_id in edges:
        parents_by_child[child_id].add(parent_id)

    ancestors_map: dict[int, frozenset[int]] = {}
    for tag_id in tag_ids:
        visited = {tag_id}
        queue = list(parents_by_child.get(tag_id, ()))
        while queue:
            parent = queue.pop()
            if parent in tag_ids and parent not in visited:
                visited.add(parent)
                queue.extend(parents_by_child.get(parent, ()))
        ancestors_map[tag_id] = frozenset(visited)

    return ancestors_map


def build_recipient_history(user, recipient: Person | PersonGroup) -> RecipientHistory:
    """Build the accessible history and tag profiles for a recipient."""
    visible_tag_ids = VisibleMetadata(user).tag_ids
    ancestors = tag_ancestor_map(visible_tag_ids)

    public_interest_tag_ids: frozenset[int] = frozenset()
    if isinstance(recipient, Person):
        relations = list(person_history_queryset(user, recipient).prefetch_related("gift__tags"))
        raw_interest_ids = set(
            recipient.interests.filter(pk__in=visible_tag_ids).values_list("pk", flat=True)
        )
        interest_tag_ids = frozenset.union(
            *(ancestors.get(tid, frozenset({tid})) for tid in raw_interest_ids),
            frozenset(),
        )
        if recipient.account_id and PermissionService.users_are_friends(user, recipient.account):
            account_profile = getattr(recipient.account, "profile", None)
            if account_profile:
                raw_pub_ids = set(
                    account_profile.public_interests.filter(
                        is_public=True, pk__in=visible_tag_ids
                    ).values_list("pk", flat=True)
                )
                public_interest_tag_ids = frozenset.union(
                    *(ancestors.get(tid, frozenset({tid})) for tid in raw_pub_ids),
                    frozenset(),
                )
    else:
        relations = list(group_history_queryset(user, recipient).prefetch_related("gift__tags"))
        interest_tag_ids = frozenset()

    raw_items: list[HistoryItem] = []
    for rel in relations:
        if isinstance(recipient, Person):
            is_direct = rel.person_id == recipient.pk and rel.group_id is None
        else:
            is_direct = rel.group_id == recipient.pk and rel.person_id is None

        gift = rel.gift
        gift_id = rel.gift_id
        gift_name = gift.name if gift else ""
        gift_visible_tags = (
            [t.pk for t in gift.tags.all() if t.pk in visible_tag_ids] if gift else []
        )
        expanded_tags = frozenset.union(
            *(ancestors.get(tid, frozenset({tid})) for tid in gift_visible_tags),
            frozenset(),
        )

        has_visible_reaction = rel.has_visible_reaction
        rating = rel.reaction_rating if has_visible_reaction else None
        note = (rel.reaction_note or "") if has_visible_reaction else ""
        slug = relation_status_slug(rel.status)
        event_name = rel.event.name if rel.event else ""
        raw_price = rel.price if rel.price is not None else (gift.price if gift else None)
        price = float(raw_price) if raw_price is not None else None

        raw_items.append(
            HistoryItem(
                relation_id=rel.pk,
                gift_id=gift_id,
                gift_name=gift_name,
                tag_ids=expanded_tags,
                status_slug=slug,
                rating=rating,
                note=note,
                comment=rel.comment or "",
                is_direct=is_direct,
                person_id=rel.person_id,
                group_id=rel.group_id,
                created=rel.creation_date,
                event_name=event_name,
                price=price,
                direct_tag_ids=frozenset(gift_visible_tags),
            )
        )

    items = tuple(
        sorted(raw_items, key=lambda item: (item.created, item.relation_id), reverse=True)
    )

    planned_gift_ids = frozenset(
        item.gift_id
        for item in items
        if item.is_direct and not is_abandoned_status(item.status_slug)
    )

    return RecipientHistory(
        recipient=recipient,
        items=items,
        planned_gift_ids=planned_gift_ids,
        interest_tag_ids=interest_tag_ids,
        ancestors=ancestors,
        public_interest_tag_ids=public_interest_tag_ids,
    )


def dismissed_suggestions_for(
    user,
    recipient: Person | PersonGroup,
    visible_tag_ids: set[int] | None = None,
    limit: int = 500,
) -> list[GiftSuggestion]:
    """Return dismissed suggestions accessible to user, with tags prefetched."""
    rec_filter = {"person": recipient} if isinstance(recipient, Person) else {"group": recipient}
    accessible_gifts = Gift.objects.accessible_by(user)
    qs = (
        GiftSuggestion.objects.filter(
            user=user,
            state=GiftSuggestion.State.DISMISSED,
            **rec_filter,
        )
        .filter(Q(gift__isnull=True) | Q(gift__in=accessible_gifts))
        .select_related("gift")
    )
    if visible_tag_ids is not None:
        qs = qs.prefetch_related(
            Prefetch("tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids)),
            Prefetch("gift__tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids)),
        )
    return list(qs.order_by("-updated_at", "-created_at")[:limit])


@dataclass(frozen=True)
class PreferenceProfile:
    """All-time positive, owned/practiced, and negative tag profiles."""

    liked_tags: tuple[tuple[str, int], ...] = ()
    owned_tags: tuple[tuple[str, int], ...] = ()
    disliked_tags: tuple[tuple[str, int], ...] = ()


def _tally_plan_affinities(
    history: RecipientHistory,
    visible_tag_ids: set[int],
    liked_counts: dict[int, int],
    disliked_counts: dict[int, int],
) -> None:
    for it in history.items:
        if it.rating is None:
            continue
        target_tags = it.direct_tag_ids & visible_tag_ids
        if not target_tags:
            continue
        if it.rating >= 4:
            for tid in target_tags:
                liked_counts[tid] += 1
        elif it.rating <= 2:
            for tid in target_tags:
                disliked_counts[tid] += 1


def _tally_dismissal_affinities(
    dismissed: list[GiftSuggestion],
    visible_tag_ids: set[int],
    owned_counts: dict[int, int],
    disliked_counts: dict[int, int],
) -> None:
    for s in dismissed:
        if s.gift_id and s.gift:
            tag_ids = {t.pk for t in s.gift.tags.all() if t.pk in visible_tag_ids}
        else:
            tag_ids = {t.pk for t in s.tags.all() if t.pk in visible_tag_ids}
        if not tag_ids:
            continue
        if s.dismiss_reason == GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED:
            for tid in tag_ids:
                owned_counts[tid] += 1
        elif s.dismiss_reason == GiftSuggestion.DismissReason.DISLIKES:
            for tid in tag_ids:
                disliked_counts[tid] += 1


def build_preference_profile(
    user,
    history: RecipientHistory,
    visible_tag_ids: set[int],
) -> PreferenceProfile:
    """Aggregate all-time direct tag affinities from 100% of plans and dismissals."""
    liked_counts: dict[int, int] = defaultdict(int)
    disliked_counts: dict[int, int] = defaultdict(int)
    owned_counts: dict[int, int] = defaultdict(int)

    # 1. Tally from all-time plans (no 50-item cutoff)
    _tally_plan_affinities(history, visible_tag_ids, liked_counts, disliked_counts)

    # 2. Tally from dismissed suggestions
    dismissed = dismissed_suggestions_for(
        user, history.recipient, visible_tag_ids=visible_tag_ids, limit=500
    )
    _tally_dismissal_affinities(dismissed, visible_tag_ids, owned_counts, disliked_counts)

    all_tag_ids = set(liked_counts) | set(disliked_counts) | set(owned_counts)
    tag_names = dict(GiftTag.objects.filter(pk__in=all_tag_ids).values_list("pk", "name"))

    def _format_bucket(counts: dict[int, int]) -> tuple[tuple[str, int], ...]:
        items = [(tag_names[tid], count) for tid, count in counts.items() if tid in tag_names]
        items.sort(key=lambda x: (-x[1], x[0].casefold()))
        return tuple(items[:20])

    return PreferenceProfile(
        liked_tags=_format_bucket(liked_counts),
        owned_tags=_format_bucket(owned_counts),
        disliked_tags=_format_bucket(disliked_counts),
    )
