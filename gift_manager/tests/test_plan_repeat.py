"""Tests for duplicating gift plans and repeating a recurring occasion's plans."""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationComment
from gift_manager.plan_repeat import find_repeat_candidates
from gift_manager.plan_repeat import repeat_plans
from gift_manager.plan_repeat import supports_plan_again
from gift_manager.services import PermissionService
from gift_manager.statuses import is_idea_status
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 5)


def _grant(user, obj, level=PermissionLevel.OWNER):
    PermissionService.create_or_update_permission(user, obj, permission_level=level)


def _christmas():
    """A yearly event: the last occurrence was 2025-12-25, the next is 2026-12-25."""
    return EventFactory(
        schedule_type=Event.ScheduleType.RECURRING,
        recurrence="yearly",
        date=date(2020, 12, 25),
    )


def _plan(user, event, *, due_date, status="Given", level=PermissionLevel.OWNER, **kwargs):
    """Create a plan on the event with every related object visible to the user."""
    person = kwargs.pop("person", None) or PersonFactory()
    gift = kwargs.pop("gift", None) or GiftFactory()
    for obj in (event, person, gift):
        _grant(user, obj, PermissionLevel.VIEWER)
    plan = RelationFactory(
        person=person,
        gift=gift,
        event=event,
        due_date=due_date,
        status=RelationStatusFactory(status=status),
        **kwargs,
    )
    _grant(user, plan, level)
    return plan


@pytest.fixture
def event(user):
    return _christmas()


class TestSupportsPlanAgain:
    def test_recurring_and_birthday_events_only(self, event):
        assert supports_plan_again(event)
        assert supports_plan_again(Event.objects.get_birthday_event())
        assert not supports_plan_again(EventFactory(schedule_type="one_time", recurrence=None))


class TestFindRepeatCandidates:
    def test_offers_last_occurrence_plan_with_next_date(self, user, event):
        plan = _plan(user, event, due_date=date(2025, 12, 24))

        [candidate] = find_repeat_candidates(user, event, TODAY)

        assert candidate.relation == plan
        assert candidate.due_date == date(2026, 12, 25)

    def test_ignores_older_occurrences_and_abandoned_plans(self, user, event):
        _plan(user, event, due_date=date(2023, 12, 25))
        _plan(user, event, due_date=date(2025, 12, 25), status="Abandoned")
        _plan(user, event, due_date=None)

        assert find_repeat_candidates(user, event, TODAY) == []

    def test_skips_pairs_already_planned_for_the_next_occurrence(self, user, event):
        old = _plan(user, event, due_date=date(2025, 12, 25))
        _plan(
            user,
            event,
            due_date=date(2026, 12, 20),
            status="Idea",
            person=old.person,
            gift=old.gift,
        )

        assert find_repeat_candidates(user, event, TODAY) == []

    def test_an_abandoned_next_plan_does_not_count_as_repeated(self, user, event):
        old = _plan(user, event, due_date=date(2025, 12, 25))
        _plan(
            user,
            event,
            due_date=date(2026, 12, 25),
            status="Abandoned",
            person=old.person,
            gift=old.gift,
        )

        assert [c.relation for c in find_repeat_candidates(user, event, TODAY)] == [old]

    def test_only_plans_the_user_can_see(self, user, event):
        hidden = RelationFactory(event=event, due_date=date(2025, 12, 25))
        _grant(user, event, PermissionLevel.VIEWER)

        assert hidden.relation_id not in [
            c.relation.relation_id for c in find_repeat_candidates(user, event, TODAY)
        ]

    def test_needs_access_to_the_gift_and_the_recipient(self, user, event):
        plan = _plan(user, event, due_date=date(2025, 12, 25))
        plan.gift.shared_with.clear()

        assert find_repeat_candidates(user, event, TODAY) == []

    def test_group_recipients_are_supported(self, user, event):
        group_plan = GroupRelationFactory(
            event=event, due_date=date(2025, 12, 25), status=RelationStatusFactory(status="Given")
        )
        for obj in (event, group_plan.group, group_plan.gift):
            _grant(user, obj, PermissionLevel.VIEWER)
        _grant(user, group_plan)

        [candidate] = find_repeat_candidates(user, event, TODAY)

        assert candidate.relation == group_plan
        assert candidate.due_date == date(2026, 12, 25)

    def test_one_time_events_have_nothing_to_repeat(self, user):
        one_time = EventFactory(schedule_type="one_time", recurrence=None, date=date(2025, 1, 1))
        _plan(user, one_time, due_date=date(2025, 1, 1))

        assert find_repeat_candidates(user, one_time, TODAY) == []

    def test_monthly_event_uses_a_one_month_window(self, user):
        monthly = EventFactory(recurrence="monthly", date=date(2025, 1, 15))
        _plan(user, monthly, due_date=date(2026, 9, 15))  # last occurrence
        _plan(user, monthly, due_date=date(2026, 7, 15))  # two occurrences ago

        [candidate] = find_repeat_candidates(user, monthly, TODAY)

        assert candidate.relation.due_date == date(2026, 9, 15)
        assert candidate.due_date == date(2026, 10, 15)

    def test_birthday_plans_use_the_recipients_next_birthday(self, user):
        birthday = Event.objects.get_birthday_event()
        person = PersonFactory(birthday_day=3, birthday_month=12)
        plan = _plan(user, birthday, due_date=date(2025, 12, 3), person=person)

        [candidate] = find_repeat_candidates(user, birthday, TODAY)

        assert candidate.relation == plan
        assert candidate.due_date == date(2026, 12, 3)

    def test_birthday_plans_without_a_known_birthday_get_no_date(self, user):
        birthday = Event.objects.get_birthday_event()
        person = PersonFactory(birthday_day=None, birthday_month=None, birthday_year=None)
        _plan(user, birthday, due_date=date(2026, 1, 1), person=person)

        [candidate] = find_repeat_candidates(user, birthday, TODAY)

        assert candidate.due_date is None

    def test_undated_copy_is_not_offered_twice(self, user):
        birthday = Event.objects.get_birthday_event()
        person = PersonFactory(birthday_day=None, birthday_month=None, birthday_year=None)
        old = _plan(user, birthday, due_date=date(2026, 1, 1), person=person)

        repeat_plans(user, birthday, [old.relation_id], TODAY)

        assert find_repeat_candidates(user, birthday, TODAY) == []


