"""Tests for friends list person-account linking, friend link view, and PersonCreateView link_to."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.messages import get_messages
from django.urls import reverse

from gift_manager.account_links import friend_link_rows
from gift_manager.account_links import linkable_persons
from gift_manager.account_links import own_records
from gift_manager.email_encoding import encode_email
from gift_manager.invitations import best_email_for_account
from gift_manager.invitations import emails_owned_by
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.services import PermissionService
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_emails_owned_by_and_best_email():
    """Verify batch email resolution and primary/best email selection."""
    user1 = UserFactory(username="u1")
    user2 = UserFactory(username="u2")
    user3 = UserFactory(username="u3")

    # user1 has verified and unverified addresses
    EmailAddress.objects.create(
        user=user1, email="verified@example.com", verified=True, primary=False
    )
    EmailAddress.objects.create(
        user=user1, email="primary@example.com", verified=True, primary=True
    )
    EmailAddress.objects.create(
        user=user1, email="unverified@example.com", verified=False, primary=False
    )

    # user2 has only unverified address
    EmailAddress.objects.create(
        user=user2, email="onlyunverified@example.com", verified=False, primary=True
    )

    # user3 has no rows, uses legacy user.email
    user3.email = encode_email("legacy@example.com")
    user3.save(update_fields=["email"])

    emails_map = emails_owned_by([user1, user2, user3])
    assert emails_map[user1.pk] == {"verified@example.com", "primary@example.com"}
    assert emails_map[user2.pk] == set()
    assert emails_map[user3.pk] == {"legacy@example.com"}

    assert best_email_for_account(user1) == "primary@example.com"
    assert best_email_for_account(user2) is None
    assert best_email_for_account(user3) == "legacy@example.com"


def test_friend_link_rows_query_count(django_assert_num_queries):
    """friend_link_rows must not issue N+1 queries as the number of friends grows."""
    viewer = UserFactory(username="viewer")

    # Create 5 friends with emails
    friends = [UserFactory(username=f"friend_{i}") for i in range(5)]
    for friend in friends:
        EmailAddress.objects.create(
            user=friend, email=f"{friend.username}@example.com", verified=True, primary=True
        )
        viewer.profile.friends.add(friend.profile)

    # Create 3 owned persons: 1 linked, 2 unlinked
    PersonFactory(owner=viewer, account=friends[0])
    PersonFactory(owner=viewer, email_address=encode_email("friend_1@example.com"))
    PersonFactory(owner=viewer, email_address=encode_email("unmatched@example.com"))

    # Baseline query count with 5 friends
    with django_assert_num_queries(3):
        # 1. friends with select_related user
        # 2. viewer owned persons
        # 3. EmailAddress rows for friends
        rows = friend_link_rows(viewer)
        assert len(rows) == 5

    # Add 5 more friends
    more_friends = [UserFactory(username=f"more_friend_{i}") for i in range(5)]
    for friend in more_friends:
        EmailAddress.objects.create(
            user=friend, email=f"{friend.username}@example.com", verified=True, primary=True
        )
        viewer.profile.friends.add(friend.profile)

    # Query count should remain exactly 3!
    with django_assert_num_queries(3):
        rows = friend_link_rows(viewer)
        assert len(rows) == 10


def test_friend_row_unlinked_shows_actions_and_hint(client):
    """An unlinked friend row shows 'Link to a person', 'Create person', and matching email hint."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    EmailAddress.objects.create(user=friend, email="ana@example.com", verified=True, primary=True)
    viewer.profile.friends.add(friend.profile)

    # 1 owned unlinked person matching friend's email
    PersonFactory(
        owner=viewer,
        first_name="Ana",
        family_name="Banana",
        email_address=encode_email("ana@example.com"),
    )

    client.force_login(viewer)
    response = client.get(reverse("gift_manager:profile_detail"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    link_url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})
    create_url = f"{reverse('gift_manager:person_create')}?link_to={friend.profile.pk}"

    assert "Link to a person" in content
    assert link_url in content
    assert "Create person" in content
    assert create_url in content
    assert "1 person has this email" in content

    # Add a second matching unlinked person -> tests ngettext pluralization
    PersonFactory(
        owner=viewer,
        first_name="Anna",
        family_name="Banana",
        email_address=encode_email("ana@example.com"),
    )
    response = client.get(reverse("gift_manager:profile_detail"))
    content = response.content.decode("utf-8")
    assert "2 persons have this email" in content


