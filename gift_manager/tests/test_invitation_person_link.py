"""Tests for inviting from a person page and linking the record on acceptance."""

import uuid
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from gift_manager.email_encoding import encode_email
from gift_manager.invitations import accept_invitation_for_user
from gift_manager.models import Invitation
from gift_manager.models import PermissionLevel
from gift_manager.models import PersonPermission
from gift_manager.models import Profile
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """Clear any leftover invitation-send cache keys between tests."""
    cache.clear()


def test_invite_button_conditions(client):
    """The 'Invite to Gift Manager' button is shown only to editors of unlinked records

    with an email belonging neither to the viewer nor to any friend.
    """
    owner = UserFactory(username="alice")
    viewer = UserFactory(username="bob")
    friend = UserFactory(username="carol")
    owner.profile.friends.add(friend.profile)
    EmailAddress.objects.create(user=friend, email="carol@example.com", verified=True)

    # 1. Eligible person: unlinked, email belongs to stranger
    person = PersonFactory(owner=owner, email_address=encode_email("stranger@example.com"))

    client.force_login(owner)
    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    response = client.get(detail_url)
    assert response.status_code == 200
    invite_url = reverse("gift_manager:send_invitation") + f"?person={person.person_id}"
    assert invite_url in response.content.decode()
    assert "Invite to Gift Manager" in response.content.decode()

    # 2. Hidden when viewer is only a viewer (not editor/owner)
    PersonPermission.objects.create(
        person=person, user=viewer, permission_type=PermissionLevel.VIEWER
    )
    client.force_login(viewer)
    response = client.get(detail_url)
    assert invite_url not in response.content.decode()

    # Back to owner login
    client.force_login(owner)

    # 3. Hidden without email
    person_no_email = PersonFactory(owner=owner, email_address="")
    url_no_email = reverse("gift_manager:person_detail", kwargs={"pk": person_no_email.person_id})
    response = client.get(url_no_email)
    assert "Invite to Gift Manager" not in response.content.decode()

    # 4. Hidden when already linked
    person_linked = PersonFactory(
        owner=owner, email_address=encode_email("linked@example.com"), account=friend
    )
    url_linked = reverse("gift_manager:person_detail", kwargs={"pk": person_linked.person_id})
    response = client.get(url_linked)
    assert "Invite to Gift Manager" not in response.content.decode()

    # 5. Hidden when email belongs to viewer
    EmailAddress.objects.create(user=owner, email="alice@example.com", verified=True)
    person_self_email = PersonFactory(owner=owner, email_address=encode_email("alice@example.com"))
    url_self = reverse("gift_manager:person_detail", kwargs={"pk": person_self_email.person_id})
    response = client.get(url_self)
    assert "Invite to Gift Manager" not in response.content.decode()

    # 6. Hidden when email belongs to an existing friend
    person_friend_email = PersonFactory(
        owner=owner, email_address=encode_email("carol@example.com")
    )
    url_friend = reverse("gift_manager:person_detail", kwargs={"pk": person_friend_email.person_id})
    response = client.get(url_friend)
    assert "Invite to Gift Manager" not in response.content.decode()


@patch("gift_manager.views.profile.send_mail")
def test_send_invitation_prefills_from_person(mock_send_mail, client):
    """GET ?person=<uuid> pre-fills recipient_email and hidden person field.

    POST saves Invitation.person only when sender is OWNER, leaving it NULL for editors.
    A forged or nonexistent UUID is ignored.
    """
    owner = UserFactory(username="alice")
    editor = UserFactory(username="ed")
    person = PersonFactory(owner=owner, email_address=encode_email("newbie@example.com"))
    PersonPermission.objects.create(
        person=person, user=editor, permission_type=PermissionLevel.EDITOR
    )

    # GET by owner
    client.force_login(owner)
    get_url = reverse("gift_manager:send_invitation") + f"?person={person.person_id}"
    response = client.get(get_url)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'value="newbie@example.com"' in content
    assert f'value="{person.person_id}"' in content
    assert 'name="person"' in content

    # GET with invalid UUID falls back cleanly
    response_invalid = client.get(reverse("gift_manager:send_invitation") + "?person=not-a-uuid")
    assert response_invalid.status_code == 200

    # POST by owner stores Invitation.person
    response = client.post(
        reverse("gift_manager:send_invitation"),
        {
            "recipient_email": "newbie@example.com",
            "person": str(person.person_id),
        },
    )
    assert response.status_code == 302
    invitation = Invitation.objects.get(sender=owner)
    assert invitation.person == person
    assert invitation.email == "newbie@example.com"
    invitation.delete()

    # POST by editor (not OWNER) leaves Invitation.person NULL
    client.force_login(editor)
    response = client.post(
        reverse("gift_manager:send_invitation"),
        {
            "recipient_email": "newbie@example.com",
            "person": str(person.person_id),
        },
    )
    assert response.status_code == 302
    invitation_ed = Invitation.objects.get(sender=editor)
    assert invitation_ed.person is None
    invitation_ed.delete()

    # POST with forged UUID leaves Invitation.person NULL
    client.force_login(owner)
    forged_uuid = uuid.uuid4()
    response = client.post(
        reverse("gift_manager:send_invitation"),
        {
            "recipient_email": "newbie@example.com",
            "person": str(forged_uuid),
        },
    )
    assert response.status_code == 302
    invitation_forged = Invitation.objects.get(sender=owner)
    assert invitation_forged.person is None


