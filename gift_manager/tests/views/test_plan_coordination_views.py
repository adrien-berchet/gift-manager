"""Claim, release and comment endpoints of a gift plan, and how the detail page shows them."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from gift_manager import plan_coordination
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationComment
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def _share(relation, user, level):
    PermissionService.create_or_update_permission(
        user, relation, permission_level=level, object_attr="relation"
    )


def _url(name, relation, **kwargs):
    return reverse(f"gift_manager:{name}", kwargs={"pk": relation.relation_id, **kwargs})


@pytest.fixture
def relation():
    return RelationFactory()


@pytest.fixture
def owner(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.OWNER)
    return user


@pytest.fixture
def editor(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.EDITOR)
    return user


@pytest.fixture
def viewer(relation):
    user = UserFactory()
    _share(relation, user, PermissionLevel.VIEWER)
    return user


@pytest.fixture
def stranger():
    return UserFactory()


def _post(client, user, url, data=None, **extra):
    client.force_login(user)
    return client.post(url, data or {}, **extra)


def _claim(relation, user):
    Relation.objects.filter(pk=relation.pk).update(claimed_by=user, claimed_at=timezone.now())


# --- claim ----------------------------------------------------------------------------------


def test_viewer_can_claim_and_the_htmx_response_is_a_fragment(client, relation, viewer):
    response = _post(client, viewer, _url("relation_claim", relation), **HX)

    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" not in content
    assert viewer.username in content
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


def test_plain_post_redirects_to_the_plan(client, relation, viewer):
    response = _post(client, viewer, _url("relation_claim", relation))

    assert response.status_code == 302
    assert response.url == relation.get_absolute_url()
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


def test_claim_endpoints_only_accept_post(client, relation, viewer):
    client.force_login(viewer)

    assert client.get(_url("relation_claim", relation)).status_code == 405
    assert client.get(_url("relation_release", relation)).status_code == 405


def test_second_claimer_gets_a_conflict_and_the_first_claim_stands(
    client, relation, viewer, editor
):
    _claim(relation, viewer)

    response = _post(client, editor, _url("relation_claim", relation), **HX)

    assert response.status_code == 409
    assert viewer.username in response.content.decode()
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


def test_second_claimer_without_htmx_is_sent_back_with_the_claim_untouched(
    client, relation, viewer, editor
):
    _claim(relation, viewer)

    response = _post(client, editor, _url("relation_claim", relation))

    assert response.status_code == 302
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


# --- release --------------------------------------------------------------------------------


def test_claimer_and_owner_can_release(client, relation, viewer, owner):
    _claim(relation, viewer)
    assert _post(client, viewer, _url("relation_release", relation), **HX).status_code == 200
    relation.refresh_from_db()
    assert relation.claimed_by is None

    _claim(relation, viewer)
    assert _post(client, owner, _url("relation_release", relation), **HX).status_code == 200
    relation.refresh_from_db()
    assert relation.claimed_by is None


def test_editor_cannot_release_someone_elses_claim(client, relation, viewer, editor):
    _claim(relation, viewer)

    response = _post(client, editor, _url("relation_release", relation), **HX)

    assert response.status_code == 403
    relation.refresh_from_db()
    assert relation.claimed_by == viewer


# --- comments -------------------------------------------------------------------------------


def test_viewer_can_comment(client, relation, viewer):
    response = _post(
        client, viewer, _url("relation_comment_add", relation), {"text": " hello "}, **HX
    )

    assert response.status_code == 200
    assert "hello" in response.content.decode()
    (comment,) = relation.comments.all()
    assert (comment.author, comment.text) == (viewer, "hello")


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_invalid_comment_is_rejected_and_the_form_keeps_the_text(client, relation, viewer, text):
    response = _post(client, viewer, _url("relation_comment_add", relation), {"text": text}, **HX)

    assert response.status_code == 422
    assert relation.comments.count() == 0
    assert "<html" not in response.content.decode()


def test_comment_html_is_escaped_on_the_detail_page(client, relation, viewer):
    plan_coordination.add_comment(relation, viewer, "<script>alert(1)</script>")
    client.force_login(viewer)

    content = client.get(_url("relation_detail", relation)).content.decode()

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content


def test_author_and_owner_can_delete_a_comment(client, relation, viewer, owner):
    own = plan_coordination.add_comment(relation, viewer, "mine")
    other = plan_coordination.add_comment(relation, viewer, "theirs")

    own_url = _url("relation_comment_delete", relation, comment_id=own.pk)
    other_url = _url("relation_comment_delete", relation, comment_id=other.pk)
    assert _post(client, viewer, own_url, **HX).status_code == 200
    assert _post(client, owner, other_url, **HX).status_code == 200
    assert RelationComment.objects.count() == 0


def test_other_editor_cannot_delete_a_comment(client, relation, viewer, editor):
    comment = plan_coordination.add_comment(relation, viewer, "mine")

    response = _post(
        client, editor, _url("relation_comment_delete", relation, comment_id=comment.pk), **HX
    )

    assert response.status_code == 403
    assert RelationComment.objects.count() == 1


def test_a_comment_of_another_plan_cannot_be_deleted_through_this_one(client, relation, owner):
    other_plan = RelationFactory()
    _share(other_plan, owner, PermissionLevel.OWNER)
    comment = plan_coordination.add_comment(other_plan, owner, "elsewhere")

    response = _post(
        client, owner, _url("relation_comment_delete", relation, comment_id=comment.pk), **HX
    )

    assert response.status_code == 404
    assert RelationComment.objects.count() == 1


# --- access ---------------------------------------------------------------------------------

ENDPOINTS = [
    ("relation_claim", {}),
    ("relation_release", {}),
    ("relation_comment_add", {"data": {"text": "hi"}}),
]


@pytest.mark.parametrize(("name", "options"), ENDPOINTS)
def test_stranger_gets_404_on_every_endpoint(client, relation, stranger, name, options):
    response = _post(client, stranger, _url(name, relation), options.get("data"), **HX)

    assert response.status_code == 404


def test_stranger_gets_404_on_comment_delete(client, relation, viewer, stranger):
    comment = plan_coordination.add_comment(relation, viewer, "mine")

    response = _post(
        client, stranger, _url("relation_comment_delete", relation, comment_id=comment.pk), **HX
    )

    assert response.status_code == 404


def test_recipient_gets_404_everywhere_once_the_plan_is_a_surprise(client, owner):
    recipient = UserFactory()
    relation = RelationFactory(person=PersonFactory(user_link=recipient), is_surprise=True)
    _share(relation, recipient, PermissionLevel.EDITOR)
    _share(relation, owner, PermissionLevel.OWNER)
    comment = plan_coordination.add_comment(relation, owner, "shh")

    gets = [_url("relation_detail", relation), _url("relation_edit", relation)]
    posts = [
        (_url("relation_claim", relation), {}),
        (_url("relation_release", relation), {}),
        (_url("relation_comment_add", relation), {"text": "hi"}),
        (_url("relation_comment_delete", relation, comment_id=comment.pk), {}),
    ]
    client.force_login(recipient)
    for url in gets:
        assert client.get(url).status_code == 404, url
    for url, data in posts:
        assert client.post(url, data, **HX).status_code == 404, url
    relation.refresh_from_db()
    assert relation.claimed_by is None
    assert relation.comments.count() == 1


# --- display --------------------------------------------------------------------------------


def test_detail_page_shows_the_claim_and_the_comments(client, relation, viewer, editor):
    _claim(relation, editor)
    plan_coordination.add_comment(relation, editor, "I know a shop")
    client.force_login(viewer)

    response = client.get(_url("relation_detail", relation))
    content = response.content.decode()

    assert editor.username in content
    assert "I know a shop" in content
    coordination = response.context["coordination"]
    assert coordination["claimed_by"] == editor
    assert coordination["can_claim"] is False
    assert coordination["can_release"] is False
    assert [item["can_delete"] for item in coordination["comments"]] == [False]


def test_detail_page_offers_release_to_the_claimer_and_deletion_to_owners(
    client, relation, viewer, owner
):
    _claim(relation, viewer)
    plan_coordination.add_comment(relation, viewer, "mine")

    client.force_login(viewer)
    as_claimer = client.get(_url("relation_detail", relation)).context["coordination"]
    client.force_login(owner)
    as_owner = client.get(_url("relation_detail", relation)).context["coordination"]

    assert as_claimer["can_release"] is True
    assert as_claimer["comments"][0]["can_delete"] is True
    assert as_owner["can_release"] is True
    assert as_owner["comments"][0]["can_delete"] is True


def test_detail_page_shows_a_free_plan_as_claimable(client, relation, viewer):
    client.force_login(viewer)

    coordination = client.get(_url("relation_detail", relation)).context["coordination"]

    assert coordination["claimed_by"] is None
    assert coordination["can_claim"] is True
    assert coordination["can_release"] is False


def test_person_detail_cards_show_who_claimed_without_extra_queries(client, viewer):
    person = PersonFactory(shared_with=[viewer])
    plans = [RelationFactory(person=person) for _ in range(5)]
    for plan in plans:
        _share(plan, viewer, PermissionLevel.VIEWER)
        PermissionService.create_or_update_permission(
            viewer, plan.gift, permission_level=PermissionLevel.VIEWER
        )
    client.force_login(viewer)
    url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

    def queries() -> int:
        with CaptureQueriesContext(connection) as context:
            assert client.get(url).status_code == 200
        return len(context)

    unclaimed = queries()
    for plan in plans:
        _claim(plan, viewer)
    claimed = queries()

    assert claimed == unclaimed
    assert client.get(url).content.decode().count(f"Claimed by {viewer.username}") == 5
