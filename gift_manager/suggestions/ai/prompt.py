"""Anonymised prompt building and structured JSON schema for AI suggestions."""

import re
from collections.abc import Iterable
from datetime import datetime
from datetime import timezone
from typing import Any

from django.contrib.auth.models import User

from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.suggestions.history import RecipientHistory

PROMPT_VERSION = 2

SYSTEM_PROMPT = (
    "You are an expert gift planner. Suggest new, concrete, appealing gift ideas for the recipient "
    "described in the anonymised JSON payload.\n\n"
    "Guidelines:\n"
    "1. Specificity & Quality: Propose tangible, realistic consumer gift ideas with clear "
    "defining attributes (e.g. 'Cooperative board game for ages 7+', 'Aeropress coffee maker') "
    "rather than vague categories (e.g. 'Board game', 'Book') or impossible/obscure product SKUs.\n"
    "2. Age & Life Stage: Strictly respect the recipient's age bracket and life stage if provided. "
    "Never suggest age-inappropriate items.\n"
    "3. Batch Diversity: When generating ideas, vary the angles across the batch (e.g. "
    "practical/everyday, hobby or passion, experiential or consumable). Do not repeat the same "
    "category or theme across ideas.\n"
    "4. Negative Feedback & Nuance: Respect the avoid list and rejected_directions. When reviewing "
    "past history, pay attention to ratings and reaction notes: a low rating (1-2) with a specific "
    "complaint indicates what to avoid, while an abandoned plan is a weak signal about "
    "logistics or price rather than taste.\n"
    "5. Target Occasion: If 'occasion' is specified (e.g. 'Birthday', 'Christmas', "
    "'Housewarming'), tailor suggestions to fit that event's context, "
    "social expectations, and mood.\n"
    "6. Budget: If budget guidelines are provided (min, max, or typical), ensure suggested ideas "
    "fit comfortably within the requested range.\n"
    "7. Notes & User Guidance: If recipient notes or 'user_hint' are provided, treat them as "
    "high-priority constraints and creative direction (allergies, dislikes, sizes, interests).\n"
    "8. Tags: Assign relevant tags. Prefer matching tag names from available_tags when applicable, "
    "but do not assign irrelevant tags.\n"
    "9. Language & Formatting: Output valid JSON adhering to the schema. Write name, description, "
    "and reason in the requested language. Keep reason concise (at most 150 characters)."
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


AGE_BRACKETS: tuple[tuple[int, str], ...] = (
    (2, "0-2"),
    (5, "3-5"),
    (9, "6-9"),
    (12, "10-12"),
    (17, "13-17"),
    (25, "18-25"),
    (39, "26-39"),
    (59, "40-59"),
    (74, "60-74"),
)


def derive_age_bracket(birthday_year: int | None, current_year: int | None = None) -> str | None:
    """Derive coarse age bracket from birth year for prompt guidance and privacy."""
    if not birthday_year:
        return None
    if current_year is None:
        current_year = datetime.now(timezone.utc).year
    age = current_year - birthday_year
    if age < 0:
        return None
    for max_age, bracket in AGE_BRACKETS:
        if age <= max_age:
            return bracket
    return "75+"


def format_relative_recency(created: datetime, now: datetime | None = None) -> str:
    """Format creation timestamp as coarse relative duration."""
    if now is None:
        now = datetime.now(timezone.utc)
    if created.tzinfo is None and now.tzinfo is not None:
        created = created.replace(tzinfo=timezone.utc)
    elif created.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - created
    days = max(0, delta.days)
    if days < 30:
        return "recently"
    if days < 365:
        months = max(1, days // 30)
        return f"{months} months ago" if months > 1 else "1 month ago"
    years = days // 365
    return f"{years} years ago" if years > 1 else "1 year ago"


def scrub_text(text: str, terms: Iterable[str], min_length: int = 3) -> str:
    """Scrub email addresses and specific names/identifiers from text."""
    if not text:
        return ""

    result = re.sub(r"\S+@\S+\.\S+", "[email]", text)

    valid_terms = sorted(
        {term.strip() for term in terms if term and len(term.strip()) >= min_length},
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
        # Do not split group names into individual tokens to avoid scrubbing common stopwords
        terms.append(history.recipient.name)

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
        terms.extend(PersonGroup.objects.filter(pk__in=group_ids).values_list("name", flat=True))

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


def _build_history_payload(
    capped_items: Iterable[Any],
    tag_names_by_id: dict[int, str],
    recipient: Person | PersonGroup,
    terms: list[str],
) -> list[dict[str, Any]]:
    member_labels: dict[Any, str] = {}
    history_payload = []
    for it in capped_items:
        if it.is_direct:
            label = "Recipient"
        elif isinstance(recipient, Person):
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

        item_tags = [tag_names_by_id[tid] for tid in sorted(it.tag_ids) if tid in tag_names_by_id]
        entry: dict[str, Any] = {
            "recipient": label,
            "gift": scrub_text(it.gift_name, terms, min_length=3),
            "tags": item_tags,
            "status": it.status_slug,
            "rating": it.rating,
            "when": format_relative_recency(it.created),
        }
        if it.note:
            entry["note"] = scrub_text(it.note[:150], terms, min_length=3)
        if it.event_name:
            entry["event"] = scrub_text(it.event_name, terms, min_length=3)
        if it.price is not None and it.price > 0:
            entry["price"] = round(it.price, 2)

        history_payload.append(entry)
    return history_payload


def _build_recipient_info(
    recipient: Person | PersonGroup,
    viewer: User,
    interests: list[str],
    terms: list[str],
) -> dict[str, Any]:
    recipient_type = "person" if isinstance(recipient, Person) else "group"
    recipient_info: dict[str, Any] = {
        "type": recipient_type,
        "interests": interests,
    }
    if isinstance(recipient, Person):
        age_bracket = derive_age_bracket(recipient.birthday_year)
        if age_bracket:
            recipient_info["age_bracket"] = age_bracket
        can_share_notes = getattr(getattr(viewer, "profile", None), "ai_share_person_notes", False)
        if can_share_notes and recipient.notes:
            recipient_info["notes"] = scrub_text(recipient.notes[:500], terms, min_length=3)
    return recipient_info


def _build_budget_info(
    history_items: Iterable[Any],
    viewer: User,
) -> dict[str, Any] | None:
    prices = [it.price for it in history_items if it.price is not None and it.price > 0]
    if not prices:
        return None
    currency = getattr(getattr(viewer, "profile", None), "currency", "EUR") or "EUR"
    sorted_prices = sorted(prices)
    typical = round(sorted_prices[len(sorted_prices) // 2])
    max_p = round(max(prices))
    return {"currency": currency, "typical": typical, "max": max_p}


def resolve_budget_info(
    budget_selection: str | None,
    history_items: Iterable[Any],
    viewer: User,
) -> dict[str, Any] | None:
    """Resolve target budget from explicit steering or retrospective history."""
    currency = getattr(getattr(viewer, "profile", None), "currency", "EUR") or "EUR"
    if budget_selection == "under_30":
        return {"currency": currency, "max": 30}
    if budget_selection == "30_75":
        return {"currency": currency, "min": 30, "max": 75}
    if budget_selection == "over_75":
        return {"currency": currency, "min": 75}
    return _build_budget_info(history_items, viewer)


def _clean_rejected_directions(
    rejected_directions: Iterable[Any] | None,
    terms: list[str],
) -> list[dict[str, Any]]:
    if not rejected_directions:
        return []
    cleaned: list[dict[str, Any]] = []
    for direction in rejected_directions:
        if not isinstance(direction, dict):
            continue
        # Scrub before truncating: a term straddling the cut would no longer
        # match \b...\b and would leak a fragment. Scrubbing can also lengthen
        # the string, so the cap has to come last.
        name = scrub_text(str(direction.get("name") or "").strip(), terms, min_length=3)[:120]
        # Tag names are a controlled vocabulary and must NEVER be scrubbed
        tags = [t for t in (direction.get("tags") or []) if isinstance(t, str)][:10]
        # A direction with no name or one that scrubbed to pure [name] with no tags
        # is meaningless noise to the model.
        if not name or (name == "[name]" and not tags):
            continue
        cleaned.append({"name": name, "tags": tags})
        if len(cleaned) >= 15:
            break
    return cleaned


def build_ai_payload(
    history: RecipientHistory,
    *,
    viewer: User,
    available_tag_names: list[str],
    avoid_names: list[str],
    count: int,
    language: str,
    rejected_directions: list[dict[str, Any]] | None = None,
    occasion: str | None = None,
    budget_selection: str | None = None,
    hint: str | None = None,
) -> dict[str, Any]:
    """Build an anonymised, capped payload dictionary for the AI provider."""
    terms = _collect_scrub_terms(history, viewer)

    all_tag_ids = set(history.interest_tag_ids)
    capped_items = history.items[:50]
    for it in capped_items:
        all_tag_ids.update(it.tag_ids)

    tag_names_by_id = dict(GiftTag.objects.filter(id__in=all_tag_ids).values_list("id", "name"))
    history_payload = _build_history_payload(
        capped_items, tag_names_by_id, history.recipient, terms
    )

    # Tag names are a controlled vocabulary and must NEVER be scrubbed
    interests = [
        tag_names_by_id[tid] for tid in sorted(history.interest_tag_ids) if tid in tag_names_by_id
    ]

    available_tags = sorted(available_tag_names, key=str.casefold)[:200]

    scrubbed_avoid = [scrub_text(name, terms, min_length=3) for name in avoid_names]
    avoid = scrubbed_avoid[:100]

    recipient_info = _build_recipient_info(history.recipient, viewer, interests, terms)
    budget_info = resolve_budget_info(budget_selection, history.items, viewer)

    recipient_type = "person" if isinstance(history.recipient, Person) else "group"
    payload: dict[str, Any] = {
        "recipient_type": recipient_type,
        "recipient": recipient_info,
        "language": language,
        "count": count,
        "history": history_payload,
        "interests": interests,
        "available_tags": available_tags,
        "avoid": avoid,
    }
    if budget_info:
        payload["budget"] = budget_info
    cleaned_rejected = _clean_rejected_directions(rejected_directions, terms)
    if cleaned_rejected:
        payload["rejected_directions"] = cleaned_rejected
    if occasion and occasion.strip():
        cleaned_occ = occasion.strip()[:60]
        scrubbed_occ = scrub_text(cleaned_occ, terms, min_length=3)
        if scrubbed_occ:
            payload["occasion"] = scrubbed_occ
    if hint and hint.strip():
        cleaned_hint = hint.strip()[:120]
        scrubbed_hint = scrub_text(cleaned_hint, terms, min_length=3)
        if scrubbed_hint:
            payload["user_hint"] = scrubbed_hint

    return payload
