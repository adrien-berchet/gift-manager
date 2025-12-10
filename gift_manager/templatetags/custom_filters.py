from django import template

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
