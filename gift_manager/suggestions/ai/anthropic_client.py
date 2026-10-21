"""Anthropic AI client adapter."""

import json
import logging
from typing import Any

from gift_manager.suggestions.ai.client import AICompletionError
from gift_manager.suggestions.ai.client import AIConnectionError
from gift_manager.suggestions.ai.client import AIRateLimitError
from gift_manager.suggestions.ai.client import AIStatusError

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Client adapter for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 15.0,
        effort: str = "low",
        max_tokens: int = 4096,
    ) -> None:
        import anthropic  # noqa: PLC0415

        self._anthropic = anthropic
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)

    def generate(self, *, system: str, payload: dict[str, Any], schema: dict[str, Any]) -> str:
        """Call Anthropic Messages API with structured JSON output."""
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort:
            output_config["effort"] = self.effort

        user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                output_config=output_config,
            )
        except self._anthropic.RateLimitError as e:
            status = getattr(e, "status_code", None)
            logger.warning("Anthropic rate limit: status %s", status)
            raise AIRateLimitError(status) from e
        except self._anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            logger.warning("Anthropic API error: status %s", status)
            raise AIStatusError(status) from e
        except self._anthropic.APIConnectionError as e:
            logger.warning("Anthropic connection error")
            raise AIConnectionError from e

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason in ("refusal", "max_tokens"):
            raise AICompletionError(str(stop_reason))

        text_parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text" or hasattr(block, "text")
        ]
        return "".join(text_parts)
