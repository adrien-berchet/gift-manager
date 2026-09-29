"""Re-pointing a shared gift plan must not expose objects to its audience (GM-AUD-004).

Sharing a relation cascades access to its gift, recipient and event. Editing an
already-shared relation to point at other objects must keep that invariant: either
the actor can share the new objects with the relation's audience (and they are
cascaded), or the edit is refused.
"""

from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.forms import GiftRelationForm
from gift_manager.forms import PersonGroupRelationForm
from gift_manager.forms import PersonRelationForm
from gift_manager.forms import RelationForm
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.permissions import get_permission
from gift_manager.sharing_service import RelationExposureDenied
from gift_manager.sharing_service import SharingService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level):
    create_or_update_permission(user, obj, permission_level=level)


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def editor(owner):
    editor = UserFactory()
    owner.profile.friends.add(editor.profile)
    return editor


@pytest.fixture
def audience(owner):
    audience = UserFactory()
    owner.profile.friends.add(audience.profile)
    return audience


@pytest.fixture
def relation(owner, editor, audience):
    """A gift plan shared with an editor and a read-only audience."""
    relation = RelationFactory()
    for obj in (relation, relation.gift, relation.person, relation.event):
        _grant(owner, obj, PermissionLevel.OWNER)
    SharingService.grant(owner, relation, editor, PermissionLevel.EDITOR)
    SharingService.grant(owner, relation, audience, PermissionLevel.VIEWER)
    return relation


@pytest.fixture
def secret_gift(editor):
    """A gift someone else owns that the editor may only view."""
    gift = GiftFactory(name="SecretGiftOnlyEditorMayView")
    _grant(UserFactory(), gift, PermissionLevel.OWNER)
    _grant(editor, gift, PermissionLevel.VIEWER)
    return gift


@pytest.fixture
def secret_person(editor):
    person = PersonFactory(first_name="Secret", family_name="Recipient")
    _grant(UserFactory(), person, PermissionLevel.OWNER)
    _grant(editor, person, PermissionLevel.VIEWER)
    return person


@pytest.fixture
def secret_group(editor):
    group = PersonGroupFactory(name="SecretGroup")
    _grant(UserFactory(), group, PermissionLevel.OWNER)
    _grant(editor, group, PermissionLevel.VIEWER)
    return group


@pytest.fixture
def secret_event(editor):
    event = EventFactory(name="SecretEvent")
    _grant(UserFactory(), event, PermissionLevel.OWNER)
    _grant(editor, event, PermissionLevel.VIEWER)
    return event


def _edit_data(relation, **overrides):
    data = {
        "recipient": relation.recipient_key,
        "gift": str(relation.gift.pk),
        "event": str(relation.event.pk) if relation.event else "",
        "status": str(relation.status.pk),
        "due_date": relation.due_date.isoformat() if relation.due_date else "",
        "comment": relation.comment,
    }
    data.update(overrides)
    return data


class TestSharingServiceReassignment:
    def test_unchanged_relation_needs_no_authority(self, relation, audience):
        previous = SharingService.relation_related_ids(relation)
        stranger = UserFactory()
        relation.comment = "Only the comment changes"

        SharingService.cascade_relation_reassignment(stranger, relation, previous)

        assert get_permission(relation.gift, audience) == PermissionLevel.VIEWER

    def test_exposing_a_gift_the_actor_cannot_share_is_refused(
        self, relation, editor, audience, secret_gift
    ):
        previous = SharingService.relation_related_ids(relation)
        relation.gift = secret_gift

        with pytest.raises(RelationExposureDenied) as excinfo:
            SharingService.cascade_relation_reassignment(editor, relation, previous)

        assert excinfo.value.attribute == "gift"
        assert get_permission(secret_gift, audience) == PermissionLevel.NONE

    def test_owned_gift_is_cascaded_to_the_audience(self, relation, owner, editor, audience):
        new_gift = GiftFactory()
        _grant(editor, new_gift, PermissionLevel.OWNER)
        previous = SharingService.relation_related_ids(relation)
        relation.gift = new_gift

        SharingService.cascade_relation_reassignment(editor, relation, previous)

        assert get_permission(new_gift, audience) == PermissionLevel.VIEWER
        assert get_permission(new_gift, owner) == PermissionLevel.OWNER
        # The actor's own access is left alone
        assert get_permission(new_gift, editor) == PermissionLevel.OWNER

    def test_audience_already_covering_the_new_object_needs_no_authority(
        self, relation, editor, audience, owner, secret_gift
    ):
        _grant(audience, secret_gift, PermissionLevel.EDITOR)
        _grant(owner, secret_gift, PermissionLevel.OWNER)
        previous = SharingService.relation_related_ids(relation)
        relation.gift = secret_gift

        SharingService.cascade_relation_reassignment(editor, relation, previous)

        # Never downgraded
        assert get_permission(secret_gift, audience) == PermissionLevel.EDITOR

    def test_group_recipient_is_cascaded_on_the_group(self, relation, editor, audience):
        group = PersonGroupFactory()
        _grant(editor, group, PermissionLevel.OWNER)
        previous = SharingService.relation_related_ids(relation)
        relation.person = None
        relation.group = group

        SharingService.cascade_relation_reassignment(editor, relation, previous)

        assert get_permission(group, audience) == PermissionLevel.VIEWER

    def test_refusal_is_all_or_nothing(self, relation, editor, audience, secret_event):
        new_gift = GiftFactory()
        _grant(editor, new_gift, PermissionLevel.OWNER)
        previous = SharingService.relation_related_ids(relation)
        relation.gift = new_gift
        relation.event = secret_event

        with pytest.raises(RelationExposureDenied) as excinfo:
            SharingService.cascade_relation_reassignment(editor, relation, previous)

        assert excinfo.value.attribute == "event"
        assert get_permission(new_gift, audience) == PermissionLevel.NONE


