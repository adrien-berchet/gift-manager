# pylint: disable=redefined-outer-name
import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import override

from gift_manager.models import Event
from gift_manager.models import EventPermission
from gift_manager.models import PermissionLevel


@pytest.mark.django_db
class TestEvent:
    """Tests for the Event model."""

    def test_event_creation(self, event, event_name, event_comment, event_date):
        """Test creating an event."""
        assert event.name == event_name
        assert event.comment == event_comment
        assert event.schedule_type == Event.ScheduleType.RECURRING
        assert event.date == event_date
        assert event.recurrence == "yearly"
        assert event.is_scheduled
        assert event.is_recurring
        assert event.event_id is not None
        assert isinstance(event.event_id, uuid.UUID)
        assert isinstance(event.creation_date, datetime)

    def test_event_string_representation(self, event, event_name):
        """Test the string representation of an event."""
        assert str(event) == event_name

    def test_event_permission(self, user, username, event, event_name):
        """Test adding a permission to an event."""
        permission = EventPermission.objects.create(
            user=user, event=event, permission_type=PermissionLevel.OWNER
        )
        assert permission.permission_type == PermissionLevel.OWNER
        assert permission.user == user
        assert permission.event == event
        assert str(permission) == f"{username} - {event_name} -> owner"
        assert user in event.shared_with.all()


@pytest.mark.django_db
class TestEventManagerMethods:
    """Tests for EventManager query methods."""

    def test_for_list_display(self, user, event):
        """Test for_list_display returns optimized queryset."""
        # Share event with user
        EventPermission.objects.create(
            user=user, event=event, permission_type=PermissionLevel.VIEWER
        )

        results = Event.objects.for_list_display(user).filter(pk=event.pk)
        assert len(results) == 1
        result = results[0]

        assert result.event_id == event.event_id
        assert result.name == event.name
        assert result.date_summary

    def test_one_time_event_next_occurrence_is_none_after_date(self):
        event = Event.objects.create(
            name="Graduation",
            schedule_type=Event.ScheduleType.ONE_TIME,
            date=timezone.localdate() - timedelta(days=1),
        )

        assert event.next_occurrence() is None

    def test_event_model_rejects_inconsistent_schedule_fields(self):
        event = Event(
            name="Graduation",
            schedule_type=Event.ScheduleType.ONE_TIME,
            date=timezone.datetime(2026, 6, 1).date(),
            recurrence="yearly",
        )

        with pytest.raises(ValidationError) as exc_info:
            event.full_clean()

        assert "recurrence" in exc_info.value.message_dict

    def test_yearly_event_next_occurrence_uses_next_matching_date(self):
        event = Event.objects.create(
            name="Birthday",
            schedule_type=Event.ScheduleType.RECURRING,
            date=timezone.datetime(2000, 5, 15).date(),
            recurrence="yearly",
        )

        assert event.next_occurrence(today=timezone.datetime(2026, 5, 16).date()).isoformat() == (
            "2027-05-15"
        )

    def test_date_summary_translates_recurrence_sentence_label(self):
        event = Event(
            name="Christmas",
            schedule_type=Event.ScheduleType.RECURRING,
            date=timezone.datetime(2000, 12, 25).date(),
            recurrence="yearly",
        )

        with override("fr"):
            assert event.get_recurrence_display() == "Annuel"
            assert event.date_summary == "Se répète annuellement à partir du 25 décembre 2000"
