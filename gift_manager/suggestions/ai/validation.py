"""AI idea validation, sanitization and de-duplication."""

import json
import unicodedata
from dataclasses import dataclass

from gift_manager.suggestions.names import normalize_gift_name

MAX_NAME_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 500
MAX_REASON_LENGTH = 150


@dataclass(frozen=True)
class AIIdea:
    """A validated, de-duplicated AI gift idea."""

    name: str
    normalized_name: str
    description: str
    reason: str
    tag_ids: frozenset[int]


def _clean_text(s: str) -> str:
    """Strip control characters (preserving tab and newline) and outer whitespace."""
    filtered = (
        ch for ch in s if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    return "".join(filtered).strip()


def _validate_raw_item(
    item: object, tags_by_name: dict[str, int]
) -> tuple[str, str, str, str, frozenset[int]] | None:
    if not isinstance(item, dict):
        return None

    raw_name = item.get("name")
    raw_description = item.get("description")
    raw_reason = item.get("reason")
    raw_tags = item.get("tags")

    if (
        not isinstance(raw_name, str)
        or not isinstance(raw_description, str)
        or not isinstance(raw_reason, str)
        or not isinstance(raw_tags, list)
    ):
        return None

    name = _clean_text(raw_name)
    if not name or len(name) > MAX_NAME_LENGTH:
        return None

    reason = _clean_text(raw_reason)
    if not reason:
        return None
    reason = reason[:MAX_REASON_LENGTH]

    description = _clean_text(raw_description)[:MAX_DESCRIPTION_LENGTH]

    normalized = normalize_gift_name(name)
    if not normalized:
        return None

    matched_tag_ids: set[int] = set()
    for tag in raw_tags:
        if isinstance(tag, str):
            cleaned_tag = _clean_text(tag).casefold()
            if cleaned_tag in tags_by_name:
                matched_tag_ids.add(tags_by_name[cleaned_tag])

    return name, normalized, description, reason, frozenset(matched_tag_ids)


def parse_ideas(
    raw: str,
    *,
    tags_by_name: dict[str, int],
    blocked_names: frozenset[str],
    limit: int,
) -> list[AIIdea]:
    """Parse, sanitize, validate and de-duplicate AI ideas from JSON response.

    Returns at most `limit` valid ideas in order of appearance.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []

    if not isinstance(data, dict):
        return []

    raw_ideas = data.get("ideas")
    if not isinstance(raw_ideas, list):
        return []

    kept_ideas: list[AIIdea] = []
    seen_normalized: set[str] = set()

    for item in raw_ideas:
        validated = _validate_raw_item(item, tags_by_name)
        if validated is None:
            continue

        name, normalized, description, reason, tag_ids = validated
        if normalized in blocked_names or normalized in seen_normalized:
            continue

        idea = AIIdea(
            name=name,
            normalized_name=normalized,
            description=description,
            reason=reason,
            tag_ids=tag_ids,
        )
        kept_ideas.append(idea)
        seen_normalized.add(normalized)

        if len(kept_ideas) >= limit:
            break

    return kept_ideas
