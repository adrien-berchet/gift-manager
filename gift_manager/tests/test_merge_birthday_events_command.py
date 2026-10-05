"""Tests for ``merge_birthday_events``: users' own Birthday events move to the global one."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from gift_manager.models import Event
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.models import RelationPermission
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _run(*args) -> str:
    out = StringIO()
    call_command("merge_birthday_events", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def global_event():
    return Event.objects.get_birthday_event()


@pytest.fixture
def old_event():
    return EventFactory(name="Birthday")


def _plans_on(event):
    return set(Relation.objects.filter(event=event).values_list("pk", flat=True))


class TestDryRun:
    def test_nothing_changes_without_apply(self, global_event, old_event):
        plans = [RelationFactory(event=old_event) for _ in range(3)]

        output = _run()

        assert _plans_on(old_event) == {plan.pk for plan in plans}
        assert _plans_on(global_event) == set()
        assert "Dry run" in output
        assert "3 gift plan(s)" in output
        assert str(old_event.event_id) in output
        assert str(global_event.event_id) in output

    def test_reports_when_there_is_nothing_to_merge(self, global_event):
        output = _run()

        assert "No Birthday event to merge." in output
        assert "Dry run" not in output


class TestApply:
    def test_moves_every_gift_plan_to_the_global_event(self, global_event, old_event):
        plans = [RelationFactory(event=old_event) for _ in range(3)]

        output = _run("--apply")

        assert _plans_on(global_event) == {plan.pk for plan in plans}
        assert _plans_on(old_event) == set()
        assert "Moved 3 gift plan(s)" in output

    def test_gift_plans_keep_their_data_and_sharing(self, global_event, old_event):
        user = UserFactory()
        status = RelationStatusFactory(status="Purchased")
        plan = RelationFactory(
            event=old_event, status=status, due_date=date(2026, 12, 25), comment="Wrapped"
        )
        RelationPermission.objects.create(
            user=user, relation=plan, permission_type=PermissionLevel.EDITOR
        )

        _run("--apply")

        plan.refresh_from_db()
        assert plan.event == global_event
        assert plan.due_date == date(2026, 12, 25)
        assert plan.status == status
        assert plan.comment == "Wrapped"
        assert RelationPermission.objects.get(user=user, relation=plan).permission_type == (
            PermissionLevel.EDITOR
        )

    def test_group_gift_plans_are_moved_too(self, global_event, old_event):
        plan = GroupRelationFactory(event=old_event)

        _run("--apply")

        plan.refresh_from_db()
        assert plan.event == global_event

    def test_other_events_are_left_alone(self, global_event, old_event):
        christmas = EventFactory(name="Christmas")
        plan = RelationFactory(event=christmas)
        RelationFactory(event=old_event)

        _run("--apply")

        plan.refresh_from_db()
        assert plan.event == christmas

    def test_plans_of_several_users_events_are_merged(self, global_event):
        first = EventFactory(name="Birthday")
        second = EventFactory(name="Birthday")
        plans = [RelationFactory(event=first), RelationFactory(event=second)]

        output = _run("--apply")

        assert _plans_on(global_event) == {plan.pk for plan in plans}
        assert "Moved 2 gift plan(s)" in output

    def test_running_it_again_is_harmless(self, global_event, old_event):
        plan = RelationFactory(event=old_event)
        _run("--apply")

        output = _run("--apply")

        plan.refresh_from_db()
        assert plan.event == global_event
        assert "Moved 0 gift plan(s)" in output

    def test_the_global_event_is_created_when_missing(self, old_event):
        Event.objects.filter(is_birthday=True).delete()
        plan = RelationFactory(event=old_event)

        _run("--apply")

        plan.refresh_from_db()
        assert plan.event.is_birthday is True
        assert plan.event.is_global is True

    def test_the_global_event_itself_is_never_a_candidate(self, global_event):
        plan = RelationFactory(event=global_event)

        output = _run("--apply")

        plan.refresh_from_db()
        assert plan.event == global_event
        assert "No Birthday event to merge." in output
        assert Event.objects.filter(pk=global_event.pk).exists()

    def test_the_global_event_is_not_chosen_by_explicit_id(self, global_event):
        output = _run("--apply", "--event-id", str(global_event.event_id))

        assert "No Birthday event to merge." in output


class TestSelection:
    @pytest.mark.parametrize("name", ["birthday", "BIRTHDAY", "  Birthday  "])
    def test_names_match_case_insensitively_and_ignore_padding(self, global_event, name):
        event = EventFactory(name=name)
        plan = RelationFactory(event=event)

        _run("--apply")

        plan.refresh_from_db()
        assert plan.event == global_event

    def test_events_with_another_name_are_listed_but_not_merged(self, global_event):
        other = EventFactory(name="Mom Birthday")
        plan = RelationFactory(event=other)

        output = _run("--apply")

        plan.refresh_from_db()
        assert plan.event == other
        assert "Not merged" in output
        assert str(other.event_id) in output

    def test_unrelated_events_are_not_listed(self, global_event):
        EventFactory(name="Christmas")

        output = _run()

        assert "Christmas" not in output

    def test_custom_names(self, global_event):
        event = EventFactory(name="Anniversaire")
        plan = RelationFactory(event=event)

        _run("--apply", "--name", "Anniversaire")

        plan.refresh_from_db()
        assert plan.event == global_event

    def test_a_custom_name_replaces_the_default(self, global_event, old_event):
        plan = RelationFactory(event=old_event)

        _run("--apply", "--name", "Anniversaire")

        plan.refresh_from_db()
        assert plan.event == old_event

    def test_an_explicit_event_id_merges_whatever_the_name(self, global_event):
        other = EventFactory(name="Mom Birthday")
        plan = RelationFactory(event=other)

        _run("--apply", "--event-id", str(other.event_id))

        plan.refresh_from_db()
        assert plan.event == global_event

    def test_an_explicit_event_id_alone_does_not_select_events_by_the_default_name(
        self, global_event, old_event
    ):
        other = EventFactory(name="Anniversaire")
        old_plan = RelationFactory(event=old_event)
        plan = RelationFactory(event=other)

        output = _run("--apply", "--event-id", str(other.event_id))

        plan.refresh_from_db()
        old_plan.refresh_from_db()
        assert plan.event == global_event
        assert old_plan.event == old_event  # named "Birthday", but not asked for
        assert "1 Birthday event(s) to merge" in output

    def test_an_event_id_and_a_name_select_both(self, global_event, old_event):
        other = EventFactory(name="Anniversaire")
        plans = [RelationFactory(event=old_event), RelationFactory(event=other)]

        _run("--apply", "--name", "Birthday", "--event-id", str(other.event_id))

        assert _plans_on(global_event) == {plan.pk for plan in plans}


class TestDeletion:
    def test_old_events_are_kept_by_default(self, global_event, old_event):
        RelationFactory(event=old_event)

        _run("--apply")

        assert Event.objects.filter(pk=old_event.pk).exists()

    def test_delete_old_events_removes_the_emptied_events(self, global_event, old_event):
        RelationFactory(event=old_event)

        output = _run("--apply", "--delete-old-events")

        assert not Event.objects.filter(pk=old_event.pk).exists()
        assert Event.objects.filter(pk=global_event.pk).exists()
        assert "Deleted 1 old event(s)" in output

    def test_delete_old_events_keeps_the_gift_plans(self, global_event, old_event):
        plan = RelationFactory(event=old_event)

        _run("--apply", "--delete-old-events")

        assert Relation.objects.filter(pk=plan.pk, event=global_event).exists()

    def test_delete_old_events_needs_apply(self, global_event, old_event):
        with pytest.raises(CommandError, match="--apply"):
            _run("--delete-old-events")

        assert Event.objects.filter(pk=old_event.pk).exists()


class TestErrors:
    def test_invalid_event_id(self, global_event):
        with pytest.raises(CommandError, match="Not a valid event id"):
            _run("--event-id", "not-a-uuid")

    def test_empty_names_and_no_event_id(self, global_event):
        with pytest.raises(CommandError, match="--name"):
            _run("--name", "  ")
