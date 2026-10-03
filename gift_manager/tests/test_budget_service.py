"""Budget totals of a person and of an event."""

from decimal import Decimal

import pytest
from django.urls import reverse

from gift_manager.permissions import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.services import BudgetService
from gift_manager.services import BudgetSummary
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def person():
    return PersonFactory()


def _plan(owner, person, *, status="Idea", price=None, gift_price=None, event=None, **extra):
    relation = RelationFactory(
        person=person,
        event=event or EventFactory(),
        gift=GiftFactory(price=Decimal(gift_price) if gift_price is not None else None),
        status=RelationStatusFactory(status=status),
        price=Decimal(price) if price is not None else None,
        **extra,
    )
    create_or_update_permission(owner, relation, permission_level=PermissionLevel.OWNER)
    return relation


def test_empty_returns_zero_summary(owner, person):
    assert BudgetService.for_person(owner, person) == BudgetSummary(
        planned=Decimal(0), spent=Decimal(0), without_price=0
    )


def test_planned_sums_effective_prices_excluding_abandoned(owner, person):
    _plan(owner, person, status="Idea", price="10")
    _plan(owner, person, status="Planned", gift_price="5")
    _plan(owner, person, status="Abandoned", price="100")

    summary = BudgetService.for_person(owner, person)

    assert summary.planned == Decimal(15)


def test_spent_counts_only_purchased_and_given(owner, person):
    _plan(owner, person, status="Idea", price="10")
    _plan(owner, person, status="Purchased", price="20")
    _plan(owner, person, status="Given", price="30")
    _plan(owner, person, status="Abandoned", price="40")

    summary = BudgetService.for_person(owner, person)

    assert summary.spent == Decimal(50)
    assert summary.planned == Decimal(60)


def test_plan_override_beats_gift_price_in_totals(owner, person):
    _plan(owner, person, price="7", gift_price="99")

    assert BudgetService.for_person(owner, person).planned == Decimal(7)


def test_plans_without_price_are_ignored_and_counted(owner, person):
    _plan(owner, person, price="10")
    _plan(owner, person)
    _plan(owner, person, status="Abandoned")

    summary = BudgetService.for_person(owner, person)

    assert summary.planned == Decimal(10)
    assert summary.without_price == 1


def test_zero_price_is_a_price(owner, person):
    _plan(owner, person, price="0")

    assert BudgetService.for_person(owner, person).without_price == 0


def test_for_person_ignores_group_plans(owner, person):
    from gift_manager.tests.factories import GroupRelationFactory

    group_plan = GroupRelationFactory(price=Decimal(50))
    create_or_update_permission(owner, group_plan, permission_level=PermissionLevel.OWNER)

    assert BudgetService.for_person(owner, person).planned == Decimal(0)


def test_viewer_sees_shared_plans_and_no_access_user_sees_nothing(owner, person):
    relation = _plan(owner, person, price="10")
    viewer = UserFactory()
    stranger = UserFactory()
    create_or_update_permission(viewer, relation, permission_level=PermissionLevel.VIEWER)

    assert BudgetService.for_person(viewer, person).planned == Decimal(10)
    assert BudgetService.for_person(stranger, person) == BudgetSummary(
        planned=Decimal(0), spent=Decimal(0), without_price=0
    )


def test_for_event_sums_plans_of_the_event(owner, person):
    event = EventFactory()
    _plan(owner, person, price="10", event=event)
    _plan(owner, PersonFactory(), status="Purchased", price="5", event=event)
    _plan(owner, person, price="1000")

    summary = BudgetService.for_event(owner, event)

    assert summary.planned == Decimal(15)
    assert summary.spent == Decimal(5)


def test_budget_uses_constant_query_count(owner, person, django_assert_num_queries):
    _plan(owner, person, price="10")
    with django_assert_num_queries(1):
        BudgetService.for_person(owner, person)
    for _ in range(5):
        _plan(owner, person, price="10")
    with django_assert_num_queries(1):
        BudgetService.for_person(owner, person)


class TestViews:
    @pytest.fixture
    def client(self, authenticated_client):
        return authenticated_client

    def test_person_detail_context_has_budget(self, client, user, person):
        create_or_update_permission(user, person, permission_level=PermissionLevel.OWNER)
        _plan(user, person, price="12")

        response = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        )

        assert response.context["budget"].planned == Decimal(12)
        assert "budget-summary" in response.content.decode()

    def test_person_budget_is_at_the_bottom_of_the_left_column(self, client, user, person):
        create_or_update_permission(user, person, permission_level=PermissionLevel.OWNER)
        _plan(user, person, price="12")

        content = client.get(
            reverse("gift_manager:person_detail", kwargs={"pk": person.person_id})
        ).content.decode()

        # The left column (col-lg-5) ends right before the right one (col-lg-7)
        assert (
            content.index("col-lg-5") < content.index("budget-summary") < content.index("col-lg-7")
        )

    def test_event_budget_comes_after_the_gift_plans(self, client, user, person):
        event = EventFactory()
        create_or_update_permission(user, event, permission_level=PermissionLevel.OWNER)
        _plan(user, person, price="12", event=event)

        content = client.get(
            reverse("gift_manager:event_detail", kwargs={"pk": event.event_id})
        ).content.decode()

        assert content.index("relation-item") < content.index("budget-summary")

    def test_event_detail_renders_budget_when_priced(self, client, user, person):
        event = EventFactory()
        create_or_update_permission(user, event, permission_level=PermissionLevel.OWNER)
        _plan(user, person, price="12", event=event)

        response = client.get(reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}))

        assert response.context["budget"].planned == Decimal(12)
        assert "budget-summary" in response.content.decode()

    def test_event_detail_hides_budget_without_plans(self, client, user):
        event = EventFactory()
        create_or_update_permission(user, event, permission_level=PermissionLevel.OWNER)

        response = client.get(reverse("gift_manager:event_detail", kwargs={"pk": event.event_id}))

        assert "budget-summary" not in response.content.decode()
