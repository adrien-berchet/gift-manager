"""Regression tests for GM-AUD-011, GM-AUD-012 and GM-AUD-013."""

import inspect
import json

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from gift_manager.forms import PersonGroupForm
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views import inline_editing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def restore_language():
    """LocaleMiddleware leaves the last request language active in the thread."""
    yield
    translation.activate(settings.LANGUAGE_CODE)


def _inline_views():
    return [
        cls
        for _, cls in inspect.getmembers(inline_editing, inspect.isclass)
        if issubclass(cls, inline_editing.InlineFieldUpdateView)
        and cls is not inline_editing.InlineFieldUpdateView
    ]


@pytest.mark.parametrize("view_class", _inline_views(), ids=lambda cls: cls.__name__)
def test_inline_allowed_fields_exist_on_model(view_class):
    """GM-AUD-012: an allowed inline field must be a real model field."""
    model_fields = {field.name for field in view_class.model._meta.get_fields()}

    assert set(view_class.allowed_fields) <= model_fields


def test_person_group_inline_rejects_comment_with_400(client):
    user = UserFactory()
    client.force_login(user)
    group = PersonGroupFactory()
    create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)

    response = client.post(
        reverse("gift_manager:person_group_inline_update", kwargs={"pk": group.group_id}),
        json.dumps({"field": "comment", "value": "x"}),
        content_type="application/json",
    )

    assert response.status_code == 400


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_person_group_form_rejects_blank_name(name):
    """GM-AUD-013: groups need a real name."""
    form = PersonGroupForm(data={"name": name})

    assert not form.is_valid()
    assert "name" in form.errors


def test_person_group_form_accepts_a_name():
    assert PersonGroupForm(data={"name": "Family"}).is_valid()


@pytest.fixture
def searcher(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.mark.parametrize("prefix", ["/en", "/fr"])
def test_global_search_urls_keep_the_active_language(client, searcher, prefix):
    """GM-AUD-011: result links are localized, not hardcoded root paths."""
    GiftFactory(name="Searchable gift", shared_with=[searcher])
    PersonFactory(first_name="Searchable", shared_with=[searcher])
    PersonGroupFactory(name="Searchable group", shared_with=[searcher])
    EventFactory(name="Searchable event", shared_with=[searcher])
    GiftTagFactory(name="Searchable tag", shared_with=[searcher])

    response = client.get(f"{prefix}/api/search/", {"q": "Searchable"})

    urls = [result["url"] for result in response.json()["results"]]
    assert len(urls) == 5
    assert all(url.startswith(f"{prefix}/") for url in urls), urls


def test_global_search_urls_match_reverse(client, searcher):
    gift = GiftFactory(name="Searchable gift", shared_with=[searcher])

    response = client.get(reverse("gift_manager:global_search"), {"q": "Searchable"})

    assert response.json()["results"][0]["url"] == reverse(
        "gift_manager:gift_detail", kwargs={"pk": gift.gift_id}
    )


def test_base_template_fetches_the_localized_search_endpoint(client, searcher):
    response = client.get(reverse("gift_manager:home"))

    assert f"fetch(`{reverse('gift_manager:global_search')}?q=" in response.content.decode()
    assert "fetch(`/api/search/" not in response.content.decode()


class TestSharePagePreselection:
    """GM-AUD-014: the bulk-share redirect must preselect the chosen objects."""

    @pytest.fixture
    def owner(self, client):
        user = UserFactory()
        client.force_login(user)
        return user

    def _share_page(self, client, **params):
        return client.get(reverse("gift_manager:share_objects"), params)

    def test_bulk_share_redirect_is_localized(self, client, owner):
        gift = GiftFactory(shared_with=[owner])
        create_or_update_permission(owner, gift, permission_level=PermissionLevel.OWNER)
        client.force_login(owner)

        response = client.post(
            reverse("gift_manager:bulk_operations"),
            json.dumps(
                {"action": "bulk_share", "entity_type": "gift", "entity_ids": [str(gift.gift_id)]}
            ),
            content_type="application/json",
        )

        assert response.json()["redirect_url"].startswith(reverse("gift_manager:share_objects"))

    @pytest.mark.parametrize(
        ("entity_type", "factory", "id_field", "field_name"),
        [
            ("gift", GiftFactory, "gift_id", "gifts"),
            ("person", PersonFactory, "person_id", "persons"),
            ("persongroup", PersonGroupFactory, "group_id", "person_groups"),
            ("event", EventFactory, "event_id", "events"),
        ],
    )
    def test_selected_objects_are_preselected(
        self, client, owner, entity_type, factory, id_field, field_name
    ):
        chosen, other = factory(shared_with=[owner]), factory(shared_with=[owner])

        response = self._share_page(
            client, entity_type=entity_type, ids=str(getattr(chosen, id_field))
        )

        assert response.context["preselected"][field_name] == [str(getattr(chosen, id_field))]
        content = response.content.decode()
        assert f'value="{getattr(chosen, id_field)}"' in content
        assert content.count("checked") >= 1
        assert str(getattr(other, id_field)) not in response.context["preselected"][field_name]

    def test_forged_and_malformed_ids_are_ignored(self, client, owner):
        mine = GiftFactory(shared_with=[owner])
        someone_elses = GiftFactory()

        response = self._share_page(
            client,
            entity_type="gift",
            ids=f"{mine.gift_id},{someone_elses.gift_id},not-a-uuid,,",
        )

        assert response.status_code == 200
        assert response.context["preselected"]["gifts"] == [str(mine.gift_id)]

    def test_unknown_entity_type_preselects_nothing(self, client, owner):
        gift = GiftFactory(shared_with=[owner])

        response = self._share_page(client, entity_type="nonsense", ids=str(gift.gift_id))

        assert response.status_code == 200
        assert not any(response.context["preselected"].values())

    def test_page_without_parameters_preselects_nothing(self, client, owner):
        response = self._share_page(client)

        assert not any(response.context["preselected"].values())