class TestRelationFormReassignment:
    def _form(self, relation, user, **overrides):
        return RelationForm(data=_edit_data(relation, **overrides), instance=relation, user=user)

    def test_gift_change_exposing_it_is_a_gift_error(self, relation, editor, secret_gift):
        form = self._form(relation, editor, gift=str(secret_gift.pk))

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_recipient_change_exposing_it_is_a_recipient_error(
        self, relation, editor, secret_person
    ):
        form = self._form(relation, editor, recipient=f"person:{secret_person.person_id}")

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_group_recipient_change_exposing_it_is_a_recipient_error(
        self, relation, editor, secret_group
    ):
        form = self._form(relation, editor, recipient=f"group:{secret_group.group_id}")

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_event_change_exposing_it_is_an_event_error(self, relation, editor, secret_event):
        form = self._form(relation, editor, event=str(secret_event.pk))

        assert not form.is_valid()
        assert "event" in form.errors

    def test_edit_without_related_changes_is_valid(self, relation, editor):
        form = self._form(relation, editor, comment="New comment")

        assert form.is_valid(), form.errors

    def test_owned_gift_change_is_valid_and_cascaded_on_save(self, relation, editor, audience):
        new_gift = GiftFactory()
        _grant(editor, new_gift, PermissionLevel.OWNER)
        form = self._form(relation, editor, gift=str(new_gift.pk))

        assert form.is_valid(), form.errors
        form.save()

        assert get_permission(new_gift, audience) == PermissionLevel.VIEWER


class TestScopedRelationFormsReassignment:
    """The person, group and gift specific forms must apply the same rule to an instance."""

    def test_person_relation_form_rejects_exposing_gift(self, relation, editor, secret_gift):
        form = PersonRelationForm(
            data=_edit_data(relation, gift=str(secret_gift.pk)),
            instance=relation,
            person_id=relation.person.person_id,
            user=editor,
        )

        assert not form.is_valid()
        assert "gift" in form.errors

    def test_person_group_relation_form_rejects_exposing_event(
        self, owner, editor, audience, secret_event
    ):
        relation = RelationFactory(person=None, group=PersonGroupFactory())
        for obj in (relation, relation.gift, relation.group, relation.event):
            _grant(owner, obj, PermissionLevel.OWNER)
        SharingService.grant(owner, relation, editor, PermissionLevel.EDITOR)
        SharingService.grant(owner, relation, audience, PermissionLevel.VIEWER)

        form = PersonGroupRelationForm(
            data=_edit_data(relation, event=str(secret_event.pk)),
            instance=relation,
            group_id=relation.group.group_id,
            user=editor,
        )

        assert not form.is_valid()
        assert "event" in form.errors

    def test_gift_relation_form_rejects_exposing_recipient(self, relation, editor, secret_person):
        form = GiftRelationForm(
            data=_edit_data(relation, recipient=f"person:{secret_person.person_id}"),
            instance=relation,
            gift_id=relation.gift.gift_id,
            user=editor,
        )

        assert not form.is_valid()
        assert "recipient" in form.errors

    def test_person_relation_form_rejects_exposing_a_new_person(
        self, relation, editor, secret_person
    ):
        """The URL-bound person is a relation change too (non-field error)."""
        form = PersonRelationForm(
            data=_edit_data(relation),
            instance=relation,
            person_id=secret_person.person_id,
            user=editor,
        )

        assert not form.is_valid()
        assert form.non_field_errors()


