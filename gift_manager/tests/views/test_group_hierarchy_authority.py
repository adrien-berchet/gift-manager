"""View and form level regression tests for GM-AUD-001."""

import json

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.forms import PersonGroupAddMultipleChildGroupsForm
from gift_manager.forms import PersonGroupAddMultiplePersonsForm
from gift_manager.forms import PersonGroupForm
from gift_manager.models import PersonGroupPermission
from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _grant(user, obj, level, *, inherit=False):
    create_or_update_permission(user, obj, permission_level=level)
    if inherit:
        PersonGroupPermission.objects.filter(user=user, group=obj).update(inherit_permissions=True)


@pytest.fixture
def actor():
    return UserFactory()


@pytest.fixture
def client(actor):
    client = Client()
    client.force_login(actor)
    return client


def _reparent(client, group, parents, action="set"):
    return client.post(
        reverse("gift_manager:api_reparent_group"),
        json.dumps(
            {
                "group_id": str(group.group_id),
                "parent_ids": [str(p.group_id) for p in parents],
                "action": action,
            }
        ),
        content_type="application/json",
    )


class TestReparentEndpoint:
    def test_viewer_only_parent_is_forbidden(self, actor, client):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.VIEWER)
        _grant(actor, child, PermissionLevel.EDITOR)

        response = _reparent(client, child, [parent])

        assert response.status_code == 403
        assert not child.parent_groups.exists()

    def test_editor_cannot_expand_inherited_access(self, actor, client):
        other = UserFactory()
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        response = _reparent(client, child, [parent], action="add")

        assert response.status_code == 403
        assert not child.parent_groups.exists()

    def test_editor_on_both_sides_succeeds(self, actor, client):
        parent, child = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, child, PermissionLevel.EDITOR)

        response = _reparent(client, child, [parent])

        assert response.status_code == 200
        assert child.parent_groups.filter(pk=parent.pk).exists()


class TestMemberViews:
    def test_remove_person_without_access_is_refused(self, actor, client):
        group, person = PersonGroupFactory(), PersonFactory()
        person.groups.add(group)
        _grant(actor, group, PermissionLevel.EDITOR)

        response = client.post(
            reverse(
                "gift_manager:remove_person_group_person",
                kwargs={"pk": group.group_id, "person_id": person.person_id},
            )
        )

        assert response.status_code in (302, 404)
        assert group.person_set.filter(pk=person.pk).exists()

    def test_remove_person_with_editor_access_succeeds(self, actor, client):
        group, person = PersonGroupFactory(), PersonFactory()
        person.groups.add(group)
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, person, PermissionLevel.EDITOR)

        client.post(
            reverse(
                "gift_manager:remove_person_group_person",
                kwargs={"pk": group.group_id, "person_id": person.person_id},
            )
        )

        assert not group.person_set.filter(pk=person.pk).exists()


