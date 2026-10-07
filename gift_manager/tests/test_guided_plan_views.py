"""Tests for the guided gift plan creation view."""

from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def url():
    return reverse("gift_manager:relation_guided_create")


@pytest.fixture
def idea_status():
    status, _ = RelationStatus.objects.get_or_create(status_en="Idea", defaults={"status": "Idea"})
    return status


@pytest.fixture
def person(user):
    return PersonFactory(shared_with=[user])


def _recipient(person) -> str:
    return f"person:{person.person_id}"


def _post(client, url, step, *, nav="next", htmx=False, **data):
    extra = HTMX if htmx else {}
    return client.post(url, {"step": step, "nav": nav, **data}, **extra)


class TestSteps:
    def test_get_renders_recipient_step_as_full_page(self, authenticated_client, url):
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert response.context["step"] == 1
        assert "recipient" in response.context["step_form"].fields
        assert "gift_manager/relation_guided.html" in [t.name for t in response.templates]

    def test_get_renders_partial_for_htmx(self, authenticated_client, url):
        response = authenticated_client.get(url, **HTMX)

        assert [t.name for t in response.templates][0] == (
            "gift_manager/includes/relation_guided_partial.html"
        )
        assert b"<html" not in response.content

    def test_next_with_invalid_step_stays_on_step_with_error(self, authenticated_client, url):
        response = _post(authenticated_client, url, 1, recipient="")

        assert response.context["step"] == 1
        assert "recipient" in response.context["step_form"].errors

    def test_next_advances_and_carries_values_as_hidden_inputs(
        self, authenticated_client, url, person
    ):
        response = _post(authenticated_client, url, 1, recipient=_recipient(person))

        assert response.context["step"] == 2
        assert ("recipient", _recipient(person)) in response.context["carried"]
        assert f'type="hidden" name="recipient" value="{_recipient(person)}"' in (
            response.content.decode()
        )

    def test_back_preserves_entered_values(self, authenticated_client, url, person, user):
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            2,
            nav="back",
            recipient=_recipient(person),
            gift=gift.pk,
        )

        assert response.context["step"] == 1
        assert response.context["step_form"].initial["recipient"] == _recipient(person)
        assert ("gift", str(gift.pk)) in response.context["carried"]

    def test_requires_login(self, client, url):
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_full_form_link_points_to_relation_create(self, authenticated_client, url):
        response = authenticated_client.get(url)

        assert response.context["full_form_url"] == reverse("gift_manager:relation_create")
        assert "Use an empty full form" in response.content.decode()


class TestFinalSubmit:
    def _final_data(self, person, **overrides):
        data = {"recipient": _recipient(person)}
        data.update(overrides)
        return data

    def test_end_to_end_creates_plan_with_existing_gift(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))

        response = _post(
            authenticated_client,
            url,
            3,
            **self._final_data(person, gift=gift.pk, event=event.pk, comment="Wrap it"),
        )

        assert response.status_code == 302
        plan = Relation.objects.get()
        assert plan.person == person
        assert plan.gift == gift
        assert plan.event == event
        assert plan.status == idea_status
        assert plan.due_date == date(2030, 12, 25)
        assert plan.comment == "Wrap it"
        assert PermissionService.get_effective_permission(plan, user) == PermissionLevel.OWNER

    def test_htmx_success_closes_the_panel(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client, url, 3, htmx=True, **self._final_data(person, gift=gift.pk)
        )

        assert response.status_code == 200
        assert "offcanvas:close" in response["HX-Trigger"]
        assert Relation.objects.count() == 1

    def test_end_to_end_with_new_gift_and_new_event(
        self, authenticated_client, url, person, user, idea_status
    ):
        response = _post(
            authenticated_client,
            url,
            3,
            **self._final_data(
                person,
                new_gift_name="Scarf",
                new_event_name="Housewarming",
                new_event_date="2030-05-04",
            ),
        )

        assert response.status_code == 302
        plan = Relation.objects.get()
        assert plan.gift.name == "Scarf"
        assert plan.event.name == "Housewarming"
        assert plan.event.schedule_type == Event.ScheduleType.ONE_TIME
        assert plan.due_date == date(2030, 5, 4)
        assert PermissionService.get_effective_permission(plan.gift, user) == PermissionLevel.OWNER
        assert PermissionService.get_effective_permission(plan.event, user) == PermissionLevel.OWNER

    def test_guided_plan_matches_full_form_plan(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))
        _post(
            authenticated_client,
            url,
            3,
            **self._final_data(person, gift=gift.pk, event=event.pk, comment="Wrap it"),
        )
        guided = Relation.objects.get()
        guided.delete()

        authenticated_client.post(
            reverse("gift_manager:relation_create"),
            {
                "recipient": _recipient(person),
                "gift": gift.pk,
                "event": event.pk,
                "status": idea_status.pk,
                "due_date": "2030-12-25",
                "comment": "Wrap it",
            },
        )
        full = Relation.objects.get()

        for field in ("person", "group", "gift", "event", "status", "due_date", "comment"):
            assert getattr(full, field) == getattr(guided, field), field
        assert full.is_surprise == guided.is_surprise

    def test_group_recipient_works(self, authenticated_client, url, user, idea_status):
        group = PersonGroupFactory(shared_with=[user])
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client, url, 3, recipient=f"group:{group.group_id}", gift=gift.pk
        )

        assert response.status_code == 302
        assert Relation.objects.get().group == group

    def test_tampered_inaccessible_gift_is_rejected_without_side_effects(
        self, authenticated_client, url, person, idea_status
    ):
        foreign_gift = GiftFactory()
        gifts_before = Gift.objects.count()
        events_before = Event.objects.count()

        response = _post(
            authenticated_client,
            url,
            3,
            **self._final_data(
                person,
                gift=foreign_gift.pk,
                new_event_name="Party",
                new_event_date="2030-05-04",
            ),
        )

        assert response.status_code == 200
        assert response.context["step"] == 2
        assert Relation.objects.count() == 0
        assert Gift.objects.count() == gifts_before
        assert Event.objects.count() == events_before

    def test_tampered_inaccessible_recipient_is_rejected(
        self, authenticated_client, url, user, idea_status
    ):
        stranger = PersonFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(authenticated_client, url, 3, recipient=_recipient(stranger), gift=gift.pk)

        assert response.context["step"] == 1
        assert Relation.objects.count() == 0

    def test_invalid_plan_rolls_back_inline_objects(
        self, authenticated_client, url, person, idea_status
    ):
        gifts_before = Gift.objects.count()
        events_before = Event.objects.count()

        with patch("gift_manager.views.relation_guided.RelationForm.is_valid", return_value=False):
            response = _post(
                authenticated_client,
                url,
                3,
                **self._final_data(
                    person,
                    new_gift_name="Scarf",
                    new_event_name="Party",
                    new_event_date="2030-05-04",
                ),
            )

        assert response.status_code == 200
        assert response.context["step"] == 3
        assert Relation.objects.count() == 0
        assert Gift.objects.count() == gifts_before
        assert Event.objects.count() == events_before
        assert response.context["step_form"].non_field_errors()
