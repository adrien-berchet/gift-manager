"""Tests for PersonLinkAccountView, link_choices, link_label, and link badges."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gift_manager import account_links
from gift_manager.account_links import link_choices
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationPermission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_non_editor_gets_403_and_stranger_gets_404(client):
    """A stranger gets 404, the linked account gets 404, and a viewer gets 403."""
    owner = UserFactory()
    viewer = UserFactory()
    stranger = UserFactory()
    linked_user = UserFactory()
    person = PersonFactory(owner=owner, account=linked_user)
    PermissionService.create_or_update_permission(
        viewer, person, permission_level=PermissionLevel.VIEWER
    )

    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    # Stranger (no permissions) gets 404
    client.force_login(stranger)
    assert client.get(url).status_code == 404
    assert client.post(url, {"account": ""}).status_code == 404

    # Linked account has no access unless granted via permission row -> 404
    client.force_login(linked_user)
    assert client.get(url).status_code == 404
    assert client.post(url, {"account": ""}).status_code == 404

    # Viewer gets 403 PermissionDenied
    client.force_login(viewer)
    assert client.get(url).status_code == 403
    assert client.post(url, {"account": ""}).status_code == 403


def test_choices_and_disabled_states():
    """Choices start with No one, Me (for owners), then friends, disabling duplicates."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    clara = UserFactory(username="clara")
    editor = UserFactory(username="ed")

    owner.profile.friends.add(ana.profile, clara.profile)
    editor.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner)
    PermissionService.create_or_update_permission(
        editor, person, permission_level=PermissionLevel.EDITOR
    )

    # For owner: "No one", "Me", friends ordered by username
    choices = link_choices(person, owner)
    assert [c.label for c in choices] == ["No one", "Me", "ana", "clara"]
    assert choices[0].value == ""
    assert choices[0].disabled is False
    assert choices[1].value == str(owner.pk)
    assert choices[1].disabled is False
    assert choices[2].value == str(ana.pk)
    assert choices[2].disabled is False

    # If owner already owns another record linked to self, "Me" is disabled
    other_self = PersonFactory(owner=owner, account=owner)
    choices = link_choices(person, owner)
    me_choice = choices[1]
    assert me_choice.label == "Me"
    assert me_choice.disabled is True
    assert me_choice.conflicts == (other_self,)

    # If owner already owns another record linked to ana, "ana" is disabled
    other_ana = PersonFactory(owner=owner, account=ana)
    choices = link_choices(person, owner)
    ana_choice = next(c for c in choices if c.account == ana)
    assert ana_choice.disabled is True
    assert ana_choice.conflicts == (other_ana,)

    # For an editor who is not an owner: "Me" is not offered
    editor_choices = link_choices(person, editor)
    labels = [c.label for c in editor_choices]
    assert "Me" not in labels
    assert labels == ["No one", "ana"]


def test_post_links_and_redirects(client):
    """Plain POST links to friend, 302 redirects to person_detail, and sets message."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    owner.profile.friends.add(ana.profile)
    person = PersonFactory(owner=owner)

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    response = client.post(url, {"account": str(ana.pk)})

    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    assert response.status_code == 302
    assert response.url == detail_url

    person.refresh_from_db()
    assert person.account == ana

    messages = [m.message for m in get_messages(response.wsgi_request)]
    assert any("Linked to ana" in msg for msg in messages)


def test_post_htmx_returns_hx_redirect(client):
    """HTMX POST returns 204 with HX-Redirect header and sets flash message."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    owner.profile.friends.add(ana.profile)
    person = PersonFactory(owner=owner)

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    response = client.post(url, {"account": str(ana.pk)}, HTTP_HX_REQUEST="true")

    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    assert response.status_code == 204
    assert response.headers.get("HX-Redirect") == detail_url

    person.refresh_from_db()
    assert person.account == ana

    messages = [m.message for m in get_messages(response.wsgi_request)]
    assert any("Linked to ana" in msg for msg in messages)


