"""Common protocol, exceptions, and factory for AI clients."""

import logging
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)


class AIError(Exception):
    """Base exception for AI generation errors."""


class AIRateLimitError(AIError):
    """Rate limit exceeded by provider."""

    def __init__(self, status: int | None = None) -> None:
        super().__init__(f"Rate limit exceeded: status {status}")
        self.status = status


class AIStatusError(AIError):
    """Upstream API returned an error status."""

    def __init__(self, status: int | None = None) -> None:
        super().__init__(f"API status error: status {status}")
        self.status = status


class AIConnectionError(AIError):
    """Connection error or timeout."""

    def __init__(self, message: str = "Connection error") -> None:
        super().__init__(message)


class AICompletionError(AIError):
    """Completion stopped, refused, or invalid."""

    def __init__(self, reason: str = "invalid_completion") -> None:
        super().__init__(f"Completion stopped: {reason}")
        self.reason = reason


class AINoChoicesError(AIError):
    """OpenAI returned no choices."""

    def __init__(self) -> None:
        super().__init__("OpenAI returned no choices")


class AIEmptyContentError(AIError):
    """OpenAI returned empty content."""

    def __init__(self) -> None:
        super().__init__("OpenAI returned empty message content")


class AIClient(Protocol):
    """Protocol implemented by AI completion providers."""

    def generate(self, *, system: str, payload: dict, schema: dict) -> str:
        """Generate structured completion from the provider.

        Args:
            system: The system prompt guiding the generation.
            payload: Anonymised context dictionary sent as user payload.
            schema: JSON schema the output must adhere to.

        Returns:
            The raw JSON string response from the provider.

        Raises:
            AIError: On provider error, refusal, or bad completion.
        """
        ...


def _build_anthropic_client() -> AIClient | None:
    api_key = getattr(settings, "GIFT_SUGGESTIONS_AI_API_KEY", "").strip()
    if not api_key:
        logger.warning("GIFT_SUGGESTIONS_AI_API_KEY is not set for anthropic provider.")
        return None
    model = getattr(settings, "GIFT_SUGGESTIONS_AI_MODEL", "").strip() or "claude-haiku-5-5"
    timeout = float(getattr(settings, "GIFT_SUGGESTIONS_AI_TIMEOUT", 15.0))
    effort = getattr(settings, "GIFT_SUGGESTIONS_AI_EFFORT", "low").strip()
    from gift_manager.suggestions.ai.anthropic_client import AnthropicClient  # noqa: PLC0415

    return AnthropicClient(api_key=api_key, model=model, timeout=timeout, effort=effort)


def _build_openai_client() -> AIClient | None:
    api_key = getattr(settings, "GIFT_SUGGESTIONS_AI_API_KEY", "").strip()
    base_url = getattr(settings, "GIFT_SUGGESTIONS_AI_BASE_URL", "").strip()
    model = getattr(settings, "GIFT_SUGGESTIONS_AI_MODEL", "").strip()
    if not model:
        logger.warning("GIFT_SUGGESTIONS_AI_MODEL is not set for openai provider.")
        return None
    if not api_key and not base_url:
        logger.warning(
            "GIFT_SUGGESTIONS_AI_API_KEY (or GIFT_SUGGESTIONS_AI_BASE_URL) "
            "is required for openai provider."
        )
        return None
    timeout = float(getattr(settings, "GIFT_SUGGESTIONS_AI_TIMEOUT", 15.0))
    from gift_manager.suggestions.ai.openai_client import OpenAIClient  # noqa: PLC0415

    return OpenAIClient(api_key=api_key, model=model, base_url=base_url or None, timeout=timeout)


def get_ai_client() -> AIClient | None:
    """Return configured AI client, or None if disabled or misconfigured."""
    provider = getattr(settings, "GIFT_SUGGESTIONS_AI_PROVIDER", "").strip().lower()
    if not provider:
        return None

    if provider == "anthropic":
        return _build_anthropic_client()

    if provider == "openai":
        return _build_openai_client()

    logger.warning("Unknown GIFT_SUGGESTIONS_AI_PROVIDER: %s", provider)
    return None
