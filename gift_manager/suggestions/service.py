"""Gift suggestion service for catalogue recommendations and plan creation."""

import uuid
from dataclasses import dataclass

from django.db import transaction
from django.shortcuts import get_object_or_404

from gift_manager.models import Gift
from gift_manager.models import GiftSuggestion
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.plan_coordination import default_surprise_for
from gift_manager.services import PermissionService
from gift_manager.statuses import is_abandoned_status
from gift_manager.suggestions.catalogue import CatalogueStrategy
from gift_manager.suggestions.history import build_recipient_history
from gift_manager.suggestions.names import normalize_gift_name
from gift_manager.suggestions.types import SuggestionCandidate
from gift_manager.suggestions.types import SuggestionContext

CATALOGUE_PAGE_SIZE = 5
CATALOGUE_FIRST_PAGE_WITH_AI = 3

_DEFAULT = object()


@dataclass(frozen=True)
class CataloguePage:
    """A single page of catalogue candidates."""

    candidates: list[SuggestionCandidate]
    next_offset: int | None


class GiftSuggestionService:
    """Coordinates suggestion scoring, pagination, and user plan actions."""

    def __init__(self, user, recipient: Person | PersonGroup, *, ai_client=_DEFAULT):
        if ai_client is _DEFAULT:
            ai_client = None
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

    def accept_gift(self, gift_uuid: uuid.UUID) -> Relation:
        """Accept a catalogue suggestion and create an Idea plan for the recipient."""
        gift = get_object_or_404(Gift.objects.accessible_by(self.user), gift_id=gift_uuid)
        return self._create_idea_plan(gift)

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
                "normalized_name": normalize_gift_name(gift.name),
            },
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

    def _create_idea_plan(self, gift: Gift) -> Relation:
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
            self._upsert_accepted_suggestion(gift)
            return plan
