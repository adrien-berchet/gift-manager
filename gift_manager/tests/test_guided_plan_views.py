"""Tests for the guided gift plan creation view."""

import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory

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


def _owned(user, obj):
    create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)
    return obj


def _post(client, view_url, step, *, nav="next", htmx=False, **data):
    extra = HTMX if htmx else {}
    return client.post(view_url, {"step": step, "nav": nav, **data}, **extra)


def _plan_fields(idea_status, **extra) -> dict:
    return {"status": idea_status.pk, "is_surprise": "false", **extra}


def _new_person(**extra) -> dict:
    return {
        "new_person-first_name": "Anna",
        "new_person-family_name": "Martin",
        "new_person-email_address": "anna@example.com",
        "new_person-birthday_day": "4",
        "new_person-birthday_month": "5",
        "new_person-notes": "Likes tea",
        **extra,
    }


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

    def test_new_object_error_is_shown_on_its_step(self, authenticated_client, url):
        response = _post(
            authenticated_client,
            url,
            1,
            **_new_person(**{"new_person-birthday_day": "31", "new_person-birthday_month": "2"}),
        )

        assert response.context["step"] == 1
        assert response.context["step_form"].new_form.errors
        assert "Enter a valid date." in response.content.decode()

    def test_multi_valued_inputs_survive_back_and_next(self, authenticated_client, url, user):
        groups = [_owned(user, PersonGroupFactory()) for _ in range(2)]
        tags = [_owned(user, GiftTagFactory()) for _ in range(2)]
        group_ids = sorted(str(group.pk) for group in groups)
        tag_ids = sorted(str(tag.pk) for tag in tags)

        forward = _post(
            authenticated_client,
            url,
            1,
            **_new_person(**{"new_person-groups": group_ids, "new_person-interests": tag_ids}),
        )
        carried = forward.context["carried"]
        assert sorted(v for n, v in carried if n == "new_person-groups") == group_ids
        assert sorted(v for n, v in carried if n == "new_person-interests") == tag_ids

        posted = {}
        for name, value in carried:
            posted.setdefault(name, []).append(value)
        back = _post(authenticated_client, url, 2, nav="back", **posted)

        initial = back.context["step_form"].new_form.initial
        assert sorted(initial["groups"]) == group_ids
        assert sorted(initial["interests"]) == tag_ids

    def test_surprise_no_survives_back_and_next(self, authenticated_client, url, user, idea_status):
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())
        gift = GiftFactory(shared_with=[user])

        first = _post(authenticated_client, url, 2, recipient=_recipient(linked), gift=gift.pk)
        assert first.context["step"] == 3
        assert first.context["step_form"].fields["is_surprise"].initial == "true"

        back = _post(
            authenticated_client,
            url,
            3,
            nav="back",
            recipient=_recipient(linked),
            gift=gift.pk,
            **_plan_fields(idea_status),
        )
        carried = dict(back.context["carried"])
        assert carried["is_surprise"] == "false"

        again = _post(authenticated_client, url, 2, gift=gift.pk, **carried)
        assert again.context["step"] == 3
        assert again.context["step_form"].initial["is_surprise"] == "false"


