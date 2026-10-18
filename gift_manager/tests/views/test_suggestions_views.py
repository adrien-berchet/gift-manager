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
