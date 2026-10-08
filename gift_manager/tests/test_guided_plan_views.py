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

    def test_next_with_invalid_step_stays_on_step_with_error(
        self, authenticated_client, url, person
    ):
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
            surprise_for=_recipient(linked),
            **_plan_fields(idea_status),
        )
        carried = dict(back.context["carried"])
        assert carried["is_surprise"] == "false"

        again = _post(authenticated_client, url, 2, gift=gift.pk, **carried)
        assert again.context["step"] == 3
        assert again.context["step_form"].initial["is_surprise"] == "false"

    def test_stale_surprise_is_dropped_when_the_recipient_changes(
        self, authenticated_client, url, user, idea_status
    ):
        plain = PersonFactory(shared_with=[user])
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())
        gift = GiftFactory(shared_with=[user])

        # Step 3 was filled for a recipient without a surprise default ("No" chosen)...
        back = _post(
            authenticated_client,
            url,
            3,
            nav="back",
            recipient=_recipient(plain),
            gift=gift.pk,
            surprise_for=_recipient(plain),
            **_plan_fields(idea_status),
        )
        carried = dict(back.context["carried"])
        # ...then the recipient is changed back in step 1 and the user moves forward again
        carried["recipient"] = _recipient(linked)
        step_two = _post(authenticated_client, url, 1, **carried)
        carried = dict(step_two.context["carried"])
        step_three = _post(authenticated_client, url, 2, gift=gift.pk, **carried)

        assert step_three.context["step"] == 3
        form = step_three.context["step_form"]
        assert "is_surprise" not in form.initial
        assert form.fields["is_surprise"].initial == "true"


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


class TestNewObjectBlocks:
    def _content(self, client, url, step):
        return client.get(url, {"step": step}, **HTMX).content.decode()

    def test_step_one_renders_new_person_inputs(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 1)

        for name in (
            "new_person-first_name",
            "new_person-family_name",
            "new_person-email_address",
            "new_person-birthday_day",
            "new_person-birthday_month",
            "new_person-birthday_year",
            "new_person-notes",
            "new_person-groups",
            "new_person-interests",
        ):
            assert f'name="{name}"' in content, name

    def test_step_two_renders_new_gift_inputs(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 2)

        for name in (
            "new_gift-name",
            "new_gift-comment",
            "new_gift-url",
            "new_gift-price",
            "new_gift-tags",
        ):
            assert f'name="{name}"' in content, name

    def test_step_three_renders_new_event_and_plan_inputs(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 3)

        for name in (
            "event",
            "new_event-name",
            "new_event-date",
            "new_event-comment",
            "new_event-schedule_type",
            "new_event-recurrence",
            "due_date",
            "comment",
            "status",
            "url",
            "price",
            "is_surprise",
        ):
            assert f'name="{name}"' in content, name

    def test_details_are_closed_by_default(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 1)

        assert re.search(r"<details[^>]*guided-new-details[^>]*>", content)
        assert not re.search(r"<details[^>]*guided-new-details[^>]* open", content)

    def test_details_open_when_values_present(self, authenticated_client, url):
        response = _post(
            authenticated_client, url, 2, nav="back", **{"new_person-notes": "Likes tea"}
        )

        content = response.content.decode()
        assert re.search(r"<details[^>]*guided-new-details[^>]* open", content)

    def test_details_open_when_the_new_object_has_errors(self, authenticated_client, url):
        response = _post(
            authenticated_client,
            url,
            1,
            **_new_person(**{"new_person-birthday_day": "31", "new_person-birthday_month": "2"}),
        )

        assert re.search(r"<details[^>]*guided-new-details[^>]* open", response.content.decode())

    @pytest.mark.parametrize(
        ("step", "name"),
        [(1, "new_person-first_name"), (2, "new_gift-name"), (3, "new_event-name")],
    )
    def test_new_object_inputs_never_block_the_browser_form(
        self, authenticated_client, url, step, name
    ):
        content = self._content(authenticated_client, url, step)

        tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', content).group(0)
        assert "required" not in tag
        assert "data-required" not in tag


