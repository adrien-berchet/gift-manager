"""Tests for Person.account semantics decoupling identity from access."""

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.plan_coordination import default_surprise_for
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views.person import get_person_grid_queryset

pytestmark = pytest.mark.django_db


def test_creating_a_person_does_not_link_the_creator(client):
    """POSTing to person_create creates an unlinked person and grants OWNER to creator."""
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("gift_manager:person_create"),
        {"first_name": "Alice", "family_name": "Smith"},
    )
    assert response.status_code in (200, 302)

    person = Person.objects.get(first_name="Alice", family_name="Smith")
    assert person.account is None
    assert PermissionService.get_effective_permission(person, user) == PermissionLevel.OWNER


def test_linked_account_has_no_access(client):
    """A user linked via Person.account has no access without explicit permissions."""
    bob = UserFactory()
    alice = UserFactory()
    person = PersonFactory(first_name="AliceRecord", owner=bob, account=alice)

    # Alice has no effective permission
    assert PermissionService.get_effective_permission(person, alice) == PermissionLevel.NONE
    # Alice cannot see the person in accessible_by
    assert person not in Person.objects.accessible_by(alice)
    # Alice does not see the person in grid rows
    assert not get_person_grid_queryset(alice).filter(pk=person.pk).exists()

    # Alice gets 404 on direct detail, edit, delete views
    client.force_login(alice)
    detail_url = reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
    edit_url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
    delete_url = reverse("gift_manager:person_delete", kwargs={"pk": person.person_id})
    assert client.get(detail_url).status_code == 404
    assert client.get(edit_url).status_code == 404
    assert client.post(delete_url).status_code == 404

    # Alice gets 400 when requesting surprise default hint for person
    hint_url = reverse("gift_manager:surprise_default_hint")
    assert client.get(hint_url, {"recipient": f"person:{person.person_id}"}).status_code == 400


def test_linked_account_is_not_an_access_holder_or_owner():
    """A linked account is not an access holder or owner."""
    bob = UserFactory()
    alice = UserFactory()
    person = PersonFactory(owner=bob, account=alice)

    assert not PermissionService.has_other_access_holder(person, bob)
    assert PermissionService._owner_user_ids(person) == {bob.id}


def test_co_giver_sees_surprise_for_a_linked_record():
    """Probe scenario 1: Carol creates surprise plan for Bob's Alice record.

    Plan is visible to Bob (co-giver) and hidden from Alice.
    """
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()

    # Bob owns record "Alice" linked to Alice, and shares it with Carol
    alice_record = PersonFactory(owner=bob, account=alice, shared_with=[carol])

    is_surprise = default_surprise_for(alice_record, carol)
    assert is_surprise is True

    plan = RelationFactory(person=alice_record, is_surprise=is_surprise)
    RelationPermission.objects.create(
        user=carol, relation=plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=bob, relation=plan, permission_type=PermissionLevel.EDITOR
    )
    RelationPermission.objects.create(
        user=alice, relation=plan, permission_type=PermissionLevel.VIEWER
    )

    # Visible to Bob, hidden from Alice
    assert Relation.objects.accessible_by(bob).filter(pk=plan.pk).exists()
    assert not Relation.objects.accessible_by(alice).filter(pk=plan.pk).exists()


def test_co_giver_sees_group_surprise():
    """Probe scenario 2: Carol creates surprise plan for a group containing Alice.

    Plan is visible to Bob (co-giver) and hidden from Alice.
    """
    bob = UserFactory()
    alice = UserFactory()
    carol = UserFactory()

    group = PersonGroupFactory(shared_with=[bob, carol])
    PersonFactory(owner=bob, account=alice, groups=[group])

    is_surprise = default_surprise_for(group, carol)
    assert is_surprise is True

    plan = GroupRelationFactory(group=group, is_surprise=is_surprise)
    RelationPermission.objects.create(
        user=carol, relation=plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=bob, relation=plan, permission_type=PermissionLevel.EDITOR
    )
    RelationPermission.objects.create(
        user=alice, relation=plan, permission_type=PermissionLevel.VIEWER
    )

    # Visible to Bob, hidden from Alice
    assert Relation.objects.accessible_by(bob).filter(pk=plan.pk).exists()
    assert not Relation.objects.accessible_by(alice).filter(pk=plan.pk).exists()


def test_self_link_hides_group_surprise_from_self():
    """Surprise plan for group containing Bob's self-record is hidden from Bob."""
    bob = UserFactory()
    carol = UserFactory()

    group = PersonGroupFactory(shared_with=[bob, carol])
    PersonFactory(owner=bob, account=bob, groups=[group])

    plan = GroupRelationFactory(group=group, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=plan, permission_type=PermissionLevel.OWNER
    )
    RelationPermission.objects.create(
        user=bob, relation=plan, permission_type=PermissionLevel.EDITOR
    )

    # Hidden from Bob
    assert not Relation.objects.accessible_by(bob).filter(pk=plan.pk).exists()


