"""Anonymised prompt building and structured JSON schema for AI suggestions."""

import re
from collections.abc import Iterable
from typing import Any

from django.contrib.auth.models import User

from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.suggestions.history import RecipientHistory

SYSTEM_PROMPT = (
    "Suggest new, concrete gift ideas for the recipient described by the anonymised history. "
    "Favour items matching what was liked, and avoid what was disliked or abandoned. "
    "Never suggest a gift name present in the avoid list. "
    "Use only tag names from the available_tags list. "
    "Write name, description, and reason in the requested language. "
    "Keep reason at most 150 characters."
)

IDEAS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["name", "description", "tags", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}


def scrub_text(text: str, terms: Iterable[str]) -> str:
    """Scrub email addresses and specific names/identifiers from text."""
    if not text:
        return ""

    result = re.sub(r"\S+@\S+\.\S+", "[email]", text)

    valid_terms = sorted(
        {term.strip() for term in terms if term and len(term.strip()) >= 2},
        key=len,
        reverse=True,
    )

    for term in valid_terms:
        pattern = rf"\b{re.escape(term)}\b"
        result = re.sub(pattern, "[name]", result, flags=re.IGNORECASE)

    return result


def _collect_scrub_terms(history: RecipientHistory, viewer: User) -> list[str]:
    terms: list[str] = []

    if isinstance(history.recipient, Person):
        terms.extend(
            [
                history.recipient.first_name,
                history.recipient.family_name or "",
                str(history.recipient),
                history.recipient.email or "",
            ]
        )
    elif isinstance(history.recipient, PersonGroup):
        terms.append(history.recipient.name)
        terms.extend(history.recipient.name.split())

    person_ids = {it.person_id for it in history.items if it.person_id}
    if person_ids:
        for p in Person.objects.filter(pk__in=person_ids):
            terms.extend(
                [
                    p.first_name,
                    p.family_name or "",
                    str(p),
                    p.email or "",
                ]
            )

    group_ids = {it.group_id for it in history.items if it.group_id}
    if group_ids:
        for g in PersonGroup.objects.filter(pk__in=group_ids):
            terms.append(g.name)
            terms.extend(g.name.split())

    if viewer:
        terms.extend(
            [
                getattr(viewer, "username", ""),
                getattr(viewer, "first_name", ""),
                getattr(viewer, "last_name", ""),
                getattr(viewer, "email", ""),
            ]
        )

    return terms


def build_ai_payload(
    history: RecipientHistory,
    *,
    viewer: User,
    available_tag_names: list[str],
    avoid_names: list[str],
    count: int,
    language: str,
) -> dict[str, Any]:
    """Build an anonymised, capped payload dictionary for the AI provider."""
    terms = _collect_scrub_terms(history, viewer)

    all_tag_ids = set(history.interest_tag_ids)
    capped_items = history.items[:50]
    for it in capped_items:
        all_tag_ids.update(it.tag_ids)

    tag_names_by_id = dict(GiftTag.objects.filter(id__in=all_tag_ids).values_list("id", "name"))

    member_labels: dict[Any, str] = {}
    history_payload = []
    for it in capped_items:
        if it.is_direct:
            label = "Recipient"
        elif isinstance(history.recipient, Person):
            label = "Recipient's group"
        elif it.person_id is not None:
            if it.person_id not in member_labels:
                member_labels[it.person_id] = f"Member {len(member_labels) + 1}"
            label = member_labels[it.person_id]
        elif it.group_id is not None:
            subgroup_key = f"g_{it.group_id}"
            if subgroup_key not in member_labels:
                member_labels[subgroup_key] = f"Subgroup {len(member_labels) + 1}"
            label = member_labels[subgroup_key]
        else:
            label = "Member"

        item_tags = [
            scrub_text(tag_names_by_id[tid], terms)
            for tid in sorted(it.tag_ids)
            if tid in tag_names_by_id
        ]

        entry = {
            "recipient": label,
            "gift": scrub_text(it.gift_name, terms),
            "tags": item_tags,
            "status": it.status_slug,
            "rating": it.rating,
        }
        if it.note:
            entry["note"] = scrub_text(it.note[:150], terms)

        history_payload.append(entry)

    interests = [
        scrub_text(tag_names_by_id[tid], terms)
        for tid in sorted(history.interest_tag_ids)
        if tid in tag_names_by_id
    ]

    scrubbed_available = [scrub_text(tag, terms) for tag in available_tag_names]
    available_tags = sorted(scrubbed_available, key=str.casefold)[:200]

    scrubbed_avoid = [scrub_text(name, terms) for name in avoid_names]
    avoid = scrubbed_avoid[:100]

    recipient_type = "person" if isinstance(history.recipient, Person) else "group"

    return {
        "recipient_type": recipient_type,
        "language": language,
        "count": count,
        "history": history_payload,
        "interests": interests,
        "available_tags": available_tags,
        "avoid": avoid,
    }
