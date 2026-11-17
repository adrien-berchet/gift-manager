"""Registry of the public Help topics.

The Help views only render templates listed here, so a URL slug never becomes a template path.
"""

from typing import NamedTuple

from django.utils.translation import gettext_lazy as _


class HelpTopic(NamedTuple):
    """One Help page."""

    slug: str
    title: str
    summary: str
    icon: str
    template: str


def _template(slug: str) -> str:
    return f"gift_manager/help/topics/{slug}.html"


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        slug="how-it-works",
        title=_("How Gift Manager works"),
        summary=_("Gift plans, recipients, gifts, events and statuses, and how they fit together."),
        icon="fas fa-hand-holding-heart",
        template=_template("how-it-works"),
    ),
    HelpTopic(
        slug="wishlist",
        title=_("Wishlist and guest links"),
        summary=_(
            "List what you would like to receive and share it, even with people without an account."
        ),
        icon="fas fa-gift",
        template=_template("wishlist"),
    ),
    HelpTopic(
        slug="friends-and-sharing",
        title=_("Friends and sharing"),
        summary=_(
            "Invite friends and plan gifts together by sharing recipients, gifts and gift plans."
        ),
        icon="fas fa-share-alt",
        template=_template("friends-and-sharing"),
    ),
    HelpTopic(
        slug="secret-santa",
        title=_("Secret Santa"),
        summary=_("Draw who gives a gift to whom, with or without an account."),
        icon="fas fa-hat-wizard",
        template=_template("secret-santa"),
    ),
    HelpTopic(
        slug="received-gifts",
        title=_("Received gifts"),
        summary=_("Remember what you received, from whom, and who you still need to thank."),
        icon="fas fa-box-open",
        template=_template("received-gifts"),
    ),
    HelpTopic(
        slug="quick-capture",
        title=_("Quick capture (bookmarklet)"),
        summary=_("Save a product page as a gift or a wish in one click from your browser."),
        icon="fas fa-bookmark",
        template=_template("quick-capture"),
    ),
    HelpTopic(
        slug="reminders",
        title=_("Reminders and calendar feed"),
        summary=_("Get reminder emails before due dates and see your gift plans in your calendar."),
        icon="fas fa-calendar-alt",
        template=_template("reminders"),
    ),
)

_TOPICS_BY_SLUG = {topic.slug: topic for topic in HELP_TOPICS}

# Anchors of the sections on the "how-it-works" page, linked to by the getting-started checklist.
CORE_SECTION_IDS = (
    "gift-plans",
    "recipients",
    "gifts",
    "occasions",
    "statuses",
    "suggestions",
    "typical-workflow",
)


def get_help_topic(slug: str) -> HelpTopic | None:
    """Return the registered topic for ``slug``, or None."""
    return _TOPICS_BY_SLUG.get(slug)
