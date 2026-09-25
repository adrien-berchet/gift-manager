from django import template

from gift_manager.email_encoding import decode_email as _decode_email
from gift_manager.metadata_visibility import VisibleMetadata
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
    "purchased": "bg-info text-dark",
    "abandoned": "bg-dark",
    "given": "bg-success",
}

_STATUS_BORDER_MAP = {
    "idea": "border-status-secondary",
    "planned": "border-status-primary",
    "purchased": "border-status-info",
    "abandoned": "border-status-secondary",
    "given": "border-status-success",
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


RATING_VALUES = (5, 4, 3, 2, 1)


@register.inclusion_tag("gift_manager/includes/rating_input.html")
def rating_input(field):
    """Render a 1-5 star radio input for a bound rating field."""
    current = field.value()
    return {
        "field": field,
        "values": RATING_VALUES,
        "current": str(current) if current not in (None, "") else "",
    }


@register.inclusion_tag("gift_manager/includes/rating_stars.html")
def rating_stars(rating):
    """Render a read-only 1-5 star rating."""
    rating = rating or 0
    return {
        "rating": rating,
        "stars": [(value, value <= rating) for value in reversed(RATING_VALUES)],
    }


@register.filter
def visible_tags(gift, user):
    """Return the tags of a gift that the user is allowed to see."""
    return VisibleMetadata.for_user(user).tags(gift)


@register.filter
def visible_groups(person, user):
    """Return the groups of a person that the user is allowed to see."""
    return VisibleMetadata.for_user(user).groups(person)