class TestRepeatPlans:
    def test_creates_idea_copies_without_reaction_and_sharing(self, user, event):
        source = _plan(
            user,
            event,
            due_date=date(2025, 12, 25),
            comment="Wrap it",
            url="https://example.com/gift",
            price="42.00",
            reaction_rating=5,
            reaction_note="Loved it",
        )
        sharer = UserFactory()
        _grant(sharer, source, PermissionLevel.VIEWER)

        [copy] = repeat_plans(user, event, [source.relation_id], TODAY)

        copy.refresh_from_db()
        assert copy.pk != source.pk
        assert is_idea_status(copy.status)
        assert copy.due_date == date(2026, 12, 25)
        assert (copy.person, copy.gift, copy.event) == (source.person, source.gift, event)
        assert (copy.comment, copy.url, str(copy.price)) == ("Wrap it", source.url, "42.00")
        assert copy.reaction_rating is None
        assert copy.reaction_note is None
        assert list(copy.shared_with.all()) == [user]
        assert PermissionService.get_effective_permission(copy, user) == PermissionLevel.OWNER
        assert PermissionService.get_effective_permission(copy, sharer) == PermissionLevel.NONE
        source.refresh_from_db()
        assert source.reaction_rating == 5

    def test_ignores_identifiers_that_are_not_candidates(self, user, event):
        outsider = RelationFactory(event=event, due_date=date(2025, 12, 25))

        assert repeat_plans(user, event, [outsider.relation_id], TODAY) == []
        assert Relation.objects.count() == 1

    def test_only_selected_candidates_are_created(self, user, event):
        first = _plan(user, event, due_date=date(2025, 12, 25))
        _plan(user, event, due_date=date(2025, 12, 25))

        assert len(repeat_plans(user, event, [first.relation_id], TODAY)) == 1
        assert Relation.objects.count() == 3


