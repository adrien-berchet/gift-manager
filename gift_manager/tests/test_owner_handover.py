"""The only owner of a shared object hands it over to someone before leaving it."""

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HANDOVER_LABEL = "Hand over and remove my access"


def _grant(user, obj, level):
    PermissionService.create_or_update_permission(user, obj, permission_level=level)
    return obj


def _friend(owner, label="friend"):
    user = UserFactory(username=label)
    owner.profile.friends.add(user.profile)
    return user


@pytest.fixture
def owner():
    return UserFactory(username="owner")


@pytest.fixture
def editor(owner):
    return _friend(owner, "editor")


@pytest.fixture
def viewer(owner):
    return _friend(owner, "viewer")


@pytest.fixture
def mom(owner, editor, viewer):
    person = _grant(owner, PersonFactory(first_name="Mom"), PermissionLevel.OWNER)
    _grant(viewer, person, PermissionLevel.VIEWER)
    _grant(editor, person, PermissionLevel.EDITOR)
    return person


def _delete_url(person):
    return reverse("gift_manager:person_delete", kwargs={"pk": person.person_id})


class TestHandoverMode:
    def test_sole_owner_of_a_shared_object_can_hand_it_over(self, owner, editor, viewer, mom):
        assert PermissionService.delete_mode_for(owner, mom) == ("handover", None)
        assert PermissionService.handover_candidates(owner, mom) == [editor, viewer]

    def test_without_a_direct_sharer_there_is_nobody_to_hand_over_to(self, owner):
        gift = _grant(owner, GiftFactory(), PermissionLevel.OWNER)

        assert PermissionService.handover_candidates(owner, gift) == []
        assert PermissionService.delete_mode_for(owner, gift)[0] == "delete"

    def test_former_friends_are_not_offered(self, owner, editor, viewer, mom):
        owner.profile.friends.remove(editor.profile)

        assert PermissionService.handover_candidates(owner, mom) == [viewer]

    def test_detail_page_offers_the_handover(self, client, owner, mom):
        client.force_login(owner)

        response = client.get(reverse("gift_manager:person_detail", kwargs={"pk": mom.person_id}))

        [button] = [
            b for b in response.context["action_buttons"] if b["type"] in {"delete", "leave"}
        ]
        assert button["type"] == "leave"
        assert button["label"] == HANDOVER_LABEL
        assert button["url"] == f"{_delete_url(mom)}?intent=leave_access"


class TestHandoverConfirmation:
    def test_page_asks_who_becomes_the_owner_editors_first(
        self, client, owner, editor, viewer, mom
    ):
        client.force_login(owner)

        content = client.get(_delete_url(mom), {"intent": "leave_access"}).content.decode()

        assert HANDOVER_LABEL in content
        assert 'name="new_owner"' in content
        assert content.index(f'value="{editor.pk}"') < content.index(f'value="{viewer.pk}"')
        assert f'<option value="{editor.pk}" selected>' in content

    def test_modal_select_belongs_to_the_delete_form(self, client, owner, mom):
        client.force_login(owner)

        content = client.get(
            _delete_url(mom), {"intent": "leave_access"}, HTTP_HX_REQUEST="true"
        ).content.decode()

        assert 'name="new_owner"' in content
        assert 'form="deleteForm"' in content
        assert f'data-confirm-label="{HANDOVER_LABEL}"' in content

    def test_handing_over_promotes_the_new_owner_then_removes_my_access(
        self, client, owner, viewer, mom
    ):
        client.force_login(owner)

        response = client.post(_delete_url(mom), {"intent": "leave_access", "new_owner": viewer.pk})

        assert response.status_code == 302
        assert Person.objects.filter(pk=mom.pk).exists()
        assert PermissionService.get_permission(mom, owner) == PermissionLevel.NONE
        assert PermissionService.get_permission(mom, viewer) == PermissionLevel.OWNER

    @pytest.mark.parametrize("new_owner", ["", "stranger", "self"])
    def test_handover_needs_a_valid_new_owner(self, client, owner, mom, new_owner):
        stranger = UserFactory()
        value = {"": "", "stranger": stranger.pk, "self": owner.pk}[new_owner]
        client.force_login(owner)

        response = client.post(_delete_url(mom), {"intent": "leave_access", "new_owner": value})

        assert response.status_code == 403
        assert PermissionService.get_permission(mom, owner) == PermissionLevel.OWNER
        assert PermissionService.get_permission(mom, stranger) == PermissionLevel.NONE

    def test_new_owner_is_ignored_when_no_handover_is_needed(
        self, client, owner, editor, viewer, mom
    ):
        _grant(editor, mom, PermissionLevel.OWNER)  # two owners: nothing to hand over
        client.force_login(owner)

        client.post(_delete_url(mom), {"intent": "leave_access", "new_owner": viewer.pk})

        assert PermissionService.get_permission(mom, owner) == PermissionLevel.NONE
        assert PermissionService.get_permission(mom, viewer) == PermissionLevel.VIEWER


