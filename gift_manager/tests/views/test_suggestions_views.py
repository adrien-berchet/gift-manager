import uuid

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.suggestions.conftest import FakeAIClient

pytestmark = pytest.mark.django_db


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


def _share(user, obj, level=PermissionLevel.VIEWER):
    create_or_update_permission(user, obj, permission_level=level)


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def client(user):
    c = Client()
    c.force_login(user)
    return c


def test_person_detail_page_renders_placeholder(client, user):
    person = PersonFactory()
    _share(user, person, level=PermissionLevel.VIEWER)

    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    suggestions_url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})

    # Full page
    res_full = client.get(detail_url)
    assert res_full.status_code == 200
    assert "data-gift-suggestions-section" in res_full.content.decode()
    assert suggestions_url in res_full.content.decode()

    # HTMX partial
    res_partial = client.get(detail_url, HTTP_HX_REQUEST="true")
    assert res_partial.status_code == 200
    assert "data-gift-suggestions-section" in res_partial.content.decode()
    assert suggestions_url in res_partial.content.decode()


def test_group_detail_page_renders_placeholder(client, user):
    group = PersonGroupFactory()
    _share(user, group, level=PermissionLevel.VIEWER)

    detail_url = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
    suggestions_url = reverse(
        "gift_manager:person_group_suggestions", kwargs={"pk": group.group_id}
    )

    # Full page
    res_full = client.get(detail_url)
    assert res_full.status_code == 200
    assert "data-gift-suggestions-section" in res_full.content.decode()
    assert suggestions_url in res_full.content.decode()

    # HTMX partial
    res_partial = client.get(detail_url, HTTP_HX_REQUEST="true")
    assert res_partial.status_code == 200
    assert "data-gift-suggestions-section" in res_partial.content.decode()
    assert suggestions_url in res_partial.content.decode()


def test_suggestions_partial_lists_ranked_items_with_reason(client, user):
    tag = GiftTagFactory(name="Books")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gift = GiftFactory(name="Great Novel", tags=[tag])
    _share(user, gift)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    content = res.content.decode()

    assert "data-gift-suggestions" in content
    assert "Great Novel" in content
    assert "From your gifts" in content
    assert "Matches their interests: Books" in content
    assert "data-suggestion-accept" in content
    assert "data-suggestion-dismiss" in content


def test_show_more_returns_next_items_only(client, user):
    tag = GiftTagFactory(name="Tag")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gifts = [GiftFactory(name=f"Gift {i}", tags=[tag]) for i in range(7)]
    for g in gifts:
        _share(user, g)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})

    # Page 1 (offset=0): returns section with 5 items + show more button
    res1 = client.get(url)
    assert res1.status_code == 200
    c1 = res1.content.decode()
    assert "data-gift-suggestions" in c1
    assert "data-suggestion-show-more" in c1

    # Page 2 (offset=5): returns only the items template
    res2 = client.get(url, {"offset": 5})
    assert res2.status_code == 200
    c2 = res2.content.decode()
    # Does NOT include the outer section wrapper
    assert "data-gift-suggestions=" not in c2 and 'data-gift-suggestions"' not in c2
    assert "data-gift-suggestions " not in c2 and "data-gift-suggestions>" not in c2
    # Has 2 items
    assert c2.count('data-suggestion-source="catalogue"') == 2
    # No more next page
    assert "data-suggestion-show-more" not in c2


@pytest.mark.parametrize(
    "level",
    [PermissionLevel.OWNER, PermissionLevel.EDITOR, PermissionLevel.VIEWER],
)
def test_permission_matrix_allows_access(client, user, level):
    person = PersonFactory()
    _share(user, person, level=level)

    tag = GiftTagFactory(name="Tag")
    _share(user, tag)
    person.interests.add(tag)

    gift = GiftFactory(tags=[tag])
    _share(user, gift)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    assert gift.name in res.content.decode()


def test_no_access_recipient_is_404(client, user):
    other_user = UserFactory()
    person = PersonFactory()
    _share(other_user, person, level=PermissionLevel.OWNER)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})
    assert client.get(url).status_code == 404

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    assert client.post(accept_url, {"gift": str(uuid.uuid4())}).status_code == 404

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    assert client.post(dismiss_url, {"gift": str(uuid.uuid4())}).status_code == 404


