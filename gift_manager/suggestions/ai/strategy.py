"""AI idea suggestion strategy using an external LLM client."""

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

        # 2. Every AI suggestion of this user+recipient in any state
        for name in GiftSuggestion.objects.filter(
            user=user, source=GiftSuggestion.Source.AI, **rec_filter
        ).values_list("name", flat=True):
            if name:
                avoid_dict[name] = None

        # 3. Dismissed catalogue gifts
        for name in GiftSuggestion.objects.filter(
            user=user,
            source=GiftSuggestion.Source.CATALOGUE,
            state=GiftSuggestion.State.DISMISSED,
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

    def _resolve_blocked_names(self, context: SuggestionContext) -> frozenset[str]:
        if context.blocked_names:
            return context.blocked_names

        user = context.user
        rec_filter = self._recipient_filter(context.recipient)

        accessible_gift_names = set(Gift.objects.accessible_by(user).values_list("name", flat=True))
        ai_suggestion_names = set(
            GiftSuggestion.objects.filter(
                user=user, source=GiftSuggestion.Source.AI, **rec_filter
            ).values_list("normalized_name", flat=True)
        )
        dismissed_catalogue_names = set(
            GiftSuggestion.objects.filter(
                user=user,
                source=GiftSuggestion.Source.CATALOGUE,
                state=GiftSuggestion.State.DISMISSED,
                **rec_filter,
            ).values_list("normalized_name", flat=True)
        )

        return frozenset(
            {normalize_gift_name(name) for name in accessible_gift_names if name}
            | {s for s in ai_suggestion_names if s}
            | {s for s in dismissed_catalogue_names if s}
        )

    def suggest(self, context: SuggestionContext, limit: int) -> list[SuggestionCandidate]:
        """Query AI client for ideas and return ranked SuggestionCandidates."""
        user = context.user
        visible_tag_ids = VisibleMetadata(user).tag_ids

        tags_qs = GiftTag.objects.filter(pk__in=visible_tag_ids).values_list("pk", "name")
        tags_by_name: dict[str, int] = {}
        available_tag_names_set: set[str] = set()

        for pk, name in tags_qs:
            name_cf = name.casefold()
            if name_cf not in tags_by_name:
                tags_by_name[name_cf] = pk
            available_tag_names_set.add(name)

        available_tag_names = sorted(available_tag_names_set, key=str.casefold)
        avoid_names = self._build_avoid_names(context)
        language = get_language() or "en"

        payload = build_ai_payload(
            context.history,
            viewer=user,
            available_tag_names=available_tag_names,
            avoid_names=avoid_names,
            count=limit,
            language=language,
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