class TestForms:
    def test_group_form_offers_only_editable_choices(self, actor):
        group = PersonGroupFactory()
        editable, viewer_only = PersonGroupFactory(), PersonGroupFactory()
        editable_person, viewer_person = PersonFactory(), PersonFactory()
        for obj in (group, editable):
            _grant(actor, obj, PermissionLevel.EDITOR)
        _grant(actor, viewer_only, PermissionLevel.VIEWER)
        _grant(actor, editable_person, PermissionLevel.EDITOR)
        _grant(actor, viewer_person, PermissionLevel.VIEWER)

        form = PersonGroupForm(instance=group, user=actor)

        assert set(form.fields["parent_groups"].queryset) == {editable}
        assert set(form.fields["child_groups"].queryset) == {editable}
        assert set(form.fields["persons"].queryset) == {editable_person}

    def test_group_form_save_keeps_links_hidden_from_choices(self, actor):
        """Existing links to objects the actor cannot edit survive an unrelated save."""
        group, viewer_parent = PersonGroupFactory(), PersonGroupFactory()
        viewer_person = PersonFactory()
        group.parent_groups.add(viewer_parent)
        viewer_person.groups.add(group)
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, viewer_parent, PermissionLevel.VIEWER)
        _grant(actor, viewer_person, PermissionLevel.VIEWER)

        form = PersonGroupForm(
            data={"name": "Renamed", "parent_groups": [], "child_groups": [], "persons": []},
            instance=group,
            user=actor,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert group.parent_groups.filter(pk=viewer_parent.pk).exists()
        assert group.person_set.filter(pk=viewer_person.pk).exists()

    def test_group_form_save_applies_editable_changes(self, actor):
        group, parent = PersonGroupFactory(), PersonGroupFactory()
        person = PersonFactory()
        for obj in (group, parent, person):
            _grant(actor, obj, PermissionLevel.EDITOR)

        form = PersonGroupForm(
            data={
                "name": group.name,
                "parent_groups": [parent.pk],
                "child_groups": [],
                "persons": [person.pk],
            },
            instance=group,
            user=actor,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert group.parent_groups.filter(pk=parent.pk).exists()
        assert group.person_set.filter(pk=person.pk).exists()

    def test_group_form_rejects_viewer_only_parent(self, actor):
        group, parent = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, parent, PermissionLevel.VIEWER)

        form = PersonGroupForm(
            data={"name": group.name, "parent_groups": [parent.pk]},
            instance=group,
            user=actor,
        )

        assert not form.is_valid()
        assert "parent_groups" in form.errors

    def test_create_new_group_under_editable_parent(self, actor):
        parent = PersonGroupFactory()
        _grant(actor, parent, PermissionLevel.EDITOR)

        form = PersonGroupForm(data={"name": "Brand new", "parent_groups": [parent.pk]}, user=actor)
        assert form.is_valid(), form.errors
        instance = form.save()

        assert instance.parent_groups.filter(pk=parent.pk).exists()

    def test_add_multiple_persons_form_offers_only_editable(self, actor):
        group = PersonGroupFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        editable, viewer_only = PersonFactory(), PersonFactory()
        _grant(actor, editable, PermissionLevel.EDITOR)
        _grant(actor, viewer_only, PermissionLevel.VIEWER)

        form = PersonGroupAddMultiplePersonsForm(user=actor, group=group)

        assert set(form.fields["persons"].queryset) == {editable}

    def test_add_multiple_child_groups_form_offers_only_editable(self, actor):
        group, editable, viewer_only = (PersonGroupFactory() for _ in range(3))
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(actor, editable, PermissionLevel.EDITOR)
        _grant(actor, viewer_only, PermissionLevel.VIEWER)

        form = PersonGroupAddMultipleChildGroupsForm(user=actor, group=group)

        assert set(form.fields["child_groups"].queryset) == {editable}


class TestPersonFormGroups:
    """PersonForm must not bypass group authority (review finding)."""

    def _form(self, actor, person, groups):
        from gift_manager.forms import PersonForm

        form = PersonForm(
            data={
                "first_name": person.first_name,
                "family_name": person.family_name,
                "groups": [g.pk for g in groups],
            },
            instance=person,
        )
        form.set_user(actor)
        return form

    def test_only_editable_groups_are_offered(self, actor):
        from gift_manager.forms import PersonForm

        person = PersonFactory()
        editable, viewer_only = PersonGroupFactory(), PersonGroupFactory()
        _grant(actor, person, PermissionLevel.EDITOR)
        _grant(actor, editable, PermissionLevel.EDITOR)
        _grant(actor, viewer_only, PermissionLevel.VIEWER)
        form = PersonForm(instance=person)
        form.set_user(actor)

        assert set(form.fields["groups"].queryset) == {editable}

    def test_viewer_only_group_cannot_be_added(self, actor):
        person, viewer_group = PersonFactory(), PersonGroupFactory()
        _grant(actor, person, PermissionLevel.EDITOR)
        _grant(actor, viewer_group, PermissionLevel.VIEWER)

        form = self._form(actor, person, [viewer_group])

        assert not form.is_valid()
        assert "groups" in form.errors

    def test_hidden_and_viewer_memberships_survive_save(self, actor):
        person, hidden, viewer_group = PersonFactory(), PersonGroupFactory(), PersonGroupFactory()
        editable = PersonGroupFactory()
        person.groups.add(hidden, viewer_group)
        _grant(actor, person, PermissionLevel.EDITOR)
        _grant(actor, viewer_group, PermissionLevel.VIEWER)
        _grant(actor, editable, PermissionLevel.EDITOR)

        form = self._form(actor, person, [editable])
        assert form.is_valid(), form.errors
        form.save()

        assert set(person.groups.all()) == {hidden, viewer_group, editable}

    def test_editable_membership_can_be_removed(self, actor):
        person, editable = PersonFactory(), PersonGroupFactory()
        person.groups.add(editable)
        _grant(actor, person, PermissionLevel.EDITOR)
        _grant(actor, editable, PermissionLevel.EDITOR)

        form = self._form(actor, person, [])
        assert form.is_valid(), form.errors
        form.save()

        assert not person.groups.exists()

    def test_create_person_in_editable_group(self, actor):
        from gift_manager.forms import PersonForm

        group = PersonGroupFactory()
        _grant(actor, group, PermissionLevel.EDITOR)
        form = PersonForm(data={"first_name": "New", "family_name": "Person", "groups": [group.pk]})
        form.set_user(actor)

        assert form.is_valid(), form.errors
        person = form.save()

        assert person.groups.filter(pk=group.pk).exists()


class TestFormErrorsInsteadOfPartialSave:
    def test_expansion_denied_is_a_form_error_and_nothing_is_saved(self, actor):
        other = UserFactory()
        parent, group = PersonGroupFactory(), PersonGroupFactory(name="Before")
        _grant(actor, parent, PermissionLevel.EDITOR)
        _grant(actor, group, PermissionLevel.EDITOR)
        _grant(other, parent, PermissionLevel.EDITOR, inherit=True)

        form = PersonGroupForm(
            data={"name": "After", "parent_groups": [parent.pk]}, instance=group, user=actor
        )

        assert not form.is_valid()
        assert "parent_groups" in form.errors
        group.refresh_from_db()
        assert group.name == "Before"


class TestReparentSetWithHiddenParents:
    def test_set_preserves_parents_the_actor_cannot_edit(self, actor, client):
        hidden_parent, new_parent, child = (PersonGroupFactory() for _ in range(3))
        child.parent_groups.add(hidden_parent)
        _grant(actor, child, PermissionLevel.EDITOR)
        _grant(actor, new_parent, PermissionLevel.EDITOR)

        response = _reparent(client, child, [new_parent], action="set")

        assert response.status_code == 200
        assert set(child.parent_groups.all()) == {hidden_parent, new_parent}
