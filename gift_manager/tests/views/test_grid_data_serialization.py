"""Tests for Grid.js data serialization and json_script elements."""

import datetime
import json
import re
import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import formats
from django.utils import translation

from gift_manager.email_encoding import encode_email
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.views.event import EventListView
from gift_manager.views.gift import GiftListView
from gift_manager.views.person import PersonListView
from gift_manager.views.person import get_person_grid_queryset
from gift_manager.views.person_group import PersonGroupListView
from gift_manager.views.relation import RelationListView
from gift_manager.views.relation import RelationStatusListView


def _extract_grid_data_json(html: str) -> list:
    """Extract and parse the #grid-data json_script payload from rendered HTML."""
    match = re.search(r'<script id="grid-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, 'Could not find <script id="grid-data"> in rendered HTML'
    return json.loads(match.group(1))


def _extract_user_permissions_json(html: str) -> dict:
    """Extract and parse the #user-permissions json_script payload from rendered HTML."""
    match = re.search(r'<script id="user-permissions"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, 'Could not find <script id="user-permissions"> in rendered HTML'
    return json.loads(match.group(1))


@pytest.mark.django_db
class TestEventGridDataSerialization:
    """Unit and integration tests for EventListView grid data serialization."""

    def test_get_grid_data_structure(self, user):
        """EventListView.get_grid_data returns rows matching Grid.js column definitions."""
        event = EventFactory(
            name="Summer Party",
            comment="Bring snacks",
            shared_with=[user],
        )
        birthday_event = Event.objects.get_birthday_event()

        view = EventListView()
        items = Event.objects.for_list_display(user).filter(
            event_id__in=[event.event_id, birthday_event.event_id]
        )
        rows = view.get_grid_data(items)

        assert len(rows) == 2
        event_row = next(r for r in rows if r[4] == str(event.event_id))
        assert event_row[0] == ""  # Checkbox placeholder
        assert event_row[1] == "Summer Party"
        assert event_row[2] == "Bring snacks"
        assert event_row[3] == event.date_summary
        assert event_row[4] == str(event.event_id)
        assert event_row[5] == reverse("gift_manager:event_detail", args=[event.event_id])
        assert event_row[6] == reverse("gift_manager:event_edit", args=[event.event_id])
        assert event_row[7] == reverse("gift_manager:event_delete", args=[event.event_id])
        assert event_row[8] is False  # is_birthday

        bday_row = next(r for r in rows if r[4] == str(birthday_event.event_id))
        assert bday_row[8] is True

    def test_event_list_page_serves_valid_grid_data_and_refreshes(self, authenticated_client, user):
        """The event list template outputs valid JSON in #grid-data that updates on change."""
        EventFactory(name="Initial Event", shared_with=[user])

        # 1. Initial page load
        response = authenticated_client.get(reverse("gift_manager:events"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        event_names = [row[1] for row in grid_data]
        assert "Initial Event" in event_names

        # 2. Simulate entity creation / update (as refreshed by GridUtils.refreshGridData)
        EventFactory(name="Freshly Added Event", shared_with=[user])
        refresh_url = f"{reverse('gift_manager:events')}?_t=123456789"
        refresh_response = authenticated_client.get(refresh_url)
        assert refresh_response.status_code == 200
        refreshed_data = _extract_grid_data_json(refresh_response.content.decode())
        refreshed_names = [row[1] for row in refreshed_data]
        assert "Initial Event" in refreshed_names
        assert "Freshly Added Event" in refreshed_names


@pytest.mark.django_db
class TestGiftGridDataSerialization:
    """Unit and integration tests for GiftListView grid data serialization."""

    def test_get_grid_data_structure(self, user):
        """GiftListView.get_grid_data properly handles tags, sanitizes URLs, and formats prices."""
        tag = GiftTagFactory(name="Books")
        PermissionService.create_or_update_permission(
            user, tag, permission_level=PermissionLevel.OWNER
        )

        gift = GiftFactory(
            name="Clean Code",
            comment="Must read",
            url="https://example.com/clean-code",
            price=Decimal("29.99"),
            tags=[tag],
            shared_with=[user],
        )

        view = GiftListView()
        items = [
            {
                "gift_id": gift.gift_id,
                "name": gift.name,
                "comment": gift.comment,
                "url": gift.url,
                "price": gift.price,
                "tags_info": [{"id": tag.tag_id, "name": tag.name}],
            },
            {
                "gift_id": "00000000-0000-0000-0000-000000000001",
                "name": "Hostile URL Gift",
                "comment": None,
                "url": "javascript:alert(1)",
                "price": None,
                "tags_info": [],
            },
        ]
        rows = view.get_grid_data(items)

        assert len(rows) == 2
        clean_row = rows[0]
        assert clean_row[0] == ""
        assert clean_row[1] == "Clean Code"
        assert clean_row[2] == "Must read"
        assert clean_row[3] == "https://example.com/clean-code"
        assert clean_row[4] == "29.99"
        assert clean_row[5] == [
            {
                "id": str(tag.tag_id),
                "name": "Books",
                "url": reverse("gift_manager:gift_tag_detail", args=[tag.tag_id]),
            }
        ]
        assert clean_row[6] == str(gift.gift_id)
        assert clean_row[7] == reverse("gift_manager:gift_relation_create", args=[gift.gift_id])
        assert clean_row[8] == reverse("gift_manager:gift_detail", args=[gift.gift_id])
        assert clean_row[9] == reverse("gift_manager:gift_edit", args=[gift.gift_id])
        assert clean_row[10] == reverse("gift_manager:gift_delete", args=[gift.gift_id])

        hostile_row = rows[1]
        assert hostile_row[1] == "Hostile URL Gift"
        assert hostile_row[2] == ""  # None becomes empty string
        assert hostile_row[3] == ""  # javascript: URL is sanitized to empty string
        assert hostile_row[4] == ""  # None price becomes empty string
        assert hostile_row[5] == []

    def test_gift_list_page_serves_valid_grid_data_and_refreshes(self, authenticated_client, user):
        """The gift list template outputs valid JSON in #grid-data that updates on change."""
        gift = GiftFactory(name="Initial Gift", shared_with=[user])

        # 1. Initial page load
        response = authenticated_client.get(reverse("gift_manager:gifts"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        gift_names = [row[1] for row in grid_data]
        assert "Initial Gift" in gift_names

        # 2. Simulate entity update (as refreshed by GridUtils.refreshGridData)
        Gift.objects.filter(gift_id=gift.gift_id).update(name="Renamed Gift")
        refresh_url = f"{reverse('gift_manager:gifts')}?_t=987654321"
        refresh_response = authenticated_client.get(refresh_url)
        assert refresh_response.status_code == 200
        refreshed_data = _extract_grid_data_json(refresh_response.content.decode())
        refreshed_names = [row[1] for row in refreshed_data]
        assert "Renamed Gift" in refreshed_names
        assert "Initial Gift" not in refreshed_names

    def test_json_script_escapes_closing_script_tags(self, authenticated_client, user):
        """Names containing </script> cannot break out of the json_script block."""
        malicious_name = "</script><script>alert('xss')</script>"
        GiftFactory(name=malicious_name, shared_with=[user])

        response = authenticated_client.get(reverse("gift_manager:gifts"))
        assert response.status_code == 200
        html = response.content.decode()

        # The raw unescaped string must not appear anywhere in rendered HTML
        assert malicious_name not in html

        # Instead, json_script must escape every '<' with unicode escape sequences
        escaped_needle = (
            "\\u003C/script\\u003E\\u003Cscript\\u003Ealert('xss')\\u003C/script\\u003E"
        )
        assert escaped_needle in html

        # The script element must encapsulate the payload without premature termination
        script_match = re.search(r'<script id="grid-data"[^>]*>(.*?)</script>', html, re.DOTALL)
        assert script_match
        raw_body = script_match.group(1)
        assert escaped_needle in raw_body

        # Parsing the json-script reproduces the original string correctly
        grid_data = json.loads(raw_body)
        gift_names = [row[1] for row in grid_data]
        assert malicious_name in gift_names

    def test_user_permissions_json_script_rendered_when_empty(self, authenticated_client):
        """An empty permissions dict renders a valid user-permissions json_script with {}."""
        response = authenticated_client.get(reverse("gift_manager:gifts"))
        assert response.status_code == 200
        perms = _extract_user_permissions_json(response.content.decode())
        assert perms == {}


@pytest.mark.django_db
class TestRelationStatusGridDataSerialization:
    """Unit and integration tests for RelationStatusListView grid data serialization."""

    def test_get_grid_data_structure(self):
        status = RelationStatusFactory(status="Pending Idea")
        view = RelationStatusListView()
        items = list(RelationStatus.objects.values("pk", "status").filter(pk=status.pk))
        rows = view.get_grid_data(items)
        assert len(rows) == 1
        assert rows[0] == [
            "Pending Idea",
            str(status.pk),
            reverse("gift_manager:relation_status_detail", args=[status.pk]),
        ]

    def test_relation_status_list_page_serves_valid_grid_data(self, authenticated_client):
        RelationStatusFactory(status="Purchased")
        response = authenticated_client.get(reverse("gift_manager:relation_statuses"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        statuses = [row[0] for row in grid_data]
        assert "Purchased" in statuses


@pytest.mark.django_db
class TestRelationGridDataSerialization:
    """Unit and integration tests for RelationAdvancedListView grid data serialization."""

    def test_get_grid_data_structure(self, user):
        gift = GiftFactory(name="Book", shared_with=[user])
        person = PersonFactory(first_name="Alice", family_name="Smith", shared_with=[user])
        event = EventFactory(name="Birthday", shared_with=[user])
        status = RelationStatusFactory(status="Planned")
        relation = RelationFactory(
            gift=gift,
            person=person,
            event=event,
            status=status,
            comment="Special gift",
            shared_with=[user],
        )

        view = RelationListView()
        items = [
            {
                "relation_id": relation.relation_id,
                "gift__gift_id": gift.gift_id,
                "gift__name": gift.name,
                "person__person_id": person.person_id,
                "group__group_id": None,
                "related_object": "Alice Smith",
                "recipient_type": "person",
                "event__event_id": event.event_id,
                "event__name": event.name,
                "event__is_birthday": True,
                "comment": "Special gift",
                "status": status.pk,
                "due_date": None,
                "urgency_key": "ideas",
                "needs_attention": False,
                "attention_label": "",
                "has_missing_data": False,
                "missing_data_label": "",
                "has_missing_due_date": False,
                "missing_due_date_label": "",
                "has_missing_event": False,
                "missing_event_label": "",
            }
        ]
        rows = view.get_grid_data(items, [status])
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == ""  # Checkbox
        assert row[1] == {
            "id": str(gift.gift_id),
            "name": "Book",
            "url": reverse("gift_manager:gift_detail", args=[gift.gift_id]),
        }
        assert row[2] == {
            "text": "Alice Smith",
            "recipientType": "person",
            "personId": str(person.person_id),
            "groupId": None,
            "url": reverse("gift_manager:person_detail", args=[person.person_id]),
        }
        assert row[3] == {
            "id": str(event.event_id),
            "name": "Birthday",
            "url": reverse("gift_manager:event_detail", args=[event.event_id]),
        }
        assert row[4] == "Special gift"
        assert row[5] == str(status.pk)
        assert row[6] == "Planned"
        assert row[7] is None  # due_date
        assert row[8]["urgencyKey"] == "ideas"
        assert row[9] == str(relation.relation_id)
        assert row[10] == reverse("gift_manager:relation_detail", args=[relation.relation_id])
        assert row[11] == reverse("gift_manager:relation_edit", args=[relation.relation_id])
        assert row[12] == reverse("gift_manager:relation_delete", args=[relation.relation_id])
        assert (
            row[13]
            == reverse("gift_manager:relation_create") + f"?duplicate_of={relation.relation_id}"
        )

    def test_relation_advanced_list_serves_valid_grid_data_and_permissions(
        self, authenticated_client, user
    ):
        gift = GiftFactory(name="Watch", shared_with=[user])
        person = PersonFactory(first_name="Bob", shared_with=[user])
        status = RelationStatusFactory(status="Selected")
        relation = RelationFactory(gift=gift, person=person, status=status, shared_with=[user])

        response = authenticated_client.get(reverse("gift_manager:relation_advanced_list"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        perms = _extract_user_permissions_json(response.content.decode())
        assert len(grid_data) >= 1
        assert str(relation.relation_id) in perms

    def test_relation_grid_data_due_date_formatting(self, user):
        """Due dates format into display and iso representations."""
        gift = GiftFactory(shared_with=[user])
        person = PersonFactory(shared_with=[user])
        status = RelationStatusFactory()
        due_date = datetime.date(2026, 12, 25)
        relation = RelationFactory(
            gift=gift,
            person=person,
            status=status,
            due_date=due_date,
            shared_with=[user],
        )

        view = RelationListView()
        items = [
            {
                "relation_id": relation.relation_id,
                "gift__gift_id": gift.gift_id,
                "gift__name": gift.name,
                "person__person_id": person.person_id,
                "group__group_id": None,
                "related_object": "Alice",
                "recipient_type": "person",
                "event__event_id": None,
                "event__name": None,
                "event__is_birthday": False,
                "comment": "",
                "status": status.pk,
                "due_date": due_date,
                "urgency_key": "due_soon",
                "needs_attention": False,
                "attention_label": "",
                "has_missing_data": False,
                "missing_data_label": "",
                "has_missing_due_date": False,
                "missing_due_date_label": "",
                "has_missing_event": False,
                "missing_event_label": "",
            }
        ]
        rows = view.get_grid_data(items, [status])
        assert len(rows) == 1
        due_data = rows[0][7]
        assert due_data == {
            "display": formats.date_format(due_date, "DATE_FORMAT"),
            "iso": "2026-12-25",
        }

    def test_relation_grid_data_translates_birthday(self, user):
        """Global Birthday events translate according to the active language."""
        event_id = uuid.uuid4()
        view = RelationListView()
        items = [
            {
                "relation_id": uuid.uuid4(),
                "gift__gift_id": None,
                "gift__name": None,
                "person__person_id": None,
                "group__group_id": None,
                "related_object": "Alice",
                "recipient_type": "person",
                "event__event_id": event_id,
                "event__name": "Birthday",
                "event__is_birthday": True,
                "comment": "",
                "status": None,
                "due_date": None,
                "urgency_key": "ideas",
                "needs_attention": False,
                "attention_label": "",
                "has_missing_data": False,
                "missing_data_label": "",
                "has_missing_due_date": False,
                "missing_due_date_label": "",
                "has_missing_event": False,
                "missing_event_label": "",
            }
        ]
        with translation.override("fr"):
            rows = view.get_grid_data(items, [])
            assert rows[0][3]["name"] == "Anniversaire"

        with translation.override("en"):
            rows = view.get_grid_data(items, [])
            assert rows[0][3]["name"] == "Birthday"


@pytest.mark.django_db
class TestPersonGridDataSerialization:
    """Unit and integration tests for PersonListView grid data serialization."""

    def test_get_grid_data_structure(self, user):
        group = PersonGroupFactory(name="Family", shared_with=[user])
        person = PersonFactory(
            first_name="Jane",
            family_name="Doe",
            email_address=encode_email("jane@example.com"),
            groups=[group],
            shared_with=[user],
        )
        view = PersonListView()
        items = [
            {
                "person_id": person.person_id,
                "first_name": "Jane",
                "family_name": "Doe",
                "email_address": encode_email("jane@example.com"),
                "groups_info": [{"id": group.group_id, "name": group.name}],
            }
        ]
        rows = view.get_grid_data(items)
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == ""
        assert row[1] == "Jane"
        assert row[2] == "Doe"
        assert row[3] == "jane@example.com"
        assert row[4] == [
            {
                "id": str(group.group_id),
                "name": "Family",
                "url": reverse("gift_manager:person_group_detail", args=[group.group_id]),
            }
        ]
        assert row[5] == str(person.person_id)
        assert row[6] == reverse("gift_manager:person_relation_create", args=[person.person_id])
        assert row[7] == reverse("gift_manager:person_detail", args=[person.person_id])
        assert row[8] == reverse("gift_manager:person_edit", args=[person.person_id])
        assert row[9] == reverse("gift_manager:person_delete", args=[person.person_id])
        assert row[10] == ""
        assert len(row) == 11

    def test_person_list_page_serves_valid_grid_data_and_permissions(
        self, authenticated_client, user
    ):
        person = PersonFactory(first_name="Charlie", family_name="Brown", shared_with=[user])
        response = authenticated_client.get(reverse("gift_manager:persons"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        perms = _extract_user_permissions_json(response.content.decode())
        names = [row[1] for row in grid_data]
        assert "Charlie" in names
        assert str(person.person_id) in perms

    def test_person_rows_end_with_link_label(self, user, user_factory):
        ana = user_factory(username="ana")
        friend_record = PersonFactory(
            first_name="Ana", family_name="Smith", account=ana, shared_with=[user]
        )
        self_record = PersonFactory(
            first_name="Self", family_name="User", account=user, shared_with=[user]
        )
        unlinked_record = PersonFactory(
            first_name="Plain", family_name="Person", shared_with=[user]
        )

        view = PersonListView()
        view.request = type("Request", (), {"user": user})()

        items = list(get_person_grid_queryset(user))
        rows = view.get_grid_data(items)
        assert len(rows) == 3

        friend_row = next(r for r in rows if r[5] == str(friend_record.person_id))
        assert len(friend_row) == 11
        assert friend_row[1] == "Ana"
        assert friend_row[10] == "Linked to ana"

        self_row = next(r for r in rows if r[5] == str(self_record.person_id))
        assert len(self_row) == 11
        assert self_row[1] == "Self"
        assert self_row[10] == "This is you"

        unlinked_row = next(r for r in rows if r[5] == str(unlinked_record.person_id))
        assert len(unlinked_row) == 11
        assert unlinked_row[10] == ""

    def test_deleted_linked_account_leaves_empty_label(self, user, user_factory):
        ana = user_factory(username="ana")
        friend_record = PersonFactory(
            first_name="Ana", family_name="Smith", account=ana, shared_with=[user]
        )
        ana.delete()

        view = PersonListView()
        view.request = type("Request", (), {"user": user})()

        items = list(get_person_grid_queryset(user))
        rows = view.get_grid_data(items)
        friend_row = next(r for r in rows if r[5] == str(friend_record.person_id))
        assert len(friend_row) == 11
        assert friend_row[10] == ""

    def test_recipient_view_people_includes_link_label(self, authenticated_client, user):
        PersonFactory(first_name="Self", family_name="User", account=user, shared_with=[user])
        response = authenticated_client.get(f"{reverse('gift_manager:recipients')}?view=people")
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        self_row = next(r for r in grid_data if r[1] == "Self")
        assert len(self_row) == 11
        assert self_row[10] == "This is you"


@pytest.mark.django_db
class TestPersonGroupGridDataSerialization:
    """Unit and integration tests for PersonGroupListView grid data serialization."""

    def test_get_grid_data_structure(self, user):
        group = PersonGroupFactory(name="Colleagues", shared_with=[user])
        view = PersonGroupListView()
        items = [
            {
                "group_id": group.group_id,
                "name": "Colleagues",
                "member_count": 5,
            }
        ]
        rows = view.get_grid_data(items)
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == ""
        assert row[1] == "Colleagues"
        assert row[2] == 5
        assert row[3] == str(group.group_id)
        assert row[4] == reverse("gift_manager:person_group_relation_create", args=[group.group_id])
        assert row[5] == reverse("gift_manager:person_group_detail", args=[group.group_id])
        assert row[6] == reverse("gift_manager:person_group_edit", args=[group.group_id])
        assert row[7] == reverse("gift_manager:person_group_delete", args=[group.group_id])

    def test_person_group_list_page_serves_valid_grid_data_and_permissions(
        self, authenticated_client, user
    ):
        group = PersonGroupFactory(name="Friends", shared_with=[user])
        response = authenticated_client.get(reverse("gift_manager:person_groups"))
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        perms = _extract_user_permissions_json(response.content.decode())
        names = [row[1] for row in grid_data]
        assert "Friends" in names
        assert str(group.group_id) in perms


@pytest.mark.django_db
class TestRecipientGridDataSerialization:
    """Integration tests for RecipientListView grid data in people and groups views."""

    def test_recipient_people_view_serves_grid_data(self, authenticated_client, user):
        person = PersonFactory(first_name="Diana", shared_with=[user])
        response = authenticated_client.get(reverse("gift_manager:recipients") + "?view=people")
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        perms = _extract_user_permissions_json(response.content.decode())
        names = [row[1] for row in grid_data]
        assert "Diana" in names
        assert str(person.person_id) in perms

    def test_recipient_groups_view_serves_grid_data(self, authenticated_client, user):
        group = PersonGroupFactory(name="Team", shared_with=[user])
        response = authenticated_client.get(reverse("gift_manager:recipients") + "?view=groups")
        assert response.status_code == 200
        grid_data = _extract_grid_data_json(response.content.decode())
        perms = _extract_user_permissions_json(response.content.decode())
        names = [row[1] for row in grid_data]
        assert "Team" in names
        assert str(group.group_id) in perms
