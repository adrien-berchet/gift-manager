from django import template

from gift_manager.email_encoding import decode_email as _decode_email
from gift_manager.statuses import relation_status_slug

register = template.Library()


@register.filter
def attr(obj, attr_name):
    return getattr(obj, attr_name)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_attr(obj, attr_name):
    return getattr(obj, attr_name, "")


@register.filter
def replace_none(value, replacement="-"):
    return value if value is not None else replacement


@register.filter
def replace_empty(value, replacement="-"):
    return value if value == 0 or value else replacement


@register.filter
def decode_email(value):
    """Decode a base64-encoded email address for display."""
    return _decode_email(value)


_STATUS_BADGE_MAP = {
    "idea": "bg-secondary",
    "planned": "bg-primary",
    "ordered": "bg-primary",
    "purchased": "bg-info text-dark",
    "wrapped": "bg-warning text-dark",
    "abandoned": "bg-dark",
    "abandonne": "bg-dark",
    "given": "bg-success",
    "received": "bg-success",
}

_STATUS_BORDER_MAP = {
    "idea": "border-status-secondary",
    "planned": "border-status-primary",
    "ordered": "border-status-primary",
    "purchased": "border-status-info",
    "wrapped": "border-status-warning",
    "abandoned": "border-status-secondary",
    "abandonne": "border-status-secondary",
    "given": "border-status-success",
    "received": "border-status-success",
}


@register.filter
def status_badge_class(status):
    """Map a RelationStatus to a Bootstrap badge class string."""
    if status is None:
        return "bg-secondary"
    return _STATUS_BADGE_MAP.get(relation_status_slug(status), "bg-secondary")


@register.filter
def status_border_class(status):
    """Map a RelationStatus to a CSS border class for relation cards."""
    if status is None:
        return "border-status-secondary"
    return _STATUS_BORDER_MAP.get(relation_status_slug(status), "border-status-secondary")


@register.filter
def gift_plan_status_class(status):
    """Map a RelationStatus to the shared gift-plan status badge class."""
    return f"gift-plan-status--{relation_status_slug(status)}"
