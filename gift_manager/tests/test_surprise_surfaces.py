"""A surprise plan never shows up for its recipient, on any surface.

Audit of the paths that read gift plans (``Relation``) outside ``accessible_by``, run once when
the surprise flag was introduced (idea 0007):

- ``mixins/performance.py`` prefetches ``persons`` / ``gifts`` / ``relations`` with
  ``Relation.objects`` (unfiltered) on the person, gift and event list views: LEAK, fixed by
  dropping those reverse prefetches (the detail views already query ``accessible_by``).
- ``views/base.py`` ``get_related_objects`` counts ``object.relations`` for the delete
  confirmation: LEAK, now counts through ``accessible_by``.
- Dashboard stats, plan list, advanced list, search, global search, detail, edit, person / group
  / gift / event detail, gift history, sharing page, budgets, reminders digest, calendar feed,
  birthdays and plan repeat all go through ``accessible_by``: safe, pinned by the tests below.
- Management commands (audit, merge, seed) are operator tools, out of scope.

Every test also checks that a collaborator still sees the plan (the control), so a page that
simply stopped listing plans cannot pass.
"""

from datetime import date
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse

from gift_manager.birthdays import build_upcoming_birthdays
from gift_manager.calendar_feed import build_calendar
from gift_manager.mixins.performance import QueryOptimizationMixin
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import Relation
from gift_manager.plan_repeat import find_repeat_candidates
from gift_manager.reminders import build_digest
from gift_manager.services import BudgetService
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

COMMENT = "SURPRISE-COMMENT-7f3a"


def _grant(obj, user, level, attr):
    PermissionService.create_or_update_permission(
        user, obj, permission_level=level, object_attr=attr
    )


class Scene:
    """A surprise plan, its recipient (also a user) and a collaborator."""

    def __init__(self, kind: str):
        self.kind = kind
        self.recipient = UserFactory()
        self.collaborator = UserFactory()
        self.gift = GiftFactory(name="Surprise gift")
        self.event = EventFactory(name="Surprise event")
        self.person = PersonFactory(user_link=self.recipient)
        if kind == "group":
            self.group = PersonGroupFactory(name="Surprise group")
            self.person.groups.add(self.group)
            recipient_kwargs = {"group": self.group, "person": None}
        else:
            self.group = None
            recipient_kwargs = {"person": self.person}
        self.plan = RelationFactory(
            gift=self.gift,
            event=self.event,
            comment=COMMENT,
            is_surprise=True,
            due_date=date.today() + timedelta(days=3),
            **recipient_kwargs,
        )
        _grant(self.plan, self.recipient, PermissionLevel.VIEWER, "relation")
        _grant(self.plan, self.collaborator, PermissionLevel.EDITOR, "relation")
        for user in (self.recipient, self.collaborator):
            _grant(self.gift, user, PermissionLevel.VIEWER, "gift")
            _grant(self.event, user, PermissionLevel.VIEWER, "event")
            if self.group is not None:
                _grant(self.group, user, PermissionLevel.VIEWER, "group")
        # The collaborator can reach the recipient person the way the owner shared it
        _grant(self.person, self.collaborator, PermissionLevel.VIEWER, "person")

    @property
    def markers(self) -> list[str]:
        return [str(self.plan.relation_id), COMMENT]


@pytest.fixture(params=["person", "group"])
def scene(request):
    return Scene(request.param)


def _get(client, user, url, **extra):
    client.force_login(user)
    return client.get(url, **extra)


def _plan_surfaces(scene):
    """Return ``(label, url)`` for every page that lists plans."""
    surfaces = [
        ("dashboard", reverse("gift_manager:home")),
        ("relations list", reverse("gift_manager:relations")),
        ("relations advanced list", reverse("gift_manager:relation_advanced_list")),
        ("relation search", reverse("gift_manager:relation_search") + "?search=Surprise"),
        ("global search", reverse("gift_manager:global_search") + "?q=Surprise"),
        ("gift detail", reverse("gift_manager:gift_detail", kwargs={"pk": scene.gift.gift_id})),
        ("event detail", reverse("gift_manager:event_detail", kwargs={"pk": scene.event.event_id})),
        ("share page", reverse("gift_manager:share_objects")),
    ]
    if scene.kind == "person":
        person_id = scene.person.person_id
        surfaces.append(
            ("person detail", reverse("gift_manager:person_detail", kwargs={"pk": person_id}))
        )
    else:
        group_id = scene.group.group_id
        surfaces.append(
            ("group detail", reverse("gift_manager:person_group_detail", kwargs={"pk": group_id}))
        )
    return surfaces


def test_plan_surfaces_hide_the_plan_from_its_recipient_only(client, scene):
    for label, url in _plan_surfaces(scene):
        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            control = _get(client, scene.collaborator, url, **extra)
            assert control.status_code == 200, (label, control.status_code)
            control_text = control.content.decode()
            assert any(marker in control_text for marker in scene.markers), (
                f"control page '{label}' does not list the plan: the test proves nothing"
            )

            response = _get(client, scene.recipient, url, **extra)
            text = response.content.decode()
            for marker in scene.markers:
                assert marker not in text, f"'{label}' leaks the surprise plan ({marker})"


@pytest.mark.parametrize("url_name", ["relation_detail", "relation_edit", "relation_delete"])
def test_direct_plan_urls_are_404_for_the_recipient(client, scene, url_name):
    url = reverse(f"gift_manager:{url_name}", kwargs={"pk": scene.plan.relation_id})

    assert _get(client, scene.collaborator, url).status_code == 200
    assert _get(client, scene.recipient, url).status_code == 404


