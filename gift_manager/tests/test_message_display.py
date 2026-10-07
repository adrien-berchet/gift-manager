"""Django flash messages are shown on pages, from the configured level up."""

import json
import re

import pytest
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from gift_manager.message_levels import parse_message_level
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def _flash(response) -> list[dict]:
    """Return the messages handed to the toast overlay (the ``flash-messages`` JSON block)."""
    content = response.content.decode()
    match = re.search(
        r'<script id="flash-messages" type="application/json">(.*?)</script>', content, re.DOTALL
    )
    return json.loads(match.group(1)) if match else []


def _json_block(response) -> str:
    match = re.search(
        r'<script id="flash-messages".*?</script>', response.content.decode(), re.DOTALL
    )
    return match.group(0) if match else ""


def _visible_html(response) -> str:
    """Return the page without its ``<noscript>`` fallback."""
    return re.sub(r"<noscript>.*?</noscript>", "", response.content.decode(), flags=re.DOTALL)


def _share(relation, user, level):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


@pytest.fixture
def claimed_plan(client):
    """A plan claimed by someone else: a plain claim attempt queues an error message."""
    user, claimer = UserFactory(), UserFactory()
    relation = RelationFactory()
    for person in (user, claimer):
        _share(relation, person, PermissionLevel.EDITOR)
    Relation.objects.filter(pk=relation.pk).update(claimed_by=claimer, claimed_at=timezone.now())
    client.force_login(user)
    return relation


def _claim_conflict(client, relation, **extra):
    return client.post(
        reverse("gift_manager:relation_claim", kwargs={"pk": relation.relation_id}), **extra
    )


def _share_with_a_friend(client):
    owner = UserFactory()
    friend = UserFactory()
    owner.profile.friends.add(friend.profile)
    person = PersonFactory()
    PermissionService.create_or_update_permission(
        owner, person, permission_level=PermissionLevel.OWNER
    )
    relation = RelationFactory(person=person, event=None)
    _share(relation, owner, PermissionLevel.OWNER)
    PermissionService.create_or_update_permission(
        owner, relation.gift, permission_level=PermissionLevel.OWNER
    )
    client.force_login(owner)
    return client.post(
        reverse("gift_manager:share_objects"),
        {
            "relations": [relation.relation_id],
            "friends": [friend.id],
            "permission_level": PermissionLevel.VIEWER,
        },
        follow=True,
    )


def test_an_error_message_is_handed_to_the_toast_overlay(client, claimed_plan):
    response = _claim_conflict(client, claimed_plan, follow=True)

    (item,) = [i for i in _flash(response) if "already claimed" in i["message"]]
    assert item["type"] == "error"


def test_a_success_message_is_handed_to_the_toast_overlay(client):
    response = _share_with_a_friend(client)

    (item,) = [i for i in _flash(response) if "Successfully shared items" in i["message"]]
    assert item["type"] == "success"


def test_messages_are_not_rendered_inline_where_they_would_move_the_layout(client, claimed_plan):
    response = _claim_conflict(client, claimed_plan, follow=True)

    visible = _visible_html(response)
    assert "has already claimed this gift plan" not in visible.replace(_json_block(response), "")


def test_without_javascript_the_messages_still_show_in_a_noscript_alert(client, claimed_plan):
    response = _claim_conflict(client, claimed_plan, follow=True)

    noscript = re.search(r"<noscript>(.*?)</noscript>", response.content.decode(), re.DOTALL)
    assert noscript is not None
    assert "has already claimed this gift plan" in noscript.group(1)
    assert "alert-danger" in noscript.group(1)


@override_settings(MESSAGES_DISPLAY_LEVEL=messages.WARNING)
def test_messages_below_the_configured_level_are_not_shown(client):
    response = _share_with_a_friend(client)

    assert not any("Successfully shared items" in i["message"] for i in _flash(response))
    assert "Successfully shared items" not in response.content.decode()


@override_settings(MESSAGES_DISPLAY_LEVEL=messages.WARNING)
def test_messages_at_or_above_the_configured_level_are_still_shown(client, claimed_plan):
    response = _claim_conflict(client, claimed_plan, follow=True)

    assert any("already claimed" in i["message"] for i in _flash(response))


def test_a_message_is_shown_only_once(client, claimed_plan):
    _claim_conflict(client, claimed_plan, follow=True)

    again = client.get(claimed_plan.get_absolute_url())

    assert "has already claimed this gift plan" not in again.content.decode()
    assert _flash(again) == []


def test_an_htmx_partial_does_not_consume_the_message_of_the_next_full_page(client, claimed_plan):
    _claim_conflict(client, claimed_plan)  # queues the message, redirects
    client.get(claimed_plan.get_absolute_url(), **HX)  # a fragment never shows messages

    full_page = client.get(claimed_plan.get_absolute_url())

    assert any("already claimed" in i["message"] for i in _flash(full_page))


@pytest.mark.parametrize(
    ("name", "level"),
    [("debug", 10), ("info", 20), ("success", 25), ("WARNING", 30), (" error ", 40)],
)
def test_the_level_can_be_named_in_any_case(name, level):
    assert parse_message_level(name) == level


def test_an_unknown_level_is_a_configuration_error():
    with pytest.raises(ImproperlyConfigured, match="MESSAGES_DISPLAY_LEVEL"):
        parse_message_level("loud")