class TestFinalSubmit:
    def _final_data(self, person, idea_status, **overrides):
        data = {"recipient": _recipient(person), **_plan_fields(idea_status)}
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
            **self._final_data(
                person, idea_status, gift=gift.pk, event=event.pk, comment="Wrap it"
            ),
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
            authenticated_client,
            url,
            3,
            htmx=True,
            **self._final_data(person, idea_status, gift=gift.pk),
        )

        assert response.status_code == 200
        assert "offcanvas:close" in response["HX-Trigger"]
        assert Relation.objects.count() == 1

    def test_end_to_end_creates_new_person_with_details_gift_and_event(
        self, authenticated_client, url, user, idea_status
    ):
        group = _owned(user, PersonGroupFactory())
        tag = _owned(user, GiftTagFactory())
        planned, _ = RelationStatus.objects.get_or_create(
            status_en="Planned", defaults={"status": "Planned"}
        )

        response = _post(
            authenticated_client,
            url,
            3,
            **_new_person(**{"new_person-groups": [group.pk], "new_person-interests": [tag.pk]}),
            **{
                "new_gift-name": "Scarf",
                "new_gift-comment": "Wool",
                "new_gift-url": "https://example.com/scarf",
                "new_gift-price": "19.90",
                "new_gift-tags": [tag.pk],
                "new_event-name": "Housewarming",
                "new_event-comment": "Party",
                "new_event-schedule_type": "recurring",
                "new_event-date": "2030-05-04",
                "new_event-recurrence": "yearly",
                "status": planned.pk,
                "url": "https://example.com/override",
                "price": "12.50",
                "comment": "Notes",
                "due_date": "2030-06-01",
                "is_surprise": "false",
            },
        )

        assert response.status_code == 302
        person = Person.objects.get(first_name="Anna")
        assert list(person.groups.all()) == [group]
        assert list(person.interests.all()) == [tag]
        gift = Gift.objects.get(name="Scarf")
        assert (gift.comment, gift.price, list(gift.tags.all())) == (
            "Wool",
            Decimal("19.90"),
            [tag],
        )
        event = Event.objects.get(name="Housewarming")
        assert (event.schedule_type, event.recurrence) == (Event.ScheduleType.RECURRING, "yearly")
        plan = Relation.objects.get()
        assert (plan.person, plan.gift, plan.event) == (person, gift, event)
        assert plan.status == planned
        assert plan.url == "https://example.com/override"
        assert plan.price == Decimal("12.50")
        assert plan.comment == "Notes"
        assert plan.due_date == date(2030, 6, 1)
        assert PermissionService.get_effective_permission(person, user) == PermissionLevel.OWNER
        assert PermissionService.get_effective_permission(plan, user) == PermissionLevel.OWNER

    def test_guided_plan_matches_full_form_plan(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])
        event = EventFactory(shared_with=[user], date=date(2030, 12, 25))
        _post(
            authenticated_client,
            url,
            3,
            **self._final_data(
                person, idea_status, gift=gift.pk, event=event.pk, comment="Wrap it"
            ),
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

    def test_guided_plan_with_new_objects_matches_full_form_plan(
        self, authenticated_client, url, user, idea_status
    ):
        data = {
            **_new_person(),
            "new_gift-name": "Scarf",
            "new_event-name": "Housewarming",
            "new_event-schedule_type": "one_time",
            "new_event-date": "2030-05-04",
            **_plan_fields(idea_status, comment="Wrap it"),
        }
        _post(authenticated_client, url, 3, **data)
        guided = Relation.objects.get()
        person, gift, event = guided.person, guided.gift, guided.event
        guided.delete()

        authenticated_client.post(
            reverse("gift_manager:relation_create"),
            {
                "recipient": _recipient(person),
                "gift": gift.pk,
                "event": event.pk,
                "status": idea_status.pk,
                "due_date": "2030-05-04",
                "comment": "Wrap it",
            },
        )
        full = Relation.objects.get()

        for field in ("person", "gift", "event", "status", "due_date", "comment", "is_surprise"):
            assert getattr(full, field) == getattr(guided, field), field

    def test_group_recipient_works(self, authenticated_client, url, user, idea_status):
        group = PersonGroupFactory(shared_with=[user])
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            recipient=f"group:{group.group_id}",
            gift=gift.pk,
            **_plan_fields(idea_status),
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
                idea_status,
                gift=foreign_gift.pk,
                **{
                    "new_event-name": "Party",
                    "new_event-schedule_type": "one_time",
                    "new_event-date": "2030-05-04",
                },
            ),
        )

        assert response.status_code == 200
        assert response.context["step"] == 2
        assert Relation.objects.count() == 0
        assert Gift.objects.count() == gifts_before
        assert Event.objects.count() == events_before

    def test_tampered_inaccessible_event_is_rejected(
        self, authenticated_client, url, person, user, idea_status
    ):
        foreign_event = EventFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            **self._final_data(person, idea_status, gift=gift.pk, event=foreign_event.pk),
        )

        assert response.context["step"] == 3
        assert Relation.objects.count() == 0

    def test_tampered_inaccessible_recipient_is_rejected(
        self, authenticated_client, url, user, idea_status
    ):
        stranger = PersonFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            recipient=_recipient(stranger),
            gift=gift.pk,
            **_plan_fields(idea_status),
        )

        assert response.context["step"] == 1
        assert Relation.objects.count() == 0

    def test_tampered_inaccessible_group_for_new_person_is_rejected_without_side_effects(
        self, authenticated_client, url, user, idea_status
    ):
        foreign_group = PersonGroupFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            gift=gift.pk,
            **_new_person(**{"new_person-groups": [foreign_group.pk]}),
            **_plan_fields(idea_status),
        )

        assert response.context["step"] == 1
        assert "groups" in response.context["step_form"].new_form.errors
        assert not Person.objects.filter(first_name="Anna").exists()
        assert foreign_group.person_set.count() == 0
        assert Relation.objects.count() == 0

    def test_invalid_plan_rolls_back_new_person_gift_event_and_group_membership(
        self, authenticated_client, url, user, idea_status
    ):
        group = _owned(user, PersonGroupFactory())
        persons_before = Person.objects.count()
        gifts_before = Gift.objects.count()
        events_before = Event.objects.count()

        with patch("gift_manager.views.relation_guided.RelationForm.is_valid", return_value=False):
            response = _post(
                authenticated_client,
                url,
                3,
                **_new_person(**{"new_person-groups": [group.pk]}),
                **{
                    "new_gift-name": "Scarf",
                    "new_event-name": "Party",
                    "new_event-schedule_type": "one_time",
                    "new_event-date": "2030-05-04",
                },
                **_plan_fields(idea_status),
            )

        assert response.status_code == 200
        assert response.context["step"] == 3
        assert Relation.objects.count() == 0
        assert Person.objects.count() == persons_before
        assert Gift.objects.count() == gifts_before
        assert Event.objects.count() == events_before
        assert group.person_set.count() == 0
        assert response.context["step_form"].non_field_errors()


