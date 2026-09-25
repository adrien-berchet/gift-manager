"""One sharing path for every UI entry point (GM-AUD-004)."""

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.sharing_service import SharingService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return UserFactory()


@pytest.fixture
def friend(actor):
    friend = UserFactory()
    actor.profile.friends.add(friend.profile)
    return friend


def _own(actor, *objs):
    for obj in objs:
        create_or_update_permission(actor, obj, permission_level=PermissionLevel.OWNER)


@pytest.fixture
def relation(actor):
    relation = RelationFactory(person=PersonFactory(), gift=GiftFactory(), event=EventFactory())
    _own(actor, relation, relation.person, relation.gift, relation.event)
    return relation


def test_related_objects_of_a_person_relation(relation):
    assert SharingService.related_objects(relation) == [
        relation.gift,
        relation.person,
        relation.event,
    ]


def test_related_objects_of_a_group_relation(actor):
    relation = RelationFactory(person=None, group=PersonGroupFactory())

    assert relation.group in SharingService.related_objects(relation)
    assert relation.person is None


def test_non_relation_objects_have_no_cascade(actor):
    assert SharingService.related_objects(GiftFactory()) == []


def test_granting_a_relation_cascades_to_related_objects(actor, friend, relation):
    SharingService.grant(actor, relation, friend, PermissionLevel.EDITOR)

    for obj in (relation, relation.gift, relation.person, relation.event):
        assert get_permission(obj, friend) == PermissionLevel.EDITOR


def test_group_relation_cascades_to_the_group(actor, friend):
    relation = RelationFactory(person=None, group=PersonGroupFactory())
    _own(actor, relation, relation.gift, relation.event)
    create_or_update_permission(actor, relation.group, permission_level=PermissionLevel.OWNER)

    SharingService.grant(actor, relation, friend, PermissionLevel.VIEWER)

    assert get_permission(relation.group, friend) == PermissionLevel.VIEWER


def test_cascade_is_refused_without_ownership_of_related_objects(actor, friend, relation):
    create_or_update_permission(actor, relation.gift, permission_level=PermissionLevel.EDITOR)

    with pytest.raises(PermissionDenied):
        SharingService.grant(actor, relation, friend, PermissionLevel.VIEWER)

    # All or nothing: the relation itself was not shared either
    assert get_permission(relation, friend) == PermissionLevel.NONE
    assert get_permission(relation.person, friend) == PermissionLevel.NONE


def test_cascade_never_downgrades_existing_access(actor, friend, relation):
    create_or_update_permission(friend, relation.gift, permission_level=PermissionLevel.OWNER)

    SharingService.grant(actor, relation, friend, PermissionLevel.VIEWER)

    assert get_permission(relation.gift, friend) == PermissionLevel.OWNER
    assert get_permission(relation, friend) == PermissionLevel.VIEWER


def test_related_object_the_friend_already_covers_needs_no_ownership(actor, friend, relation):
    """Nothing is expanded on the gift, so editor-only access to it is enough."""
    create_or_update_permission(actor, relation.gift, permission_level=PermissionLevel.EDITOR)
    create_or_update_permission(friend, relation.gift, permission_level=PermissionLevel.EDITOR)

    SharingService.grant(actor, relation, friend, PermissionLevel.VIEWER)

    assert get_permission(relation, friend) == PermissionLevel.VIEWER


def test_plain_object_is_shared_alone(actor, friend):
    gift = GiftFactory()
    _own(actor, gift)

    SharingService.grant(actor, gift, friend, PermissionLevel.VIEWER)

    assert get_permission(gift, friend) == PermissionLevel.VIEWER


class TestEntryPointsShareTheSameGraph:
    """Create form, edit form and the sharing page must give the same permission graph."""

    def _client(self, actor):
        client = Client()
        client.force_login(actor)
        return client

    def test_create_form_cascades(self, actor, friend):
        person, gift = PersonFactory(), GiftFactory()
        _own(actor, person, gift)
        status = RelationStatus.objects.get_or_create(status="Idea")[0]

        response = self._client(actor).post(
            reverse("gift_manager:relation_create"),
            {
                "recipient": f"person:{person.person_id}",
                "gift": gift.pk,
                "status": status.pk,
                f"share_with_{friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 302, (
            getattr(response, "context", None) and response.context["form"].errors
        )
        assert get_permission(person, friend) == PermissionLevel.VIEWER
        assert get_permission(gift, friend) == PermissionLevel.VIEWER

    def test_create_form_is_refused_and_rolled_back_without_ownership(self, actor, friend):
        from gift_manager.models import Relation

        person, gift = PersonFactory(), GiftFactory()
        _own(actor, person)
        create_or_update_permission(actor, gift, permission_level=PermissionLevel.EDITOR)
        status = RelationStatus.objects.get_or_create(status="Idea")[0]

        response = self._client(actor).post(
            reverse("gift_manager:relation_create"),
            {
                "recipient": f"person:{person.person_id}",
                "gift": gift.pk,
                "status": status.pk,
                f"share_with_{friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 403
        assert not Relation.objects.filter(gift=gift).exists()
        assert get_permission(gift, friend) == PermissionLevel.NONE

    def test_edit_form_permission_field_cascades(self, actor, friend, relation):
        response = self._client(actor).post(
            reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            {
                "recipient": relation.recipient_key,
                "gift": relation.gift.pk,
                "event": relation.event.pk,
                "status": relation.status.pk,
                "due_date": relation.due_date.isoformat(),
                f"permission_{friend.id}": str(PermissionLevel.VIEWER),
            },
        )

        assert response.status_code == 302, response.context["form"].errors
        assert get_permission(relation.gift, friend) == PermissionLevel.VIEWER
        assert get_permission(relation.event, friend) == PermissionLevel.VIEWER

    def test_share_action_on_detail_page_cascades(self, actor, friend, relation):
        response = self._client(actor).post(
            reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            {"share_with": "1", "user_id": friend.id, "permission": PermissionLevel.VIEWER},
        )

        assert response.status_code in (200, 302)
        assert get_permission(relation.person, friend) == PermissionLevel.VIEWER

    def test_sharing_page_gives_the_same_graph(self, actor, friend, relation):
        self._client(actor).post(
            reverse("gift_manager:share_objects"),
            {
                "friends": [friend.id],
                "relations": [str(relation.relation_id)],
                "permission_level": str(PermissionLevel.VIEWER),
            },
        )

        for obj in (relation, relation.gift, relation.person, relation.event):
            assert get_permission(obj, friend) == PermissionLevel.VIEWER
