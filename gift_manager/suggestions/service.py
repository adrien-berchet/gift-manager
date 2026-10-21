"""Gift suggestion service for catalogue recommendations and plan creation."""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _

from gift_manager.metadata_visibility import VisibleMetadata
from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftSuggestionGeneration
from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_coordination import default_surprise_for
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.suggestions.ai.client import get_ai_client
from gift_manager.suggestions.ai.prompt import PROMPT_VERSION
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


def normalize_dismiss_input(reason: str = "", comment: str = "") -> tuple[str, str]:
    """Normalize dismissal reason and comment.

    Infers 'custom' if a note is provided without reason.
    """
    reason = (reason or "").strip()
    comment = (comment or "").strip()[: GiftSuggestion.DISMISS_COMMENT_MAX_LENGTH]
    valid_reasons = set(GiftSuggestion.DismissReason.values)
    if reason and reason not in valid_reasons:
        reason = ""
    if comment and not reason:
        reason = GiftSuggestion.DismissReason.CUSTOM
    elif reason == GiftSuggestion.DismissReason.CUSTOM and not comment:
        reason = ""
    return reason, comment


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

    def _ai_context(
        self,
        occasion: str = "",
        budget: str = "",
        hint: str = "",
    ) -> SuggestionContext:
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

        planned_gift_names = set(
            Gift.objects.filter(pk__in=history.planned_gift_ids).values_list("name", flat=True)
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
            {normalize_gift_name(name) for name in planned_gift_names if name}
            | {s for s in ai_suggestion_names if s}
            | {s for s in dismissed_catalogue_names if s}
        )

        return SuggestionContext(
            user=self.user,
            recipient=self.recipient,
            history=history,
            excluded_gift_ids=excluded_gift_ids,
            blocked_names=blocked_names,
            occasion=occasion,
            budget=budget,
            hint=hint,
        )

    def _get_today_generations_count(self) -> int:
        now = timezone.now()
        today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        timeout = float(getattr(settings, "GIFT_SUGGESTIONS_AI_TIMEOUT", 15.0))
        in_flight_window = now - timedelta(seconds=int(timeout * 2))
        return (
            GiftSuggestionGeneration.objects.filter(
                user=self.user,
                created_at__gte=today_start,
            )
            .filter(Q(succeeded=True) | Q(succeeded=False, created_at__gte=in_flight_window))
            .count()
        )

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

    def request_more_ideas(
        self,
        count: int = AI_BATCH_SIZE,
        occasion: str = "",
        budget: str = "",
        hint: str = "",
    ) -> AIBlock:
        """Generate another batch of AI ideas, subject to the daily limit."""
        if not self.ai_enabled:
            return AIBlock(ideas=[], notice=None, can_request_more=False)

        count = max(1, min(count, 5))
        daily_limit = getattr(settings, "GIFT_SUGGESTIONS_AI_DAILY_LIMIT", 20)

        user_model = get_user_model()
        rec_filter = self._recipient_filter()
        with transaction.atomic():
            user_model.objects.select_for_update().get(pk=self.user.pk)
            today_count = self._get_today_generations_count()
            if today_count >= daily_limit:
                ideas = self._get_pending_ai_ideas()
                return AIBlock(ideas=ideas, notice="limit", can_request_more=False)

            model_name = getattr(self.ai_client, "model", "") if self.ai_client else ""
            generation = GiftSuggestionGeneration.objects.create(
                user=self.user,
                prompt_version=PROMPT_VERSION,
                model=model_name,
                succeeded=False,
                idea_count=0,
                **rec_filter,
            )

        start_time = time.monotonic()
        try:
            strategy = AIStrategy(self.ai_client)
            ctx = self._ai_context(occasion=occasion, budget=budget, hint=hint)
            candidates = strategy.suggest(ctx, limit=count)
            duration_ms = int((time.monotonic() - start_time) * 1000)
        except Exception:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            generation.duration_ms = duration_ms
            generation.save(update_fields=["duration_ms"])
            logger.exception(
                "AI suggestion generation failed for user %s on recipient %s",
                self.user.pk,
                self.recipient.pk,
            )
            ideas = self._get_pending_ai_ideas()
            return AIBlock(ideas=ideas, notice="unavailable", can_request_more=False)

        with transaction.atomic():
            user_model.objects.select_for_update().get(pk=self.user.pk)
            # Re-fetch existing normalized names for this user and recipient to catch any suggestion
            # created, accepted, or dismissed while the AI provider call was in flight.
            existing_blocked = set(
                GiftSuggestion.objects.filter(
                    user=self.user,
                    **rec_filter,
                ).values_list("normalized_name", flat=True)
            )
            existing_blocked.update(
                normalize_gift_name(name)
                for name in Gift.objects.filter(pk__in=ctx.history.planned_gift_ids).values_list(
                    "name", flat=True
                )
                if name
            )

            created_count = 0
            for cand in candidates:
                norm_name = normalize_gift_name(cand.name)
                if not norm_name or norm_name in existing_blocked:
                    continue
                existing_blocked.add(norm_name)

                sugg = GiftSuggestion.objects.create(
                    user=self.user,
                    source=GiftSuggestion.Source.AI,
                    state=GiftSuggestion.State.PENDING,
                    name=cand.name,
                    description=cand.description,
                    reason=cand.reason if isinstance(cand.reason, str) else cand.reason_text,
                    normalized_name=norm_name,
                    score=cand.score,
                    generation=generation,
                    **rec_filter,
                )
                if cand.tag_ids:
                    sugg.tags.set(cand.tag_ids)
                created_count += 1

            generation.succeeded = True
            generation.idea_count = created_count
            generation.duration_ms = duration_ms
            generation.save(update_fields=["succeeded", "idea_count", "duration_ms"])

        ideas = self._get_pending_ai_ideas()
        new_today_count = self._get_today_generations_count()
        can_more = new_today_count < daily_limit
        return AIBlock(ideas=ideas, notice=None, can_request_more=can_more)

    def accept_gift(self, gift_uuid: uuid.UUID) -> Relation:
        """Accept a catalogue suggestion and create an Idea plan for the recipient."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        return self._create_idea_plan(gift, record_catalogue_acceptance=True)

    def dismiss_gift(self, gift_uuid: uuid.UUID, *, reason: str = "", comment: str = "") -> None:
        """Dismiss a catalogue suggestion so it no longer appears."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        reason, comment = normalize_dismiss_input(reason, comment)
        rec_filter = self._recipient_filter()
        suggestion, _ = GiftSuggestion.objects.update_or_create(
            user=self.user,
            gift=gift,
            source=GiftSuggestion.Source.CATALOGUE,
            **rec_filter,
            defaults={
                "state": GiftSuggestion.State.DISMISSED,
                "name": gift.name,
                "normalized_name": normalize_gift_name(gift.name),
                "dismiss_reason": reason,
                "dismiss_comment": comment,
            },
        )
        suggestion.tags.set(gift.tags.all())

    def dismissed_count(self) -> int:
        """Return count of dismissed suggestions for this recipient."""
        accessible_gifts = Gift.objects.accessible_by(self.user)
        return (
            GiftSuggestion.objects.filter(
                user=self.user,
                state=GiftSuggestion.State.DISMISSED,
                **self._recipient_filter(),
            )
            .filter(Q(gift__isnull=True) | Q(gift__in=accessible_gifts))
            .count()
        )

    def dismissed_suggestions(self) -> list[GiftSuggestion]:
        """Return all dismissed suggestions for this recipient."""
        accessible_gifts = Gift.objects.accessible_by(self.user)
        visible_tag_ids = VisibleMetadata(self.user).tag_ids
        visible_gift_tags = Prefetch(
            "gift__tags",
            queryset=GiftTag.objects.filter(pk__in=visible_tag_ids),
        )
        visible_ai_tags = Prefetch(
            "tags",
            queryset=GiftTag.objects.filter(pk__in=visible_tag_ids),
        )
        return list(
            GiftSuggestion.objects.filter(
                user=self.user,
                state=GiftSuggestion.State.DISMISSED,
                **self._recipient_filter(),
            )
            .filter(Q(gift__isnull=True) | Q(gift__in=accessible_gifts))
            .select_related("gift")
            .prefetch_related(visible_ai_tags, visible_gift_tags)
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
            suggestion.dismiss_reason = ""
            suggestion.dismiss_comment = ""
            suggestion.save(
                update_fields=["state", "dismiss_reason", "dismiss_comment", "updated_at"]
            )

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

    def _reconcile_existing_gift(self, name: str) -> Gift | None:
        """Find an existing accessible gift matching the normalized suggestion name."""
        norm_name = normalize_gift_name(name)
        if not norm_name:
            return None

        # Fast path: exact or case-insensitive DB match
        exact = Gift.objects.accessible_by(self.user).filter(name__iexact=name.strip()).first()
        if exact is not None and normalize_gift_name(exact.name) == norm_name:
            return exact

        # Fallback: lightweight scan of (pk, name) tuples avoiding full model loading
        for gift_pk, gift_name in (
            Gift.objects.accessible_by(self.user).values_list("pk", "name").iterator()
        ):
            if normalize_gift_name(gift_name) == norm_name:
                return Gift.objects.get(pk=gift_pk)

        return None

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
                if (
                    suggestion.gift_id
                    and not Gift.objects.accessible_by(self.user)
                    .filter(pk=suggestion.gift_id)
                    .exists()
                ):
                    raise Http404(_("Suggestion not found."))
                plan = self._get_existing_plan(suggestion.gift)
                if plan is not None:
                    return plan
                return self._create_idea_plan(suggestion.gift, record_catalogue_acceptance=False)

            existing_gift = self._reconcile_existing_gift(suggestion.name)
            if existing_gift is not None:
                gift = existing_gift
            else:
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

    def dismiss_suggestion(
        self, suggestion_uuid: uuid.UUID, *, reason: str = "", comment: str = ""
    ) -> None:
        """Dismiss an AI suggestion so it no longer appears."""
        reason, comment = normalize_dismiss_input(reason, comment)
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

            if suggestion.state == GiftSuggestion.State.ACCEPTED:
                raise Http404(_("Suggestion not found."))

            if suggestion.state != GiftSuggestion.State.DISMISSED:
                suggestion.state = GiftSuggestion.State.DISMISSED
            suggestion.dismiss_reason = reason
            suggestion.dismiss_comment = comment
            suggestion.save(
                update_fields=["state", "dismiss_reason", "dismiss_comment", "updated_at"]
            )

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
