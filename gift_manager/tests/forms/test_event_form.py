from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.forms import EventForm
from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


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


@pytest.mark.django_db
def test_event_form_recurrent_event_appears_in_upcoming_occasions(client):
    user = UserFactory()
    client.force_login(user)
    anchor_date = timezone.localdate()
    form = EventForm(
        data={
            "name": "Gift occasion",
            "comment": "",
            "date_type": "recurrence",
            "absolute_date": anchor_date.isoformat(),
            "recurrence": "yearly",
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    person = PersonFactory(shared_with=[user])
    gift = GiftFactory(shared_with=[user])
    status = RelationStatusFactory(status="Planned")
    relation = RelationFactory(person=person, gift=gift, event=event, status=status)
    PermissionService.create_or_update_permission(
        user, event, permission_level=PermissionLevel.OWNER
    )
    PermissionService.create_or_update_permission(
        user, relation, permission_level=PermissionLevel.OWNER
    )

    response = client.get(reverse("gift_manager:home"))

    assert response.status_code == 200
    upcoming_items = response.context["upcoming_occasion_recipients"]
    assert len(upcoming_items) == 1
    assert upcoming_items[0]["event"] == event
