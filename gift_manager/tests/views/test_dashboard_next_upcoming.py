"""Regression tests for the dashboard "coming up next" item with recurring events."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import Event
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory


@pytest.mark.django_db
@pytest.mark.parametrize("days_until_occurrence", [5, 18, 59, 200, 360])
def test_yearly_event_started_years_ago_beats_later_gift_plan(client, user, days_until_occurrence):
    """A yearly event created long ago is picked when its next occurrence is the soonest."""
    # Arrange
    client.force_login(user)
    today = timezone.localdate()
    next_occurrence = today + timedelta(days=days_until_occurrence)
    event = EventFactory(
        name="Yearly event",
        schedule_type=Event.ScheduleType.RECURRING,
        recurrence="yearly",
        date=next_occurrence.replace(year=next_occurrence.year - 2),
        shared_with=[user],
    )
    RelationFactory(
        gift=GiftFactory(name="Later plan"),
        status=RelationStatusFactory(status="Planned"),
        due_date=next_occurrence + timedelta(days=30),
        shared_with=[user],
    )

    # Act
    response = client.get(reverse("gift_manager:home"))

    # Assert
    item = response.context["next_upcoming_item"]
    assert response.context["dashboard_action_groups"] == []
    assert item["kind"] == "event"
    assert item["date"] == next_occurrence
    assert item["days_until"] == days_until_occurrence
    assert item["url"] == reverse("gift_manager:event_detail", kwargs={"pk": event.event_id})
