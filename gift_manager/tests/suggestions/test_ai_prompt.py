"""Tests for anonymised AI prompt generation and schema."""

import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.suggestions.ai.prompt import IDEAS_SCHEMA
from gift_manager.suggestions.ai.prompt import PROMPT_VERSION
from gift_manager.suggestions.ai.prompt import build_ai_payload
from gift_manager.suggestions.ai.prompt import derive_age_bracket
from gift_manager.suggestions.ai.prompt import format_relative_recency
from gift_manager.suggestions.ai.prompt import scrub_text
from gift_manager.suggestions.ai.prompt import window_person_notes
from gift_manager.suggestions.history import HistoryItem
from gift_manager.suggestions.history import PreferenceProfile
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
    terms = ["A", " ", "", "du", "Bob"]
    result = scrub_text("A big apple for du and Bob", terms)
    # 'A' and 'du' (< 3 chars) are ignored; 'Bob' (>= 3 chars) is scrubbed
    assert result == "A big apple for du and [name]"


@pytest.mark.django_db
def test_payload_contains_no_names_emails_or_ids(user):
    person = Person.objects.create(
        pk=9876,
        first_name="Marguerite",
        family_name="Dupont",
    )
    person.set_email("marguerite@example.com")
    person.save()
    group = PersonGroup.objects.create(pk=8765, name="Famille Dupont")
    user.first_name = "Adrien"
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
        count=15,
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
    assert payload["count"] == 15
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


@pytest.mark.django_db
def test_french_stopwords_and_tags_are_not_mutilated(user):
    group = PersonGroup.objects.create(name="Les amis de la fac")
    person = Person.objects.create(first_name="Camille", family_name="Dupont")
    user.username = "papa"
    user.first_name = "Jean"
    user.last_name = "Martin"
    user.save()

    tag1 = GiftTag.objects.create(name="Jeux de société")
    tag2 = GiftTag.objects.create(name="Coffret de thé")

    item = HistoryItem(
        relation_id=1,
        gift_id=10,
        gift_name="Bracelet en or rose",
        tag_ids=frozenset([tag1.pk]),
        status_slug="given",
        rating=5,
        note="Offert par Jean Martin, Camille a adoré",
        comment="",
        is_direct=True,
        person_id=person.pk,
        group_id=group.pk,
        created=datetime.now(timezone.utc),
    )
    history = RecipientHistory(
        recipient=person,
        items=(item,),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset([tag2.pk]),
        ancestors={tag1.pk: frozenset([tag1.pk]), tag2.pk: frozenset([tag2.pk])},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=["Jeux de société", "Coffret de thé", "Matériel de jardinage"],
        avoid_names=["Bracelet en or rose", "Collier pour Camille"],
        count=2,
        language="fr",
    )

    # Tag names MUST NOT be corrupted by scrubbing
    assert "Jeux de société" in payload["available_tags"]
    assert "Coffret de thé" in payload["available_tags"]
    assert "Matériel de jardinage" in payload["available_tags"]
    assert "[name]" not in " ".join(payload["available_tags"])
    assert payload["interests"] == ["Coffret de thé"]
    assert payload["history"][0]["tags"] == ["Jeux de société"]

    # Gift name "Bracelet en or rose" must not have French stopwords or common nouns scrubbed
    assert payload["history"][0]["gift"] == "Bracelet en or rose"
    assert "Bracelet en or rose" in payload["avoid"]

    # But personal first names in avoid and notes must be scrubbed
    assert "Collier pour [name]" in payload["avoid"]
    assert "Jean Martin" not in payload["history"][0]["note"]
    assert "Camille" not in payload["history"][0]["note"]


@pytest.mark.parametrize(
    ("birth_year", "current_year", "expected"),
    [
        (None, 2026, None),
        (2030, 2026, None),
        (2025, 2026, "0-2"),
        (2024, 2026, "0-2"),
        (2021, 2026, "3-5"),
        (2018, 2026, "6-9"),
        (2015, 2026, "10-12"),
        (2010, 2026, "13-17"),
        (2005, 2026, "18-25"),
        (1995, 2026, "26-39"),
        (1975, 2026, "40-59"),
        (1960, 2026, "60-74"),
        (1940, 2026, "75+"),
    ],
)
def test_derive_age_bracket(birth_year, current_year, expected):
    assert derive_age_bracket(birth_year, current_year=current_year) == expected


def test_format_relative_recency():
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    assert format_relative_recency(now - timedelta(days=5), now=now) == "recently"
    assert format_relative_recency(now - timedelta(days=29), now=now) == "recently"
    assert format_relative_recency(now - timedelta(days=35), now=now) == "1 month ago"
    assert format_relative_recency(now - timedelta(days=95), now=now) == "3 months ago"
    assert format_relative_recency(now - timedelta(days=400), now=now) == "1 year ago"
    assert format_relative_recency(now - timedelta(days=800), now=now) == "2 years ago"