class TestStepThreeSections:
    def _content(self, client, url):
        return client.get(url, {"step": 3}, **HTMX).content.decode()

    def test_step_three_separates_the_event_from_the_gift_plan(self, authenticated_client, url):
        content = self._content(authenticated_client, url)

        event_part, plan_part = content.split("guided-section--plan", 1)
        assert "guided-section--event" in event_part
        for name in ("event", "new_event-name", "new_event-date", "new_event-comment"):
            assert f'name="{name}"' in event_part, name
            assert f'name="{name}"' not in plan_part, name
        for name in ("due_date", "comment", "status", "url", "price", "is_surprise"):
            assert f'name="{name}"' in plan_part, name
            assert f'name="{name}"' not in event_part, name

    def test_step_three_sections_have_headings_and_distinct_disclosures(
        self, authenticated_client, url
    ):
        content = self._content(authenticated_client, url)

        event_part, plan_part = content.split("guided-section--plan", 1)
        assert re.search(r"<h3[^>]*>\s*Event\s*</h3>", event_part)
        assert re.search(r"<h3[^>]*>\s*Gift Plan\s*</h3>", plan_part)
        assert "More event details" in event_part
        assert "More gift plan details" in plan_part
        assert "More event details" not in plan_part

    def test_progress_label_of_the_last_step_uses_the_workflow_words(
        self, authenticated_client, url
    ):
        response = authenticated_client.get(url, {"step": 3}, **HTMX)

        assert str(response.context["steps"][2]["label"]) == "Event and gift plan"


class TestModeMarkup:
    def _content(self, client, url, step):
        return client.get(url, {"step": step}, **HTMX).content.decode()

    @staticmethod
    def _radios(content, name):
        return re.findall(rf'<input[^>]*type="radio"[^>]*name="{name}"[^>]*>', content)

    def test_step_one_offers_existing_or_new_when_people_exist(
        self, authenticated_client, url, person
    ):
        content = self._content(authenticated_client, url, 1)

        radios = self._radios(content, "recipient_mode")
        assert [re.search(r'value="(\w+)"', tag).group(1) for tag in radios] == [
            "existing",
            "new",
        ]
        assert "checked" in radios[0]
        assert "Existing recipient" in content
        assert "New person" in content
        assert "guided-panel--existing" in content
        assert "guided-panel--new" in content

    def test_step_one_skips_the_choice_without_existing_people(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 1)

        assert not self._radios(content, "recipient_mode")
        assert re.search(
            r'<input[^>]*type="hidden"[^>]*name="recipient_mode"[^>]*value="new"', content
        )
        assert "guided-panel--existing" not in content
        assert "guided-panel--new" in content

    def test_step_two_offers_existing_or_new_when_gifts_exist(
        self, authenticated_client, url, user
    ):
        GiftFactory(shared_with=[user])

        content = self._content(authenticated_client, url, 2)

        assert len(self._radios(content, "gift_mode")) == 2
        assert "Existing gift" in content
        assert "New gift" in content

    def test_step_three_offers_existing_new_and_no_event(self, authenticated_client, url):
        content = self._content(authenticated_client, url, 3)

        radios = self._radios(content, "event_mode")
        assert [re.search(r'value="(\w+)"', tag).group(1) for tag in radios] == [
            "existing",
            "new",
            "none",
        ]
        assert "No event" in content

    def test_posted_mode_is_carried_and_restored(self, authenticated_client, url, person):
        forward = _post(
            authenticated_client,
            url,
            1,
            recipient_mode="new",
            **_new_person(),
        )

        assert ("recipient_mode", "new") in forward.context["carried"]
        back = _post(
            authenticated_client,
            url,
            2,
            nav="back",
            **dict(forward.context["carried"]),
        )
        radios = self._radios(back.content.decode(), "recipient_mode")
        assert "checked" in next(tag for tag in radios if 'value="new"' in tag)
        assert "checked" not in next(tag for tag in radios if 'value="existing"' in tag)

    def test_stale_chooser_value_does_not_set_the_surprise_default_in_new_mode(
        self, authenticated_client, url, user
    ):
        linked = PersonFactory(shared_with=[user], user_link=UserFactory())
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            2,
            recipient_mode="new",
            recipient=_recipient(linked),
            gift=gift.pk,
            **_new_person(),
        )

        assert response.context["step"] == 3
        assert response.context["step_form"].fields["is_surprise"].initial == "false"


