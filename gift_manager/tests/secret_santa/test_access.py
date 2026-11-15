"""Tests of what a Secret Santa sees of their recipient."""

import random

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gift_manager.secret_santa import access
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExchangeWishFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def exchange():
    exchange = ExchangeFactory()
    for name in ("Anna", "Bob", "Carl", "Dora"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    return exchange


def draw(exchange):
    service.run_draw(exchange, rng=random.Random(1))  # noqa: S311 - reproducible test


def santa_and_recipient(exchange):
    santa = ExchangeParticipant.objects.select_related("exchange").get(
        exchange=exchange, name="Anna"
    )
    return santa, ExchangeParticipant.objects.get(pk=santa.gives_to_id)


def test_nothing_before_the_draw(exchange):
    santa = exchange.participants.get(name="Anna")
    assert access.recipient_view(santa) is None


def test_nothing_for_a_declined_santa(exchange):
    draw(exchange)
    santa, _ = santa_and_recipient(exchange)
    santa.declined = True
    assert access.recipient_view(santa) is None


def test_nothing_once_closed(exchange):
    draw(exchange)
    Exchange.objects.filter(pk=exchange.pk).update(status=Exchange.Status.CLOSED)
    santa, _ = santa_and_recipient(exchange)
    assert access.recipient_view(santa) is None


def test_exchange_wishes_and_note_of_my_recipient_only(exchange):
    draw(exchange)
    santa, recipient = santa_and_recipient(exchange)
    recipient.note_for_santa = "Size M"
    recipient.save()
    wish = ExchangeWishFactory(participant=recipient, title="Board game")
    ExchangeWishFactory(participant=santa, title="Santa's own wish")

    view = access.recipient_view(santa)

    assert view.name == recipient.name
    assert view.note == "Size M"
    assert view.exchange_wishes == [wish]
    assert view.shared_wishes == []
    assert view.has_content


def test_shared_wishes_need_confirmation(exchange):
    draw(exchange)
    santa, recipient = santa_and_recipient(exchange)
    account = UserFactory()
    wish = WishFactory(wisher=account)
    recipient.linked_account = account
    recipient.save()
    recipient.shared_wishes.add(wish)

    assert access.recipient_view(santa).shared_wishes == []

    recipient.wishlist_confirmed = True
    recipient.save()
    view = access.recipient_view(santa)
    assert view.shared_wishes == [wish]
    assert view.shared_currency == account.profile.currency


def test_only_selected_active_wishes_are_shared(exchange):
    draw(exchange)
    santa, recipient = santa_and_recipient(exchange)
    account = UserFactory()
    shared = WishFactory(wisher=account, title="Shared")
    WishFactory(wisher=account, title="Not selected")
    archived = WishFactory(wisher=account, title="Archived", is_archived=True)
    received = WishFactory(wisher=account, title="Received")
    ReceivedGiftFactory(recipient_user=account, wish=received, fulfills_wish=True)
    recipient.linked_account = account
    recipient.wishlist_confirmed = True
    recipient.save()
    recipient.shared_wishes.add(shared, archived, received)

    assert [w.title for w in access.recipient_view(santa).shared_wishes] == ["Shared"]


def test_unlinked_recipient_shares_nothing(exchange):
    draw(exchange)
    santa, recipient = santa_and_recipient(exchange)
    account = UserFactory()
    wish = WishFactory(wisher=account)
    recipient.linked_account = account
    recipient.wishlist_confirmed = True
    recipient.save()
    recipient.shared_wishes.add(wish)

    account.delete()

    assert access.recipient_view(santa).shared_wishes == []


def test_shared_wishes_load_no_claim_columns(exchange):
    draw(exchange)
    santa, recipient = santa_and_recipient(exchange)
    account = UserFactory()
    recipient.shared_wishes.add(WishFactory(wisher=account))
    recipient.linked_account = account
    recipient.wishlist_confirmed = True
    recipient.save()

    (wish,) = access.recipient_view(santa).shared_wishes

    assert "is_fulfilled" in wish.get_deferred_fields()


def test_never_reads_who_drew_the_santa(exchange):
    draw(exchange)
    santa, _ = santa_and_recipient(exchange)

    with CaptureQueriesContext(connection) as queries:
        access.recipient_view(santa)

    for query in queries.captured_queries:
        assert f'"gives_to_id" = {santa.pk}' not in query["sql"]


def test_viewer_is_linked():
    account = UserFactory()
    participant = ExchangeParticipantFactory(linked_account=account)
    other = UserFactory()

    assert access.viewer_is_linked(participant, account)
    assert not access.viewer_is_linked(participant, other)
    assert not access.viewer_is_linked(participant, None)
    assert not access.viewer_is_linked(ExchangeParticipantFactory(), account)
    account.is_active = False
    assert not access.viewer_is_linked(participant, account)