@pytest.mark.django_db
def test_payload_includes_age_bracket_and_notes_opt_in(user):
    person = Person.objects.create(
        first_name="Camille",
        birthday_day=15,
        birthday_month=6,
        birthday_year=datetime.now(timezone.utc).year - 10,
        notes="Allergique aux noix et adore les jeux d'échecs. Offrir à Camille.",
    )
    user.profile.ai_share_person_notes = True
    user.profile.save()

    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
    )

    assert payload["recipient"]["age_bracket"] == "10-12"
    assert "notes" in payload["recipient"]
    # Notes are scrubbed of recipient's first name
    assert "Camille" not in payload["recipient"]["notes"]
    assert "échecs" in payload["recipient"]["notes"]

    # When opt-in is false, notes are omitted
    user.profile.ai_share_person_notes = False
    user.profile.save()

    payload_opt_out = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
    )
    assert "notes" not in payload_opt_out["recipient"]
    assert payload_opt_out["recipient"]["age_bracket"] == "10-12"


@pytest.mark.django_db
def test_payload_includes_event_price_and_budget(user):
    person = Person.objects.create(first_name="Leo")
    user.profile.currency = "USD"
    user.profile.save()

    item1 = HistoryItem(
        relation_id=1,
        gift_id=10,
        gift_name="Lego Star Wars",
        tag_ids=frozenset(),
        status_slug="given",
        rating=5,
        note="",
        comment="",
        is_direct=True,
        person_id=person.pk,
        group_id=None,
        created=datetime.now(timezone.utc),
        event_name="Anniversaire de Leo",
        price=49.99,
    )
    item2 = HistoryItem(
        relation_id=2,
        gift_id=11,
        gift_name="Livre BD",
        tag_ids=frozenset(),
        status_slug="given",
        rating=4,
        note="",
        comment="",
        is_direct=True,
        person_id=person.pk,
        group_id=None,
        created=datetime.now(timezone.utc),
        event_name="Noël",
        price=15.00,
    )

    history = RecipientHistory(
        recipient=person,
        items=(item1, item2),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
    )

    assert payload["history"][0]["event"] == "Anniversaire de [name]"
    assert payload["history"][0]["price"] == 49.99
    assert payload["history"][0]["when"] == "recently"

    assert "budget" in payload
    assert payload["budget"]["currency"] == "USD"
    # Prices sorted: [15.00, 49.99]. Median (index 1) is 50, max is 50.
    assert payload["budget"]["typical"] == 50
    assert payload["budget"]["max"] == 50


@pytest.mark.django_db
def test_payload_includes_rejected_directions(user):
    person = Person.objects.create(first_name="Alice")
    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    rejected = [
        {"name": "Echarpe en laine", "tags": ["Vêtements"]},
        {"name": "Mug humoristique", "tags": []},
    ]

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
        rejected_directions=rejected,
    )

    assert payload["rejected_directions"] == rejected


@pytest.mark.django_db
def test_payload_rejected_directions_scrubs_and_bounds(user):
    person = Person.objects.create(first_name="Alice", family_name="Dupont")
    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    long_name = "Livre " + ("Alice " * 30)
    rejected = [
        # Name contains recipient's name, tags must remain unscrubbed
        {"name": "Portrait d'Alice", "tags": ["Art", "Alice"]},
        # Long name should be scrubbed then capped at 120 chars
        {"name": long_name, "tags": []},
        # Safe handling of tags=None
        {"name": "Mug", "tags": None},
        # Non-dict or empty name should be handled safely
        "invalid",
        {"name": "", "tags": ["Decor"]},
    ]
    # Add 20 more items to test list capping at 15
    rejected.extend({"name": f"Item {i}", "tags": ["Other"]} for i in range(20))

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
        rejected_directions=rejected,
    )

    clean_rejected = payload["rejected_directions"]
    assert len(clean_rejected) == 15
    # First item name scrubbed Alice -> [name], but tag 'Alice' remains intact (controlled vocabulary)
    assert clean_rejected[0]["name"] == "Portrait d'[name]"
    assert clean_rejected[0]["tags"] == ["Art", "Alice"]
    # Long item scrubbed and truncated to <= 120 chars
    assert "[name]" in clean_rejected[1]["name"]
    assert len(clean_rejected[1]["name"]) <= 120
    # tags=None parsed as empty list
    assert clean_rejected[2]["name"] == "Mug"
    assert clean_rejected[2]["tags"] == []


@pytest.mark.django_db
def test_payload_rejected_directions_includes_reason_and_scrubs_comment(user):
    person = Person.objects.create(first_name="Alice", family_name="Dupont")
    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    rejected = [
        {
            "name": "Baptême de parapente",
            "tags": ["Parapente"],
            "reason": "already_owned_or_practiced",
            "comment": "Alice pratique déjà le parapente en solo",
        },
        {
            "name": "Montre de luxe",
            "tags": ["Mode"],
            "reason": "too_expensive",
        },
    ]

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
        rejected_directions=rejected,
    )

    clean_rejected = payload["rejected_directions"]
    assert len(clean_rejected) == 2
    assert clean_rejected[0]["name"] == "Baptême de parapente"
    assert clean_rejected[0]["tags"] == ["Parapente"]
    assert clean_rejected[0]["reason"] == "already_owned_or_practiced"
    # Comment is scrubbed of Alice -> [name]
    assert "Alice" not in clean_rejected[0]["comment"]
    assert clean_rejected[0]["comment"] == "[name] pratique déjà le parapente en solo"

    assert clean_rejected[1]["reason"] == "too_expensive"
    assert "comment" not in clean_rejected[1]