def test_dashboard_plan_count_ignores_the_hidden_plan(client, scene):
    response = _get(client, scene.recipient, reverse("gift_manager:home"))

    assert response.context["stats"]["relations"] == 0
    control = _get(client, scene.collaborator, reverse("gift_manager:home"))
    assert control.context["stats"]["relations"] == 1


def test_delete_confirmations_do_not_count_the_hidden_plan(client, scene):
    gift_owner = UserFactory()
    for user in (scene.recipient, gift_owner):
        _grant(scene.gift, user, PermissionLevel.OWNER, "gift")
        _grant(scene.event, user, PermissionLevel.OWNER, "event")
    _grant(scene.plan, gift_owner, PermissionLevel.EDITOR, "relation")

    for url_name, kwargs in (
        ("gift_delete", {"pk": scene.gift.gift_id}),
        ("event_delete", {"pk": scene.event.event_id}),
    ):
        url = reverse(f"gift_manager:{url_name}", kwargs=kwargs)
        control = _get(client, gift_owner, url)
        assert control.status_code == 200
        assert control.context["related_objects"], f"{url_name} control counts nothing"
        response = _get(client, scene.recipient, url)
        assert response.context["related_objects"] == [], f"{url_name} counts the hidden plan"


def test_list_pages_do_not_show_the_hidden_plan(client, scene):
    for url_name in ("persons", "gifts", "events"):
        text = _get(client, scene.recipient, reverse(f"gift_manager:{url_name}")).content.decode()
        for marker in scene.markers:
            assert marker not in text, f"{url_name} list leaks the surprise plan"


@pytest.mark.parametrize(
    ("model", "pk_field", "accessor"),
    [(Person, "person", "persons"), (Gift, "gift", "gifts"), (Event, "event", "relations")],
)
def test_query_optimization_mixin_prefetches_only_visible_plans(scene, model, pk_field, accessor):
    pk = getattr(scene, pk_field).pk

    def prefetched_plans(user):
        mixin = QueryOptimizationMixin()
        mixin.request = SimpleNamespace(user=user)
        (instance,) = mixin.optimize_model_queryset(model.objects.filter(pk=pk))
        return list(getattr(instance, accessor).all())

    if scene.kind == "group" and model is Person:
        pytest.skip("a group plan has no person recipient to prefetch from")
    assert scene.plan in prefetched_plans(scene.collaborator)
    assert scene.plan not in prefetched_plans(scene.recipient)


def test_gift_history_ignores_the_hidden_plan(client, scene):
    Relation.objects.filter(pk=scene.plan.pk).update(
        status=RelationStatusFactory(status="Given"),
        due_date=date.today() - timedelta(days=400),
    )
    if scene.kind == "person":
        url = reverse("gift_manager:person_gift_history", kwargs={"pk": scene.person.person_id})
    else:
        url = reverse("gift_manager:person_group_gift_history", kwargs={"pk": scene.group.group_id})

    control = _get(client, scene.collaborator, url).content.decode()
    hidden = _get(client, scene.recipient, url).content.decode()

    assert scene.gift.name in control, "control history does not list the plan"
    assert scene.gift.name not in hidden


def test_budget_totals_ignore_the_hidden_plan(scene):
    scene.plan.price = 40
    scene.plan.save()

    if scene.kind == "person":
        assert BudgetService.for_person(scene.collaborator, scene.person).planned == 40
        assert BudgetService.for_person(scene.recipient, scene.person).planned == 0
    assert BudgetService.for_event(scene.collaborator, scene.event).planned == 40
    assert BudgetService.for_event(scene.recipient, scene.event).planned == 0


def test_reminder_digest_ignores_the_hidden_plan(scene):
    def digest_text(user) -> str:
        digest = build_digest(user, today=date.today(), lookahead_days=14)
        return repr(digest)

    assert scene.gift.name in digest_text(scene.collaborator)
    assert scene.gift.name not in digest_text(scene.recipient)


def test_calendar_feed_ignores_the_hidden_plan(scene):
    assert scene.gift.name in build_calendar(scene.collaborator)
    assert scene.gift.name not in build_calendar(scene.recipient)


def test_birthday_planning_ignores_the_hidden_plan(scene):
    today = date.today()
    birthday = today + timedelta(days=5)
    scene.person.birthday_day, scene.person.birthday_month = birthday.day, birthday.month
    scene.person.save()
    Relation.objects.filter(pk=scene.plan.pk).update(
        person=scene.person, group=None, due_date=birthday
    )

    def has_plan(user) -> bool:
        items = build_upcoming_birthdays(user, today, window_days=14)
        return [item["has_plan"] for item in items if item["person"].pk == scene.person.pk][0]

    assert has_plan(scene.collaborator) is True
    assert has_plan(scene.recipient) is False


def test_plan_again_candidates_ignore_the_hidden_plan(scene):
    last_occurrence = date.today() - timedelta(days=100)
    Event.objects.filter(pk=scene.event.pk).update(
        schedule_type=Event.ScheduleType.RECURRING, recurrence="yearly", date=last_occurrence
    )
    Relation.objects.filter(pk=scene.plan.pk).update(due_date=last_occurrence)
    scene.event.refresh_from_db()

    def candidate_plans(user):
        return [candidate.relation for candidate in find_repeat_candidates(user, scene.event)]

    assert scene.plan in candidate_plans(scene.collaborator), "control offers no candidate"
    assert scene.plan not in candidate_plans(scene.recipient)


def test_the_recipient_loses_nothing_when_the_flag_is_off(client, scene):
    Relation.objects.filter(pk=scene.plan.pk).update(is_surprise=False)

    text = _get(client, scene.recipient, reverse("gift_manager:relations")).content.decode()

    assert any(marker in text for marker in scene.markers)
