import pytest
from django.urls import reverse

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission


def grant_owner(user, *objects):
    for obj in objects:
        create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


@pytest.fixture
def form_choice_data(user):
    person = Person.objects.create(
        user_link=user,
        first_name="Ada",
        family_name="Lovelace",
    )
    group = PersonGroup.objects.create(name="Family")
    gift = Gift.objects.create(name="Notebook", comment="")
    event = Event.objects.create(name="Birthday", comment="", recurrence="yearly")
    tag = GiftTag.objects.create(name="Books")
    RelationStatus.objects.create(status="Idea")
    grant_owner(user, group, gift, event, tag)
    return {
        "person": person,
        "group": group,
        "gift": gift,
        "event": event,
        "tag": tag,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "expected_fields", "form_type"),
    [
        (
            "gift_manager:person_create",
            ["first_name", "family_name", "email_address"],
            "person-edit",
        ),
        ("gift_manager:gift_create", ["name", "comment", "tags"], "gift"),
        (
            "gift_manager:event_create",
            ["name", "comment", "date_type", "absolute_date", "recurrence"],
            "event-edit",
        ),
        (
            "gift_manager:person_group_create",
            ["name", "parent_groups", "child_groups"],
            "person_group",
        ),
        ("gift_manager:gift_tag_create", ["name", "parent_tags"], "gift_tag"),
        ("gift_manager:relation_create", ["recipient", "gift", "comment", "status"], "relation"),
    ],
)
def test_create_forms_share_full_page_and_htmx_structure(
    authenticated_client,
    form_choice_data,
    url_name,
    expected_fields,
    form_type,
):
    url = reverse(url_name)

    full_page_response = authenticated_client.get(url)
    htmx_response = authenticated_client.get(url, HTTP_HX_REQUEST="true")

    assert full_page_response.status_code == 200
    assert htmx_response.status_code == 200

    full_page_content = full_page_response.content.decode()
    htmx_content = htmx_response.content.decode()

    assert "page-form-actions" in full_page_content
    assert "offcanvas-form" in htmx_content
    assert "panel-form-actions" in htmx_content
    assert f'data-form-type="{form_type}"' in full_page_content
    assert f'data-form-type="{form_type}"' in htmx_content

    for field_name in expected_fields:
        assert f'name="{field_name}"' in full_page_content
        assert f'name="{field_name}"' in htmx_content


@pytest.mark.django_db
def test_gift_create_forms_offer_save_and_create_gift_plan(authenticated_client):
    url = reverse("gift_manager:gift_create")

    full_page_response = authenticated_client.get(url)
    htmx_response = authenticated_client.get(url, HTTP_HX_REQUEST="true")

    assert full_page_response.status_code == 200
    assert htmx_response.status_code == 200

    for response in (full_page_response, htmx_response):
        content = response.content.decode()
        assert 'name="after_save"' in content
        assert 'value="create_gift_plan"' in content
        assert "Save and create gift plan" in content


@pytest.mark.django_db
def test_non_gift_create_forms_do_not_offer_save_and_create_gift_plan(
    authenticated_client,
    form_choice_data,
):
    urls = [
        reverse("gift_manager:person_create"),
        reverse("gift_manager:gift_edit", kwargs={"pk": form_choice_data["gift"].gift_id}),
    ]

    for url in urls:
        response = authenticated_client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert 'value="create_gift_plan"' not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "object_key", "pk_attr"),
    [
        ("gift_manager:person_relation_create", "person", "person_id"),
        ("gift_manager:person_group_relation_create", "group", "group_id"),
    ],
)
def test_contextual_relation_create_forms_use_unified_offcanvas_structure(
    authenticated_client,
    form_choice_data,
    url_name,
    object_key,
    pk_attr,
):
    target = form_choice_data[object_key]
    url = reverse(url_name, kwargs={"pk": getattr(target, pk_attr)})

    response = authenticated_client.get(url, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    content = response.content.decode()
    assert "offcanvas-form" in content
    assert "panel-form-actions" in content
    assert 'data-form-type="relation"' in content
    assert f'action="{url}"' in content
    assert f'hx-post="{url}"' in content
    assert 'name="recipient"' not in content
    assert 'name="gift"' in content
    assert 'name="status"' in content


@pytest.mark.django_db
def test_full_page_form_validation_uses_shared_error_pattern(authenticated_client):
    response = authenticated_client.post(
        reverse("gift_manager:person_create"),
        {
            "first_name": "",
            "family_name": "",
            "email_address": "not-an-email",
        },
    )

    content = response.content.decode()

    assert response.status_code == 200
    assert "form-error-summary" in content
    assert "invalid-feedback" in content
    assert 'href="#id_first_name"' in content
    assert 'href="#id_email_address"' in content


@pytest.mark.django_db
def test_edit_form_sharing_controls_submit_without_javascript(authenticated_client, user):
    friend = type(user).objects.create_user(
        username="friend",
        password="password123",
        email="friend@example.com",
    )
    user.profile.friends.add(friend.profile)

    person = Person.objects.create(
        user_link=user,
        first_name="Grace",
        family_name="Hopper",
        email_address="grace@example.com",
    )
    grant_owner(user, person)

    edit_url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
    get_response = authenticated_client.get(edit_url)

    assert get_response.status_code == 200
    get_content = get_response.content.decode()
    assert f'name="permission_{friend.id}"' in get_content
    assert "sharing-permission-select" in get_content
    assert reverse("gift_manager:person_delete", kwargs={"pk": person.person_id}) in get_content
    assert 'data-action="delete"' in get_content

    response = authenticated_client.post(
        edit_url,
        {
            "first_name": "Grace",
            "family_name": "Hopper",
            "email_address": "grace@example.com",
            f"permission_{friend.id}": str(PermissionLevel.EDITOR),
        },
    )

    assert response.status_code == 302
    assert get_permission(person, friend) == PermissionLevel.EDITOR
