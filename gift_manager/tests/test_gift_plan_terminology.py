"""Regression tests for the Gift Plan user-facing terminology."""

from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]

USER_FACING_PATHS = (
    SOURCE_ROOT / "gift_manager" / "forms.py",
    SOURCE_ROOT / "gift_manager" / "models.py",
    SOURCE_ROOT / "gift_manager" / "templates" / "gift_manager",
    SOURCE_ROOT / "gift_manager" / "views" / "common.py",
    SOURCE_ROOT / "gift_manager" / "views" / "relation.py",
    SOURCE_ROOT / "gift_manager" / "views" / "search.py",
    SOURCE_ROOT / "gift_manager" / "views" / "bulk_operations.py",
    SOURCE_ROOT / "gift_manager" / "static" / "gift_manager" / "bulk-operations.js",
)

LEGACY_USER_FACING_TERMS = (
    '"Giftings"',
    '"All Giftings"',
    '"View all giftings"',
    '"New Gifting"',
    '"New gifting"',
    '"Upcoming Giftings"',
    '"No upcoming giftings in the next 30 days"',
    '"Giftings by Status"',
    '"No giftings yet"',
    '"Create new gifting"',
    '"Gifting details"',
    '"Gifting status details"',
    '"Giftings with this status"',
    '"No giftings with this status"',
    '"You don\'t have any giftings to share."',
    '"You are about to delete one gifting."',
    '"You are about to delete %(count)s giftings."',
    '"Gifting not found"',
    '"Add Relation"',
    '"Add Relation for"',
    '"Relations for this Event"',
    '"No relations for this event"',
    '"Filter relations"',
    '"Sort relations"',
    '"Add a new relation for this person"',
    '"View relation details"',
    '"Edit relation"',
    '"Delete relation"',
    '"No relations found for this person."',
    '"Manage who can access this relation"',
    '"This relation is not shared with any friend."',
    '"Persons related to this gift"',
    '"No persons related to this gift"',
    '"Offered to"',
    '"Beneficiary:"',
    '"Person" %} / {% trans "Group"',
    '"Either a person or a group must be specified but not both."',
    '{% trans "Relations" %}',
    'object_type = "Relations"',
    'object_type = "Gifting"',
)

EXPECTED_GIFT_PLAN_TERMS = (
    "Gift Plans",
    "New Gift Plan",
    "Create new gift plan",
    "Gift Plan details",
    "Edit gift plan",
    "gift plan",
    "Recipients",
    "Select a recipient",
    "Gift plans target this group directly.",
)


def iter_user_facing_sources():
    for path in USER_FACING_PATHS:
        if path.is_dir():
            yield from sorted(path.rglob("*"))
        else:
            yield path


def test_legacy_relation_and_gifting_terms_are_not_user_facing():
    offenders = []

    for path in iter_user_facing_sources():
        if path.suffix not in {".html", ".py", ".js"}:
            continue

        content = path.read_text(encoding="utf-8")
        found_terms = [term for term in LEGACY_USER_FACING_TERMS if term in content]
        if found_terms:
            offenders.append(f"{path.relative_to(SOURCE_ROOT)}: {', '.join(found_terms)}")

    assert offenders == []


def test_gift_plan_language_is_present_on_primary_surfaces():
    combined_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in iter_user_facing_sources()
        if path.suffix in {".html", ".py", ".js"}
    )

    for term in EXPECTED_GIFT_PLAN_TERMS:
        assert term in combined_source


def test_french_gift_plan_translation_uses_project_language():
    catalog = (SOURCE_ROOT / "locale" / "fr" / "LC_MESSAGES" / "django.po").read_text(
        encoding="utf-8"
    )

    assert "Projet de cadeau" in catalog  # codespell:ignore
    assert "Projets de cadeaux" in catalog  # codespell:ignore
    assert "plan cadeau" not in catalog.lower()
