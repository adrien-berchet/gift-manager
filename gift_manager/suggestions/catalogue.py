"""Catalogue suggestion strategy based on recipient history and gift ratings."""

from collections import defaultdict

from django.db.models import Prefetch
from django.db.models import Q
from django.utils.translation import gettext as _

from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.statuses import can_rate_status
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_given_status
from gift_manager.suggestions.names import normalize_gift_name
from gift_manager.suggestions.types import SuggestionCandidate
from gift_manager.suggestions.types import SuggestionContext
from gift_manager.suggestions.types import SuggestionReason

DIRECT_WEIGHT = 1.0
INDIRECT_WEIGHT = 0.5
INTEREST_SIGNAL = 1.0


def _item_signal(item) -> float:
    if item.rating is not None:
        return {5: 2.0, 4: 1.0, 3: 0.0, 2: -1.0, 1: -2.0}.get(item.rating, 0.0)
    if is_abandoned_status(item.status_slug):
        return -1.0
    if is_given_status(item.status_slug):
        return 0.5
    return 0.0


def describe_reason(reason: SuggestionReason | str, recipient=None) -> str:  # noqa: ARG001
    """Format a human-readable reason for a gift suggestion."""
    if isinstance(reason, str):
        return reason

    tags_str = ", ".join(reason.tag_names)
    text = ""
    if reason.code == "liked_tags":
        if reason.rating is not None:
            text = _("Shares tags with gifts rated %(rating)s/5: %(tags)s") % {
                "rating": reason.rating,
                "tags": tags_str,
            }
        else:
            text = _("Shares tags with past favourites: %(tags)s") % {"tags": tags_str}
    elif reason.code == "related_liked_tags":
        text = _("Shares tags with gifts liked by related recipients: %(tags)s") % {
            "tags": tags_str
        }
    elif reason.code == "interests":
        text = _("Matches their interests: %(tags)s") % {"tags": tags_str}
    elif reason.code == "popular":
        text = _("Rated %(rating)s/5 on average") % {"rating": reason.rating}
    return text


