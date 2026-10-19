"""Unit tests for AI idea output validation and de-duplication."""

import json

import pytest

from gift_manager.suggestions.ai.validation import parse_ideas


def test_valid_ideas_are_parsed():
    raw = json.dumps(
        {
            "ideas": [
                {
                    "name": "Livre de cuisine",
                    "description": "Recettes faciles pour tous les jours.",
                    "tags": ["Cuisine", "Livres"],
                    "reason": "A aimé les cours de cuisine l'année dernière.",
                }
            ]
        }
    )
    tags_by_name = {"cuisine": 1, "livres": 2}
    blocked = frozenset()

    ideas = parse_ideas(raw, tags_by_name=tags_by_name, blocked_names=blocked, limit=5)
    assert len(ideas) == 1
    idea = ideas[0]
    assert idea.name == "Livre de cuisine"
    assert idea.normalized_name == "livre de cuisine"
    assert idea.description == "Recettes faciles pour tous les jours."
    assert idea.reason == "A aimé les cours de cuisine l'année dernière."
    assert idea.tag_ids == frozenset([1, 2])


def test_invalid_json_returns_empty():
    assert parse_ideas("not a json", tags_by_name={}, blocked_names=frozenset(), limit=5) == []
    assert parse_ideas("[]", tags_by_name={}, blocked_names=frozenset(), limit=5) == []
    assert (
        parse_ideas('{"no_ideas": []}', tags_by_name={}, blocked_names=frozenset(), limit=5) == []
    )
    assert (
        parse_ideas('{"ideas": "not a list"}', tags_by_name={}, blocked_names=frozenset(), limit=5)
        == []
    )


@pytest.mark.parametrize(
    "bad_item",
    [
        "not a dict",
        123,
        {"name": 123, "description": "d", "tags": [], "reason": "r"},
        {"name": "n", "description": 123, "tags": [], "reason": "r"},
        {"name": "n", "description": "d", "tags": "not a list", "reason": "r"},
        {"name": "n", "description": "d", "tags": []},  # missing reason
        {"name": "n", "description": "d", "tags": [], "reason": 123},
        {"name": "", "description": "d", "tags": [], "reason": "r"},  # empty name
        {"name": "   ", "description": "d", "tags": [], "reason": "r"},
        {"name": "n", "description": "d", "tags": [], "reason": ""},  # empty reason
        {"name": "n", "description": "d", "tags": [], "reason": "   "},
    ],
)
def test_wrong_types_are_dropped(bad_item):
    raw = json.dumps({"ideas": [bad_item]})
    assert parse_ideas(raw, tags_by_name={}, blocked_names=frozenset(), limit=5) == []


def test_overlong_name_dropped_and_long_fields_truncated():
    long_name = "A" * 121
    valid_name = "B" * 120
    long_desc = "D" * 600
    long_reason = "R" * 300

    raw = json.dumps(
        {
            "ideas": [
                {
                    "name": long_name,
                    "description": "d",
                    "tags": [],
                    "reason": "r",
                },
                {
                    "name": valid_name,
                    "description": long_desc,
                    "tags": [],
                    "reason": long_reason,
                },
            ]
        }
    )

    ideas = parse_ideas(raw, tags_by_name={}, blocked_names=frozenset(), limit=5)
    assert len(ideas) == 1
    assert ideas[0].name == valid_name
    assert len(ideas[0].description) == 500
    assert len(ideas[0].reason) == 200


def test_unknown_tags_are_ignored():
    raw = json.dumps(
        {
            "ideas": [
                {
                    "name": "Puzzle",
                    "description": "1000 pieces",
                    "tags": ["Known", "Unknown", 123],
                    "reason": "Likes games",
                }
            ]
        }
    )
    tags_by_name = {"known": 42}
    ideas = parse_ideas(raw, tags_by_name=tags_by_name, blocked_names=frozenset(), limit=5)
    assert len(ideas) == 1
    assert ideas[0].tag_ids == frozenset([42])


def test_blocked_and_duplicate_names_dropped():
    raw = json.dumps(
        {
            "ideas": [
                {
                    "name": "Lego Technic!",
                    "description": "Blocked by normalized existing",
                    "tags": [],
                    "reason": "r1",
                },
                {
                    "name": "Puzzle 3D",
                    "description": "Keep this one",
                    "tags": [],
                    "reason": "r2",
                },
                {
                    "name": "  puzzle 3D! ",
                    "description": "Duplicate of previous",
                    "tags": [],
                    "reason": "r3",
                },
            ]
        }
    )
    # "lego technic" is blocked
    blocked = frozenset(["lego technic"])
    ideas = parse_ideas(raw, tags_by_name={}, blocked_names=blocked, limit=5)
    assert len(ideas) == 1
    assert ideas[0].name == "Puzzle 3D"
    assert ideas[0].normalized_name == "puzzle 3d"


def test_limit_is_applied():
    raw = json.dumps(
        {
            "ideas": [
                {"name": f"Idea {i}", "description": "d", "tags": [], "reason": "r"}
                for i in range(10)
            ]
        }
    )
    ideas = parse_ideas(raw, tags_by_name={}, blocked_names=frozenset(), limit=3)
    assert len(ideas) == 3
    assert [idea.name for idea in ideas] == ["Idea 0", "Idea 1", "Idea 2"]


def test_html_is_kept_as_text():
    raw = json.dumps(
        {
            "ideas": [
                {
                    "name": "<b>Bold gift</b>",
                    "description": "<i>Italic</i> &amp; cool",
                    "tags": [],
                    "reason": "<s>Reason</s>",
                }
            ]
        }
    )
    ideas = parse_ideas(raw, tags_by_name={}, blocked_names=frozenset(), limit=5)
    assert len(ideas) == 1
    assert ideas[0].name == "<b>Bold gift</b>"
    assert ideas[0].description == "<i>Italic</i> &amp; cool"
    assert ideas[0].reason == "<s>Reason</s>"