def test_surprise_checkbox_shown_for_records_the_user_created(client):
    """Surprise checkbox is shown unchecked for unlinked records, hidden for self, checked for friends."""
    user = UserFactory()
    friend = UserFactory()
    client.force_login(user)

    # Unlinked record created by user
    unlinked = PersonFactory(owner=user)
    res_unlinked = client.get(
        reverse("gift_manager:surprise_default_hint"),
        {"recipient": f"person:{unlinked.person_id}"},
    )
    assert res_unlinked.status_code == 200
    content_unlinked = res_unlinked.content.decode()
    assert 'name="is_surprise"' in content_unlinked
    assert "checked" not in content_unlinked

    # User's self-record
    self_record = PersonFactory(owner=user, account=user)
    res_self = client.get(
        reverse("gift_manager:surprise_default_hint"),
        {"recipient": f"person:{self_record.person_id}"},
    )
    assert res_self.status_code == 200
    content_self = res_self.content.decode()
    assert "is_surprise" not in content_self

    # Record linked to a friend
    friend_record = PersonFactory(owner=user, account=friend)
    res_friend = client.get(
        reverse("gift_manager:surprise_default_hint"),
        {"recipient": f"person:{friend_record.person_id}"},
    )
    assert res_friend.status_code == 200
    content_friend = res_friend.content.decode()
    assert 'name="is_surprise"' in content_friend
    assert "checked" in content_friend


def test_hidden_surprises_excluding_person():
    """excluding_person removes target person and their single-member groups from hidden surprises."""
    alice = UserFactory()
    carol = UserFactory()

    p1 = PersonFactory(account=alice)
    p2 = PersonFactory(account=alice)

    # Individual plans
    s1 = RelationFactory(person=p1, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=s1, permission_type=PermissionLevel.OWNER
    )
    s2 = RelationFactory(person=p2, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=s2, permission_type=PermissionLevel.OWNER
    )

    # Group plans:
    # g1 has only p1 as member
    g1 = PersonGroupFactory()
    p1.groups.add(g1)
    sg1 = GroupRelationFactory(group=g1, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=sg1, permission_type=PermissionLevel.OWNER
    )

    # g2 has both p1 and p2 as members
    g2 = PersonGroupFactory()
    p1.groups.add(g2)
    p2.groups.add(g2)
    sg2 = GroupRelationFactory(group=g2, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=sg2, permission_type=PermissionLevel.OWNER
    )

    # g3_parent contains g3_child which contains p2
    g3_parent = PersonGroupFactory()
    g3_child = PersonGroupFactory()
    g3_child.parent_groups.add(g3_parent)
    p2.groups.add(g3_child)
    sg3 = GroupRelationFactory(group=g3_parent, is_surprise=True)
    RelationPermission.objects.create(
        user=carol, relation=sg3, permission_type=PermissionLevel.OWNER
    )

    # Without excluding_person, all 5 plans are hidden from Alice
    all_hidden = Relation.objects.hidden_surprises_for(alice)
    assert s1 in all_hidden
    assert s2 in all_hidden
    assert sg1 in all_hidden
    assert sg2 in all_hidden
    assert sg3 in all_hidden

    # With excluding_person=p1:
    # s1 is excluded; s2 remains hidden
    # sg1 (only p1) is excluded
    # sg2 (p1 and p2) remains hidden because p2 is still a member
    # sg3 (p2 in descendant group) remains hidden because p2 is still a member
    filtered = Relation.objects.hidden_surprises_for(alice, excluding_person=p1)
    assert s1 not in filtered
    assert s2 in filtered
    assert sg1 not in filtered
    assert sg2 in filtered
    assert sg3 in filtered


def test_own_person_form_disables_email_address_field(client):
    """When editing their own person record, the email address field is disabled."""
    alice = UserFactory(email="alice@example.com")
    person = PersonFactory(first_name="Alice", owner=alice, account=alice)
    client.force_login(alice)

    edit_url = reverse("gift_manager:person_edit", kwargs={"pk": person.person_id})
    response = client.get(edit_url)
    assert response.status_code == 200

    form = response.context["form"]
    assert form.fields["email_address"].disabled is True
    assert "profile settings" in str(form.fields["email_address"].help_text)

    # Attempting to POST a new email does not change person.email_address
    post_response = client.post(
        edit_url,
        {
            "first_name": "AliceUpdated",
            "family_name": "",
            "email_address": "hacked@example.com",
            "birthday_day": "",
            "birthday_month": "",
            "birthday_year": "",
            "notes": "",
        },
    )
    assert post_response.status_code in (200, 302)
    person.refresh_from_db()
    assert person.first_name == "AliceUpdated"
    assert person.email != "hacked@example.com"
