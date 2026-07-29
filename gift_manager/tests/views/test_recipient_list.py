import re

import pytest
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
def test_recipient_list_combines_accessible_people_and_groups(client):
    user = UserFactory()
    client.force_login(user)

    family = PersonGroupFactory(name="Family", shared_with=[user])
    team = PersonGroupFactory(name="Team", shared_with=[user])
    child_group = PersonGroupFactory(name="Team Kids", shared_with=[user])
    child_group.parent_groups.add(team)
    person = PersonFactory(
        first_name="Ada",
        family_name="Lovelace",
        groups=[family],
        shared_with=[user],
    )
    PersonFactory(first_name="Grace", family_name="Hopper", groups=[team], shared_with=[user])

    private_person = PersonFactory(first_name="Private", family_name="Person")
    private_group = PersonGroupFactory(name="Private Group")
    hidden_member = PersonFactory(first_name="Hidden", family_name="Member", groups=[team])
    hidden_child = PersonGroupFactory(name="Hidden Child")
    hidden_child.parent_groups.add(team)

    response = client.get(reverse("gift_manager:recipients"))

    assert response.status_code == 200
    team_recipient = next(
        recipient
        for recipient in response.context["recipients"]
        if recipient["key"] == f"group:{team.group_id}"
    )
    person_recipient = next(
        recipient
        for recipient in response.context["recipients"]
        if recipient["key"] == f"person:{person.person_id}"
    )
    assert team_recipient["member_count"] == 1
    assert team_recipient["child_count"] == 1
    assert list(person_recipient["groups"]) == [family]

    content = response.content.decode("utf-8")
    assert "Recipients" in content
    assert f'data-recipient-key="person:{person.person_id}"' in content
    assert f'data-recipient-key="group:{team.group_id}"' in content
    assert (
        f'href="{reverse("gift_manager:person_relation_create", kwargs={"pk": person.person_id})}" '
        'class="btn btn-sm btn-primary" data-action="create"'
    ) in content
    assert (
        f'href="{reverse("gift_manager:person_group_relation_create", kwargs={"pk": team.group_id})}" '
        'class="btn btn-sm btn-primary" data-action="create"'
    ) in content
    assert "recipient-type-badge--person" in content
    assert "recipient-type-badge--group" in content
    assert "recipient-membership-badge" in content
    assert "Gift plans target this group directly." in content
    assert "Manage Groups" in content
    assert "Group Explorer" in content
    assert "Family" in content
    assert "Team Kids" in content
    assert str(private_person) not in content
    assert private_group.name not in content
    assert str(hidden_member) not in content
    assert hidden_child.name not in content
    assert "2 members" not in content
    assert "2 child groups" not in content


def assert_recipients_nav_is_active_without_groups_nav(content):
    recipients_url = reverse("gift_manager:recipients")
    groups_url = reverse("gift_manager:person_groups")

    assert re.search(
        rf'<a class="nav-link [^"]*active[^"]*" href="{re.escape(recipients_url)}">',
        content,
    )
    assert not re.search(
        rf'<a class="nav-link[^"]*" href="{re.escape(groups_url)}">',
        content,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "person_groups",
        "person_group_explorer",
        "person_group_create",
        "person_group_detail",
        "person_group_edit",
        "add_person_group_person",
        "add_child_groups_to_group",
        "person_group_relation_create",
    ],
)
def test_groups_are_nested_under_recipients_in_primary_navigation(client, url_name):
    user = UserFactory()
    client.force_login(user)
    group = PersonGroupFactory(name="Family", shared_with=[user])
    create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)

    kwargs = {}
    if url_name not in {"person_groups", "person_group_explorer", "person_group_create"}:
        kwargs["pk"] = group.group_id

    response = client.get(reverse(f"gift_manager:{url_name}", kwargs=kwargs))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert_recipients_nav_is_active_without_groups_nav(content)
