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
