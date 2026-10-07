"""The minimum level of the Django messages shown on pages (``MESSAGES_DISPLAY_LEVEL``)."""

from django.contrib.messages import constants
from django.core.exceptions import ImproperlyConfigured

MESSAGE_LEVELS = {
    "debug": constants.DEBUG,
    "info": constants.INFO,
    "success": constants.SUCCESS,
    "warning": constants.WARNING,
    "error": constants.ERROR,
}


def parse_message_level(name: str) -> int:
    """Return the numeric message level named ``name`` (debug, info, success, warning, error)."""
    try:
        return MESSAGE_LEVELS[name.strip().lower()]
    except KeyError:
        choices = ", ".join(MESSAGE_LEVELS)
        message = f"MESSAGES_DISPLAY_LEVEL must be one of: {choices} (got {name!r})"
        raise ImproperlyConfigured(message) from None
