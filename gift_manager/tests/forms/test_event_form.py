from datetime import timedelta

import pytest
from django.utils import timezone

from gift_manager.forms import EventForm
from gift_manager.models import Event


@pytest.mark.django_db
def test_recurrent_event_form_persists_anchor_date_to_usual_date():
    anchor_date = timezone.localdate() + timedelta(days=7)
    form = EventForm(
        data={
            "name": "Weekly dinner",
            "comment": "",
            "date_type": "recurrence",
            "absolute_date": anchor_date.isoformat(),
            "recurrence": "weekly",
        }
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.usual_date == anchor_date
    assert event.recurrence == "weekly"
    assert event.absolute_date is None


@pytest.mark.django_db
def test_event_form_switching_to_absolute_clears_recurrence_fields():
    event = Event.objects.create(
        name="Birthday",
        usual_date=timezone.localdate(),
        recurrence="yearly",
    )
    absolute_date = timezone.localdate() + timedelta(days=3)
    form = EventForm(
        data={
            "name": "One-time party",
            "comment": "",
            "date_type": "absolute",
            "absolute_date": absolute_date.isoformat(),
            "recurrence": "yearly",
        },
        instance=event,
    )

    assert form.is_valid(), form.errors
    event = form.save()

    assert event.absolute_date == absolute_date
    assert event.usual_date is None
    assert event.recurrence is None
