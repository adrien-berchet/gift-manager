"""Tests for anonymised AI prompt generation and schema."""

import json
from datetime import datetime
from datetime import timezone

import pytest

from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.suggestions.ai.prompt import IDEAS_SCHEMA
from gift_manager.suggestions.ai.prompt import build_ai_payload
from gift_manager.suggestions.ai.prompt import scrub_text
from gift_manager.suggestions.history import HistoryItem
from gift_manager.suggestions.history import RecipientHistory


def test_schema_is_strict_compatible():
    def _check_schema_object(obj):
        if not isinstance(obj, dict):
            return
        if obj.get("type") == "object":
            assert obj.get("additionalProperties") is False
            properties = obj.get("properties", {})
            required = obj.get("required", [])
            assert set(properties.keys()) == set(required)
            for prop in properties.values():
                _check_schema_object(prop)
        elif obj.get("type") == "array":
            _check_schema_object(obj.get("items", {}))

    _check_schema_object(IDEAS_SCHEMA)


def test_scrub_is_case_insensitive_and_word_bounded():
    terms = ["Ann", "Dupont"]
    result = scrub_text("Ann's gift for Dupont and annual event", terms)
    assert result == "[name]'s gift for [name] and annual event"


def test_short_terms_are_ignored():
    terms = ["A", " ", "", "du"]
    result = scrub_text("A big apple for du", terms)
    # 'A' is 1 char so ignored; 'du' is 2 chars so scrubbed
    assert result == "A big apple for [name]"


@pytest.mark.django_db
def test_payload_contains_no_names_emails_or_ids(user):
    person = Person.objects.create(
        first_name="Marguerite",
        family_name="Dupont",
    )
    person.set_email("marguerite@example.com")
    person.save()
    group = PersonGroup.objects.create(name="Famille Dupont")
    user.username = "adrien"
    user.save()

    tag = GiftTag.objects.create(name="Photo")

    item = HistoryItem(
        relation_id=123,
        gift_id=456,
        gift_name="Album photo Marguerite",
        tag_ids=frozenset([tag.pk]),
        status_slug="given",
        rating=5,
        note="Marguerite loved it, ask adrien at marguerite@example.com",
        comment="Famille Dupont photo collection",
        is_direct=True,
        person_id=person.pk,
        group_id=group.pk,
        created=datetime.now(timezone.utc),
    )

    history = RecipientHistory(
        recipient=person,
        items=(item,),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset([tag.pk]),
        ancestors={tag.pk: frozenset([tag.pk])},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=["Photo", "Jeux"],
        avoid_names=["Album photo Marguerite"],
        count=7,
        language="fr",
    )

    dumped = json.dumps(payload)
    for forbidden in [
        "Marguerite",
        "Dupont",
        "marguerite@example.com",
        "adrien",
        "Famille",
        str(person.pk),
        str(group.pk),
        str(person.person_id),
        str(group.group_id),
        "123",
        "456",
        "relation_id",
        "gift_id",
        "person_id",
        "group_id",
    ]:
        assert forbidden not in dumped

    assert "[name]" in dumped
    assert "[email]" in dumped
    assert payload["recipient_type"] == "person"
    assert payload["language"] == "fr"
    assert payload["count"] == 7
    assert len(payload["history"]) == 1
    assert payload["history"][0]["recipient"] == "Recipient"
    assert payload["history"][0]["rating"] == 5


@pytest.mark.django_db
def test_group_payload_labels_members(user):
    group = PersonGroup.objects.create(name="Amis")
    p1 = Person.objects.create(first_name="Alice", family_name="Smith")
    p2 = Person.objects.create(first_name="Bob", family_name="Jones")

    item_direct = HistoryItem(
        relation_id=1,
        gift_id=10,
        gift_name="Group gift",
        tag_ids=frozenset(),
        status_slug="given",
        rating=4,
        note="",
        comment="",
        is_direct=True,
        person_id=None,
        group_id=group.pk,
        created=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    item_m1 = HistoryItem(
        relation_id=2,
        gift_id=11,
        gift_name="Alice gift",
        tag_ids=frozenset(),
        status_slug="given",
        rating=5,
        note="",
        comment="",
        is_direct=False,
        person_id=p1.pk,
        group_id=group.pk,
        created=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    item_m2 = HistoryItem(
        relation_id=3,
        gift_id=12,
        gift_name="Bob gift",
        tag_ids=frozenset(),
        status_slug="given",
        rating=3,
        note="",
        comment="",
        is_direct=False,
        person_id=p2.pk,
        group_id=group.pk,
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    history = RecipientHistory(
        recipient=group,
        items=(item_direct, item_m1, item_m2),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
    )

    assert payload["recipient_type"] == "group"
    recipients = [h["recipient"] for h in payload["history"]]
    assert recipients == ["Recipient", "Member 1", "Member 2"]
    assert "Amis" not in json.dumps(payload)


@pytest.mark.django_db
def test_ratings_and_notes_only_when_visible(user):
    person = Person.objects.create(first_name="Claire", family_name="Martin")
    item = HistoryItem(
        relation_id=1,
        gift_id=2,
        gift_name="Scarf",
        tag_ids=frozenset(),
        status_slug="given",
        rating=None,
        note="",
        comment="Secret plan",
        is_direct=True,
        person_id=person.pk,
        group_id=None,
        created=datetime.now(timezone.utc),
    )
    history = RecipientHistory(
        recipient=person,
        items=(item,),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=1,
        language="fr",
    )

    history_item = payload["history"][0]
    assert history_item["rating"] is None
    assert history_item.get("note", "") == ""


@pytest.mark.django_db
def test_caps_are_applied(user):
    person = Person.objects.create(first_name="David", family_name="Lee")
    now = datetime.now(timezone.utc)
    items = tuple(
        HistoryItem(
            relation_id=i,
            gift_id=100 + i,
            gift_name=f"Gift {i}",
            tag_ids=frozenset(),
            status_slug="given",
            rating=5,
            note="N" * 500,
            comment="C" * 500,
            is_direct=True,
            person_id=person.pk,
            group_id=None,
            created=now,
        )
        for i in range(60)
    )
    history = RecipientHistory(
        recipient=person,
        items=items,
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    tags = [f"Tag {i}" for i in range(250)]
    avoid = [f"Avoid {i}" for i in range(150)]

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=tags,
        avoid_names=avoid,
        count=2,
        language="fr",
    )

    assert len(payload["history"]) == 50
    assert len(payload["history"][0]["note"]) <= 150
    assert "comment" not in payload["history"][0]
    assert len(payload["available_tags"]) == 200
    assert len(payload["avoid"]) == 100
