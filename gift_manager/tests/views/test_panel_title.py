"""The edit panel shows "Create <thing>" or "Edit <thing>" depending on the form it holds."""

import pytest
from django.urls import reverse
from django.utils import translation

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def client_user(client, user):
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    ("url_name", "title"),
    [
        ("person_create", "Create Person"),
        ("gift_create", "Create Gift"),
        ("event_create", "Create Event"),
        ("relation_create", "Create Gift Plan"),
    ],
)
def test_create_forms_in_the_panel_carry_a_create_title(client_user, url_name, title):
    content = client_user.get(reverse(f"gift_manager:{url_name}"), **HTMX).content.decode()

    assert f'data-panel-title="{title}"' in content
    assert 'data-panel-title="Edit' not in content


def test_edit_form_in_the_panel_carries_an_edit_title(client_user, user):
    person = PersonFactory()
    PermissionService.create_or_update_permission(
        user, person, permission_level=PermissionLevel.EDITOR
    )

    content = client_user.get(
        reverse("gift_manager:person_edit", kwargs={"pk": person.person_id}), **HTMX
    ).content.decode()

    assert 'data-panel-title="Edit Person"' in content


def test_titles_are_translated(client_user):
    with translation.override("fr"):
        content = client_user.get("/fr/persons/create/", **HTMX).content.decode()

    assert 'data-panel-title="Création Personne"' in content


def test_full_page_forms_do_not_carry_a_panel_title(client_user):
    content = client_user.get(reverse("gift_manager:person_create")).content.decode()

    assert "data-panel-title" not in content
    assert "<h1>Create Person</h1>" in content
