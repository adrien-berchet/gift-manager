"""Tests for person link suggestions and suggestion dismissal."""

import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse

from gift_manager import account_links
from gift_manager.account_links import link_suggestion
from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_suggests_friend_by_verified_email(client):
    """An unlinked person whose email matches a friend's verified email shows a friend suggestion banner."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))

    # Direct helper assertion
    suggested = link_suggestion(person, owner)
    assert suggested == ana

    # Detail page renders banner
    client.force_login(owner)
    url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "This email belongs to your friend ana. Link this person to their account?" in content
    assert reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id}) in content
    assert (
        reverse("gift_manager:person_dismiss_link_suggestion", kwargs={"pk": person.person_id})
        in content
    )
    assert f'value="{ana.pk}"' in content


def test_suggests_friend_by_legacy_user_email(client):
    """An unlinked person whose email matches a friend's legacy user.email shows a suggestion banner."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    ana.email = encode_email("legacy_ana@example.com")
    ana.save(update_fields=["email"])
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("legacy_ana@example.com"))

    suggested = link_suggestion(person, owner)
    assert suggested == ana


def test_unverified_secondary_email_is_not_suggested():
    """An unverified secondary email belonging to a friend does not trigger a suggestion."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="primary@example.com", verified=True, primary=True)
    EmailAddress.objects.create(
        user=ana, email="unverified@example.com", verified=False, primary=False
    )
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("unverified@example.com"))

    assert link_suggestion(person, owner) is None


def test_suggests_self_for_own_email(client):
    """An unlinked person whose email matches the owner shows a self-suggestion banner."""
    owner = UserFactory(username="bob")
    EmailAddress.objects.create(user=owner, email="bob@example.com", verified=True, primary=True)

    person = PersonFactory(owner=owner, email_address=encode_email("bob@example.com"))

    suggested = link_suggestion(person, owner)
    assert suggested == owner

    client.force_login(owner)
    url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "This email is yours. Is this person you?" in content
    assert "This is me" in content
    assert "Not me" in content


def test_no_banner_for_editor_self_email_without_owner():
    """An editor who does not own the person sees no self-suggestion banner."""
    owner = UserFactory(username="bob")
    editor = UserFactory(username="ed")
    EmailAddress.objects.create(user=editor, email="ed@example.com", verified=True, primary=True)

    person = PersonFactory(owner=owner, email_address=encode_email("ed@example.com"))
    PermissionService.create_or_update_permission(
        editor, person, permission_level=PermissionLevel.EDITOR
    )

    assert link_suggestion(person, editor) is None


def test_no_banner_for_viewers_linked_records_or_refused_links():
    """No banner is shown for viewers, already-linked persons, or duplicate conflicts."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    viewer = UserFactory(username="viewer")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))
    PermissionService.create_or_update_permission(
        viewer, person, permission_level=PermissionLevel.VIEWER
    )

    # Viewer gets no suggestion
    assert link_suggestion(person, viewer) is None

    # Already linked person gets no suggestion
    person.account = ana
    person.save(update_fields=["account"])
    assert link_suggestion(person, owner) is None

    # Duplicate conflict: owner already owns another record linked to ana
    person.account = None
    person.save(update_fields=["account"])
    PersonFactory(owner=owner, account=ana)
    assert link_suggestion(person, owner) is None


def test_no_banner_without_or_with_invalid_email():
    """No suggestion is made if the person has no email, invalid email, or friend has empty email."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    ana.email = ""
    ana.save(update_fields=["email"])
    owner.profile.friends.add(ana.profile)

    # Empty email on person
    person_no_email = PersonFactory(owner=owner, email_address=None)
    assert link_suggestion(person_no_email, owner) is None

    # Invalid email on person
    person_invalid_email = PersonFactory(
        owner=owner, email_address=encode_email("invalid-email-value")
    )
    assert link_suggestion(person_invalid_email, owner) is None

    # Person with empty string
    person_empty_email = PersonFactory(owner=owner, email_address="")
    assert link_suggestion(person_empty_email, owner) is None


def test_dismissal_is_per_account(client):
    """Dismissing ana hides her banner; changing the person email to ben shows ben's banner."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    ben = UserFactory(username="ben")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    EmailAddress.objects.create(user=ben, email="ben@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile, ben.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))

    assert link_suggestion(person, owner) == ana

    # Dismiss ana
    dismiss_url = reverse(
        "gift_manager:person_dismiss_link_suggestion", kwargs={"pk": person.person_id}
    )
    client.force_login(owner)
    response = client.post(dismiss_url, {"account": str(ana.pk)})
    assert response.status_code == 302
    assert response.url == reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})

    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account == ana
    assert link_suggestion(person, owner) is None

    # Change email to ben: banner shows ben
    person.set_email("ben@example.com")
    person.save(update_fields=["email_address"])
    assert link_suggestion(person, owner) == ben