def test_reason_never_mentions_data_from_unshared_plans(client, user):
    secret_tag = GiftTagFactory(name="Secret Tag")
    _share(user, secret_tag)

    person = PersonFactory()
    _share(user, person)

    other_user = UserFactory()
    other_person = PersonFactory()
    unshared_gift = GiftFactory(tags=[secret_tag])
    unshared_plan = RelationFactory(
        person=other_person, gift=unshared_gift, status=_status("Given"), reaction_rating=5
    )
    _share(other_user, unshared_plan, level=PermissionLevel.OWNER)

    candidate = GiftFactory(tags=[secret_tag])
    _share(user, candidate)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    assert "Secret Tag" not in res.content.decode()


def test_accept_htmx_returns_section_and_list_update_trigger(client, user):
    tag = GiftTagFactory(name="Tag")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gift = GiftFactory(tags=[tag])
    _share(user, gift)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(
        accept_url,
        {"gift": str(gift.gift_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "data-gift-suggestions" in res.content.decode()
    assert "list:update" in res.headers.get("HX-Trigger", "")


def test_accept_full_page_surface_refreshes(client, user):
    tag = GiftTagFactory(name="Tag")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gift = GiftFactory(tags=[tag])
    _share(user, gift)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(
        accept_url,
        {"gift": str(gift.gift_id), "surface": "page"},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code in {200, 204}
    assert res.headers.get("HX-Refresh") == "true"


def test_accept_without_htmx_redirects_to_detail(client, user):
    tag = GiftTagFactory(name="Tag")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gift = GiftFactory(tags=[tag])
    _share(user, gift)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(accept_url, {"gift": str(gift.gift_id)})
    assert res.status_code == 302
    assert res.url == reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})


def test_dismiss_removes_item_from_section(client, user):
    tag = GiftTagFactory(name="Tag")
    _share(user, tag)

    person = PersonFactory()
    person.interests.add(tag)
    _share(user, person)

    gift = GiftFactory(name="Dismissible", tags=[tag])
    _share(user, gift)

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    res = client.post(
        dismiss_url,
        {"gift": str(gift.gift_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "Dismissible" not in res.content.decode()


def test_post_with_malformed_uuid_is_404(client, user):
    person = PersonFactory()
    _share(user, person)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(accept_url, {"gift": "not-a-uuid"})
    assert res.status_code == 404


def test_get_on_accept_is_405(client, user):
    person = PersonFactory()
    _share(user, person)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.get(accept_url)
    assert res.status_code == 405


def test_section_is_translated_in_french(client, user):
    from django.conf import settings
    from django.utils import translation

    try:
        tag = GiftTagFactory(name="Tag")
        _share(user, tag)

        person = PersonFactory()
        person.interests.add(tag)
        _share(user, person)

        gift = GiftFactory(tags=[tag])
        _share(user, gift)

        url = f"/fr/persons/{person.person_id}/suggestions/"
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "Ajouter comme idée" in content
        assert "Parmi vos cadeaux" in content
        assert "Ignorer" in content
    finally:
        translation.activate(settings.LANGUAGE_CODE)


def test_section_includes_ai_placeholder_only_when_enabled(client, user, monkeypatch):
    person = PersonFactory()
    _share(user, person)

    url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})

    # 1. AI disabled -> no AI placeholder
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: None)
    res_disabled = client.get(url)
    assert res_disabled.status_code == 200
    assert "data-gift-suggestions-ai" not in res_disabled.content.decode()

    # 2. AI enabled -> AI placeholder with hx-get and loading
    fake = FakeAIClient()
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)
    res_enabled = client.get(url)
    assert res_enabled.status_code == 200
    content = res_enabled.content.decode()
    assert "data-gift-suggestions-ai" in content
    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    assert f'hx-get="{ideas_url}"' in content
    assert 'hx-trigger="load"' in content
    assert "Loading…" in content or "Chargement" in content


def test_ideas_get_does_not_generate_and_post_generates(client, user, monkeypatch):
    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Canned Idea",
                "description": "A wonderful thought",
                "reason": "Because they like it",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})

    # First GET does not trigger generation; renders empty prompt and generate button
    res1 = client.get(ideas_url)
    assert res1.status_code == 200
    content1 = res1.content.decode()
    assert "data-gift-suggestions-ai" in content1
    assert "Ask for AI suggestions tailored to this recipient." in content1
    assert "Generate ideas" in content1
    assert "data-suggestion-more-ideas" in content1
    assert "data-no-button-loading" in content1
    assert "Generating ideas with AI…" in content1
    assert len(fake.calls) == 0

    # POST triggers generation
    res_post = client.post(ideas_url, data={"count": "1"})
    assert res_post.status_code == 200
    content_post = res_post.content.decode()
    assert "Canned Idea" in content_post
    assert 'data-suggestion-source="ai"' in content_post
    assert "Add ideas" in content_post
    assert len(fake.calls) == 1

    # Second GET renders generated ideas without triggering another call
    res2 = client.get(ideas_url)
    assert res2.status_code == 200
    content2 = res2.content.decode()
    assert "Canned Idea" in content2
    assert len(fake.calls) == 1