class TestHandoverEdgeCases:
    def test_inherited_group_owner_cannot_hand_over(self, owner):
        from gift_manager.models import PersonGroupPermission
        from gift_manager.tests.factories import PersonGroupFactory

        friend = _friend(owner, "cousin")
        parent = PersonGroupFactory(name="Family")
        child = PersonGroupFactory(name="Cousins")
        child.parent_groups.add(parent)
        PersonGroupPermission.objects.create(
            user=owner,
            group=parent,
            permission_type=PermissionLevel.OWNER,
            inherit_permissions=True,
        )
        _grant(friend, child, PermissionLevel.VIEWER)

        mode, reason = PermissionService.delete_mode_for(owner, child)

        assert mode == "none"
        assert reason == "This group access is inherited from a parent group."

    def test_superuser_without_ownership_is_not_asked_to_hand_over(self, owner, viewer, mom):
        admin = UserFactory(is_superuser=True)
        admin.profile.friends.add(viewer.profile)
        _grant(admin, mom, PermissionLevel.VIEWER)

        assert PermissionService.delete_mode_for(admin, mom)[0] == "leave"

    def test_an_inactive_co_owner_does_not_count(self, owner, editor, mom):
        former = UserFactory(is_active=False)
        _grant(former, mom, PermissionLevel.OWNER)

        assert PermissionService.delete_mode_for(owner, mom)[0] == "handover"

    def test_candidate_unfriended_after_the_page_loaded_is_refused(
        self, client, owner, editor, mom
    ):
        client.force_login(owner)
        client.get(_delete_url(mom), {"intent": "leave_access"})
        owner.profile.friends.remove(editor.profile)

        response = client.post(_delete_url(mom), {"intent": "leave_access", "new_owner": editor.pk})

        assert response.status_code == 403
        assert PermissionService.get_permission(mom, editor) == PermissionLevel.EDITOR
        assert PermissionService.get_permission(mom, owner) == PermissionLevel.OWNER


@pytest.mark.parametrize(
    ("who", "label"),
    [("editor", "Remove my access"), ("owner", HANDOVER_LABEL)],
)
def test_edit_form_delete_button_follows_the_delete_mode(client, owner, editor, mom, who, label):
    client.force_login({"owner": owner, "editor": editor}[who])

    content = client.get(
        reverse("gift_manager:person_edit", kwargs={"pk": mom.person_id}), HTTP_HX_REQUEST="true"
    ).content.decode()

    assert f'href="{_delete_url(mom)}?intent=leave_access"' in content
    assert label in content


def test_edit_form_disables_delete_when_nobody_can_take_over(client, owner, editor, mom):
    owner.profile.friends.clear()
    client.force_login(owner)

    content = client.get(
        reverse("gift_manager:person_edit", kwargs={"pk": mom.person_id}), HTTP_HX_REQUEST="true"
    ).content.decode()

    assert f'href="{_delete_url(mom)}' not in content
    assert 'title="At least one owner is required."' in content
