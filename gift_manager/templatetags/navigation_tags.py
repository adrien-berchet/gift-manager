from django import template

register = template.Library()

# Exact URL names per section, checked in order.
_SECTION_URL_NAMES = (
    ("home", {"home"}),
    (
        "gift_plans",
        {
            "relations",
            "relation_detail",
            "relation_edit",
            "relation_create",
            "relation_guided_create",
            "relation_advanced_list",
        },
    ),
    (
        "recipients",
        {
            "recipients",
            "persons",
            "person_detail",
            "person_edit",
            "person_create",
            "add_child_groups_to_group",
        },
    ),
    ("gifts", {"gifts", "gift_detail", "gift_edit", "gift_create"}),
    ("more", {"share_objects"}),
)

# URL name fragments per section, checked after the exact names.
_SECTION_URL_FRAGMENTS = (
    ("recipients", ("person_group",)),
    ("more", ("gift_tag", "event", "relation_status")),
)


def navigation_section(url_name):
    """Return the main navigation section a URL name belongs to, or an empty string.

    Sections are ``home``, ``gift_plans``, ``recipients``, ``gifts`` and ``more``
    (the secondary items grouped under the "More" menu).
    """
    if not url_name:
        return ""
    for section, names in _SECTION_URL_NAMES:
        if url_name in names:
            return section
    for section, fragments in _SECTION_URL_FRAGMENTS:
        if any(fragment in url_name for fragment in fragments):
            return section
    return ""


@register.simple_tag
def nav_section(request):
    """Return the navigation section of the current request (see ``navigation_section``)."""
    match = getattr(request, "resolver_match", None)
    return navigation_section(match.url_name if match else None)
