import pytest
from django.urls import reverse

from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
def test_person_search_serializes_current_group_id(client):
    user = UserFactory()
    client.force_login(user)
    group = PersonGroupFactory(name="Family", shared_with=[user])
    person = PersonFactory(first_name="Ada", family_name="Lovelace", shared_with=[user])
    person.groups.add(group)

    response = client.get(reverse("gift_manager:person_search"), {"search": "Ada"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["groups_info"] == [{"id": str(group.group_id), "name": "Family"}]


@pytest.mark.django_db
def test_gift_search_serializes_current_tag_id(client):
    user = UserFactory()
    client.force_login(user)
    tag = GiftTagFactory(name="Books", shared_with=[user])
    gift = GiftFactory(name="Novel", shared_with=[user])
    gift.tags.add(tag)

    response = client.get(reverse("gift_manager:gift_search"), {"search": "Novel"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["tags_info"] == [{"id": str(tag.tag_id), "name": "Books"}]


@pytest.mark.django_db
def test_event_search_serializes_schedule_contract(client):
    user = UserFactory()
    client.force_login(user)
    event = EventFactory(
        name="Graduation",
        schedule_type="one_time",
        recurrence="yearly",
        shared_with=[user],
    )

    response = client.get(reverse("gift_manager:event_search"), {"search": "Graduation"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0] == {
        "event_id": str(event.event_id),
        "name": "Graduation",
        "comment": event.comment,
        "schedule_type": "one_time",
        "schedule_type_label": event.get_schedule_type_display(),
        "date": event.date.isoformat(),
        "date_summary": event.date_summary,
        "schedule_display": event.date_summary,
        "recurrence": "",
        "recurrence_label": "",
    }
