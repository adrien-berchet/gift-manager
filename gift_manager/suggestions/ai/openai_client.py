"""OpenAI AI client adapter."""

import json
import logging
from typing import Any

from gift_manager.suggestions.ai.client import AICompletionError
from gift_manager.suggestions.ai.client import AIConnectionError
from gift_manager.suggestions.ai.client import AIEmptyContentError
from gift_manager.suggestions.ai.client import AINoChoicesError
from gift_manager.suggestions.ai.client import AIRateLimitError
from gift_manager.suggestions.ai.client import AIStatusError

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client adapter for OpenAI models and OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        import openai  # noqa: PLC0415

        self._openai = openai
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or None
        self.timeout = timeout
        self._client = openai.OpenAI(
            api_key=api_key or "unused",
            base_url=self.base_url,
            timeout=timeout,
            max_retries=0,
        )

    def generate(self, *, system: str, payload: dict[str, Any], schema: dict[str, Any]) -> str:
        """Call OpenAI Chat Completions API with structured JSON schema output."""
        user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "gift_ideas",
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
        except self._openai.RateLimitError as e:
            status = getattr(e, "status_code", None)
            logger.warning("OpenAI rate limit: status %s", status)
            raise AIRateLimitError(status) from e
        except self._openai.APIStatusError as e:
            status = getattr(e, "status_code", None)
            logger.warning("OpenAI API error: status %s", status)
            raise AIStatusError(status) from e
        except self._openai.APIConnectionError as e:
            logger.warning("OpenAI connection error")
            raise AIConnectionError from e

        if not getattr(response, "choices", None):
            raise AINoChoicesError

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason != "stop":
            raise AICompletionError(str(finish_reason))

        message = getattr(choice, "message", None)
        if getattr(message, "refusal", None):
            raise AICompletionError(str(message.refusal))

        content = getattr(message, "content", None)
        if content is None:
            raise AIEmptyContentError

        return content