@pytest.mark.django_db
def test_payload_includes_occasion_and_budget_steering(user):
    person = Person.objects.create(first_name="Lucas")
    user.profile.currency = "EUR"
    user.profile.save()

    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    # 1. Under 30 budget
    payload1 = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="en",
        occasion="Birthday",
        budget_selection="under_30",
    )
    assert payload1["occasion"] == "Birthday"
    assert payload1["budget"] == {"currency": "EUR", "max": 30}

    # 2. 30-75 budget
    payload2 = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="en",
        budget_selection="30_75",
    )
    assert payload2["budget"] == {"currency": "EUR", "min": 30, "max": 75}

    # 3. Over 75 budget
    payload3 = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="en",
        budget_selection="over_75",
    )
    assert payload3["budget"] == {"currency": "EUR", "min": 75}

    # Test occasion with personal name is scrubbed
    payload_occ = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="en",
        occasion="Anniversaire de Lucas",
    )
    assert payload_occ["occasion"] == "Anniversaire de [name]"


@pytest.mark.django_db
def test_payload_includes_scrubbed_user_hint(user):
    person = Person.objects.create(first_name="Chloe", family_name="Martin")
    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    hint = "Ideas for Chloe Martin who loves Japanese cooking and ceramic pottery"
    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
        hint=hint,
    )

    assert "user_hint" in payload
    # Chloe Martin must be scrubbed out of hint
    assert "Chloe Martin" not in payload["user_hint"]
    assert "Japanese cooking" in payload["user_hint"]
    assert "ceramic pottery" in payload["user_hint"]

    # Test hint longer than 120 chars is clamped
    long_hint = "A" * 200
    payload_long = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=2,
        language="fr",
        hint=long_hint,
    )
    assert len(payload_long["user_hint"]) == 120


def test_prompt_version_is_4():
    assert PROMPT_VERSION == 4


def test_window_person_notes_preserves_baseline_and_recent_provenance():
    bio = "Marguerite est passionnée par les arts créatifs, la couture et la poterie. " * 7
    old_provenance = [
        f"[2024-0{i + 1}-01 - Suggestion: Ancien cadeau {i}]: Note descriptive ancienne"
        for i in range(8)
    ]
    p1 = "[2025-01-10 - Suggestion: Machine à coudre]: Acheté récemment"
    p2 = "[2025-02-15 - Gift idea: Laine mérinos]: Préfère la laine biologique"
    p3 = "[2025-03-20 - Suggestion: Patron de robe]: A déjà ce modèle"
    raw_notes = f"{bio}\n" + "\n".join(old_provenance) + f"\n{p1}\n{p2}\n{p3}"

    windowed = window_person_notes(raw_notes, terms=["Marguerite"], max_length=800)
    assert len(windowed) <= 800
    assert "[name]" in windowed
    assert "Marguerite" not in windowed
    assert p3 in windowed
    assert "…" in windowed


def test_window_person_notes_scrubs_before_truncation():
    long_prefix = "A" * 390
    name = "Bartholomew"
    notes = f"{long_prefix} {name} has specific tastes in literature."
    windowed = window_person_notes(notes, terms=[name], max_length=400)
    assert name not in windowed
    assert "[name]" in windowed


@pytest.mark.django_db
def test_build_ai_payload_includes_all_time_preferences(user):
    tag_liked = GiftTag.objects.create(name="Manga")
    tag_owned = GiftTag.objects.create(name="Coffee")
    tag_disliked = GiftTag.objects.create(name="Candle")

    person = Person.objects.create(first_name="Leo", family_name="Bernard")
    history = RecipientHistory(
        recipient=person,
        items=(),
        planned_gift_ids=frozenset(),
        interest_tag_ids=frozenset(),
        ancestors={},
    )

    profile = PreferenceProfile(
        liked_tags=((tag_liked.name, 3),),
        owned_tags=((tag_owned.name, 2),),
        disliked_tags=((tag_disliked.name, 1),),
    )

    payload = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=["Manga", "Coffee", "Candle"],
        avoid_names=[],
        count=3,
        language="en",
        preference_profile=profile,
    )

    assert "all_time_preferences" in payload
    prefs = payload["all_time_preferences"]
    assert prefs["liked_tags"] == [{"tag": "Manga", "count": 3}]
    assert prefs["owned_or_practiced_tags"] == [{"tag": "Coffee", "count": 2}]
    assert prefs["disliked_tags"] == [{"tag": "Candle", "count": 1}]

    # When profile is empty or None, all_time_preferences is omitted
    payload_empty = build_ai_payload(
        history,
        viewer=user,
        available_tag_names=[],
        avoid_names=[],
        count=3,
        language="en",
        preference_profile=PreferenceProfile(),
    )
    assert "all_time_preferences" not in payload_empty
