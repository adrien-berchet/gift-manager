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
    assert len(fake.calls) == 0

    # POST triggers generation
    res_post = client.post(ideas_url, data={"count": "1"})
    assert res_post.status_code == 200
    content_post = res_post.content.decode()
    assert "Canned Idea" in content_post
    assert 'data-suggestion-source="ai"' in content_post
    assert "More ideas" in content_post
    assert len(fake.calls) == 1

    # Second GET renders generated ideas without triggering another call
    res2 = client.get(ideas_url)
    assert res2.status_code == 200
    content2 = res2.content.decode()
    assert "Canned Idea" in content2
    assert len(fake.calls) == 1


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
        assert "Demandez des suggestions de l'IA adaptées à ce destinataire." in content_get

        res_post = client.post(url, data={"count": "1"})
        assert res_post.status_code == 200
        content_post = res_post.content.decode()
        assert "Roman" in content_post
        assert "Plus d'idées" in content_post
    finally:
        translation.activate(settings.LANGUAGE_CODE)