def test_accepting_links_the_record_existing_user():
    """An existing user accepting an invitation linked to a person links that person."""
    sender = UserFactory(username="alice")
    recipient = UserFactory(username="bob")
    EmailAddress.objects.create(user=recipient, email="bob@example.com", verified=True)
    person = PersonFactory(owner=sender, email_address=encode_email("bob@example.com"))

    invitation = Invitation.objects.create(
        sender=sender,
        recipient_email=encode_email("bob@example.com"),
        person=person,
    )

    success = accept_invitation_for_user(invitation, recipient)
    assert success is True

    invitation.refresh_from_db()
    assert invitation.accepted is True
    person.refresh_from_db()
    assert person.account == recipient

    # Friendship exists in both directions
    sender_profile = Profile.objects.get(user=sender)
    recipient_profile = Profile.objects.get(user=recipient)
    assert recipient_profile in sender_profile.friends.all()
    assert sender_profile in recipient_profile.friends.all()


@override_settings(USE_I18N=False)
def test_accepting_links_the_record_new_user(client):
    """A new user signing up and confirming email claims the invitation and links the person."""
    sender = UserFactory(username="alice")
    person = PersonFactory(owner=sender, email_address=encode_email("newbie@example.com"))
    invitation = Invitation.objects.create(
        sender=sender,
        recipient_email=encode_email("newbie@example.com"),
        person=person,
    )

    accept_url = reverse("gift_manager:accept_invitation", kwargs={"token": invitation.token})
    client.get(accept_url)

    response = client.post(
        reverse("account_signup"),
        {
            "username": "newbie_user",
            "email": "newbie@example.com",
            "email2": "newbie@example.com",
            "password1": "StrongPassword123!",
            "password2": "StrongPassword123!",
        },
    )
    assert response.status_code == 302

    new_user = User.objects.get(username="newbie_user")
    email_address = EmailAddress.objects.get(user=new_user, email="newbie@example.com")
    email_address.verified = True
    email_address.save(update_fields=["verified"])

    request = Mock(GET={}, POST={}, session=client.session)
    email_confirmed.send(sender=EmailAddress, request=request, email_address=email_address)

    invitation.refresh_from_db()
    assert invitation.accepted is True
    person.refresh_from_db()
    assert person.account == new_user


@pytest.mark.parametrize(
    "reason",
    ["deleted", "non_owner", "already_linked", "duplicate_conflict"],
)
def test_accepting_skips_linking_when(reason):
    """When linking conditions fail at acceptance time, linking is skipped silently

    without failing the invitation acceptance or friendship.
    """
    sender = UserFactory(username="alice")
    recipient = UserFactory(username="bob")
    EmailAddress.objects.create(user=recipient, email="bob@example.com", verified=True)
    person = PersonFactory(owner=sender, email_address=encode_email("bob@example.com"))

    invitation = Invitation.objects.create(
        sender=sender,
        recipient_email=encode_email("bob@example.com"),
        person=person,
    )

    other_user = UserFactory(username="charlie")

    if reason == "deleted":
        person.delete()
    elif reason == "non_owner":
        PersonPermission.objects.filter(person=person, user=sender).update(
            permission_type=PermissionLevel.EDITOR
        )
    elif reason == "already_linked":
        person.account = other_user
        person.save(update_fields=["account"])
    elif reason == "duplicate_conflict":
        # Sender already has another person linked to recipient
        PersonFactory(owner=sender, account=recipient)

    success = accept_invitation_for_user(invitation, recipient)
    assert success is True

    invitation.refresh_from_db()
    assert invitation.accepted is True

    # Mutual friendship still exists
    sender_profile = Profile.objects.get(user=sender)
    recipient_profile = Profile.objects.get(user=recipient)
    assert recipient_profile in sender_profile.friends.all()
    assert sender_profile in recipient_profile.friends.all()

    if reason != "deleted":
        person.refresh_from_db()
        if reason == "already_linked":
            assert person.account == other_user
        else:
            assert person.account is None
