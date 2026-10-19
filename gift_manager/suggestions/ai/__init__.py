"""AI gift suggestions adapters and utilities."""

from gift_manager.suggestions.ai.client import AIClient
from gift_manager.suggestions.ai.client import AIError
from gift_manager.suggestions.ai.client import get_ai_client

__all__ = ["AIClient", "AIError", "get_ai_client"]
