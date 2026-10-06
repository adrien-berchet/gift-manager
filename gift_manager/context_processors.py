"""Template context shared by every page."""

from django.conf import settings
from django.contrib.messages import get_messages
from django.utils.functional import SimpleLazyObject


def display_messages(request):
    """Expose the flash messages to show, from ``settings.MESSAGES_DISPLAY_LEVEL`` up.

    The list is lazy: only a template that iterates it (the base page) consumes the queued
    messages, so an HTMX fragment rendered in between does not swallow them. Messages below the
    level are consumed with the others and never shown.
    """
    minimum = settings.MESSAGES_DISPLAY_LEVEL
    return {
        "display_messages": SimpleLazyObject(
            lambda: [message for message in get_messages(request) if message.level >= minimum]
        )
    }
