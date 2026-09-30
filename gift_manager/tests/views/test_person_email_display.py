"""GM-AUD-006: person emails are displayed decoded, never as stored ciphertext."""

import pytest
from django.test import override_settings
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views.person import PersonDeleteView
from gift_manager.views.person import PersonListView

PLAIN_EMAIL = "visible@example.com"

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def person(owner):
    person = PersonFactory(first_name="Ada", family_name="Lovelace")
    person.set_email(PLAIN_EMAIL)
    person.save()
    PermissionService.create_or_update_permission(
        owner, person, permission_level=PermissionLevel.OWNER
    )
    assert person.email_address.startswith("gAAAA")
    return person


def test_fallback_person_list_shows_decoded_email(client, owner, person):
    client.force_login(owner)

    response = client.get(reverse("gift_manager:persons"), {"no_js": "1"})

    assert response.status_code == 200
    (row,) = response.context["fallback_table_data"]["rows"]
    assert row["email_address"] == PLAIN_EMAIL
    content = response.content.decode()
    assert PLAIN_EMAIL in content
    assert person.email_address not in content


def test_fallback_person_list_renders_blank_for_missing_email(client, owner):
    person = PersonFactory(email_address=None)
    PermissionService.create_or_update_permission(
        owner, person, permission_level=PermissionLevel.OWNER
    )
    client.force_login(owner)

    response = client.get(reverse("gift_manager:persons"), {"no_js": "1"})

    (row,) = response.context["fallback_table_data"]["rows"]
    assert row["email_address"] == ""


def test_person_list_fallback_value_decodes_instances_and_rows(person):
    view = PersonListView()

    from_row = view.get_fallback_field_value(
        {"email_address": person.email_address}, "email_address"
    )
    from_instance = view.get_fallback_field_value(person, "email_address")

    assert from_row == PLAIN_EMAIL
    assert from_instance == PLAIN_EMAIL
    assert view.get_fallback_field_value({"first_name": "Ada"}, "first_name") == "Ada"


def test_entity_details_use_decoded_email(person):
    view = PersonDeleteView()
    view.object = person

    details = view.get_entity_details()

    assert any(PLAIN_EMAIL in detail for detail in details)
    assert not any(person.email_address in detail for detail in details)


@override_settings(USE_I18N=False)
def test_delete_confirmation_shows_decoded_email(client, owner, person):
    client.force_login(owner)
    url = reverse("gift_manager:person_delete", kwargs={"pk": person.person_id})

    response = client.get(url, HTTP_HX_REQUEST="true")
    content = response.content.decode()
    assert response.status_code == 200
    assert f"Email: {PLAIN_EMAIL}" in content
    assert person.email_address not in content

    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert person.email_address not in content
