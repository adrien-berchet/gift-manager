"""Regression tests for person-group access gaps.

Covers:
- removing a person from a group only mutates on POST (CSRF-safe);
- the reparent API does not reveal names or existence of inaccessible groups;
- the group explorer member counts only include persons the viewer can access.
"""

import json
import uuid

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level=PermissionLevel.OWNER):
    create_or_update_permission(user, obj, permission_level=level)


@pytest.fixture
def actor():
    return UserFactory()


@pytest.fixture
def client(actor):
    client = Client()
    client.force_login(actor)
    return client


# ---------------------------------------------------------------------------
# Gap A: removing a person from a group must not happen over GET
# ---------------------------------------------------------------------------


@pytest.fixture
def membership(actor):
    group = PersonGroupFactory(name="Family")
    person = PersonFactory(first_name="Alice", family_name="Martin")
    _grant(actor, group)
    _grant(actor, person)
    person.groups.add(group)
    url = reverse(
        "gift_manager:remove_person_group_person",
        kwargs={"pk": group.group_id, "person_id": person.person_id},
    )
    return group, person, url


class TestRemovePersonFromGroup:
    def test_get_does_not_remove_person(self, client, membership):
        group, person, url = membership

        client.get(url)

        assert person.groups.filter(pk=group.pk).exists()

    def test_htmx_get_does_not_remove_person(self, client, membership):
        group, person, url = membership

        client.get(url, HTTP_HX_REQUEST="true")

        assert person.groups.filter(pk=group.pk).exists()

    def test_get_renders_confirmation_page_with_post_form(self, client, membership):
        group, _person, url = membership

        response = client.get(url)

        assert response.status_code == 200
        body = response.content.decode()
        assert "<html" in body
        assert 'method="post"' in body
        assert f'action="{url}"' in body
        assert "csrfmiddlewaretoken" in body
        assert "Alice" in body
        assert "Family" in body
        detail_url = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        assert f'href="{detail_url}"' in body

    def test_htmx_get_renders_modal_confirmation_partial(self, client, membership):
        _group, _person, url = membership

        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        body = response.content.decode()
        assert "<html" not in body
        # The global delete handler submits the form with this id
        assert 'id="deleteForm"' in body
        assert 'method="post"' in body
        assert f'action="{url}"' in body
        assert "csrfmiddlewaretoken" in body

    def test_get_without_editor_permission_does_not_offer_form(self, actor, client):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.VIEWER)
        _grant(actor, person)
        person.groups.add(group)
        url = reverse(
            "gift_manager:remove_person_group_person",
            kwargs={"pk": group.group_id, "person_id": person.person_id},
        )

        response = client.get(url)
        htmx_response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 302
        assert htmx_response.status_code == 403
        assert 'id="deleteForm"' not in htmx_response.content.decode()
        assert person.groups.filter(pk=group.pk).exists()

    def test_post_removes_person_and_redirects(self, client, membership):
        group, person, url = membership

        response = client.post(url)

        assert response.status_code == 302
        assert response.url == reverse(
            "gift_manager:person_group_detail", kwargs={"pk": group.group_id}
        )
        assert not person.groups.filter(pk=group.pk).exists()

    def test_htmx_post_removes_person_and_updates_lists_without_reload(self, client, membership):
        group, person, url = membership

        response = client.post(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        # The detail page refreshes its membership section on list:update, no full reload
        assert "HX-Refresh" not in response
        triggers = json.loads(response["HX-Trigger"])
        assert "modal:close" in triggers
        assert "list:update" in triggers
        assert triggers["showNotification"]["type"] == "success"
        assert not person.groups.filter(pk=group.pk).exists()

    def test_htmx_post_refused_by_service_returns_error(self, actor, client):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, person, PermissionLevel.VIEWER)
        person.groups.add(group)
        url = reverse(
            "gift_manager:remove_person_group_person",
            kwargs={"pk": group.group_id, "person_id": person.person_id},
        )

        response = client.post(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 403
        triggers = json.loads(response["HX-Trigger"])
        assert triggers["showNotification"]["type"] == "error"
        assert person.groups.filter(pk=group.pk).exists()

    def test_other_methods_are_rejected(self, client, membership):
        group, person, url = membership

        response = client.put(url)

        assert response.status_code == 405
        assert person.groups.filter(pk=group.pk).exists()

    def test_inaccessible_group_is_not_found(self, actor, client):
        group, person = PersonGroupFactory(), PersonFactory()
        _grant(actor, person)
        person.groups.add(group)
        url = reverse(
            "gift_manager:remove_person_group_person",
            kwargs={"pk": group.group_id, "person_id": person.person_id},
        )

        assert client.get(url).status_code == 404
        assert client.post(url).status_code == 404
        assert person.groups.filter(pk=group.pk).exists()


# ---------------------------------------------------------------------------
# Gap B: reparent API must not reveal inaccessible groups
# ---------------------------------------------------------------------------


def _reparent(client, payload):
    return client.post(
        reverse("gift_manager:api_reparent_group"),
        data=json.dumps(payload),
        content_type="application/json",
    )


class TestReparentDoesNotLeakGroups:
    def test_inaccessible_parent_name_is_not_leaked(self, actor, client):
        stranger = UserFactory()
        group = PersonGroupFactory()
        _grant(actor, group)
        private = PersonGroupFactory(name="PrivateGroupNameOfStranger")
        _grant(stranger, private)

        response = _reparent(
            client, {"group_id": str(group.group_id), "parent_ids": [str(private.group_id)]}
        )

        assert response.status_code == 404
        assert "PrivateGroupNameOfStranger" not in response.content.decode()
        assert not group.parent_groups.exists()

    def test_inaccessible_parent_answers_like_unknown_parent(self, actor, client):
        stranger = UserFactory()
        group = PersonGroupFactory()
        _grant(actor, group)
        private = PersonGroupFactory()
        _grant(stranger, private)
        unknown_id = str(uuid.uuid4())

        hidden = _reparent(
            client, {"group_id": str(group.group_id), "parent_ids": [str(private.group_id)]}
        )
        unknown = _reparent(client, {"group_id": str(group.group_id), "parent_ids": [unknown_id]})

        assert hidden.status_code == unknown.status_code == 404
        hidden_message = hidden.json()["message"].replace(str(private.group_id), "<id>")
        unknown_message = unknown.json()["message"].replace(unknown_id, "<id>")
        assert hidden_message == unknown_message

    def test_inaccessible_moved_group_answers_like_unknown_group(self, client):
        stranger = UserFactory()
        private = PersonGroupFactory(name="PrivateMovedGroup")
        _grant(stranger, private)

        hidden = _reparent(client, {"group_id": str(private.group_id), "parent_ids": []})
        unknown = _reparent(client, {"group_id": str(uuid.uuid4()), "parent_ids": []})

        assert hidden.status_code == unknown.status_code == 404
        assert hidden.json() == unknown.json()
        assert "PrivateMovedGroup" not in hidden.content.decode()

    def test_viewer_on_moved_group_is_forbidden(self, actor, client):
        group = PersonGroupFactory()
        _grant(actor, group, PermissionLevel.VIEWER)

        response = _reparent(client, {"group_id": str(group.group_id), "parent_ids": []})

        assert response.status_code == 403

    @pytest.mark.parametrize("group_id", ["not-a-uuid", 12, ["x"], {"a": 1}])
    def test_malformed_group_id_is_bad_request(self, client, group_id):
        response = _reparent(client, {"group_id": group_id, "parent_ids": []})

        assert response.status_code == 400
        assert response.json()["success"] is False

    @pytest.mark.parametrize("parent_ids", [["not-a-uuid"], [12], "not-a-list", [None]])
    def test_malformed_parent_ids_are_bad_request(self, actor, client, parent_ids):
        group = PersonGroupFactory()
        _grant(actor, group)

        response = _reparent(client, {"group_id": str(group.group_id), "parent_ids": parent_ids})

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert not group.parent_groups.exists()

    def test_non_object_json_body_is_bad_request(self, client):
        response = _reparent(client, ["not", "an", "object"])

        assert response.status_code == 400

    def test_non_canonical_parent_uuid_is_accepted(self, actor, client):
        group, parent = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, group)
        _grant(actor, parent)

        response = _reparent(
            client,
            {"group_id": str(group.group_id), "parent_ids": [str(parent.group_id).upper()]},
        )

        assert response.status_code == 200
        assert group.parent_groups.filter(pk=parent.pk).exists()