def test_unlink_with_revealed_surprises_asks_confirmation(client):
    """Unlinking revealing surprises re-renders with warning; confirm=1 unlinks."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    owner.profile.friends.add(ana.profile)
    person = PersonFactory(owner=owner, account=ana)

    # Two surprise plans for person shared with ana
    plans = RelationFactory.create_batch(
        2,
        person=person,
        is_surprise=True,
        shared_with=[ana],
    )
    for p in plans:
        RelationPermission.objects.create(
            user=owner, relation=p, permission_type=PermissionLevel.OWNER
        )

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    # POST account="" without confirm: no changes, re-renders with warning
    response = client.post(url, {"account": ""})
    assert response.status_code == 200
    person.refresh_from_db()
    assert person.account == ana

    content = response.content.decode()
    assert "2 surprise plans shared with ana would become visible to them." in content
    assert 'name="confirm"' in content
    assert 'value="1"' in content
    assert 'name="confirm_account"' in content
    assert f'value="{ana.pk}"' in content

    # POST account="" with confirm=1 and confirm_account: unlinks
    response = client.post(
        url,
        {"account": "", "confirm": "1", "confirm_account": str(ana.pk)},
    )
    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    assert response.status_code == 302
    assert response.url == detail_url

    person.refresh_from_db()
    assert person.account is None


def test_stale_post_after_unfriending_shows_refusal(client):
    """POST for a friend removed meanwhile returns 400 and refusal message."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    owner.profile.friends.add(ana.profile)
    person = PersonFactory(owner=owner)

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    # Unfriend before POST
    owner.profile.friends.remove(ana.profile)

    response = client.post(url, {"account": str(ana.pk)})
    assert response.status_code == 400
    person.refresh_from_db()
    assert person.account is None

    content = response.content.decode()
    assert "You can only link a person to one of your friends." in content


def test_stale_post_after_another_link_asks_confirmation(client):
    """If another editor relinked to Ben meanwhile, unconfirmed POST warns about Ben."""
    owner = UserFactory(username="bob")
    editor = UserFactory(username="carol")
    ana = UserFactory(username="ana")
    ben = UserFactory(username="ben")

    owner.profile.friends.add(ana.profile, ben.profile)
    editor.profile.friends.add(ana.profile, ben.profile)

    person = PersonFactory(owner=owner)
    PermissionService.create_or_update_permission(
        editor, person, permission_level=PermissionLevel.EDITOR
    )

    # Ben has a surprise plan for person
    plan = RelationFactory(
        person=person,
        is_surprise=True,
        shared_with=[ben],
    )
    RelationPermission.objects.create(
        user=owner, relation=plan, permission_type=PermissionLevel.OWNER
    )

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    # Meanwhile, editor links person to Ben
    account_links.link(person, ben, editor)

    # Owner submits form targeting Ana without Ben's confirmation
    response = client.post(url, {"account": str(ana.pk)})
    assert response.status_code == 200
    person.refresh_from_db()
    assert person.account == ben  # Not overwritten

    content = response.content.decode()
    assert "1 surprise plan shared with ben would become visible to them." in content


def test_htmx_get_returns_partial(client):
    """GET with HX-Request returns partial template without base HTML shell."""
    owner = UserFactory(username="bob")
    person = PersonFactory(owner=owner)

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    response = client.get(url, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-form-type="person-link"' in content
    assert "<!DOCTYPE html>" not in content
    assert "<html" not in content


def test_detail_page_shows_badge_and_button(client):
    """Detail page shows link badge and appropriate action buttons."""
    owner = UserFactory(username="bob")
    viewer = UserFactory(username="carol")
    ana = UserFactory(username="ana")
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner)
    PermissionService.create_or_update_permission(
        viewer, person, permission_level=PermissionLevel.VIEWER
    )

    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

    # 1. Unlinked, viewed by owner (editor)
    client.force_login(owner)
    res = client.get(detail_url)
    assert res.status_code == 200
    c = res.content.decode()
    assert "Link account" in c
    assert "Change link" not in c
    assert "Linked to" not in c
    assert "This is you" not in c

    # 2. Linked to Ana, viewed by owner
    person.account = ana
    person.save(update_fields=["account"])
    res = client.get(detail_url)
    c = res.content.decode()
    assert "Change link" in c
    assert "Linked to ana" in c

    # 3. Linked to Ana, viewed by viewer
    client.force_login(viewer)
    res = client.get(detail_url)
    c = res.content.decode()
    assert "Linked to ana" in c
    assert "Link account" not in c
    assert "Change link" not in c

    # 4. Self-record, viewed by owner
    person.account = owner
    person.save(update_fields=["account"])
    client.force_login(owner)
    res = client.get(detail_url)
    c = res.content.decode()
    assert "This is you" in c


