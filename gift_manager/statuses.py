"""Shared helpers for relation status classification."""

from django.utils.text import slugify

IDEA_STATUS_SLUGS = {"idea", "idee"}
TERMINAL_STATUS_SLUGS = {
    "abandoned",
    "abandonne",
    "completed",
    "done",
    "given",
    "received",
}


def relation_status_slug(status) -> str:
    """Return a stable slug for a relation status, preferring canonical English."""
    if status is None:
        return "unknown"

    for attr_name in ("status_en", "status"):
        value = getattr(status, attr_name, None)
        if value:
            return slugify(str(value)) or "unknown"

    return slugify(str(status)) or "unknown"


def is_idea_status(status) -> bool:
    """Return whether *status* is the open-ended Idea status."""
    return relation_status_slug(status) in IDEA_STATUS_SLUGS


def is_terminal_status(status) -> bool:
    """Return whether *status* represents work that no longer needs action."""
    return relation_status_slug(status) in TERMINAL_STATUS_SLUGS