class TestEventPlanAgainView:
    def _url(self, event):
        return reverse("gift_manager:event_plan_again", kwargs={"pk": event.event_id})

    def test_requires_login(self, client, event):
        assert client.get(self._url(event)).status_code == 302

    def test_lists_candidates(self, client, user, event):
        plan = _plan(user, event, due_date=date(2025, 12, 25))
        client.force_login(user)

        response = client.get(self._url(event))

        assert response.status_code == 200
        assert [c.relation for c in response.context["candidates"]] == [plan]
        assert str(plan.relation_id) in response.content.decode()

    def test_post_creates_plans_and_redirects_to_the_event(self, client, user, event):
        plan = _plan(user, event, due_date=date(2025, 12, 25))
        client.force_login(user)

        response = client.post(self._url(event), {"relations": [str(plan.relation_id), "junk"]})

        assert response.status_code == 302
        assert response.url == reverse("gift_manager:event_detail", kwargs={"pk": event.event_id})
        assert Relation.objects.filter(event=event).count() == 2

    def test_post_without_selection_creates_nothing(self, client, user, event):
        _plan(user, event, due_date=date(2025, 12, 25))
        client.force_login(user)

        assert client.post(self._url(event), {}).status_code == 302
        assert Relation.objects.count() == 1

    def test_event_without_access_is_not_found(self, client, user, event):
        other = _christmas()
        client.force_login(user)

        assert client.get(self._url(other)).status_code == 404
        assert client.post(self._url(other), {}).status_code == 404

    def test_non_repeating_event_is_not_found(self, client, user):
        one_time = EventFactory(schedule_type="one_time", recurrence=None)
        _grant(user, one_time, PermissionLevel.VIEWER)
        client.force_login(user)

        assert client.get(self._url(one_time)).status_code == 404

    def test_viewer_of_the_event_can_plan_again_into_their_own_plans(self, client, user, event):
        plan = _plan(user, event, due_date=date(2025, 12, 25), level=PermissionLevel.VIEWER)
        client.force_login(user)

        client.post(self._url(event), {"relations": [str(plan.relation_id)]})

        copy = Relation.objects.exclude(pk=plan.pk).get()
        assert PermissionService.get_effective_permission(copy, user) == PermissionLevel.OWNER

    def test_event_detail_links_to_plan_again_for_repeating_events_only(self, client, user, event):
        _grant(user, event, PermissionLevel.VIEWER)
        one_time = EventFactory(schedule_type="one_time", recurrence=None)
        _grant(user, one_time, PermissionLevel.VIEWER)
        client.force_login(user)

        with_link = client.get(reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}))
        without = client.get(reverse("gift_manager:event_detail", kwargs={"pk": one_time.event_id}))

        assert self._url(event) in with_link.content.decode()
        assert self._url(one_time) not in without.content.decode()


class TestDuplicatePlan:
    def _create_url(self, plan=None, raw=None):
        base = reverse("gift_manager:relation_create")
        return f"{base}?duplicate_of={raw if raw is not None else plan.relation_id}"

    def test_form_is_prefilled_from_the_plan_without_reaction(self, client, user, event):
        plan = _plan(
            user,
            event,
            due_date=date(2030, 5, 1),
            comment="Wrap it",
            url="https://example.com/g",
            price="12.50",
            reaction_rating=4,
        )
        client.force_login(user)

        response = client.get(self._create_url(plan))

        initial = response.context["form"].initial
        assert initial["recipient"] == f"person:{plan.person.person_id}"
        assert initial["gift"] == plan.gift_id
        assert initial["event"] == event.pk
        assert initial["due_date"] == date(2030, 5, 1)
        assert initial["comment"] == "Wrap it"
        assert "reaction_rating" not in initial
        assert "status" not in initial

    def test_posting_the_form_creates_a_new_plan_and_keeps_the_original(self, client, user, event):
        plan = _plan(user, event, due_date=date(2030, 5, 1), reaction_rating=4)
        client.force_login(user)
        form = client.get(self._create_url(plan)).context["form"]

        response = client.post(
            reverse("gift_manager:relation_create"),
            {
                "recipient": form.initial["recipient"],
                "gift": plan.gift_id,
                "event": event.pk,
                "status": RelationStatusFactory(status="Idea").pk,
                "due_date": "2030-05-01",
                "comment": form.initial["comment"],
            },
        )

        assert response.status_code == 302
        assert Relation.objects.count() == 2
        plan.refresh_from_db()
        assert plan.reaction_rating == 4

    @pytest.mark.parametrize("raw", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", ""])
    def test_invalid_source_is_ignored(self, client, user, raw):
        client.force_login(user)

        response = client.get(self._create_url(raw=raw))

        assert response.status_code == 200
        assert "gift" not in response.context["form"].initial

    def test_plan_without_access_is_ignored(self, client, user):
        hidden = RelationFactory()
        client.force_login(user)

        response = client.get(self._create_url(hidden))

        assert response.status_code == 200
        assert "gift" not in response.context["form"].initial

    def test_detail_and_card_link_to_the_duplicate_form(self, client, user, event):
        plan = _plan(user, event, due_date=date(2030, 5, 1))
        client.force_login(user)
        url = self._create_url(plan)

        detail = client.get(
            reverse("gift_manager:relation_detail", kwargs={"pk": plan.relation_id})
        )

        assert url in detail.content.decode()


class TestCoordinationCarryOver:
    def test_repeat_keeps_the_surprise_flag_but_not_the_claim_or_comments(self, user, event):
        source = _plan(user, event, due_date=date(2025, 12, 25), is_surprise=True)
        Relation.objects.filter(pk=source.pk).update(claimed_by=user, claimed_at=timezone.now())
        RelationComment.objects.create(relation=source, author=user, text="I will buy it")

        (copy,) = repeat_plans(user, event, [source.relation_id], TODAY)

        assert copy.is_surprise is True
        assert copy.claimed_by is None
        assert copy.claimed_at is None
        assert copy.comments.count() == 0
