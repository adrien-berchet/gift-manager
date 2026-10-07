"""Template context shared by every page."""

from django.conf import settings
from django.contrib.messages import get_messages

# Bootstrap contextual class of an alert, by the toast type of the message
ALERT_CLASSES = {"success": "success", "warning": "warning", "error": "danger", "info": "info"}


def display_messages(request):
    """Expose the flash messages to show, from ``settings.MESSAGES_DISPLAY_LEVEL`` up.

    ``flash_messages`` is a callable: the template engine calls it when the variable is resolved,
    so only the page that uses it (the base page) consumes the queued messages, and an HTMX
    fragment rendered in between does not swallow them. Messages below the level are consumed
    with the others and never shown. Each item holds the text, the toast type (``success``,
    ``error``, ``warning`` or ``info``) and the matching alert class for the no-JavaScript
    fallback.
    """
    minimum = settings.MESSAGES_DISPLAY_LEVEL

    def flash_messages() -> list[dict[str, str]]:
        items = []
        for message in get_messages(request):
            if message.level < minimum:
                continue
            toast_type = message.level_tag if message.level_tag in ALERT_CLASSES else "info"
            items.append(
                {
                    "message": str(message),
                    "type": toast_type,
                    "alert_class": ALERT_CLASSES[toast_type],
                }
            )
        return items

    return {"flash_messages": flash_messages}