def test_friend_row_linked_shows_records_and_unlink(client):
    """When viewer owns records linked to friend, show each record name and Unlink button, hide Link/Create."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    viewer.profile.friends.add(friend.profile)

    # Two owned records linked to the same friend (e.g. one created, one shared as owner)
    p1 = PersonFactory(owner=viewer, first_name="Ana", family_name="One", account=friend)
    p2 = PersonFactory(owner=viewer, first_name="Ana", family_name="Two", account=friend)

    client.force_login(viewer)
    response = client.get(reverse("gift_manager:profile_detail"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Shows both record names linking to their person pages
    assert reverse("gift_manager:person_detail", kwargs={"pk": p1.person_id}) in content
    assert reverse("gift_manager:person_detail", kwargs={"pk": p2.person_id}) in content

    # Shows Unlink buttons linking to person_link_account
    assert reverse("gift_manager:person_link_account", kwargs={"pk": p1.person_id}) in content
    assert reverse("gift_manager:person_link_account", kwargs={"pk": p2.person_id}) in content

    # Does not show "Link to a person" or "Create person" for this friend
    assert (
        reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})
        not in content
    )
    assert f"link_to={friend.profile.pk}" not in content


def test_link_to_a_person_page_orders_email_matches_first(client):
    """linkable_persons and friend_link_person page put email matches first, excluding dismissed accounts."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    EmailAddress.objects.create(user=friend, email="ana@example.com", verified=True, primary=True)
    viewer.profile.friends.add(friend.profile)

    # 1. Email match (not dismissed) -> should come first
    p_match = PersonFactory(
        owner=viewer,
        first_name="Zoey",
        family_name="Zebra",
        email_address=encode_email("ana@example.com"),
    )
    # 2. Email match but dismissed for this friend -> sorted by name, not first
    p_dismissed = PersonFactory(
        owner=viewer,
        first_name="Alice",
        family_name="Dismissed",
        email_address=encode_email("ana@example.com"),
        link_suggestion_dismissed_account=friend,
    )
    # 3. Different email
    p_other = PersonFactory(
        owner=viewer,
        first_name="Bob",
        family_name="Brown",
        email_address=encode_email("other@example.com"),
    )

    ordered = linkable_persons(viewer, friend)
    assert [p.pk for p in ordered] == [p_match.pk, p_other.pk, p_dismissed.pk]

    client.force_login(viewer)
    url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Same email" in content


def test_link_to_a_person_post_links(client):
    """POST to friend_link_person links the person record to the friend."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    viewer.profile.friends.add(friend.profile)
    person = PersonFactory(owner=viewer, first_name="Ana")

    client.force_login(viewer)
    url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})
    response = client.post(url, {"person": str(person.person_id)})

    assert response.status_code == 302
    assert response.url == reverse("gift_manager:profile_detail")

    person.refresh_from_db()
    assert person.account == friend

    flashed = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("Linked to ana." in m for m in flashed)


def test_link_to_a_person_post_refused_or_already_linked(client):
    """POST with an already-linked person or when duplicate guard refuses shows error and does not change link."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    other_user = UserFactory(username="bob")
    viewer.profile.friends.add(friend.profile)

    # 1. Already linked to someone else
    person_linked = PersonFactory(owner=viewer, first_name="Already", account=other_user)
    client.force_login(viewer)
    url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})
    response = client.post(url, {"person": str(person_linked.person_id)})
    assert response.status_code == 302
    assert response.url == url
    person_linked.refresh_from_db()
    assert person_linked.account == other_user
    flashed = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("already linked" in m for m in flashed)

    # 2. Duplicate guard refusal: viewer already owns a record linked to ana
    PersonFactory(owner=viewer, first_name="FirstAna", account=friend)
    person_unlinked = PersonFactory(owner=viewer, first_name="SecondAna")
    response = client.post(url, {"person": str(person_unlinked.person_id)})
    assert response.status_code == 302
    assert response.url == url
    person_unlinked.refresh_from_db()
    assert person_unlinked.account is None
    flashed = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("already has a person linked" in m for m in flashed)