def test_current_link_shown_and_checked_for_non_friend_editor(client):
    """Current link is always in choices, checked and enabled, even if editor is not friend."""
    owner = UserFactory(username="bob")
    editor = UserFactory(username="carol")
    ana = UserFactory(username="ana")

    owner.profile.friends.add(ana.profile)
    # Carol is NOT friends with Ana

    person = PersonFactory(owner=owner, account=ana)
    PermissionService.create_or_update_permission(
        editor, person, permission_level=PermissionLevel.EDITOR
    )

    choices = link_choices(person, editor)
    ana_choice = next((c for c in choices if c.account == ana), None)
    assert ana_choice is not None
    assert ana_choice.disabled is False
    assert ana_choice.label == "ana"

    client.force_login(editor)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    res = client.get(url)
    content = res.content.decode()
    assert f'value="{ana.pk}"' in content
    assert "checked" in content


def test_post_without_account_returns_400(client):
    """POST missing account field returns 400 and changes nothing."""
    owner = UserFactory()
    person = PersonFactory(owner=owner)

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    res = client.post(url, {})
    assert res.status_code == 400
    person.refresh_from_db()
    assert person.account is None


def test_conflicts_not_accessible_are_not_named(client):
    """Conflicts the actor cannot access are not named or linked; generic message shows."""
    owner1 = UserFactory(username="bob")
    owner2 = UserFactory(username="carol")
    ana = UserFactory(username="ana")
    owner1.profile.friends.add(ana.profile)
    owner2.profile.friends.add(ana.profile)

    # Shared person
    person = PersonFactory(owner=owner1)
    PermissionService.create_or_update_permission(
        owner2, person, permission_level=PermissionLevel.OWNER
    )

    # Secret person owned by owner1 linked to ana, not shared with owner2
    secret_person = PersonFactory(owner=owner1, account=ana, first_name="TopSecret")

    choices = link_choices(person, owner2)
    ana_choice = next(c for c in choices if c.account == ana)
    assert ana_choice.disabled is True
    # In link_choices, conflicts only contains accessible records
    assert secret_person not in ana_choice.conflicts
    assert ana_choice.conflicts == ()

    client.force_login(owner2)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})
    res = client.get(url)
    content = res.content.decode()
    assert "TopSecret" not in content
    assert (
        "One of this person&#x27;s owners already has a person linked to this account." in content
        or "One of this person's owners already has a person linked to this account." in content
    )


def test_stale_confirm_account_asks_confirmation_again(client):
    """Stale confirm_account matching previous account does not confirm new link."""
    owner = UserFactory(username="bob")
    editor = UserFactory(username="carol")
    ana = UserFactory(username="ana")
    ben = UserFactory(username="ben")

    owner.profile.friends.add(ana.profile, ben.profile)
    editor.profile.friends.add(ana.profile, ben.profile)

    person = PersonFactory(owner=owner, account=ana)
    PermissionService.create_or_update_permission(
        editor, person, permission_level=PermissionLevel.EDITOR
    )

    # Both have surprise plans
    p1 = RelationFactory(person=person, is_surprise=True, shared_with=[ana])
    RelationPermission.objects.create(
        user=owner, relation=p1, permission_type=PermissionLevel.OWNER
    )
    p2 = RelationFactory(person=person, is_surprise=True, shared_with=[ben])
    RelationPermission.objects.create(
        user=owner, relation=p2, permission_type=PermissionLevel.OWNER
    )

    client.force_login(owner)
    url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    # Meanwhile editor relinks person to ben
    account_links.link(person, ben, editor)

    # Owner posts confirm=1 with stale confirm_account=ana.pk
    res = client.post(
        url,
        {"account": "", "confirm": "1", "confirm_account": str(ana.pk)},
    )
    assert res.status_code == 200
    person.refresh_from_db()
    assert person.account == ben  # NOT unlinked

    content = res.content.decode()
    assert "1 surprise plan shared with ben would become visible to them." in content