def test_dismiss_permissions_and_inaccessible_record(client):
    """The dismiss URL returns 404 for strangers / linked accounts and 403 for viewers."""
    owner = UserFactory(username="bob")
    stranger = UserFactory(username="stranger")
    viewer = UserFactory(username="viewer")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))
    PermissionService.create_or_update_permission(
        viewer, person, permission_level=PermissionLevel.VIEWER
    )

    dismiss_url = reverse(
        "gift_manager:person_dismiss_link_suggestion", kwargs={"pk": person.person_id}
    )

    # Stranger -> 404
    client.force_login(stranger)
    assert client.post(dismiss_url, {"account": str(ana.pk)}).status_code == 404

    # Linked account without permission -> 404
    person.account = ana
    person.save(update_fields=["account"])
    client.force_login(ana)
    assert client.post(dismiss_url, {"account": str(ana.pk)}).status_code == 404

    person.account = None
    person.save(update_fields=["account"])

    # Viewer -> 403
    client.force_login(viewer)
    assert client.post(dismiss_url, {"account": str(ana.pk)}).status_code == 403


def test_dismissal_tampered_or_stale_account_is_noop(client):
    """A POST with malformed or mismatched account does not error or modify dismissed account."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))
    dismiss_url = reverse(
        "gift_manager:person_dismiss_link_suggestion", kwargs={"pk": person.person_id}
    )

    client.force_login(owner)

    # Malformed string: redirects without 500
    res = client.post(dismiss_url, {"account": "abc"})
    assert res.status_code == 302
    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account is None

    # Mismatched ID: redirects without change
    res = client.post(dismiss_url, {"account": "999999"})
    assert res.status_code == 302
    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account is None


def test_dismissal_on_linked_record_is_noop(client):
    """Dismissing a suggestion on an already linked record is a no-op."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    person = PersonFactory(owner=owner, account=ana, email_address=encode_email("ana@example.com"))

    account_links.dismiss_link_suggestion(person, ana, owner)
    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account is None


def test_dismissal_htmx_returns_hx_redirect(client):
    """An HTMX POST to dismiss returns 204 with HX-Redirect header."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))
    dismiss_url = reverse(
        "gift_manager:person_dismiss_link_suggestion", kwargs={"pk": person.person_id}
    )

    client.force_login(owner)
    response = client.post(dismiss_url, {"account": str(ana.pk)}, HTTP_HX_REQUEST="true")
    assert response.status_code == 204
    assert response["HX-Redirect"] == reverse(
        "gift_manager:person_detail", kwargs={"pk": person.person_id}
    )
    person.refresh_from_db()
    assert person.link_suggestion_dismissed_account == ana


def test_banner_link_button_links(client):
    """Posting from the banner to person_link_account links the person and badge appears."""
    owner = UserFactory(username="bob")
    ana = UserFactory(username="ana")
    EmailAddress.objects.create(user=ana, email="ana@example.com", verified=True, primary=True)
    owner.profile.friends.add(ana.profile)

    person = PersonFactory(owner=owner, email_address=encode_email("ana@example.com"))
    link_url = reverse("gift_manager:person_link_account", kwargs={"pk": person.person_id})

    client.force_login(owner)
    response = client.post(link_url, {"account": str(ana.pk)})
    assert response.status_code == 302

    person.refresh_from_db()
    assert person.account == ana

    # Detail page now displays the badge and no suggestion banner
    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    detail_res = client.get(detail_url)
    content = detail_res.content.decode("utf-8")
    assert "Linked to ana" in content
    assert "This email belongs to your friend" not in content


def test_query_count_bounded_with_many_friends(client, django_assert_max_num_queries):
    """Link suggestion calculation scales in constant queries even with 15 friends."""
    owner = UserFactory(username="bob")
    friends = [UserFactory(username=f"friend_{i}") for i in range(15)]
    for f in friends:
        EmailAddress.objects.create(
            user=f, email=f"{f.username}@example.com", verified=True, primary=True
        )
    owner.profile.friends.add(*(f.profile for f in friends))

    matching_friend = friends[5]
    person = PersonFactory(
        owner=owner, email_address=encode_email(f"{matching_friend.username}@example.com")
    )

    # link_suggestion on its own:
    # 1. Effective perm (PermissionService)
    # 2. _owner_ids (PersonPermission)
    # 3. Viewer owning email (EmailAddress)
    # 4. _friend_candidates (Profile.friends + friends__user subquery)
    # 5. Candidate EmailAddress batch
    # 6. duplicate_conflicts (Person + PersonPermission)
    # Bound to <= 10 queries
    with django_assert_max_num_queries(10):
        suggested = link_suggestion(person, owner)
        assert suggested == matching_friend