def test_forged_person_id_is_404_and_non_friend_is_404(client):
    """Record not owned by viewer is 404, non-friend or self is 404, invalid UUID is 400."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    stranger = UserFactory(username="stranger")
    viewer.profile.friends.add(friend.profile)

    # Person owned by someone else
    not_owned_person = PersonFactory(owner=stranger)

    client.force_login(viewer)
    url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": friend.profile.pk})

    # Forged person id in POST
    assert client.post(url, {"person": str(not_owned_person.person_id)}).status_code == 404

    # Invalid UUID in POST
    assert client.post(url, {"person": "not-a-uuid"}).status_code == 400

    # Non-friend profile id
    non_friend_url = reverse(
        "gift_manager:friend_link_person", kwargs={"friend_id": stranger.profile.pk}
    )
    assert client.get(non_friend_url).status_code == 404
    assert (
        client.post(non_friend_url, {"person": "00000000-0000-0000-0000-000000000000"}).status_code
        == 404
    )

    # Viewer's own profile id
    self_url = reverse("gift_manager:friend_link_person", kwargs={"friend_id": viewer.profile.pk})
    assert client.get(self_url).status_code == 404


def test_create_person_prefills_from_friend_and_links_on_save(client):
    """GET person_create?link_to=<pk> prefills name & email; POST creates and links."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana", first_name="Ana", last_name="Smith")
    EmailAddress.objects.create(
        user=friend, email="ana.smith@example.com", verified=True, primary=True
    )
    viewer.profile.friends.add(friend.profile)

    client.force_login(viewer)
    create_url = f"{reverse('gift_manager:person_create')}?link_to={friend.profile.pk}"

    response = client.get(create_url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert 'value="Ana"' in content
    assert 'value="Smith"' in content
    assert 'value="ana.smith@example.com"' in content
    assert f'type="hidden" name="link_to" value="{friend.profile.pk}"' in content

    # POST to create person
    post_data = {
        "first_name": "Ana",
        "family_name": "Smith",
        "email_address": "ana.smith@example.com",
        "link_to": str(friend.profile.pk),
    }
    response = client.post(reverse("gift_manager:person_create"), post_data)
    assert response.status_code == 302
    assert response.url == reverse("gift_manager:profile_detail")

    created_person = Person.objects.get(first_name="Ana", family_name="Smith")
    assert created_person.account == friend
    assert (
        PermissionService.get_effective_permission(created_person, viewer) == PermissionLevel.OWNER
    )

    flashed = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("Linked to ana." in m for m in flashed)


def test_create_person_prefill_fallback_to_username():
    """If friend has blank first and last names, first_name defaults to username and family_name is empty."""
    from django.test import RequestFactory

    from gift_manager.views.person import PersonCreateView

    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="mystery_friend", first_name="", last_name="")
    viewer.profile.friends.add(friend.profile)

    rf = RequestFactory()
    request = rf.get(f"/persons/create/?link_to={friend.profile.pk}")
    request.user = viewer

    view = PersonCreateView()
    view.setup(request)
    initial = view.get_initial()

    assert initial.get("first_name") == "mystery_friend"
    assert initial.get("family_name") == ""


def test_create_person_duplicate_guard_shows_warning_without_brackets(client):
    """When duplicate guard refuses link during person_create, message is a warning without brackets."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    viewer.profile.friends.add(friend.profile)

    # Viewer already owns a record linked to ana
    PersonFactory(owner=viewer, first_name="ExistingAna", account=friend)

    client.force_login(viewer)
    post_data = {
        "first_name": "SecondAna",
        "family_name": "Test",
        "email_address": "",
        "link_to": str(friend.profile.pk),
    }
    response = client.post(reverse("gift_manager:person_create"), post_data)
    assert response.status_code == 302

    created_person = Person.objects.get(first_name="SecondAna")
    assert created_person.account is None

    flashed = [str(m) for m in get_messages(response.wsgi_request)]
    warning_msgs = [m for m in flashed if "already has a person linked" in m]
    assert len(warning_msgs) == 1
    # Ensure it's not formatted as a Python list repr "['...']"
    assert not warning_msgs[0].startswith("['")


def test_create_person_non_friend_or_invalid_link_to_ignored(client):
    """Non-friend, own profile, non-numeric or huge int link_to is ignored without 500 error."""
    viewer = UserFactory(username="viewer")
    stranger = UserFactory(username="stranger")

    client.force_login(viewer)

    for invalid_link_to in [
        str(stranger.profile.pk),
        str(viewer.profile.pk),
        "abc",
        "9999999999999999999999",
    ]:
        post_data = {
            "first_name": f"Person_{invalid_link_to[:5]}",
            "family_name": "Test",
            "link_to": invalid_link_to,
        }
        response = client.post(reverse("gift_manager:person_create"), post_data)
        assert response.status_code == 302
        created = Person.objects.get(first_name=f"Person_{invalid_link_to[:5]}")
        assert created.account is None


def test_create_person_validation_error_preserves_link_to(client):
    """When person form validation fails, link_to hidden input is preserved."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    viewer.profile.friends.add(friend.profile)

    client.force_login(viewer)
    post_data = {
        "first_name": "Ana",
        "family_name": "Test",
        "email_address": "not-an-email",
        "link_to": str(friend.profile.pk),
    }
    response = client.post(reverse("gift_manager:person_create"), post_data)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert f'type="hidden" name="link_to" value="{friend.profile.pk}"' in content


def test_create_person_htmx_get_preserves_link_to(client):
    """HTMX GET of person_create?link_to=... renders the hidden field."""
    viewer = UserFactory(username="viewer")
    friend = UserFactory(username="ana")
    viewer.profile.friends.add(friend.profile)

    client.force_login(viewer)
    url = f"{reverse('gift_manager:person_create')}?link_to={friend.profile.pk}"
    response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert f'type="hidden" name="link_to" value="{friend.profile.pk}"' in content


def test_profile_lists_own_records(client):
    """Profile detail page lists 'Your own person record: <name>' for each self-linked owned record."""
    viewer = UserFactory(username="viewer")
    p1 = PersonFactory(owner=viewer, first_name="Me", family_name="Myself", account=viewer)

    # Direct helper assertion
    assert own_records(viewer) == [p1]

    client.force_login(viewer)
    response = client.get(reverse("gift_manager:profile_detail"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Your own person record:" in content
    assert reverse("gift_manager:person_detail", kwargs={"pk": p1.person_id}) in content
    assert "Me Myself" in content