# ---------------------------------------------------------------------------
# Gap C: explorer member counts must ignore persons the viewer cannot access
# ---------------------------------------------------------------------------


def _add_members(group, *, visible_to, visible=0, hidden=0):
    stranger = UserFactory()
    for _ in range(visible):
        person = PersonFactory()
        _grant(visible_to, person)
        person.groups.add(group)
    for _ in range(hidden):
        person = PersonFactory()
        _grant(stranger, person)
        person.groups.add(group)


def _normalized_body(response):
    return " ".join(response.content.decode().split())


class TestExplorerMemberCounts:
    def test_root_groups_count_only_accessible_members(self, actor, client):
        group = PersonGroupFactory()
        _grant(actor, group)
        _add_members(group, visible_to=actor, visible=2, hidden=7)

        response = client.get(reverse("gift_manager:person_group_explorer"))

        assert response.status_code == 200
        body = _normalized_body(response)
        assert "2 members" in body
        assert "9 members" not in body
        assert "7 members" not in body

    def test_child_and_parent_groups_count_only_accessible_members(self, actor, client):
        parent, selected, child = (PersonGroupFactory() for _ in range(3))
        for group in (parent, selected, child):
            _grant(actor, group)
        selected.parent_groups.add(parent)
        child.parent_groups.add(selected)
        _add_members(parent, visible_to=actor, visible=1, hidden=4)
        _add_members(child, visible_to=actor, visible=3, hidden=5)

        response = client.get(
            reverse(
                "gift_manager:person_group_explorer_with_group", kwargs={"pk": selected.group_id}
            )
        )

        assert response.status_code == 200
        body = _normalized_body(response)
        assert "1 member" in body
        assert "3 members" in body
        assert "5 members" not in body
        assert "8 members" not in body

    def test_root_member_counts_do_not_add_queries_per_group(self, actor, client):
        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                response = client.get(reverse("gift_manager:person_group_explorer"))
            assert response.status_code == 200
            return len(queries)

        first = PersonGroupFactory()
        _grant(actor, first)
        _add_members(first, visible_to=actor, visible=1, hidden=1)
        count_queries()  # warm the session so both measured requests do the same work
        baseline = count_queries()

        for _ in range(4):
            group = PersonGroupFactory()
            _grant(actor, group)
            _add_members(group, visible_to=actor, visible=2, hidden=1)

        assert count_queries() == baseline

    def test_child_member_counts_do_not_add_queries_per_group(self, actor, client):
        selected = PersonGroupFactory()
        _grant(actor, selected)
        url = reverse(
            "gift_manager:person_group_explorer_with_group", kwargs={"pk": selected.group_id}
        )

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
            assert response.status_code == 200
            return len(queries)

        def add_child():
            child = PersonGroupFactory()
            _grant(actor, child)
            child.parent_groups.add(selected)
            _add_members(child, visible_to=actor, visible=1, hidden=1)

        add_child()
        count_queries()  # warm the session so both measured requests do the same work
        baseline = count_queries()
        for _ in range(3):
            add_child()

        assert count_queries() == baseline
