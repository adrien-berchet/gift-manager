from datetime import timedelta

import pytest
from django.utils import timezone

from gift_manager.forms import EventForm
from gift_manager.models import Event


@pytest.mark.django_db
def test_unscheduled_event_form_clears_date_and_recurrence():
    form = EventForm(
        data={
            "name": "Housewarming",
            "comment": "",
            "schedule_type": Event.ScheduleType.UNSCHEDULED,
            "date": timezone.localdate().isoformat(),
            "recurrence": "weekly",
        }
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.schedule_type == Event.ScheduleType.UNSCHEDULED
    assert event.date is None
    assert event.recurrence is None


@pytest.mark.django_db
def test_one_time_event_form_requires_date_and_clears_recurrence():
    event_date = timezone.localdate() + timedelta(days=7)
    form = EventForm(
        data={
            "name": "Graduation party",
            "comment": "",
            "schedule_type": Event.ScheduleType.ONE_TIME,
            "date": event_date.isoformat(),
            "recurrence": "yearly",
        }
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.schedule_type == Event.ScheduleType.ONE_TIME
    assert event.date == event_date
    assert event.recurrence is None


@pytest.mark.django_db
def test_recurring_event_form_requires_date_and_recurrence():
    event_date = timezone.localdate() + timedelta(days=7)
    form = EventForm(
        data={
            "name": "Weekly dinner",
            "comment": "",
            "schedule_type": Event.ScheduleType.RECURRING,
            "date": event_date.isoformat(),
            "recurrence": "weekly",
        }
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.schedule_type == Event.ScheduleType.RECURRING
    assert event.date == event_date
    assert event.recurrence == "weekly"


@pytest.mark.django_db
def test_recurring_event_form_rejects_missing_recurrence():
    form = EventForm(
        data={
            "name": "Weekly dinner",
            "comment": "",
            "schedule_type": Event.ScheduleType.RECURRING,
            "date": timezone.localdate().isoformat(),
            "recurrence": "",
        }
    )

    assert not form.is_valid()
    assert "recurrence" in form.errors


@pytest.mark.django_db
def test_event_form_switching_to_unscheduled_clears_stale_schedule_fields():
    event = Event.objects.create(
        name="Birthday",
        schedule_type=Event.ScheduleType.RECURRING,
        date=timezone.localdate(),
        recurrence="yearly",
    )
    form = EventForm(
        data={
            "name": "Birthday",
            "comment": "",
            "schedule_type": Event.ScheduleType.UNSCHEDULED,
            "date": timezone.localdate().isoformat(),
            "recurrence": "yearly",
        },
        instance=event,
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.schedule_type == Event.ScheduleType.UNSCHEDULED
    assert event.date is None
    assert event.recurrence is None