class TestEntryPoints:
    def test_relation_list_links_to_guided_flow(self, authenticated_client, url):
        response = authenticated_client.get(reverse("gift_manager:relations"))

        assert f'href="{url}"' in response.content.decode()

    def test_home_links_to_guided_flow(self, authenticated_client, url):
        response = authenticated_client.get(reverse("gift_manager:home"))

        assert f'href="{url}"' in response.content.decode()

    def test_full_form_link_is_a_create_link_in_the_offcanvas(self, authenticated_client, url):
        content = authenticated_client.get(url, **HTMX).content.decode()

        link = re.search(r"<a[^>]*relations/create/[^>]*>", content).group(0)
        assert 'data-action="create"' in link

    def test_full_form_link_is_a_plain_link_on_the_page(self, authenticated_client, url):
        content = authenticated_client.get(url).content.decode()

        link = re.search(r"<a[^>]*relations/create/[^>]*>", content).group(0)
        assert 'data-action="create"' not in link

    def test_later_steps_are_flagged_as_holding_unsaved_input(
        self, authenticated_client, url, person
    ):
        first = authenticated_client.get(url, **HTMX).content.decode()
        second = _post(
            authenticated_client, url, 1, htmx=True, recipient=_recipient(person)
        ).content.decode()

        assert "data-unsaved-always-dirty" not in first
        assert 'data-unsaved-always-dirty="true"' in second
        assert 'data-unsaved-no-save="true"' in second
