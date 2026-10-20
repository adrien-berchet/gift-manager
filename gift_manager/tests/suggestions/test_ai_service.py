import datetime

import pytest
from django.http import Http404
from django.test import override_settings
from django.utils import timezone

from gift_manager.models import Gift
from gift_manager.models import GiftPermission
from gift_manager.models import GiftSuggestion
from gift_manager.models import GiftSuggestionGeneration
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.statuses import is_idea_status
from gift_manager.suggestions.ai.client import AICompletionError
from gift_manager.suggestions.service import AIBlock
from gift_manager.suggestions.service import GiftSuggestionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.suggestions.conftest import FakeAIClient

pytestmark = pytest.mark.django_db


def test_ai_block_does_not_auto_generate_and_request_more_ideas_generates(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    canned = {
        "ideas": [
            {
                "name": "Idea 1",
                "description": "Desc 1",
                "reason": "Reason 1",
                "tags": [],
            },
            {
                "name": "Idea 2",
                "description": "Desc 2",
                "reason": "Reason 2",
                "tags": [],
            },
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    # Initial ai_block returns empty block without triggering AI generation
    block1 = service.ai_block()
    assert isinstance(block1, AIBlock)
    assert len(block1.ideas) == 0
    assert block1.notice is None
    assert block1.can_request_more is True
    assert len(client.calls) == 0
    assert GiftSuggestionGeneration.objects.filter(user=user, person=person).count() == 0

    # Explicit request_more_ideas triggers generation
    block2 = service.request_more_ideas(count=2)
    assert len(block2.ideas) == 2
    assert block2.notice is None
    assert block2.can_request_more is True
    assert len(client.calls) == 1

    gen_rows = GiftSuggestionGeneration.objects.filter(user=user, person=person)
    assert gen_rows.count() == 1
    gen = gen_rows.first()
    assert gen.succeeded is True
    assert gen.idea_count == 2

    # Subsequent ai_block() returns the pending ideas without another generation
    block3 = service.ai_block()
    assert len(block3.ideas) == 2
    assert len(client.calls) == 1


def test_request_more_ideas_supports_custom_count_and_clamping(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    canned1 = {"ideas": [{"name": "Single Idea", "description": "D", "reason": "R", "tags": []}]}
    client = FakeAIClient(canned_responses=[canned1])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas(count=1)
    assert len(block.ideas) == 1
    assert len(client.calls) == 1


def test_more_ideas_adds_a_batch_and_keeps_previous(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    batch1 = {
        "ideas": [
            {"name": "Batch 1 Idea 1", "description": "D1", "reason": "R1", "tags": []},
            {"name": "Batch 1 Idea 2", "description": "D2", "reason": "R2", "tags": []},
        ]
    }
    batch2 = {
        "ideas": [
            {"name": "Batch 2 Idea 1", "description": "D3", "reason": "R3", "tags": []},
            {"name": "Batch 2 Idea 2", "description": "D4", "reason": "R4", "tags": []},
        ]
    }
    client = FakeAIClient(canned_responses=[batch1, batch2])
    service = GiftSuggestionService(user, person, ai_client=client)

    block1 = service.request_more_ideas()
    assert len(block1.ideas) == 2

    block2 = service.request_more_ideas()
    assert len(block2.ideas) == 4
    assert len(client.calls) == 2
    # Newest first
    assert [i.name for i in block2.ideas[:2]] == ["Batch 2 Idea 1", "Batch 2 Idea 2"]


def test_ai_ideas_matching_planned_or_dismissed_are_dropped(user, share, status):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # 1. Accessible gift "Atlas" (not planned or dismissed for person -> allowed)
    atlas = GiftFactory(name="Atlas")
    share(user, atlas, level=PermissionLevel.VIEWER)

    # 2. Planned gift "Novel" for this person (must be dropped)
    novel = GiftFactory(name="Novel")
    share(user, novel, level=PermissionLevel.VIEWER)
    plan = RelationFactory(person=person, gift=novel, status=status("Given"))
    share(user, plan, level=PermissionLevel.VIEWER)

    # 3. Dismissed AI idea "Kite" for this person (must be dropped)
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
        name="Kite",
        normalized_name="kite",
    )

    canned = {
        "ideas": [
            {"name": "Atlas", "description": "Book of maps", "reason": "Maps", "tags": []},
            {"name": "novel", "description": "Reading", "reason": "Books", "tags": []},
            {"name": "Kite", "description": "Flying toy", "reason": "Wind", "tags": []},
            {"name": "Telescope", "description": "Stars", "reason": "Astronomy", "tags": []},
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas()
    # "novel" (planned) and "Kite" (dismissed) are dropped; "Atlas" and "Telescope" remain
    names = [idea.name for idea in block.ideas]
    assert names == ["Atlas", "Telescope"]


def test_ai_payload_has_no_identifiers(user, share, status):
    person = PersonFactory(first_name="Marguerite", family_name="Dupont")
    person.set_email("marguerite@example.com")
    person.save()
    share(user, person, level=PermissionLevel.VIEWER)

    gift = GiftFactory(name="Album photo Marguerite")
    share(user, gift, level=PermissionLevel.VIEWER)

    plan = RelationFactory(
        person=person,
        gift=gift,
        status=status("Given"),
        reaction_rating=5,
        reaction_note=f"Marguerite loved it, ask {user.username}",
    )
    share(user, plan, level=PermissionLevel.VIEWER)

    client = FakeAIClient(canned_responses=[{"ideas": []}])
    service = GiftSuggestionService(user, person, ai_client=client)
    service.request_more_ideas()

    assert len(client.calls) == 1
    payload_str = str(client.payload)
    for forbidden in (
        "Marguerite",
        "Dupont",
        "marguerite@example.com",
        user.username,
        str(person.person_id),
        str(gift.gift_id),
        "person_id",
        "gift_id",
        "relation_id",
    ):
        assert forbidden not in payload_str


def test_ai_error_falls_back_with_notice(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    client = FakeAIClient(error=AICompletionError("Provider unavailable"))
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas()
    assert block.notice == "unavailable"
    assert len(block.ideas) == 0
    assert block.can_request_more is False

    failed_gens = GiftSuggestionGeneration.objects.filter(user=user, person=person)
    assert failed_gens.count() == 1
    assert failed_gens.first().succeeded is False

    # Catalogue page is unaffected
    page = service.catalogue_page()
    assert isinstance(page.candidates, list)


def test_daily_limit_blocks_calls(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # Create a generation from yesterday that shouldn't count against today's limit
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old_gen = GiftSuggestionGeneration.objects.create(
        user=user, person=person, succeeded=True, idea_count=2
    )
    GiftSuggestionGeneration.objects.filter(pk=old_gen.pk).update(created_at=yesterday)

    batch = {
        "ideas": [
            {"name": "Idea A", "description": "DA", "reason": "RA", "tags": []},
            {"name": "Idea B", "description": "DB", "reason": "RB", "tags": []},
        ]
    }
    client = FakeAIClient(canned_responses=[batch, batch])

    with override_settings(GIFT_SUGGESTIONS_AI_DAILY_LIMIT=1):
        service = GiftSuggestionService(user, person, ai_client=client)
        block1 = service.request_more_ideas()
        assert len(block1.ideas) == 2
        assert block1.notice is None
        assert len(client.calls) == 1

        block2 = service.request_more_ideas()
        assert block2.notice == "limit"
        assert block2.can_request_more is False
        assert len(client.calls) == 1  # Not called again


def test_ai_disabled_returns_no_block(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    service = GiftSuggestionService(user, person, ai_client=None)
    assert service.ai_enabled is False

    block = service.ai_block()
    assert len(block.ideas) == 0
    assert block.notice is None
    assert block.can_request_more is False

    # Catalogue page first page uses CATALOGUE_PAGE_SIZE = 5 when AI disabled
    tag = GiftTagFactory(name="Tag")
    share(user, tag, level=PermissionLevel.VIEWER)
    person.interests.add(tag)
    gifts = [GiftFactory(name=f"Gift {i}", tags=[tag]) for i in range(7)]
    for g in gifts:
        share(user, g, level=PermissionLevel.VIEWER)

    page = service.catalogue_page(offset=0)
    assert len(page.candidates) == 5


def test_accept_ai_idea_creates_gift_and_idea_plan(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag_shared = GiftTagFactory(name="Books")
    tag_unshared = GiftTagFactory(name="Secret")
    share(user, tag_shared, level=PermissionLevel.VIEWER)
    # tag_unshared is not shared with user

    canned = {
        "ideas": [
            {
                "name": "Sci-Fi Novel",
                "description": "Engaging space adventure",
                "reason": "They like reading",
                "tags": ["Books", "Secret"],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas()
    assert len(block.ideas) == 1
    suggestion = block.ideas[0]

    plan = service.accept_suggestion(suggestion.suggestion_id)
    assert isinstance(plan, Relation)
    assert is_idea_status(plan.status)
    assert plan.person == person

    gift = plan.gift
    assert gift.name == "Sci-Fi Novel"
    assert gift.comment == "Engaging space adventure"
    assert gift.tags.count() == 1
    assert gift.tags.first() == tag_shared
    assert tag_unshared not in gift.tags.all()

    # User has OWNER permission on the gift
    assert GiftPermission.objects.filter(
        gift=gift, user=user, permission_type=PermissionLevel.OWNER
    ).exists()

    # Suggestion row is accepted and links to gift
    suggestion.refresh_from_db()
    assert suggestion.state == GiftSuggestion.State.ACCEPTED
    assert suggestion.gift == gift

    # Accepted suggestion is no longer in pending ideas
    block_after = service.ai_block()
    assert len(block_after.ideas) == 0


def test_accept_ai_idea_reconciles_existing_accessible_gift(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # An existing accessible gift with the same name
    existing_gift = GiftFactory(name="Écharpe en laine", comment="Warm scarf")
    share(user, existing_gift, level=PermissionLevel.VIEWER)

    canned = {
        "ideas": [
            {
                "name": "Echarpe en laine",
                "description": "A very warm winter scarf",
                "reason": "Cold weather",
                "tags": [],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas()
    assert len(block.ideas) == 1
    suggestion = block.ideas[0]

    plan = service.accept_suggestion(suggestion.suggestion_id)
    assert isinstance(plan, Relation)
    assert plan.gift == existing_gift
    # No duplicate Gift row was created
    assert Gift.objects.filter(name__icontains="charpe").count() == 1

    suggestion.refresh_from_db()
    assert suggestion.state == GiftSuggestion.State.ACCEPTED
    assert suggestion.gift == existing_gift


def test_accept_twice_creates_one_plan(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    canned = {
        "ideas": [
            {
                "name": "Board Game",
                "description": "Fun tabletop game",
                "reason": "They enjoy games",
                "tags": [],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas()
    suggestion_id = block.ideas[0].suggestion_id

    plan1 = service.accept_suggestion(suggestion_id)
    plan2 = service.accept_suggestion(suggestion_id)

    assert plan1.pk == plan2.pk
    assert Gift.objects.filter(name="Board Game").count() == 1
    assert Relation.objects.filter(gift=plan1.gift).count() == 1


def test_accept_other_users_suggestion_is_404(user, share):
    other_user = UserFactory()
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)
    share(other_user, person, level=PermissionLevel.VIEWER)

    sugg = GiftSuggestion.objects.create(
        user=other_user,
        person=person,
        source=GiftSuggestion.Source.AI,
        name="Other's Idea",
        normalized_name="other's idea",
        state=GiftSuggestion.State.PENDING,
    )

    service = GiftSuggestionService(user, person)
    with pytest.raises(Http404):
        service.accept_suggestion(sugg.suggestion_id)


def test_accept_dismissed_suggestion_is_404(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    sugg = GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.AI,
        name="Dismissed Idea",
        normalized_name="dismissed idea",
        state=GiftSuggestion.State.DISMISSED,
    )

    service = GiftSuggestionService(user, person)
    with pytest.raises(Http404):
        service.accept_suggestion(sugg.suggestion_id)


def test_dismissed_ai_idea_never_comes_back(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    batch1 = {
        "ideas": [
            {"name": "Kite", "description": "Flying kite", "reason": "Fun outdoors", "tags": []}
        ]
    }
    batch2 = {
        "ideas": [
            {"name": "kite", "description": "Another kite", "reason": "Wind", "tags": []},
            {"name": "Drone", "description": "RC quadcopter", "reason": "Tech", "tags": []},
        ]
    }
    client = FakeAIClient(canned_responses=[batch1, batch2])
    service = GiftSuggestionService(user, person, ai_client=client)

    block1 = service.request_more_ideas()
    assert len(block1.ideas) == 1
    kite_sugg = block1.ideas[0]
    assert kite_sugg.name == "Kite"

    # Dismiss Kite
    service.dismiss_suggestion(kite_sugg.suggestion_id)
    kite_sugg.refresh_from_db()
    assert kite_sugg.state == GiftSuggestion.State.DISMISSED

    # Second batch proposes "kite" again; it should be dropped
    block2 = service.request_more_ideas()
    assert len(block2.ideas) == 1
    assert block2.ideas[0].name == "Drone"


def test_accept_and_dismiss_for_group(user, share):
    group = PersonGroupFactory()
    share(user, group, level=PermissionLevel.VIEWER)

    batch = {
        "ideas": [
            {
                "name": "Group Fondue Set",
                "description": "Cheesy fun",
                "reason": "Group meals",
                "tags": [],
            },
            {"name": "Party Game", "description": "Games", "reason": "Parties", "tags": []},
        ]
    }
    client = FakeAIClient(canned_responses=[batch])
    service = GiftSuggestionService(user, group, ai_client=client)

    block = service.request_more_ideas()
    assert len(block.ideas) == 2
    fondue_sugg = block.ideas[0]
    party_sugg = block.ideas[1]

    # Dismiss one
    service.dismiss_suggestion(party_sugg.suggestion_id)
    party_sugg.refresh_from_db()
    assert party_sugg.state == GiftSuggestion.State.DISMISSED

    # Accept the other
    plan = service.accept_suggestion(fondue_sugg.suggestion_id)
    assert plan.group == group
    assert plan.gift.name == "Group Fondue Set"
    fondue_sugg.refresh_from_db()
    assert fondue_sugg.state == GiftSuggestion.State.ACCEPTED


def test_ai_generation_with_tagged_history_and_interest_tags(user, share):
    """Verify strategy.suggest() handles tagged history + interest tags without AttributeError (B1 fix)."""
    parent_tag = GiftTagFactory(name="Outdoor Sports")
    child_tag = GiftTagFactory(name="Mountain Biking")
    child_tag.parent_tags.add(parent_tag)

    other_user = UserFactory()
    unshared_gift = GiftFactory(name="Unshared Avoid Item")
    share(other_user, unshared_gift)

    person = PersonFactory()
    past_gift = GiftFactory(name="Helmets", tags=[child_tag])
    status_given = RelationFactory(person=person, gift=past_gift, reaction_rating=5)

    for obj in (parent_tag, child_tag, person, past_gift, status_given):
        share(user, obj)
    person.interests.add(child_tag)

    # User also dismissed an unshared gift in the past
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=unshared_gift,
        name=unshared_gift.name,
        normalized_name="unshared avoid item",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
    )

    batch = {
        "ideas": [
            {
                "name": "Bike Gloves",
                "description": "Trail gloves",
                "reason": "For mountain biking",
                "tags": ["Mountain Biking"],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[batch])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas(count=1)
    assert len(block.ideas) == 1
    assert block.ideas[0].name == "Bike Gloves"

    # Verify available_tags was scoped to relevant tags + ancestors
    payload = client.payload
    assert "Mountain Biking" in payload["available_tags"]
    assert "Outdoor Sports" in payload["available_tags"]

    # Verify unshared gift is NOT leaked into avoid list (n1 fix)
    assert "Unshared Avoid Item" not in payload["avoid"]


def test_failed_generation_does_not_consume_daily_quota(user, share):
    """Failed generations (e.g. provider error) do not consume the user's daily limit once cooldown expires."""
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    fail_client = FakeAIClient(error=AICompletionError("Provider error"))
    service = GiftSuggestionService(user, person, ai_client=fail_client)

    with override_settings(GIFT_SUGGESTIONS_AI_DAILY_LIMIT=1):
        block = service.request_more_ideas()
        assert block.notice == "unavailable"

        # The failed generation is recorded for telemetry
        gen = GiftSuggestionGeneration.objects.get(user=user, person=person)
        assert gen.succeeded is False

        # In-flight/recent cooldown counts it immediately
        assert service._get_today_generations_count() == 1

        # Once past the cooldown window, it no longer counts against the daily limit
        gen.created_at = timezone.now() - datetime.timedelta(seconds=60)
        gen.save(update_fields=["created_at"])
        assert service._get_today_generations_count() == 0

        # Now try with a working client - user still has their 1 generation available
        success_batch = {
            "ideas": [{"name": "Valid Idea", "description": "D", "reason": "R", "tags": []}]
        }
        success_client = FakeAIClient(canned_responses=[success_batch])
        service_success = GiftSuggestionService(user, person, ai_client=success_client)

        success_block = service_success.request_more_ideas()
        assert success_block.notice is None
        assert len(success_block.ideas) == 1
        assert service_success._get_today_generations_count() == 1


def test_in_flight_generation_counts_towards_daily_limit(user, share):
    """In-flight generations count against the daily limit to prevent race conditions."""
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    # Simulate an in-flight generation (created just now, not yet succeeded)
    GiftSuggestionGeneration.objects.create(
        user=user,
        person=person,
        succeeded=False,
        idea_count=0,
    )

    success_batch = {
        "ideas": [{"name": "Valid Idea", "description": "D", "reason": "R", "tags": []}]
    }
    client = FakeAIClient(canned_responses=[success_batch])
    service = GiftSuggestionService(user, person, ai_client=client)

    with override_settings(GIFT_SUGGESTIONS_AI_DAILY_LIMIT=1):
        assert service._get_today_generations_count() == 1
        block = service.request_more_ideas()
        assert block.notice == "limit"
        assert block.can_request_more is False


@pytest.mark.django_db(transaction=True)
def test_concurrent_generation_requests_serialize_and_respect_limit(user, share):
    """Multiple concurrent requests serialize via row lock and strictly respect the daily limit."""
    import concurrent.futures

    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    success_batch = {
        "ideas": [{"name": "Valid Idea", "description": "D", "reason": "R", "tags": []}]
    }
    client = FakeAIClient(canned_responses=[success_batch] * 6)

    with override_settings(GIFT_SUGGESTIONS_AI_DAILY_LIMIT=2):

        def worker():
            from django.db import connections

            try:
                svc = GiftSuggestionService(user, person, ai_client=client)
                return svc.request_more_ideas()
            finally:
                connections.close_all()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker) for _ in range(4)]
            results = [f.result() for f in futures]

        succeeded = [r for r in results if r.notice is None]
        limited = [r for r in results if r.notice == "limit"]
        assert len(succeeded) == 2
        assert len(limited) == 2


def test_overlapping_generation_requests_deduplicate_ideas(user, share):
    """If another request or user action saves a gift/suggestion while AI is generating, it is deduplicated."""
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    batch = {
        "ideas": [
            {"name": "Parallel Idea", "description": "D1", "reason": "R1", "tags": []},
            {"name": "Unique Idea", "description": "D2", "reason": "R2", "tags": []},
        ]
    }

    def simulate_concurrent_insertion():
        # This executes while the AI provider call is in flight, so _ai_context() didn't see it!
        GiftSuggestion.objects.create(
            user=user,
            person=person,
            name="Parallel Idea",
            normalized_name="parallel idea",
            source=GiftSuggestion.Source.AI,
            state=GiftSuggestion.State.PENDING,
        )

    client = FakeAIClient(canned_responses=[batch], on_generate=simulate_concurrent_insertion)
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas(count=2)
    # The existing "Parallel Idea" is kept, the duplicate from the AI is skipped, and "Unique Idea" is added
    assert len(block.ideas) == 2
    idea_names = [i.name for i in block.ideas]
    assert idea_names.count("Parallel Idea") == 1
    assert "Unique Idea" in idea_names
    assert (
        GiftSuggestion.objects.filter(
            user=user, person=person, normalized_name="parallel idea"
        ).count()
        == 1
    )


def test_generation_records_telemetry(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    canned = {
        "ideas": [
            {
                "name": "Idea 1",
                "description": "Desc 1",
                "reason": "Reason 1",
                "tags": [],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    client.model = "gpt-4o"
    service = GiftSuggestionService(user, person, ai_client=client)

    service.request_more_ideas(count=1)

    gen = GiftSuggestionGeneration.objects.filter(user=user, person=person).latest("id")
    assert gen.succeeded is True
    assert gen.prompt_version == 2
    assert gen.model == "gpt-4o"
    assert gen.idea_count == 1
    assert gen.duration_ms is not None
    assert gen.duration_ms >= 0


def test_rejected_directions_passed_to_ai_and_blocks_regeneration(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag = GiftTagFactory(name="Cuisine")
    share(user, tag, level=PermissionLevel.VIEWER)
    dismissed = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Tablier de cuisine",
        normalized_name="tablier de cuisine",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )
    dismissed.tags.add(tag)

    canned = {
        "ideas": [
            {
                "name": "Tablier de cuisine",
                "description": "Already dismissed",
                "reason": "Should be dropped",
                "tags": [],
            },
            {
                "name": "Couteau de chef",
                "description": "New suggestion",
                "reason": "Great tool",
                "tags": [],
            },
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    block = service.request_more_ideas(count=2)

    assert client.payload is not None
    rejected = client.payload.get("rejected_directions")
    assert rejected == [{"name": "Tablier de cuisine", "tags": ["Cuisine"]}]

    assert len(block.ideas) == 1
    assert block.ideas[0].name == "Couteau de chef"


def test_rejected_directions_tags_respect_visibility(user, share):
    person = PersonFactory()
    share(user, person, level=PermissionLevel.VIEWER)

    tag_visible = GiftTagFactory(name="VisibleTag")
    tag_unshared = GiftTagFactory(name="UnsharedTag")
    share(user, tag_visible, level=PermissionLevel.VIEWER)

    dismissed = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Tablier",
        normalized_name="tablier",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )
    dismissed.tags.add(tag_visible, tag_unshared)

    canned = {
        "ideas": [
            {
                "name": "Couteau de chef",
                "description": "New suggestion",
                "reason": "Great tool",
                "tags": [],
            },
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    service.request_more_ideas(count=1)

    assert client.payload is not None
    rejected = client.payload.get("rejected_directions")
    assert rejected == [{"name": "Tablier", "tags": ["VisibleTag"]}]


def test_steering_parameters_passed_to_ai_payload(user, share):
    person = PersonFactory(first_name="Maxime")
    share(user, person, level=PermissionLevel.VIEWER)

    canned = {
        "ideas": [
            {
                "name": "Mug isotherme",
                "description": "Pratique pour les voyages",
                "reason": "Compact et utile",
                "tags": [],
            }
        ]
    }
    client = FakeAIClient(canned_responses=[canned])
    service = GiftSuggestionService(user, person, ai_client=client)

    service.request_more_ideas(
        count=1,
        occasion="Secret Santa",
        budget="under_30",
        hint="Needs to be compact for office use",
    )

    assert client.payload is not None
    assert client.payload.get("occasion") == "Secret Santa"
    assert client.payload.get("budget") == {"currency": "EUR", "max": 30}
    assert client.payload.get("user_hint") == "Needs to be compact for office use"
