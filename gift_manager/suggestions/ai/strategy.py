"""AI idea suggestion strategy using an external LLM client."""

from typing import Any

from django.db.models import Prefetch
from django.db.models import Q
from django.utils.translation import get_language

from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.suggestions.ai.client import AIClient
from gift_manager.suggestions.ai.prompt import IDEAS_SCHEMA
from gift_manager.suggestions.ai.prompt import SYSTEM_PROMPT
from gift_manager.suggestions.ai.prompt import build_ai_payload
from gift_manager.suggestions.ai.validation import parse_ideas
from gift_manager.suggestions.catalogue import CatalogueStrategy
from gift_manager.suggestions.names import normalize_gift_name
from gift_manager.suggestions.types import SuggestionCandidate
from gift_manager.suggestions.types import SuggestionContext

AI_CATALOGUE_AVOID_LIMIT = 3


class AIStrategy:
    """Suggestion strategy that queries an AI provider for new gift ideas."""

    def __init__(self, client: AIClient) -> None:
        self.client = client

    def _recipient_filter(self, recipient: object) -> dict[str, object]:
        if isinstance(recipient, Person):
            return {"person": recipient}
        return {"group": recipient}

    def _build_avoid_names(self, context: SuggestionContext) -> list[str]:
        user = context.user
        recipient = context.recipient
        rec_filter = self._recipient_filter(recipient)

        avoid_dict: dict[str, None] = {}

        # 1. Names of history.planned_gift_ids gifts
        if context.history.planned_gift_ids:
            for name in Gift.objects.filter(pk__in=context.history.planned_gift_ids).values_list(
                "name", flat=True
            ):
                if name:
                    avoid_dict[name] = None

        # 2. AI suggestions for this recipient in pending or accepted state
        for name in GiftSuggestion.objects.filter(
            user=user,
            source=GiftSuggestion.Source.AI,
            state__in=[GiftSuggestion.State.PENDING, GiftSuggestion.State.ACCEPTED],
            **rec_filter,
        ).values_list("name", flat=True):
            if name:
                avoid_dict[name] = None

        # 3. Dismissed catalogue gifts
        accessible_gifts = Gift.objects.accessible_by(user)
        for name in GiftSuggestion.objects.filter(
            user=user,
            source=GiftSuggestion.Source.CATALOGUE,
            state=GiftSuggestion.State.DISMISSED,
            gift__in=accessible_gifts,
            **rec_filter,
        ).values_list("gift__name", flat=True):
            if name:
                avoid_dict[name] = None

        # 4. Current first catalogue page
        catalogue_candidates = CatalogueStrategy().suggest(context, limit=AI_CATALOGUE_AVOID_LIMIT)
        for cand in catalogue_candidates:
            if cand.name:
                avoid_dict[cand.name] = None

        return list(avoid_dict.keys())

    def _build_rejected_directions(
        self, context: SuggestionContext, visible_tag_ids: set[int] | None = None
    ) -> list[dict[str, Any]]:
        user = context.user
        recipient = context.recipient
        rec_filter = self._recipient_filter(recipient)
        accessible_gifts = Gift.objects.accessible_by(user)

        prefetch_tags = (
            Prefetch("tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids))
            if visible_tag_ids is not None
            else "tags"
        )
        prefetch_gift_tags = (
            Prefetch("gift__tags", queryset=GiftTag.objects.filter(pk__in=visible_tag_ids))
            if visible_tag_ids is not None
            else "gift__tags"
        )

        dismissed = (
            GiftSuggestion.objects.filter(
                user=user,
                state=GiftSuggestion.State.DISMISSED,
                **rec_filter,
            )
            .filter(
                Q(source=GiftSuggestion.Source.AI)
                | (
                    Q(source=GiftSuggestion.Source.CATALOGUE, gift__in=accessible_gifts)
                    & ~Q(dismiss_reason="")
                )
            )
            .select_related("gift")
            .prefetch_related(prefetch_tags, prefetch_gift_tags)
            .order_by("-updated_at")[:15]
        )
        results: list[dict[str, Any]] = []
        for s in dismissed:
            name = s.gift.name if s.gift_id and s.gift else s.name
            if not name:
                continue
            tags_qs = s.gift.tags.all() if s.gift_id and s.gift else s.tags.all()
            item: dict[str, Any] = {
                "name": name,
                "tags": [
                    t.name for t in tags_qs if visible_tag_ids is None or t.pk in visible_tag_ids
                ],
            }
            if s.dismiss_reason:
                item["reason"] = s.dismiss_reason
            if s.dismiss_comment:
                item["comment"] = s.dismiss_comment
            results.append(item)
        return results

    def _resolve_blocked_names(self, context: SuggestionContext) -> frozenset[str]:
        if context.blocked_names:
            return context.blocked_names

        avoid_names = self._build_avoid_names(context)
        rejected = self._build_rejected_directions(context)
        all_names = list(avoid_names) + [r["name"] for r in rejected if r.get("name")]
        return frozenset(normalize_gift_name(name) for name in all_names if name)

    def suggest(self, context: SuggestionContext, limit: int) -> list[SuggestionCandidate]:
        """Query AI client for ideas and return ranked SuggestionCandidates."""
        user = context.user
        visible_tag_ids = VisibleMetadata(user).tag_ids

        tags_qs = GiftTag.objects.filter(pk__in=visible_tag_ids).values_list("pk", "name")
        tags_by_name: dict[str, int] = {}
        tags_name_by_pk: dict[int, str] = {}

        for pk, name in tags_qs:
            name_cf = name.casefold()
            if name_cf not in tags_by_name:
                tags_by_name[name_cf] = pk
            tags_name_by_pk[pk] = name

        relevant_tag_ids = set(context.history.interest_tag_ids)
        for it in context.history.items:
            relevant_tag_ids.update(it.tag_ids)

        expanded_tag_ids = set(relevant_tag_ids)
        for tid in relevant_tag_ids:
            expanded_tag_ids.update(context.history.ancestors.get(tid, ()))

        available_tag_names = sorted(
            {tags_name_by_pk[pk] for pk in expanded_tag_ids if pk in tags_name_by_pk},
            key=str.casefold,
        )
        avoid_names = self._build_avoid_names(context)
        rejected_directions = self._build_rejected_directions(
            context, visible_tag_ids=visible_tag_ids
        )
        language = get_language() or "en"

        payload = build_ai_payload(
            context.history,
            viewer=user,
            available_tag_names=available_tag_names,
            avoid_names=avoid_names,
            count=limit,
            language=language,
            rejected_directions=rejected_directions,
            occasion=context.occasion,
            budget_selection=context.budget,
            hint=context.hint,
        )

        raw_json = self.client.generate(system=SYSTEM_PROMPT, payload=payload, schema=IDEAS_SCHEMA)
        blocked_names = self._resolve_blocked_names(context)
        ideas = parse_ideas(
            raw_json, tags_by_name=tags_by_name, blocked_names=blocked_names, limit=limit
        )

        candidates: list[SuggestionCandidate] = []
        for index, idea in enumerate(ideas):
            candidates.append(
                SuggestionCandidate(
                    source=GiftSuggestion.Source.AI,
                    score=float(limit - index),
                    gift=None,
                    name=idea.name,
                    description=idea.description,
                    reason=idea.reason,
                    tag_ids=idea.tag_ids,
                    reason_text=idea.reason,
                )
            )
        return candidates