def test_ideas_steering_controls_rendered_and_submitted(client, user, monkeypatch):
    import datetime

    today = datetime.date.today()
    bday_date = today + datetime.timedelta(days=20)
    person = PersonFactory(
        birthday_day=bday_date.day,
        birthday_month=bday_date.month,
        birthday_year=2000,
    )
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Santoku Knife",
                "description": "High quality kitchen knife",
                "reason": "Great for cooking",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})

    # GET renders steering controls with Birthday preselected (<= 60 days)
    res_get = client.get(ideas_url)
    assert res_get.status_code == 200
    content_get = res_get.content.decode()
    assert 'name="occasion"' in content_get
    assert 'value="Birthday"' in content_get
    assert "checked" in content_get
    assert 'name="budget"' in content_get
    assert 'value="30_75"' in content_get
    assert 'name="hint"' in content_get

    # POST submits occasion, budget, and hint
    res_post = client.post(
        ideas_url,
        data={
            "count": "1",
            "occasion": "Birthday",
            "budget": "30_75",
            "hint": "loves Japanese cooking",
        },
    )
    assert res_post.status_code == 200
    content_post = res_post.content.decode()
    assert "Santoku Knife" in content_post
    assert 'value="30_75"' in content_post
    assert "loves Japanese cooking" in content_post
    assert len(fake.calls) == 1
    call_payload = fake.calls[0]["payload"]
    assert call_payload["occasion"] == "Birthday"
    assert call_payload["budget"] == {"currency": "EUR", "min": 30, "max": 75}
    assert call_payload["user_hint"] == "loves Japanese cooking"


def test_ideas_steering_invalid_occasion_and_long_hint_handled(client, user, monkeypatch):
    person = PersonFactory(birthday_day=None, birthday_month=None)
    _share(user, person)

    canned = {"ideas": [{"name": "Book", "description": "D", "reason": "R", "tags": []}]}
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})

    # Post with occasion not in upcoming occasions, invalid budget, and hint > 120 chars
    long_hint = "x" * 150
    res = client.post(
        ideas_url,
        data={
            "count": "1",
            "occasion": "Unshared Secret Event",
            "budget": "invalid_budget",
            "hint": long_hint,
        },
    )
    assert res.status_code == 200
    content = res.content.decode()
    assert f'id="ai_budget_{person.pk}_any"' in content
    assert len(fake.calls) == 1
    call_payload = fake.calls[0]["payload"]
    assert "occasion" not in call_payload
    assert "budget" not in call_payload
    assert len(call_payload["user_hint"]) == 120
    assert f'value="{"x" * 120}"' in content


def test_more_ideas_post_adds_batch(client, user, monkeypatch):
    person = PersonFactory()
    _share(user, person)

    batch1 = {"ideas": [{"name": "Idea One", "description": "D1", "reason": "R1", "tags": []}]}
    batch2 = {"ideas": [{"name": "Idea Two", "description": "D2", "reason": "R2", "tags": []}]}
    fake = FakeAIClient(canned_responses=[batch1, batch2])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})

    # Initial POST generates batch 1
    res1 = client.post(ideas_url, data={"count": "1"})
    assert res1.status_code == 200
    assert "Idea One" in res1.content.decode()

    # Second POST generates batch 2
    res2 = client.post(ideas_url, data={"count": "1"})
    assert res2.status_code == 200
    content2 = res2.content.decode()
    assert "Idea One" in content2
    assert "Idea Two" in content2
    assert len(fake.calls) == 2


def test_ai_failure_shows_notice_and_status_200(client, user, monkeypatch):
    from gift_manager.suggestions.ai.client import AICompletionError

    person = PersonFactory()
    _share(user, person)

    fake = FakeAIClient(error=AICompletionError("Provider unreachable"))
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    res = client.post(ideas_url)
    assert res.status_code == 200
    content = res.content.decode()
    assert "data-suggestion-notice" in content
    assert "New ideas are unavailable right now." in content


def test_ai_idea_html_is_escaped(client, user, monkeypatch):
    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "<script>alert('xss')</script>",
                "description": "<b>Safe Bold</b>",
                "reason": "<i>Italic</i>",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    res = client.post(ideas_url)
    assert res.status_code == 200
    content = res.content.decode()
    assert "<script>alert('xss')</script>" not in content
    assert (
        "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in content
        or "&lt;script&gt;alert('xss')&lt;/script&gt;" in content
    )