class TestInvalidStepResponses:
    def test_invalid_htmx_step_returns_422_with_a_notification(
        self, authenticated_client, url, person
    ):
        response = _post(authenticated_client, url, 1, htmx=True, recipient="")

        assert response.status_code == 422
        assert "showNotification" in response["HX-Trigger"]
        assert response.context["step"] == 1

    def test_invalid_step_without_htmx_stays_200(self, authenticated_client, url, person):
        response = _post(authenticated_client, url, 1, recipient="")

        assert response.status_code == 200
        assert "HX-Trigger" not in response

    def test_valid_htmx_step_stays_200(self, authenticated_client, url, person):
        response = _post(authenticated_client, url, 1, htmx=True, recipient=_recipient(person))

        assert response.status_code == 200
        assert response.context["step"] == 2

    def test_rejected_plan_returns_422_for_htmx(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])

        with patch("gift_manager.views.relation_guided.RelationForm.is_valid", return_value=False):
            response = _post(
                authenticated_client,
                url,
                3,
                htmx=True,
                recipient=_recipient(person),
                gift=gift.pk,
                **_plan_fields(idea_status),
            )

        assert response.status_code == 422
        assert response.context["step"] == 3

    def test_invalid_step_found_at_the_final_submit_returns_422_for_htmx(
        self, authenticated_client, url, user, idea_status
    ):
        stranger = PersonFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            htmx=True,
            recipient=_recipient(stranger),
            gift=gift.pk,
            **_plan_fields(idea_status),
        )

        assert response.status_code == 422
        assert response.context["step"] == 1


class TestSingleErrorSummary:
    def test_step_three_shows_one_summary_for_event_and_plan_errors(
        self, authenticated_client, url, person, user, idea_status
    ):
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            htmx=True,
            recipient=_recipient(person),
            gift=gift.pk,
            event_mode="new",
            **{"new_event-schedule_type": "one_time", "url": "not a url"},
            **_plan_fields(idea_status),
        )

        content = response.content.decode()
        assert content.count("form-error-summary") == 1
        assert "Enter a valid URL" in content
        assert 'href="#id_new_event-name"' in content
        assert 'href="#id_url"' in content


class TestTamperedMultiValuedInputs:
    def test_tampered_inaccessible_tag_for_a_new_gift_is_rejected(
        self, authenticated_client, url, person, idea_status
    ):
        foreign_tag = GiftTagFactory()

        response = _post(
            authenticated_client,
            url,
            3,
            recipient=_recipient(person),
            gift_mode="new",
            **{"new_gift-name": "Scarf", "new_gift-tags": [foreign_tag.pk]},
            **_plan_fields(idea_status),
        )

        assert response.context["step"] == 2
        assert "tags" in response.context["step_form"].new_form.errors
        assert not Gift.objects.filter(name="Scarf").exists()

    def test_tampered_inaccessible_interest_for_a_new_person_is_rejected(
        self, authenticated_client, url, user, idea_status
    ):
        foreign_tag = GiftTagFactory()
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            gift=gift.pk,
            recipient_mode="new",
            **_new_person(**{"new_person-interests": [foreign_tag.pk]}),
            **_plan_fields(idea_status),
        )

        assert response.context["step"] == 1
        assert "interests" in response.context["step_form"].new_form.errors
        assert not Person.objects.filter(first_name="Anna").exists()

    def test_multi_valued_inputs_reach_the_final_save(
        self, authenticated_client, url, user, idea_status
    ):
        groups = [_owned(user, PersonGroupFactory()) for _ in range(2)]
        tags = [_owned(user, GiftTagFactory()) for _ in range(2)]
        gift = GiftFactory(shared_with=[user])

        response = _post(
            authenticated_client,
            url,
            3,
            gift=gift.pk,
            recipient_mode="new",
            **_new_person(
                **{
                    "new_person-groups": [group.pk for group in groups],
                    "new_person-interests": [tag.pk for tag in tags],
                }
            ),
            **_plan_fields(idea_status),
        )

        assert response.status_code == 302
        person = Person.objects.get(first_name="Anna")
        assert set(person.groups.all()) == set(groups)
        assert set(person.interests.all()) == set(tags)
