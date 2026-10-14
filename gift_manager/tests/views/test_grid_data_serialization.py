"""Tests for Grid.js data serialization and json_script elements."""

import json
import re
from decimal import Decimal

import pytest
from django.urls import reverse

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.views.event import EventListView
from gift_manager.views.gift import GiftListView


def _extract_grid_data_json(html: str) -> list:
    """Extract and parse the #grid-data json_script payload from rendered HTML."""
    match = re.search(r'<script id="grid-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, 'Could not find <script id="grid-data"> in rendered HTML'
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