def test_accept_ai_suggestion_creates_plan(client, user, monkeypatch):
    from gift_manager.models import Gift
    from gift_manager.models import GiftSuggestion
    from gift_manager.statuses import is_idea_status

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Handmade Scarf",
                "description": "Warm winter scarf",
                "reason": "Loves winter clothing",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Handmade Scarf")
    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})

    # Accept via HTMX
    res = client.post(accept_url, {"suggestion": str(sugg.suggestion_id)}, HTTP_HX_REQUEST="true")
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.ACCEPTED
    assert sugg.gift is not None
    assert sugg.gift.name == "Handmade Scarf"

    from gift_manager.models import Relation

    gift = Gift.objects.get(name="Handmade Scarf")
    plan = Relation.objects.filter(gift=gift).first()
    assert plan is not None
    assert plan.person == person
    assert is_idea_status(plan.status)


def test_dismiss_ai_suggestion(client, user, monkeypatch):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Flying Kite",
                "description": "Outdoor toy",
                "reason": "Spring fun",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Flying Kite")
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    res = client.post(dismiss_url, {"suggestion": str(sugg.suggestion_id)}, HTTP_HX_REQUEST="true")
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.DISMISSED


def test_dismiss_with_reason_and_comment(client, user, monkeypatch):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Paragliding Tandem",
                "description": "Flight experience",
                "reason": "Air sport",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Paragliding Tandem")
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    res = client.post(
        dismiss_url,
        {
            "suggestion": str(sugg.suggestion_id),
            "reason": "already_owned_or_practiced",
            "comment": "Already a licensed solo pilot",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.DISMISSED
    assert sugg.dismiss_reason == GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED
    assert sugg.dismiss_comment == "Already a licensed solo pilot"


def test_dismiss_with_invalid_reason_defaults_to_empty(client, user, monkeypatch):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Book",
                "description": "A novel",
                "reason": "Reading",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Book")
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    res = client.post(
        dismiss_url,
        {
            "suggestion": str(sugg.suggestion_id),
            "reason": "completely_invalid_reason",
            "comment": "",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.DISMISSED
    assert sugg.dismiss_reason == ""
    assert sugg.dismiss_comment == ""


def test_dismiss_with_comment_only_infers_custom_reason(client, user, monkeypatch):
    """Pressing Enter in the comment input submits comment with reason='', inferring custom."""
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Board Game",
                "description": "Fun game",
                "reason": "Social",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Board Game")
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    res = client.post(
        dismiss_url,
        {
            "suggestion": str(sugg.suggestion_id),
            "reason": "",
            "comment": "Already plays this with friends",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.DISMISSED
    assert sugg.dismiss_reason == GiftSuggestion.DismissReason.CUSTOM
    assert sugg.dismiss_comment == "Already plays this with friends"


def test_dismiss_with_custom_reason_and_empty_comment_resets_to_empty(client, user, monkeypatch):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    canned = {
        "ideas": [
            {
                "name": "Tea Set",
                "description": "Ceramic set",
                "reason": "Tea lover",
                "tags": [],
            }
        ]
    }
    fake = FakeAIClient(canned_responses=[canned])
    monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

    ideas_url = reverse("gift_manager:person_suggestion_ideas", kwargs={"pk": person.person_id})
    client.post(ideas_url)

    sugg = GiftSuggestion.objects.get(user=user, name="Tea Set")
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    res = client.post(
        dismiss_url,
        {
            "suggestion": str(sugg.suggestion_id),
            "reason": "custom",
            "comment": "   ",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.DISMISSED
    assert sugg.dismiss_reason == ""
    assert sugg.dismiss_comment == ""


def test_post_with_gift_and_suggestion_is_400(client, user):
    person = PersonFactory()
    _share(user, person)

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})

    fake_id = str(uuid.uuid4())

    # Both provided -> 400
    res_both = client.post(accept_url, {"gift": fake_id, "suggestion": fake_id})
    assert res_both.status_code == 400

    # Neither provided -> 400
    res_neither = client.post(accept_url, {})
    assert res_neither.status_code == 400

    # Dismiss both -> 400
    res_both_dismiss = client.post(dismiss_url, {"gift": fake_id, "suggestion": fake_id})
    assert res_both_dismiss.status_code == 400

    # Dismiss neither -> 400
    res_neither_dismiss = client.post(dismiss_url, {})
    assert res_neither_dismiss.status_code == 400


def test_other_users_suggestion_is_404(client, user):
    from gift_manager.models import GiftSuggestion

    other_user = UserFactory()
    person = PersonFactory()
    _share(user, person)
    _share(other_user, person)

    sugg = GiftSuggestion.objects.create(
        user=other_user,
        person=person,
        source=GiftSuggestion.Source.AI,
        name="Private Idea",
        normalized_name="private idea",
    )

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(accept_url, {"suggestion": str(sugg.suggestion_id)})
    assert res.status_code == 404


def test_ideas_endpoint_for_inaccessible_recipient_is_404(client, user):
    other_user = UserFactory()
    inaccessible_person = PersonFactory()
    _share(other_user, inaccessible_person)  # not shared with user

    url = reverse(
        "gift_manager:person_suggestion_ideas", kwargs={"pk": inaccessible_person.person_id}
    )
    res_get = client.get(url)
    assert res_get.status_code == 404

    res_post = client.post(url)
    assert res_post.status_code == 404


def test_ai_block_translated_in_french(client, user, monkeypatch):
    from django.conf import settings
    from django.utils import translation

    try:
        person = PersonFactory()
        _share(user, person)

        canned = {
            "ideas": [
                {
                    "name": "Roman",
                    "description": "Livre captivant",
                    "reason": "Aime lire",
                    "tags": [],
                }
            ]
        }
        fake = FakeAIClient(canned_responses=[canned])
        monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

        url = f"/fr/persons/{person.person_id}/suggestions/ideas/"
        res_get = client.get(url)
        assert res_get.status_code == 200
        content_get = res_get.content.decode()
        assert "Nouvelles idées" in content_get
        assert "Générer des idées" in content_get
        assert "Génération des idées avec l'IA…" in content_get
        assert "Demandez des suggestions de l'IA adaptées à ce destinataire." in content_get

        res_post = client.post(url, data={"count": "1"})
        assert res_post.status_code == 200
        content_post = res_post.content.decode()
        assert "Roman" in content_post
        assert "Ajouter des idées" in content_post
    finally:
        translation.activate(settings.LANGUAGE_CODE)


def test_suggestions_section_renders_dismissed_button_and_count(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    # Initially 0 dismissed: button present, no badge count
    suggestions_url = reverse("gift_manager:person_suggestions", kwargs={"pk": person.person_id})
    res0 = client.get(suggestions_url)
    assert res0.status_code == 200
    c0 = res0.content.decode()
    assert "data-suggestions-review-dismissed" in c0
    assert "data-dismissed-count" not in c0

    # Dismiss a suggestion
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
        name="Board Game",
        normalized_name="board game",
    )

    res1 = client.get(suggestions_url)
    assert res1.status_code == 200
    c1 = res1.content.decode()
    assert "data-suggestions-review-dismissed" in c1
    assert "data-dismissed-count" in c1
    assert '<span class="badge bg-secondary ms-1" data-dismissed-count>1</span>' in c1


def test_person_suggestions_dismissed_empty_state(client, user):
    person = PersonFactory()
    _share(user, person)

    url = reverse("gift_manager:person_suggestions_dismissed", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    content = res.content.decode()
    assert "data-dismissed-suggestions-container" in content
    assert "data-dismissed-empty" in content
    assert "No dismissed suggestions for this recipient." in content


def test_person_suggestions_dismissed_lists_items(client, user):
    from gift_manager.models import GiftSuggestion

    tag = GiftTagFactory(name="Sci-Fi")
    _share(user, tag)

    person = PersonFactory()
    _share(user, person)

    # 1 catalogue dismissal
    gift = GiftFactory(name="Stellaris", tags=[tag])
    _share(user, gift)
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=gift,
        name=gift.name,
        normalized_name="stellaris",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
        dismiss_reason=GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED,
        dismiss_comment="Already has one",
        reason="Matches tag Sci-Fi",
    )

    # 1 AI dismissal
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Solar Telescope",
        normalized_name="solar telescope",
        description="Great for daytime astronomy",
        reason="Loves space science",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )

    url = reverse("gift_manager:person_suggestions_dismissed", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    content = res.content.decode()

    assert "data-dismissed-item" in content
    assert "Stellaris" in content
    assert "From your gifts" in content
    assert "Already owned or practiced" in content
    assert "Already has one" in content
    assert "Solar Telescope" in content
    assert "New idea" in content
    assert "Great for daytime astronomy" in content
    assert "Loves space science" in content
    assert "Sci-Fi" in content
    assert 'data-action="restore"' in content
    assert 'data-action="purge"' in content


def test_person_suggestion_restore_ai_idea(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    sugg = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Astronomy Binoculars",
        normalized_name="astronomy binoculars",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )

    restore_url = reverse("gift_manager:person_suggestion_restore", kwargs={"pk": person.person_id})
    res = client.post(
        restore_url,
        {"suggestion": str(sugg.suggestion_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "suggestions:refresh" in res.headers.get("HX-Trigger", "")

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.PENDING

    # Panel content re-rendered without the restored item
    content = res.content.decode()
    assert "Astronomy Binoculars" not in content
    assert "data-dismissed-empty" in content


def test_person_suggestion_restore_catalogue_idea(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    gift = GiftFactory(name="Vintage Camera")
    _share(user, gift)

    dismissal = GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=gift,
        name=gift.name,
        normalized_name="vintage camera",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
    )

    restore_url = reverse("gift_manager:person_suggestion_restore", kwargs={"pk": person.person_id})
    res = client.post(
        restore_url,
        {"gift": str(gift.gift_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "suggestions:refresh" in res.headers.get("HX-Trigger", "")

    # Dismissal record removed so catalogue scoring suggests it again
    assert not GiftSuggestion.objects.filter(pk=dismissal.pk).exists()

    content = res.content.decode()
    assert "Vintage Camera" not in content
    assert "data-dismissed-empty" in content


def test_person_suggestion_purge_ai_idea(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    sugg = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Leather Journal",
        normalized_name="leather journal",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )

    purge_url = reverse("gift_manager:person_suggestion_purge", kwargs={"pk": person.person_id})
    res = client.post(
        purge_url,
        {"suggestion": str(sugg.suggestion_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "suggestions:refresh" in res.headers.get("HX-Trigger", "")

    # Record wiped from DB
    assert not GiftSuggestion.objects.filter(pk=sugg.pk).exists()

    content = res.content.decode()
    assert "Leather Journal" not in content
    assert "data-dismissed-empty" in content


def test_person_suggestion_purge_catalogue_idea(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    gift = GiftFactory(name="Fountain Pen")
    _share(user, gift)

    dismissal = GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=gift,
        name=gift.name,
        normalized_name="fountain pen",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
    )

    purge_url = reverse("gift_manager:person_suggestion_purge", kwargs={"pk": person.person_id})
    res = client.post(
        purge_url,
        {"gift": str(gift.gift_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    assert "suggestions:refresh" in res.headers.get("HX-Trigger", "")
    assert not GiftSuggestion.objects.filter(pk=dismissal.pk).exists()


def test_restore_and_purge_validation_errors(client, user):
    person = PersonFactory()
    _share(user, person)

    restore_url = reverse("gift_manager:person_suggestion_restore", kwargs={"pk": person.person_id})
    purge_url = reverse("gift_manager:person_suggestion_purge", kwargs={"pk": person.person_id})
    fake_id = str(uuid.uuid4())

    # Both gift and suggestion -> 400
    assert client.post(restore_url, {"gift": fake_id, "suggestion": fake_id}).status_code == 400
    assert client.post(purge_url, {"gift": fake_id, "suggestion": fake_id}).status_code == 400

    # Neither -> 400
    assert client.post(restore_url, {}).status_code == 400
    assert client.post(purge_url, {}).status_code == 400

    # Malformed UUID -> 404
    assert client.post(restore_url, {"gift": "bad-uuid"}).status_code == 404
    assert client.post(purge_url, {"suggestion": "bad-uuid"}).status_code == 404


def test_restore_and_purge_non_htmx_redirects(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    sugg1 = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Idea 1",
        normalized_name="idea 1",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )
    sugg2 = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Idea 2",
        normalized_name="idea 2",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )

    restore_url = reverse("gift_manager:person_suggestion_restore", kwargs={"pk": person.person_id})
    purge_url = reverse("gift_manager:person_suggestion_purge", kwargs={"pk": person.person_id})
    expected_redirect = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

    res_restore = client.post(restore_url, {"suggestion": str(sugg1.suggestion_id)})
    assert res_restore.status_code == 302
    assert res_restore.url == expected_redirect

    res_purge = client.post(purge_url, {"suggestion": str(sugg2.suggestion_id)})
    assert res_purge.status_code == 302
    assert res_purge.url == expected_redirect


def test_person_group_suggestions_dismissed_flow(client, user):
    from gift_manager.models import GiftSuggestion

    group = PersonGroupFactory()
    _share(user, group)

    sugg = GiftSuggestion.objects.create(
        user=user,
        group=group,
        name="Board Game Night",
        normalized_name="board game night",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )

    # GET dismissed panel
    dismissed_url = reverse(
        "gift_manager:person_group_suggestions_dismissed", kwargs={"pk": group.group_id}
    )
    res_list = client.get(dismissed_url)
    assert res_list.status_code == 200
    assert "Board Game Night" in res_list.content.decode()

    # Restore
    restore_url = reverse(
        "gift_manager:person_group_suggestion_restore", kwargs={"pk": group.group_id}
    )
    res_restore = client.post(
        restore_url,
        {"suggestion": str(sugg.suggestion_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res_restore.status_code == 200
    assert "suggestions:refresh" in res_restore.headers.get("HX-Trigger", "")

    sugg.refresh_from_db()
    assert sugg.state == GiftSuggestion.State.PENDING

    # Purge another dismissed suggestion
    sugg_to_purge = GiftSuggestion.objects.create(
        user=user,
        group=group,
        name="Cooking Class",
        normalized_name="cooking class",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.DISMISSED,
    )
    purge_url = reverse("gift_manager:person_group_suggestion_purge", kwargs={"pk": group.group_id})
    res_purge = client.post(
        purge_url,
        {"suggestion": str(sugg_to_purge.suggestion_id)},
        HTTP_HX_REQUEST="true",
    )
    assert res_purge.status_code == 200
    assert not GiftSuggestion.objects.filter(pk=sugg_to_purge.pk).exists()


def test_dismissed_endpoints_for_inaccessible_recipient_is_404(client, user):
    other_user = UserFactory()
    inaccessible_person = PersonFactory()
    _share(other_user, inaccessible_person)

    pk = inaccessible_person.person_id
    dismissed_url = reverse("gift_manager:person_suggestions_dismissed", kwargs={"pk": pk})
    restore_url = reverse("gift_manager:person_suggestion_restore", kwargs={"pk": pk})
    purge_url = reverse("gift_manager:person_suggestion_purge", kwargs={"pk": pk})

    assert client.get(dismissed_url).status_code == 404
    assert client.post(restore_url, {"suggestion": str(uuid.uuid4())}).status_code == 404
    assert client.post(purge_url, {"suggestion": str(uuid.uuid4())}).status_code == 404


def test_dismissed_panel_translated_in_french(client, user):
    from django.conf import settings
    from django.utils import translation

    from gift_manager.models import GiftSuggestion

    try:
        person = PersonFactory()
        _share(user, person)

        GiftSuggestion.objects.create(
            user=user,
            person=person,
            name="Roman",
            normalized_name="roman",
            description="Livre",
            reason="Aime lire",
            source=GiftSuggestion.Source.AI,
            state=GiftSuggestion.State.DISMISSED,
        )

        url = f"/fr/persons/{person.person_id}/suggestions/dismissed/"
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()

        assert (
            "Passez en revue les suggestions précédemment refusées pour ce destinataire." in content
        )
        assert "Restaurer" in content
        assert "Supprimer définitivement" in content
        assert "Nouvelle idée" in content
    finally:
        translation.activate(settings.LANGUAGE_CODE)


def test_dismissed_panel_does_not_leak_unshared_tags_or_unshared_gifts(client, user):
    from gift_manager.models import GiftSuggestion

    other_user = UserFactory()
    person = PersonFactory()
    _share(user, person)

    public_tag = GiftTagFactory(name="Public Hobbies")
    secret_tag = GiftTagFactory(name="Secret Private Medical")
    _share(user, public_tag)
    _share(other_user, secret_tag)  # user has no access to secret_tag

    gift = GiftFactory(name="Shared Gift", tags=[public_tag, secret_tag])
    _share(user, gift)

    GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=gift,
        name=gift.name,
        normalized_name="shared gift",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
    )

    # An unshared gift that was dismissed previously
    unshared_gift = GiftFactory(name="Unshared Secret Gift")
    _share(other_user, unshared_gift)  # not shared with user
    GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=unshared_gift,
        name=unshared_gift.name,
        normalized_name="unshared secret gift",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.DISMISSED,
    )

    url = reverse("gift_manager:person_suggestions_dismissed", kwargs={"pk": person.person_id})
    res = client.get(url)
    assert res.status_code == 200
    content = res.content.decode()

    # Public tag is visible, secret tag is not leaked
    assert "Public Hobbies" in content
    assert "Secret Private Medical" not in content

    # Unshared gift is excluded
    assert "Shared Gift" in content
    assert "Unshared Secret Gift" not in content


def test_dismiss_already_accepted_suggestion_is_404(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory()
    _share(user, person)

    sugg = GiftSuggestion.objects.create(
        user=user,
        person=person,
        name="Already Accepted",
        normalized_name="already accepted",
        source=GiftSuggestion.Source.AI,
        state=GiftSuggestion.State.ACCEPTED,
    )

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    res = client.post(dismiss_url, {"suggestion": str(sugg.suggestion_id)}, HTTP_HX_REQUEST="true")
    assert res.status_code == 404


def test_reaccept_accepted_suggestion_with_unshared_gift_is_404(client, user):
    from gift_manager.models import GiftSuggestion

    other_user = UserFactory()
    person = PersonFactory()
    _share(user, person)

    unshared_gift = GiftFactory(name="Unshared Revoked Gift")
    _share(other_user, unshared_gift)

    sugg = GiftSuggestion.objects.create(
        user=user,
        person=person,
        gift=unshared_gift,
        name=unshared_gift.name,
        normalized_name="unshared revoked gift",
        source=GiftSuggestion.Source.CATALOGUE,
        state=GiftSuggestion.State.ACCEPTED,
    )

    accept_url = reverse("gift_manager:person_suggestion_accept", kwargs={"pk": person.person_id})
    res = client.post(accept_url, {"suggestion": str(sugg.suggestion_id)}, HTTP_HX_REQUEST="true")
    assert res.status_code == 404


def test_dismiss_suggestion_with_promote_to_profile_appends_note_and_tags(client, user):
    import json

    from gift_manager.models import GiftSuggestion

    person = PersonFactory(notes="Prefers quiet evenings.")
    _share(user, person, level=PermissionLevel.EDITOR)

    tag = GiftTagFactory(name="Origami")
    _share(user, tag, level=PermissionLevel.VIEWER)

    gift = GiftFactory(name="Livre Origami Japonais")
    gift.tags.add(tag)
    _share(user, gift, level=PermissionLevel.VIEWER)

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    res = client.post(
        dismiss_url,
        {
            "gift": str(gift.gift_id),
            "reason": GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED,
            "comment": "Pratique le pliage depuis longtemps",
            "promote_to_profile": "1",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    person.refresh_from_db()
    assert (
        "Suggestion: Livre Origami Japonais]: Pratique le pliage depuis longtemps" in person.notes
    )
    assert person.interests.filter(name="Origami").exists()

    hx_trigger = json.loads(res.headers.get("HX-Trigger", "{}"))
    assert "showNotification" in hx_trigger
    assert hx_trigger["showNotification"]["type"] == "info"


def test_dismiss_suggestion_with_promote_to_profile_when_already_owned_no_comment_appends_default_note(
    client, user
):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory(notes="")
    _share(user, person, level=PermissionLevel.EDITOR)

    tag = GiftTagFactory(name="Astronomy")
    _share(user, tag, level=PermissionLevel.VIEWER)

    gift = GiftFactory(name="Telescope 70mm")
    gift.tags.add(tag)
    _share(user, gift, level=PermissionLevel.VIEWER)

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    res = client.post(
        dismiss_url,
        {
            "gift": str(gift.gift_id),
            "reason": GiftSuggestion.DismissReason.ALREADY_OWNED_OR_PRACTICED,
            "promote_to_profile": "1",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    person.refresh_from_db()
    assert "Suggestion: Telescope 70mm]: Already owned or practiced" in person.notes
    assert person.interests.filter(name="Astronomy").exists()


def test_dismiss_suggestion_with_promote_to_profile_ignored_when_read_only_viewer(client, user):
    from gift_manager.models import GiftSuggestion

    person = PersonFactory(notes="Initial")
    _share(user, person, level=PermissionLevel.VIEWER)  # read-only!

    gift = GiftFactory(name="Headphones")
    _share(user, gift, level=PermissionLevel.VIEWER)

    dismiss_url = reverse("gift_manager:person_suggestion_dismiss", kwargs={"pk": person.person_id})
    res = client.post(
        dismiss_url,
        {
            "gift": str(gift.gift_id),
            "reason": GiftSuggestion.DismissReason.DISLIKES,
            "comment": "Does not like in-ear style",
            "promote_to_profile": "1",
        },
        HTTP_HX_REQUEST="true",
    )
    assert res.status_code == 200
    person.refresh_from_db()
    # Notes must remain unchanged because viewer does not have EDITOR permissions
    assert person.notes == "Initial"
