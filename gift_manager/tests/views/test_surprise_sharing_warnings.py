"""Sharing a surprise plan with someone who cannot see it warns the sharer, and the list says so."""

import json

import pytest
from django.contrib.messages import WARNING
from django.contrib.messages import get_messages
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def _grant(obj, user, level, attr=None):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


@pytest.fixture
def owner(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.fixture
def recipient(owner):
    user = UserFactory()
    owner.profile.friends.add(user.profile)
    return user


@pytest.fixture
def surprise(owner, recipient):
    gift = GiftFactory(name="Secret Gift")
    _grant(gift, owner, PermissionLevel.OWNER)
    relation = RelationFactory(
        person=PersonFactory(user_link=recipient, shared_with=[owner]),
        gift=gift,
        event=None,
        is_surprise=True,
    )
    _grant(relation, owner, PermissionLevel.OWNER, "relation")
    return relation


def _warnings(response):
    return [str(m) for m in get_messages(response.wsgi_request) if m.level == WARNING]


def test_share_page_warns_about_a_recipient(client, surprise, recipient):
    response = client.post(
        reverse("gift_manager:share_objects"),
        {
            "relations": [surprise.relation_id],
            "friends": [recipient.id],
            "permission_level": PermissionLevel.VIEWER,
        },
    )

    assert response.status_code == 302
    (warning,) = _warnings(response)
    assert recipient.username in warning
    assert "Secret Gift" in warning


def test_share_page_does_not_warn_for_a_friend_who_can_see_the_plan(client, surprise, owner):
    friend = UserFactory()
    owner.profile.friends.add(friend.profile)

    response = client.post(
        reverse("gift_manager:share_objects"),
        {
            "relations": [surprise.relation_id],
            "friends": [friend.id],
            "permission_level": PermissionLevel.VIEWER,
        },
    )

    assert _warnings(response) == []


def test_sharing_from_the_plan_warns_in_a_notification(client, surprise, recipient):
    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        {"share_with": "1", "user_id": recipient.id, "permission": PermissionLevel.VIEWER},
        **HX,
    )

    assert response.status_code == 204
    notification = json.loads(response["HX-Trigger"])["showNotification"]
    assert notification["type"] == "warning"
    assert recipient.username in notification["message"]


def test_changing_a_permission_warns_in_a_notification(client, surprise, recipient):
    _grant(surprise, recipient, PermissionLevel.VIEWER, "relation")

    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        {
            "update_permission": "1",
            "user_id": recipient.id,
            "permission": PermissionLevel.EDITOR,
        },
        **HX,
    )

    assert response.status_code == 204
    assert recipient.username in json.loads(response["HX-Trigger"])["showNotification"]["message"]


def test_sharing_with_the_page_form_warns_in_a_message(client, surprise, recipient):
    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        {"share_with": "1", "user_id": recipient.id, "permission": PermissionLevel.VIEWER},
    )

    (warning,) = _warnings(response)
    assert recipient.username in warning


def test_changing_a_permission_with_the_page_form_warns_in_a_message(client, surprise, recipient):
    _grant(surprise, recipient, PermissionLevel.VIEWER, "relation")

    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        {
            "update_permission": "1",
            "user_id": recipient.id,
            "permission": PermissionLevel.EDITOR,
        },
    )

    (warning,) = _warnings(response)
    assert recipient.username in warning


def test_sharing_a_normal_plan_with_a_friend_does_not_warn(client, owner):
    friend = UserFactory()
    owner.profile.friends.add(friend.profile)
    relation = RelationFactory(person=PersonFactory(user_link=friend), event=None)
    _grant(relation, owner, PermissionLevel.OWNER, "relation")
    _grant(relation.gift, owner, PermissionLevel.OWNER)

    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
        {"share_with": "1", "user_id": friend.id, "permission": PermissionLevel.VIEWER},
        **HX,
    )

    assert "showNotification" not in response.headers.get("HX-Trigger", "")


def test_shared_with_list_marks_the_people_who_cannot_see_the_plan(client, surprise, recipient):
    friend = UserFactory()
    _grant(surprise, recipient, PermissionLevel.VIEWER, "relation")
    _grant(surprise, friend, PermissionLevel.VIEWER, "relation")

    response = client.get(
        reverse("gift_manager:relation_detail", kwargs={"pk": surprise.relation_id})
    )

    flags = {
        item["user"].username: item["hidden_surprise"] for item in response.context["shared_users"]
    }
    assert flags == {recipient.username: True, friend.username: False}
    assert "Can't see it" in response.content.decode()


def test_shared_with_list_query_count_does_not_grow_with_the_sharees(client, surprise, recipient):
    url = reverse("gift_manager:relation_detail", kwargs={"pk": surprise.relation_id})

    def queries() -> int:
        with CaptureQueriesContext(connection) as context:
            assert client.get(url).status_code == 200
        return len(context)

    _grant(surprise, recipient, PermissionLevel.VIEWER, "relation")
    few = queries()
    for _ in range(6):
        _grant(surprise, UserFactory(), PermissionLevel.VIEWER, "relation")

    assert queries() == few


# --- the warning must actually reach the sharer ----------------------------------------------


def _edit_form_data(relation, **extra):
    return {
        "recipient": f"person:{relation.person.person_id}",
        "gift": str(relation.gift_id),
        "comment": "",
        "event": "",
        "status": str(relation.status_id),
        "due_date": "",
        "is_surprise": "on",
        **extra,
    }


def test_the_warning_is_rendered_on_the_page_after_sharing(client, surprise, recipient):
    response = client.post(
        reverse("gift_manager:share_objects"),
        {
            "relations": [surprise.relation_id],
            "friends": [recipient.id],
            "permission_level": PermissionLevel.VIEWER,
        },
        follow=True,
    )

    content = response.content.decode()
    assert f"{recipient.username} will not be able to see" in content
    assert "alert-warning" in content


def test_a_queued_warning_is_shown_once(client, surprise, recipient):
    client.post(
        reverse("gift_manager:share_objects"),
        {
            "relations": [surprise.relation_id],
            "friends": [recipient.id],
            "permission_level": PermissionLevel.VIEWER,
        },
        follow=True,
    )

    again = client.get(reverse("gift_manager:share_objects")).content.decode()

    assert "will not be able to see" not in again


def test_saving_the_plan_form_with_a_new_sharee_warns_after_the_redirect(
    client, surprise, recipient
):
    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        _edit_form_data(surprise, **{f"permission_{recipient.id}": str(PermissionLevel.VIEWER)}),
        follow=True,
    )

    assert f"{recipient.username} will not be able to see" in response.content.decode()


def test_saving_the_plan_form_through_htmx_warns_in_a_notification(client, surprise, recipient):
    response = client.post(
        reverse("gift_manager:relation_edit", kwargs={"pk": surprise.relation_id}),
        _edit_form_data(surprise, **{f"permission_{recipient.id}": str(PermissionLevel.VIEWER)}),
        **HX,
    )

    triggers = json.loads(response["HX-Trigger"])
    assert recipient.username in triggers["showWarning"]["message"]
    assert "showNotification" in triggers  # the usual success notification is kept
    assert _warnings(response) == []  # nothing is left queued for a later page load
