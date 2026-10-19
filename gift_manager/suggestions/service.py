"""Gift suggestion service for catalogue recommendations and plan creation."""

import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _

from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftSuggestionGeneration
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_coordination import default_surprise_for
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.suggestions.ai.client import AIError
from gift_manager.suggestions.ai.client import get_ai_client
from gift_manager.suggestions.ai.strategy import AIStrategy
from gift_manager.suggestions.catalogue import CatalogueStrategy
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.suggestions.names import normalize_gift_name
from gift_manager.suggestions.types import SuggestionCandidate
from gift_manager.suggestions.types import SuggestionContext

logger = logging.getLogger(__name__)

CATALOGUE_PAGE_SIZE = 5
CATALOGUE_FIRST_PAGE_WITH_AI = 3
AI_BATCH_SIZE = 2
AI_MAX_VISIBLE = 6

_DEFAULT = object()


@dataclass(frozen=True)
class CataloguePage:
    """A single page of catalogue candidates."""

    candidates: list[SuggestionCandidate]
    next_offset: int | None


@dataclass(frozen=True)
class AIBlock:
    """A block of AI suggestions with status notices."""

    ideas: list[GiftSuggestion]
    notice: str | None
    can_request_more: bool


class GiftSuggestionService:
    """Coordinates suggestion scoring, pagination, and user plan actions."""

    def __init__(self, user, recipient: Person | PersonGroup, *, ai_client=_DEFAULT):
        if ai_client is _DEFAULT:
            ai_client = get_ai_client()
        self.user = user
        self.recipient = recipient
        self.ai_client = ai_client

    @property
    def ai_enabled(self) -> bool:
        """Return whether an AI ideas provider is active."""
        return self.ai_client is not None

    def _recipient_filter(self) -> dict[str, Person | PersonGroup]:
        if isinstance(self.recipient, Person):
            return {"person": self.recipient}
        return {"group": self.recipient}

    def catalogue_page(self, offset: int = 0) -> CataloguePage:
        """Return a page of ranked catalogue suggestions."""
        page_size = (
            CATALOGUE_FIRST_PAGE_WITH_AI
            if (offset == 0 and self.ai_enabled)
            else CATALOGUE_PAGE_SIZE
        )

        history = build_recipient_history(self.user, self.recipient)
        rec_filter = self._recipient_filter()

        user_catalogue_gift_ids = set(
            GiftSuggestion.objects.filter(
                user=self.user,
                source=GiftSuggestion.Source.CATALOGUE,
                state__in=[GiftSuggestion.State.DISMISSED, GiftSuggestion.State.ACCEPTED],
                **rec_filter,
            ).values_list("gift_id", flat=True)
        )
        excluded_gift_ids = frozenset(history.planned_gift_ids | user_catalogue_gift_ids)

        blocked_names = frozenset(
            GiftSuggestion.objects.filter(
                user=self.user,
                state=GiftSuggestion.State.DISMISSED,
                **rec_filter,
            ).values_list("normalized_name", flat=True)
        )

        ctx = SuggestionContext(
            user=self.user,
            recipient=self.recipient,
            history=history,
            excluded_gift_ids=excluded_gift_ids,
            blocked_names=blocked_names,
        )

        candidates = CatalogueStrategy().suggest(ctx, limit=offset + page_size + 1)
        page_candidates = candidates[offset : offset + page_size]
        has_next = len(candidates) > offset + page_size
        next_offset = (offset + page_size) if has_next else None

        return CataloguePage(candidates=page_candidates, next_offset=next_offset)

    def _ai_context(self) -> SuggestionContext:
        history = build_recipient_history(self.user, self.recipient)
        rec_filter = self._recipient_filter()

        user_catalogue_gift_ids = set(
            GiftSuggestion.objects.filter(
                user=self.user,
                source=GiftSuggestion.Source.CATALOGUE,
                state__in=[GiftSuggestion.State.DISMISSED, GiftSuggestion.State.ACCEPTED],
                **rec_filter,
            ).values_list("gift_id", flat=True)
        )
        excluded_gift_ids = frozenset(history.planned_gift_ids | user_catalogue_gift_ids)

        accessible_gift_names = set(
            Gift.objects.accessible_by(self.user).values_list("name", flat=True)
        )
        ai_suggestion_names = set(
            GiftSuggestion.objects.filter(
                user=self.user,
                source=GiftSuggestion.Source.AI,
                **rec_filter,
            ).values_list("normalized_name", flat=True)
        )
        dismissed_catalogue_names = set(
            GiftSuggestion.objects.filter(
                user=self.user,
                source=GiftSuggestion.Source.CATALOGUE,
                state=GiftSuggestion.State.DISMISSED,
                **rec_filter,
            ).values_list("normalized_name", flat=True)
        )
        blocked_names = frozenset(
            {normalize_gift_name(name) for name in accessible_gift_names if name}
            | {s for s in ai_suggestion_names if s}
            | {s for s in dismissed_catalogue_names if s}
        )

        return SuggestionContext(
            user=self.user,
            recipient=self.recipient,
            history=history,
            excluded_gift_ids=excluded_gift_ids,
            blocked_names=blocked_names,
        )

    def _get_today_generations_count(self) -> int:
        now = timezone.now()
        today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        return GiftSuggestionGeneration.objects.filter(
            user=self.user, created_at__gte=today_start
        ).count()

    def _get_pending_ai_ideas(self) -> list[GiftSuggestion]:
        rec_filter = self._recipient_filter()
        return list(
            GiftSuggestion.objects.filter(
                user=self.user,
                source=GiftSuggestion.Source.AI,
                state=GiftSuggestion.State.PENDING,
                **rec_filter,
            )
            .prefetch_related("tags")
            .order_by("-generation__created_at", "-score", "pk")[:AI_MAX_VISIBLE]
        )

    def ai_block(self) -> AIBlock:
        """Return the current block of AI suggestions without auto-generating."""
        if not self.ai_enabled:
            return AIBlock(ideas=[], notice=None, can_request_more=False)

        ideas = self._get_pending_ai_ideas()
        today_count = self._get_today_generations_count()
        daily_limit = getattr(settings, "GIFT_SUGGESTIONS_AI_DAILY_LIMIT", 20)

        can_request_more = today_count < daily_limit
        notice = "limit" if today_count >= daily_limit else None

        return AIBlock(ideas=ideas, notice=notice, can_request_more=can_request_more)

    def request_more_ideas(self, count: int = AI_BATCH_SIZE) -> AIBlock:
        """Generate another batch of AI ideas, subject to the daily limit."""
        if not self.ai_enabled:
            return AIBlock(ideas=[], notice=None, can_request_more=False)

        count = max(1, min(count, 5))
        today_count = self._get_today_generations_count()
        daily_limit = getattr(settings, "GIFT_SUGGESTIONS_AI_DAILY_LIMIT", 20)

        if today_count >= daily_limit:
            ideas = self._get_pending_ai_ideas()
            return AIBlock(ideas=ideas, notice="limit", can_request_more=False)

        rec_filter = self._recipient_filter()
        generation = GiftSuggestionGeneration.objects.create(
            user=self.user,
            succeeded=False,
            idea_count=0,
            **rec_filter,
        )

        try:
            strategy = AIStrategy(self.ai_client)
            ctx = self._ai_context()
            candidates = strategy.suggest(ctx, limit=count)
        except AIError:
            logger.warning(
                "AI suggestion generation failed for user %s on recipient %s",
                self.user.pk,
                self.recipient.pk,
            )
            ideas = self._get_pending_ai_ideas()
            return AIBlock(ideas=ideas, notice="unavailable", can_request_more=False)

        with transaction.atomic():
            for cand in candidates:
                sugg = GiftSuggestion.objects.create(
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    state=GiftSuggestion.State.PENDING,
                    name=cand.name,
                    description=cand.description,
                    reason=cand.reason if isinstance(cand.reason, str) else cand.reason_text,
                    normalized_name=normalize_gift_name(cand.name),
                    score=cand.score,
                    generation=generation,
                    **rec_filter,
                )
                if cand.tag_ids:
                    sugg.tags.set(cand.tag_ids)

            generation.succeeded = True
            generation.idea_count = len(candidates)
            generation.save(update_fields=["succeeded", "idea_count"])

        ideas = self._get_pending_ai_ideas()
        new_today_count = today_count + 1
        can_more = new_today_count < daily_limit
        return AIBlock(ideas=ideas, notice=None, can_request_more=can_more)

    def accept_gift(self, gift_uuid: uuid.UUID) -> Relation:
        """Accept a catalogue suggestion and create an Idea plan for the recipient."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        return self._create_idea_plan(gift, record_catalogue_acceptance=True)

    def dismiss_gift(self, gift_uuid: uuid.UUID) -> None:
        """Dismiss a catalogue suggestion so it no longer appears."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        rec_filter = self._recipient_filter()
        GiftSuggestion.objects.update_or_create(
            user=self.user,
            gift=gift,
            source=GiftSuggestion.Source.CATALOGUE,
            **rec_filter,
            defaults={
                "state": GiftSuggestion.State.DISMISSED,
                "name": gift.name,
                "normalized_name": normalize_gift_name(gift.name),
            },
        )

    def dismissed_count(self) -> int:
        """Return count of dismissed suggestions for this recipient."""
        return GiftSuggestion.objects.filter(
            user=self.user,
            state=GiftSuggestion.State.DISMISSED,
            **self._recipient_filter(),
        ).count()

    def dismissed_suggestions(self) -> list[GiftSuggestion]:
        """Return all dismissed suggestions for this recipient."""
        return list(
            GiftSuggestion.objects.filter(
                user=self.user,
                state=GiftSuggestion.State.DISMISSED,
                **self._recipient_filter(),
            )
            .select_related("gift")
            .prefetch_related("tags", "gift__tags")
            .order_by("-updated_at", "-created_at")
        )

    def restore_gift(self, gift_uuid: uuid.UUID) -> None:
        """Restore a dismissed catalogue gift so it becomes eligible for suggestions again."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        rec_filter = self._recipient_filter()
        deleted, _ = GiftSuggestion.objects.filter(
            user=self.user,
            gift=gift,
            source=GiftSuggestion.Source.CATALOGUE,
            state=GiftSuggestion.State.DISMISSED,
            **rec_filter,
        ).delete()
        if not deleted:
            raise Http404(_("Suggestion not found."))

    def restore_suggestion(self, suggestion_uuid: uuid.UUID) -> None:
        """Restore a dismissed AI suggestion so it returns to pending ideas."""
        rec_filter = self._recipient_filter()
        with transaction.atomic():
            try:
                suggestion = GiftSuggestion.objects.select_for_update().get(
                    suggestion_id=suggestion_uuid,
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    state=GiftSuggestion.State.DISMISSED,
                    **rec_filter,
                )
            except GiftSuggestion.DoesNotExist:
                raise Http404(_("Suggestion not found.")) from None

            suggestion.state = GiftSuggestion.State.PENDING
            suggestion.save(update_fields=["state", "updated_at"])

    def purge_gift(self, gift_uuid: uuid.UUID) -> None:
        """Completely purge a catalogue suggestion dismissal record."""
        self.restore_gift(gift_uuid)

    def purge_suggestion(self, suggestion_uuid: uuid.UUID) -> None:
        """Completely purge an AI suggestion record from history so the AI can suggest it again."""
        rec_filter = self._recipient_filter()
        with transaction.atomic():
            try:
                suggestion = GiftSuggestion.objects.select_for_update().get(
                    suggestion_id=suggestion_uuid,
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    state=GiftSuggestion.State.DISMISSED,
                    **rec_filter,
                )
            except GiftSuggestion.DoesNotExist:
                raise Http404(_("Suggestion not found.")) from None

            suggestion.delete()

    def accept_suggestion(self, suggestion_uuid: uuid.UUID) -> Relation:
        """Accept an AI gift idea, create the Gift and Relation plan."""
        rec_filter = self._recipient_filter()
        with transaction.atomic():
            try:
                suggestion = GiftSuggestion.objects.select_for_update().get(
                    suggestion_id=suggestion_uuid,
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    **rec_filter,
                )
            except GiftSuggestion.DoesNotExist:
                raise Http404(_("Suggestion not found.")) from None

            if suggestion.state == GiftSuggestion.State.DISMISSED:
                raise Http404(_("Suggestion not found."))

            if suggestion.state == GiftSuggestion.State.ACCEPTED:
                plan = self._get_existing_plan(suggestion.gift)
                if plan is not None:
                    return plan
                return self._create_idea_plan(suggestion.gift, record_catalogue_acceptance=False)

            gift = Gift.objects.create(
                name=suggestion.name,
                comment=suggestion.description,
            )
            visible_tag_ids = VisibleMetadata(self.user).tag_ids
            sugg_tag_ids = set(suggestion.tags.values_list("pk", flat=True))
            valid_tag_ids = sugg_tag_ids & visible_tag_ids
            if valid_tag_ids:
                gift.tags.set(valid_tag_ids)

            PermissionService.create_or_update_permission(
                self.user, gift, permission_level=PermissionLevel.OWNER, object_attr="gift"
            )

            plan = self._create_idea_plan(gift, record_catalogue_acceptance=False)

            suggestion.state = GiftSuggestion.State.ACCEPTED
            suggestion.gift = gift
            suggestion.save(update_fields=["state", "gift"])

            return plan

    def dismiss_suggestion(self, suggestion_uuid: uuid.UUID) -> None:
        """Dismiss an AI suggestion so it no longer appears."""
        rec_filter = self._recipient_filter()
        with transaction.atomic():
            try:
                suggestion = GiftSuggestion.objects.select_for_update().get(
                    suggestion_id=suggestion_uuid,
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    **rec_filter,
                )
            except GiftSuggestion.DoesNotExist:
                raise Http404(_("Suggestion not found.")) from None

            if suggestion.state != GiftSuggestion.State.DISMISSED:
                suggestion.state = GiftSuggestion.State.DISMISSED
                suggestion.save(update_fields=["state"])

    def _upsert_accepted_suggestion(self, gift: Gift) -> None:
        rec_filter = self._recipient_filter()
        GiftSuggestion.objects.update_or_create(
            user=self.user,
            gift=gift,
            source=GiftSuggestion.Source.CATALOGUE,
            **rec_filter,
            defaults={
                "state": GiftSuggestion.State.ACCEPTED,
                "normalized_name": normalize_gift_name(gift.name),
            },
        )

    def _get_existing_plan(self, gift: Gift | None) -> Relation | None:
        if gift is None:
            return None
        if isinstance(self.recipient, Person):
            existing_plans = Relation.objects.accessible_by(self.user).filter(
                person=self.recipient, gift=gift, group__isnull=True
            )
        else:
            existing_plans = Relation.objects.accessible_by(self.user).filter(
                group=self.recipient, gift=gift, person__isnull=True
            )
        for plan in existing_plans.select_related("status"):
            if not is_abandoned_status(plan.status):
                return plan
        return existing_plans.first()

    def _create_idea_plan(
        self, gift: Gift, *, record_catalogue_acceptance: bool = True
    ) -> Relation:
        with transaction.atomic():
            if isinstance(self.recipient, Person):
                Person.objects.select_for_update().filter(pk=self.recipient.pk).first()
                existing_plans = Relation.objects.accessible_by(self.user).filter(
                    person=self.recipient, gift=gift, group__isnull=True
                )
            else:
                PersonGroup.objects.select_for_update().filter(pk=self.recipient.pk).first()
                existing_plans = Relation.objects.accessible_by(self.user).filter(
                    group=self.recipient, gift=gift, person__isnull=True
                )

            for plan in existing_plans.select_related("status"):
                if not is_abandoned_status(plan.status):
                    if record_catalogue_acceptance:
                        self._upsert_accepted_suggestion(gift)
                    return plan

            create_kwargs = (
                {"person": self.recipient}
                if isinstance(self.recipient, Person)
                else {"group": self.recipient}
            )
            plan = Relation.objects.create(
                gift=gift,
                status_id=RelationStatus.get_default_pk(),
                is_surprise=default_surprise_for(self.recipient, self.user),
                **create_kwargs,
            )
            PermissionService.create_or_update_permission(
                self.user, plan, permission_level=PermissionLevel.OWNER, object_attr="relation"
            )
            if record_catalogue_acceptance:
                self._upsert_accepted_suggestion(gift)
            return plan
