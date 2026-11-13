"""A given gift plan shows when it was given instead of a missing due date."""

from datetime import UTC
from datetime import date
from datetime import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager import plan_coordination
from gift_manager.models import Relation
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

GIVEN_AT = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def _plan(user, status_name, **kwargs):
    kwargs.setdefault("due_date", None)
    return RelationFactory(
        person=PersonFactory(first_name="Ada", family_name="Lovelace", shared_with=[user]),
        gift=GiftFactory(name="Book", shared_with=[user]),
        status=RelationStatusFactory(status=status_name),
        shared_with=[user],
        **kwargs,
    )


def _set_status_date(relation, value):
    Relation.objects.filter(pk=relation.pk).update(status_changed_at=value)
    relation.refresh_from_db()


@pytest.mark.django_db
def test_given_on_is_the_day_the_plan_became_given(user):
    relation = _plan(user, "Given", due_date=date(2026, 3, 1))
    _set_status_date(relation, GIVEN_AT)
    assert relation.given_on == date(2026, 3, 14)


@pytest.mark.django_db
def test_given_on_falls_back_to_the_due_date_then_to_nothing(user):
    relation = _plan(user, "Given", due_date=date(2026, 3, 1))
    _set_status_date(relation, None)
    assert relation.given_on == date(2026, 3, 1)

    undated = _plan(user, "Given")
    _set_status_date(undated, None)
    assert undated.given_on is None


@pytest.mark.django_db
def test_given_on_is_empty_while_the_plan_is_not_given(user):
    relation = _plan(user, "Planned", due_date=date(2026, 3, 1))
    assert relation.given_on is None


@pytest.mark.django_db
def test_detail_page_shows_given_on_instead_of_no_date(client, user):
    relation = _plan(user, "Given")
    _set_status_date(relation, GIVEN_AT)

    content = client.get(
        reverse("gift_manager:relation_detail", args=[relation.relation_id])
    ).content.decode()

    assert "Given on" in content
    assert "March 14, 2026" in content
    assert "No date" not in content
    assert "Due Date" not in content


@pytest.mark.django_db
def test_detail_page_keeps_the_due_date_of_a_given_plan(client, user):
    relation = _plan(user, "Given", due_date=date(2026, 3, 1))
    _set_status_date(relation, GIVEN_AT)

    content = client.get(
        reverse("gift_manager:relation_detail", args=[relation.relation_id])
    ).content.decode()

    assert "Given on" in content
    assert "Due Date" in content
    assert "March 1, 2026" in content


@pytest.mark.django_db
def test_detail_page_of_a_plan_in_progress_still_asks_for_a_date(client, user):
    relation = _plan(user, "Planned")

    content = client.get(
        reverse("gift_manager:relation_detail", args=[relation.relation_id])
    ).content.decode()

    assert "No date" in content
    assert "Given on" not in content


@pytest.mark.django_db
def test_workspace_card_shows_given_on(client, user):
    relation = _plan(user, "Given")
    _set_status_date(relation, GIVEN_AT)

    content = client.get(reverse("gift_manager:relations")).content.decode()

    assert "Given on" in content
    assert "No date" not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_name, expected", [("Planned", True), ("Given", False), ("Abandoned", False)]
)
def test_claim_is_only_offered_while_the_plan_is_in_progress(user, status_name, expected):
    relation = _plan(user, status_name)
    assert plan_coordination.coordination_context(relation, user)["can_claim"] is expected


@pytest.mark.django_db
def test_surprise_badge_is_hidden_once_the_plan_is_revealed(client, user):
    relation = _plan(user, "Given", is_surprise=True)
    url = reverse("gift_manager:relation_detail", args=[relation.relation_id])
    assert "Surprise" in client.get(url).content.decode()

    Relation.objects.filter(pk=relation.pk).update(revealed_at=timezone.now())
    assert 'fa-gift me-1" aria-hidden="true"></i>Surprise' not in client.get(url).content.decode()
