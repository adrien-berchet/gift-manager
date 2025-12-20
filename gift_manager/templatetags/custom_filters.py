from django import template

from gift_manager.email_encoding import decode_email as _decode_email

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