class TestRelationEditView:
    def _post(self, user, relation, **overrides):
        return _client(user).post(
            reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            _edit_data(relation, **overrides),
        )

    def test_editor_cannot_expose_unshared_gift_by_reassigning_relation(
        self, relation, editor, audience, secret_gift
    ):
        """The exact audit probe scenario."""
        original_gift_id = relation.gift_id

        response = self._post(editor, relation, gift=str(secret_gift.pk))

        assert response.status_code == 200
        assert "gift" in response.context["form"].errors
        relation.refresh_from_db()
        assert relation.gift_id == original_gift_id
        assert get_permission(secret_gift, audience) == PermissionLevel.NONE
        detail = _client(audience).get(
            reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
        )
        assert "SecretGiftOnlyEditorMayView" not in detail.content.decode()

    def test_editor_cannot_expose_unshared_recipient(
        self, relation, editor, audience, secret_person
    ):
        original_person_id = relation.person_id

        response = self._post(editor, relation, recipient=f"person:{secret_person.person_id}")

        assert response.status_code == 200
        assert "recipient" in response.context["form"].errors
        relation.refresh_from_db()
        assert relation.person_id == original_person_id
        assert get_permission(secret_person, audience) == PermissionLevel.NONE

    def test_editor_cannot_expose_unshared_event(self, relation, editor, audience, secret_event):
        original_event_id = relation.event_id

        response = self._post(editor, relation, event=str(secret_event.pk))

        assert response.status_code == 200
        assert "event" in response.context["form"].errors
        relation.refresh_from_db()
        assert relation.event_id == original_event_id
        assert get_permission(secret_event, audience) == PermissionLevel.NONE

    def test_htmx_refusal_is_a_form_error(self, relation, editor, secret_gift):
        response = _client(editor).post(
            reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
            _edit_data(relation, gift=str(secret_gift.pk)),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 422

    def test_editor_owning_the_new_gift_cascades_it_to_the_audience(
        self, relation, owner, editor, audience
    ):
        new_gift = GiftFactory(name="EditorOwnedGift")
        _grant(editor, new_gift, PermissionLevel.OWNER)

        response = self._post(editor, relation, gift=str(new_gift.pk))

        assert response.status_code == 302
        relation.refresh_from_db()
        assert relation.gift_id == new_gift.pk
        assert get_permission(new_gift, audience) == PermissionLevel.VIEWER
        assert get_permission(new_gift, owner) == PermissionLevel.OWNER

    def test_edit_that_changes_nothing_related_still_works(self, relation, editor):
        response = self._post(editor, relation, comment="Only the comment changes")

        assert response.status_code == 302
        relation.refresh_from_db()
        assert relation.comment == "Only the comment changes"

    def test_unshared_relation_can_be_repointed_freely(self, editor, secret_gift):
        """With no audience nothing is exposed, so viewer access to the gift is enough."""
        relation = RelationFactory()
        for obj in (relation, relation.gift, relation.person, relation.event):
            _grant(editor, obj, PermissionLevel.OWNER)

        response = self._post(editor, relation, gift=str(secret_gift.pk))

        assert response.status_code == 302
        relation.refresh_from_db()
        assert relation.gift_id == secret_gift.pk


class TestPlanQuickAction:
    @pytest.fixture
    def idea_relation(self, relation):
        RelationStatus.objects.get_or_create(status="Planned")
        relation.status = RelationStatus.objects.get_or_create(status="Idea")[0]
        relation.event = None
        relation.due_date = None
        relation.save(update_fields=["status", "event", "due_date"])
        return relation

    def _plan(self, user, relation, event):
        return _client(user).post(
            reverse("gift_manager:relation_quick_action", kwargs={"pk": relation.relation_id}),
            {"action": "plan", "event": str(event.event_id), "due_date": "2026-12-24"},
            HTTP_HX_REQUEST="true",
        )

    def test_plan_cannot_expose_unshared_event(self, idea_relation, editor, audience, secret_event):
        response = self._plan(editor, idea_relation, secret_event)

        assert response.status_code == 400
        assert "not allowed to share" in response.content.decode()
        idea_relation.refresh_from_db()
        assert idea_relation.event is None
        assert idea_relation.due_date is None
        assert get_permission(secret_event, audience) == PermissionLevel.NONE

    def test_plan_with_owned_event_cascades_it(self, idea_relation, editor, audience):
        event = EventFactory()
        _grant(editor, event, PermissionLevel.OWNER)

        response = self._plan(editor, idea_relation, event)

        assert response.status_code == 200
        idea_relation.refresh_from_db()
        assert idea_relation.event == event
        assert idea_relation.due_date == date(2026, 12, 24)
        assert get_permission(event, audience) == PermissionLevel.VIEWER


def test_relation_is_left_untouched_in_database_after_refusal(relation, editor, secret_gift):
    before = Relation.objects.values().get(pk=relation.pk)

    _client(editor).post(
        reverse("gift_manager:relation_edit", kwargs={"pk": relation.relation_id}),
        _edit_data(relation, gift=str(secret_gift.pk), comment="changed"),
    )

    assert Relation.objects.values().get(pk=relation.pk) == before
