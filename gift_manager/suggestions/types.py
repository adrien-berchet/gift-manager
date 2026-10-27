"""Data types and interfaces for gift suggestions."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol

if TYPE_CHECKING:
    from gift_manager.models import Gift
    from gift_manager.models import GiftSuggestion
    from gift_manager.suggestions.history import RecipientHistory


@dataclass(frozen=True)
class SuggestionReason:
    """Structured explanation for why a suggestion was made."""

    code: str  # "liked_tags", "related_liked_tags", "interests", "popular"
    tag_names: tuple[str, ...] = ()
    rating: float | int | None = None


@dataclass(frozen=True)
class SuggestionCandidate:
    """A ranked candidate suggestion from any provider."""

    source: str  # GiftSuggestion.Source value
    score: float
    gift: "Gift | None"
    name: str
    description: str
    reason: SuggestionReason | str
    tag_ids: frozenset[int]
    suggestion: "GiftSuggestion | None" = None
    reason_text: str = ""


@dataclass(frozen=True)
class SuggestionContext:
    """Context required to score and filter suggestions for a recipient."""

    user: Any
    recipient: Any
    history: "RecipientHistory"
    excluded_gift_ids: frozenset[int] = frozenset()
    blocked_names: frozenset[str] = frozenset()
    occasion: str = ""
    budget: str = ""
    hint: str = ""
    preference_profile: Any = None


class SuggestionStrategy(Protocol):
    """Protocol for suggestion providers (catalogue, AI)."""

    def suggest(self, context: SuggestionContext, limit: int) -> list[SuggestionCandidate]:
        """Return at most *limit* ranked candidates."""
        ...
