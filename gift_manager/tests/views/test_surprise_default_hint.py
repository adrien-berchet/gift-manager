"""The plan form refreshes the surprise checkbox when the recipient changes."""

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = reverse("gift_manager:surprise_default_hint")


@pytest.fixture
def creator(client):
    user = UserFactory()
    client.force_login(user)
    return user


def _hint(client, recipient):
    return client.get(URL, {"recipient": recipient})


def test_requires_login(client):
    assert client.get(URL).status_code == 302


def test_checkbox_is_checked_for_a_person_linked_to_another_user(client, creator):
    person = PersonFactory(user_link=UserFactory(), shared_with=[creator])

    response = _hint(client, f"person:{person.person_id}")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="is_surprise"' in content
    assert "checked" in content


def test_checkbox_is_unchecked_for_an_unlinked_person(client, creator):
    person = PersonFactory(shared_with=[creator])

    content = _hint(client, f"person:{person.person_id}").content.decode()

    assert 'name="is_surprise"' in content
    assert "checked" not in content


def test_checkbox_is_checked_for_a_group_with_a_linked_member(client, creator):
    group = PersonGroupFactory(shared_with=[creator])
    PersonFactory(user_link=UserFactory(), groups=[group])

    content = _hint(client, f"group:{group.group_id}").content.decode()

    assert "checked" in content


def test_no_checkbox_for_the_creators_own_person(client, creator):
    person = PersonFactory(user_link=creator)

    response = _hint(client, f"person:{person.person_id}")

    assert response.status_code == 200
    assert "is_surprise" not in response.content.decode()


@pytest.mark.parametrize("recipient", ["", "garbage", "person:not-a-uuid", "team:1"])
def test_malformed_recipient_is_a_bad_request(client, creator, recipient):
    assert _hint(client, recipient).status_code == 400


def test_inaccessible_recipient_gets_the_same_bad_request(client, creator):
    stranger_person = PersonFactory()

    assert _hint(client, f"person:{stranger_person.person_id}").status_code == 400


def test_create_page_renders_the_checkbox_and_refreshes_it_on_recipient_change(client, creator):
    response = client.get(reverse("gift_manager:relation_create"))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="is_surprise"' in content
    assert f'hx-get="{URL}"' in content


def test_edit_page_renders_the_checkbox_without_the_refresh(client, creator):
    relation = RelationFactory(person=PersonFactory(user_link=UserFactory()))
    PermissionService.create_or_update_permission(
        creator, relation, permission_level=PermissionLevel.OWNER, object_attr="relation"
    )

    response = client.get(
        reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id})
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="is_surprise"' in content
    assert f'hx-get="{URL}"' not in content
