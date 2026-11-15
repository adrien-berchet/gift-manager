"""Tests of the Secret Santa dashboard cards."""

import random

import pytest
from django.urls import reverse
from django.utils import timezone

from gift_manager.secret_santa import dashboard
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    return UserFactory()


@pytest.fixture
def exchange(account):
    exchange = ExchangeFactory(name="Family 2026")
    ExchangeParticipantFactory(exchange=exchange, name="Me", linked_account=account)
    for name in ("Bob", "Carl", "Dora"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    return exchange


def me(exchange):
    return exchange.participants.get(name="Me")


def draw(exchange):
    service.run_draw(exchange, rng=random.Random(1))  # noqa: S311 - reproducible test


def test_imported_into_a_draft_sees_nothing(exchange, account):
    assert dashboard.cards(account) == []


@pytest.mark.parametrize(
    "fields",
    [{"invited_at": timezone.now()}, {"account_attached_by_participant": True}],
)
def test_invited_or_self_attached_sees_the_draft(exchange, account, fields):
    ExchangeParticipant.objects.filter(pk=me(exchange).pk).update(**fields)

    (card,) = dashboard.cards(account)

    assert card.exchange == exchange
    assert not card.is_organizer
    assert card.recipient_name is None


def test_drawn_shows_my_recipient_only(exchange, account):
    draw(exchange)

    (card,) = dashboard.cards(account)

    assert card.recipient_name == ExchangeParticipant.objects.get(pk=me(exchange).gives_to_id).name


@pytest.mark.parametrize("change", ["declined", "closed", "organizer_inactive"])
def test_declined_or_closed_sees_nothing(exchange, account, change):
    draw(exchange)
    if change == "declined":
        ExchangeParticipant.objects.filter(pk=me(exchange).pk).update(declined=True)
    elif change == "closed":
        Exchange.objects.filter(pk=exchange.pk).update(status=Exchange.Status.CLOSED)
    else:
        exchange.organizer.is_active = False
        exchange.organizer.save()

    assert dashboard.cards(account) == []


def test_organizer_and_participant_cards_are_merged(account):
    exchange = ExchangeFactory(organizer=account)
    ExchangeParticipantFactory(exchange=exchange, linked_account=account)
    ExchangeFactory(organizer=account, status=Exchange.Status.CLOSED)

    (card,) = dashboard.cards(account)

    assert card.is_organizer
    assert card.participant is not None  # even in draft: the organizer sees their own row


def test_home_page_shows_the_card(client, exchange, account):
    draw(exchange)
    client.force_login(account)

    content = client.get(reverse("gift_manager:home")).content.decode()

    assert "Family 2026" in content
    assert reverse("gift_manager:secret_santa_participant", args=[me(exchange).token]) in content
    assert (
        reverse("gift_manager:secret_santa_plan_gift", args=[me(exchange).participant_id])
        in content
    )