def _build_profile(
    history,
    dismissed_tag_signals: dict[int, float] | None = None,
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    profile: dict[int, float] = defaultdict(float)
    direct_contrib: dict[int, float] = defaultdict(float)
    related_contrib: dict[int, float] = defaultdict(float)
    interest_contrib: dict[int, float] = defaultdict(float)

    for item in history.items:
        sig = _item_signal(item)
        w = DIRECT_WEIGHT if item.is_direct else INDIRECT_WEIGHT
        item_points = w * sig
        for tid in item.tag_ids:
            profile[tid] += item_points
            if sig > 0:
                if item.is_direct:
                    direct_contrib[tid] += item_points
                else:
                    related_contrib[tid] += item_points

    for tid in history.interest_tag_ids:
        profile[tid] += INTEREST_SIGNAL
        interest_contrib[tid] += INTEREST_SIGNAL

    if dismissed_tag_signals:
        for tid, sig in dismissed_tag_signals.items():
            profile[tid] += sig
            if sig > 0:
                interest_contrib[tid] += sig

    return profile, direct_contrib, related_contrib, interest_contrib


def _compute_dismissed_signals(
    context: SuggestionContext,
    visible_tag_ids: set[int],
    ancestors: dict[int, frozenset[int]],
) -> dict[int, float]:
    rec_filter = (
        {"person": context.recipient}
        if isinstance(context.recipient, Person)
        else {"group": context.recipient}
    )
    accessible_gifts = Gift.objects.accessible_by(context.user)
    dismissed = (
        GiftSuggestion.objects.filter(
            user=context.user,
            state=GiftSuggestion.State.DISMISSED,
            **rec_filter,
        )
        .filter(Q(gift__isnull=True) | Q(gift__in=accessible_gifts))
        .exclude(dismiss_reason="")
        .select_related("gift")
        .prefetch_related(
            Prefetch("tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids)),
            Prefetch("gift__tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids)),
        )
    )
    signals: dict[int, float] = defaultdict(float)
    for s in dismissed:
        if s.gift_id and s.gift:
            tag_ids = {t.pk for t in s.gift.tags.all()}
        else:
            tag_ids = {t.pk for t in s.tags.all()}

        if not tag_ids:
            continue

        if s.dismiss_reason == GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED:
            sig = INTEREST_SIGNAL
            # Positive interest naturally expands upward to ancestor categories
            target_tag_ids = frozenset.union(
                *(ancestors.get(tid, frozenset({tid})) for tid in tag_ids),
                frozenset(),
            )
        elif s.dismiss_reason == GiftSuggestion.DismissReason.DISLIKES:
            sig = -INTEREST_SIGNAL
            # Negative feedback must NOT propagate upward to ancestors (which would poison
            # sibling tags). Furthermore, if multiple tags are on the item, isolate leaf tags:
            # exclude any tag that is an ancestor of another tag on this item (e.g. drop 'Books'
            # if 'Horror' is present).
            ancestor_ids_on_gift = {
                a
                for tid in tag_ids
                for a in ancestors.get(tid, frozenset({tid}))
                if a != tid and a in tag_ids
            }
            target_tag_ids = frozenset(tag_ids - ancestor_ids_on_gift) or frozenset(tag_ids)
        else:
            continue

        for tid in target_tag_ids:
            signals[tid] += sig
    return signals


def _compute_popularity(user) -> dict[int, float]:
    relations_qs = (
        Relation.objects.accessible_by(user)
        .filter(reaction_rating__isnull=False, gift__isnull=False)
        .select_related("status")
    )
    ratings_by_gift: dict[int, list[int]] = defaultdict(list)
    for rel in relations_qs:
        if can_rate_status(rel.status) and rel.reaction_rating is not None:
            ratings_by_gift[rel.gift_id].append(rel.reaction_rating)

    popularity_by_gift: dict[int, float] = {}
    for gift_id, ratings in ratings_by_gift.items():
        if ratings:
            popularity_by_gift[gift_id] = sum(ratings) / len(ratings)
    return popularity_by_gift


def _determine_normal_reason(
    expanded_tag_ids: frozenset[int],
    matching_tag_ids: list[int],
    profile: dict[int, float],
    direct_contrib: dict[int, float],
    related_contrib: dict[int, float],
    interest_contrib: dict[int, float],
    history,
    tag_names_by_id: dict[int, str],
) -> SuggestionReason:
    cand_direct = sum(direct_contrib.get(tid, 0.0) for tid in matching_tag_ids)
    cand_related = sum(related_contrib.get(tid, 0.0) for tid in matching_tag_ids)
    cand_interest = sum(interest_contrib.get(tid, 0.0) for tid in matching_tag_ids)

    if cand_interest > cand_direct and cand_interest > cand_related:
        code = "interests"
    elif cand_direct >= cand_related and cand_direct > 0:
        code = "liked_tags"
    elif cand_related > 0:
        code = "related_liked_tags"
    else:
        code = "liked_tags"

    top_tags = sorted(
        matching_tag_ids,
        key=lambda tid: (-profile[tid], tag_names_by_id.get(tid, "")),
    )
    tag_names = tuple(tag_names_by_id[tid] for tid in top_tags[:2] if tid in tag_names_by_id)

    if code == "interests":
        reason_rating = None
    elif code == "liked_tags":
        contributing_ratings = [
            item.rating
            for item in history.items
            if item.is_direct
            and _item_signal(item) > 0
            and (item.tag_ids & expanded_tag_ids)
            and item.rating is not None
        ]
        reason_rating = max(contributing_ratings) if contributing_ratings else None
    elif code == "related_liked_tags":
        contributing_ratings = [
            item.rating
            for item in history.items
            if not item.is_direct
            and _item_signal(item) > 0
            and (item.tag_ids & expanded_tag_ids)
            and item.rating is not None
        ]
        reason_rating = max(contributing_ratings) if contributing_ratings else None
    else:
        reason_rating = None

    return SuggestionReason(code=code, tag_names=tag_names, rating=reason_rating)


class CatalogueStrategy:
    """Ranks accessible catalogue gifts using recipient history and interests."""

    def suggest(self, context: SuggestionContext, limit: int) -> list[SuggestionCandidate]:
        user = context.user
        history = context.history
        visible_tag_ids = VisibleMetadata(user).tag_ids
        ancestors = history.ancestors

        dismissed_signals = _compute_dismissed_signals(context, visible_tag_ids, ancestors)
        profile, direct_contrib, related_contrib, interest_contrib = _build_profile(
            history, dismissed_signals
        )
        has_positive_tag = any(score > 0 for score in profile.values())

        gifts_qs = (
            Gift.objects.accessible_by(user)
            .exclude(pk__in=context.excluded_gift_ids)
            .prefetch_related(
                Prefetch(
                    "tags",
                    queryset=GiftTag.objects.filter(pk__in=visible_tag_ids),
                )
            )
        )
        candidate_gifts = [
            g for g in gifts_qs if normalize_gift_name(g.name) not in context.blocked_names
        ]

        popularity_by_gift = _compute_popularity(user)
        tag_names_by_id = dict(
            GiftTag.objects.filter(pk__in=visible_tag_ids).values_list("pk", "name")
        )

        scored_candidates: list[tuple[tuple, SuggestionCandidate]] = []

        for gift in candidate_gifts:
            direct_visible_tags = [t for t in gift.tags.all() if t.pk in visible_tag_ids]
            direct_tag_ids = frozenset(t.pk for t in direct_visible_tags)
            expanded_tag_ids = frozenset.union(
                *(ancestors.get(t.pk, frozenset({t.pk})) for t in direct_visible_tags),
                frozenset(),
            )

            tag_score = sum(profile.get(tid, 0.0) for tid in expanded_tag_ids)
            pop = popularity_by_gift.get(gift.pk)

            if tag_score < 0:
                continue

            if has_positive_tag:
                if tag_score <= 0:
                    continue

                matching_tag_ids = [tid for tid in expanded_tag_ids if profile.get(tid, 0.0) > 0]
                reason = _determine_normal_reason(
                    expanded_tag_ids,
                    matching_tag_ids,
                    profile,
                    direct_contrib,
                    related_contrib,
                    interest_contrib,
                    history,
                    tag_names_by_id,
                )
                candidate = SuggestionCandidate(
                    source=GiftSuggestion.Source.CATALOGUE,
                    score=float(tag_score),
                    gift=gift,
                    name=gift.name,
                    description=gift.comment or "",
                    reason=reason,
                    tag_ids=direct_tag_ids,
                    suggestion=None,
                )
                sort_key = (-tag_score, -(pop or 0.0), gift.name.casefold())
                scored_candidates.append((sort_key, candidate))
            else:
                if pop is None or pop < 4:
                    continue

                reason = SuggestionReason(
                    code="popular",
                    tag_names=(),
                    rating=round(pop, 1),
                )
                candidate = SuggestionCandidate(
                    source=GiftSuggestion.Source.CATALOGUE,
                    score=float(pop),
                    gift=gift,
                    name=gift.name,
                    description=gift.comment or "",
                    reason=reason,
                    tag_ids=direct_tag_ids,
                    suggestion=None,
                )
                sort_key = (-pop, gift.name.casefold())
                scored_candidates.append((sort_key, candidate))

        scored_candidates.sort(key=lambda item: item[0])
        return [c for _, c in scored_candidates[:limit]]
