"""Domain helpers for promoting feedback and gift metadata to recipient person profiles."""

import re
from collections.abc import Iterable
from datetime import date

from django.db import transaction
from django.utils import timezone

from gift_manager.models import GiftTag
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.suggestions.history import tag_ancestor_map


def promotion_target(user, target: object) -> Person | None:
    """Resolve whether *target* is eligible for profile feedback promotion.

    Returns the Person instance if the viewer has at least EDITOR permission on them,
    and target is NOT a surprise plan and NOT a group. Otherwise returns None.
    """
    if isinstance(target, Relation):
        if target.is_surprise or target.group_id is not None or target.person_id is None:
            return None
        person = target.person
    elif isinstance(target, Person):
        person = target
    else:
        return None

    if PermissionService.get_effective_permission(person, user) < PermissionLevel.EDITOR:
        return None

    return person


def append_person_provenance_note(
    person: Person,
    *,
    source_label: str,
    item_name: str,
    text: str,
    today: date | None = None,
) -> bool:
    """Atomically append a provenance note line to Person.notes, preventing duplicates.

    Format: `[YYYY-MM-DD - {source_label}: {cleaned_name}]: {cleaned_text}`.
    Deduplicates on `{source_label}: {cleaned_name}]: {cleaned_text}`.
    Returns True if appended, False if duplicate or invalid.
    """
    cleaned_name = re.sub(r"\s+", " ", str(item_name or "")).strip()[:120]
    cleaned_text = re.sub(r"\s+", " ", str(text or "")).strip()[:200]
    cleaned_label = re.sub(r"\s+", " ", str(source_label or "")).strip()[:50]

    if not cleaned_text:
        return False

    if today is None:
        today = timezone.localdate()

    dup_marker = f"{cleaned_label}: {cleaned_name}]: {cleaned_text}"
    if dup_marker in (person.notes or ""):
        return False

    with transaction.atomic():
        p = Person.objects.select_for_update().get(pk=person.pk)
        if dup_marker in (p.notes or ""):
            return False

        line = f"[{today.isoformat()} - {cleaned_label}: {cleaned_name}]: {cleaned_text}"
        p.notes = f"{p.notes}\n{line}" if (p.notes and p.notes.strip()) else line
        p.save(update_fields=["notes"])
        person.notes = p.notes

    return True


def promote_tags_to_person_interests(
    person: Person,
    tags: Iterable[GiftTag],
    user,
    limit: int = 5,
) -> list[str]:
    """Promote accessible tags to person.interests, skipping existing interests and ancestors.

    Returns the list of added tag names.
    """
    raw_tag_pks = [t.pk for t in tags if t and t.pk]
    if not raw_tag_pks:
        return []

    accessible_tags = list(
        GiftTag.objects.accessible_by(user).filter(pk__in=raw_tag_pks).order_by("name")
    )
    if not accessible_tags:
        return []

    existing_interest_pks = set(person.interests.values_list("pk", flat=True))
    all_known_pks = existing_interest_pks | {t.pk for t in accessible_tags}
    ancestors = tag_ancestor_map(all_known_pks)

    tags_to_add: list[GiftTag] = []
    for tag in accessible_tags:
        if tag.pk in existing_interest_pks:
            continue
        # If tag is an ancestor of an already-present interest, skip it
        if any(
            tag.pk in ancestors.get(eid, frozenset()) and tag.pk != eid
            for eid in existing_interest_pks
        ):
            continue
        tags_to_add.append(tag)
        if len(tags_to_add) >= limit:
            break

    if tags_to_add:
        person.interests.add(*tags_to_add)

    return [t.name for t in tags_to_add]
