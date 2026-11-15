"""Tests of what a participant does from their personal page."""

import random
from decimal import Decimal

import pytest

from gift_manager.secret_santa import participation
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import MAX_EXCHANGE_WISHES
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExchangeWish
from gift_manager.secret_santa.service import ExchangeError
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExchangeWishFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def exchange():
    exchange = ExchangeFactory(budget=Decimal(30), currency="EUR")
    for name in ("Anna", "Bob", "Carl", "Dora"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    return exchange


@pytest.fixture
def anna(exchange):
    return exchange.participants.select_related("exchange").get(name="Anna")


def draw(exchange):
    service.run_draw(exchange, rng=random.Random(1))  # noqa: S311 - reproducible test


def test_add_and_delete_own_wish(anna):
    wish = participation.add_exchange_wish(
        anna, title=" Book ", url="https://example.com", price=Decimal("12.50")
    )
    assert wish.title == "Book"
    assert list(anna.exchange_wishes.all()) == [wish]

    participation.delete_exchange_wish(anna, wish.wish_id)
    assert not anna.exchange_wishes.exists()


def test_cannot_delete_a_wish_of_someone_else(anna, exchange):
    other = ExchangeWishFactory(participant=exchange.participants.get(name="Bob"))

    with pytest.raises(ExchangeWish.DoesNotExist):
        participation.delete_exchange_wish(anna, other.wish_id)
    assert ExchangeWish.objects.filter(pk=other.pk).exists()


def test_31st_wish_is_refused(anna):
    ExchangeWish.objects.bulk_create(
        ExchangeWish(participant=anna, title=f"W{i}") for i in range(MAX_EXCHANGE_WISHES)
    )
    with pytest.raises(ExchangeError, match="at most 30"):
        participation.add_exchange_wish(anna, title="One too many")


def test_note_is_limited_to_2000(anna):
    participation.save_note(anna, "x" * 2000)
    anna.refresh_from_db()
    assert len(anna.note_for_santa) == 2000

    with pytest.raises(ExchangeError, match="2000"):
        participation.save_note(anna, "x" * 2001)


def test_decline_and_rejoin_only_before_the_draw(anna, exchange):
    participation.decline(anna)
    anna.refresh_from_db()
    assert anna.declined
    with pytest.raises(ExchangeError, match="do not take part"):
        participation.add_exchange_wish(anna, title="Nope")

    participation.rejoin(anna)
    anna.refresh_from_db()
    assert not anna.declined

    draw(exchange)
    anna.exchange.refresh_from_db()
    with pytest.raises(ExchangeError, match="tell the organizer"):
        participation.decline(anna)


def test_closed_exchange_refuses_writes(anna, exchange):
    Exchange.objects.filter(pk=exchange.pk).update(status=Exchange.Status.CLOSED)

    for call in (
        lambda: participation.add_exchange_wish(anna, title="X"),
        lambda: participation.save_note(anna, "X"),
        lambda: participation.decline(anna),
        lambda: participation.attach_account(anna, UserFactory()),
    ):
        with pytest.raises(ExchangeError, match="closed"):
            call()


def test_attach_and_detach(anna):
    account = UserFactory()

    participation.attach_account(anna, account)
    anna.refresh_from_db()
    assert anna.linked_account == account
    assert anna.account_attached_by_participant

    participation.attach_account(anna, account)  # again: nothing changes

    participation.detach_account(anna, account)
    anna.refresh_from_db()
    assert anna.linked_account is None
    assert not anna.account_attached_by_participant


def test_attach_refused_when_the_account_is_linked_elsewhere_in_the_exchange(anna, exchange):
    account = UserFactory()
    ExchangeParticipant.objects.filter(exchange=exchange, name="Bob").update(linked_account=account)

    with pytest.raises(ExchangeError, match="another participant"):
        participation.attach_account(anna, account)
    anna.refresh_from_db()
    assert anna.linked_account is None


def test_attach_refused_when_linked_to_another_account(anna):
    first = UserFactory()
    participation.attach_account(anna, first)

    with pytest.raises(ExchangeError, match="already linked to an account"):
        participation.attach_account(anna, UserFactory())
    anna.refresh_from_db()
    assert anna.linked_account == first


def test_detach_needs_the_linked_account_and_clears_the_selection(anna):
    account = UserFactory()
    participation.attach_account(anna, account)
    wish = WishFactory(wisher=account)
    participation.save_shared_wishes(anna, account, [wish.wish_id])

    with pytest.raises(ExchangeError):
        participation.detach_account(anna, UserFactory())

    participation.detach_account(anna, account)
    anna.refresh_from_db()
    assert not anna.wishlist_confirmed
    assert not anna.shared_wishes.exists()


@pytest.mark.parametrize(
    ("currency", "budget", "price", "ticked"),
    [
        ("EUR", Decimal(30), Decimal(25), True),
        ("EUR", Decimal(30), Decimal(30), True),
        ("EUR", Decimal(30), Decimal(31), False),
        ("EUR", Decimal(30), None, False),
        ("USD", Decimal(30), Decimal(25), False),
        ("EUR", None, Decimal(25), False),
    ],
)
def test_prefill_rules(anna, currency, budget, price, ticked):
    Exchange.objects.filter(pk=anna.exchange_id).update(budget=budget)
    anna.exchange.refresh_from_db()
    account = UserFactory()
    account.profile.currency = currency
    account.profile.save()
    WishFactory(wisher=account, price_hint=price)
    participation.attach_account(anna, account)

    ((_, checked),) = participation.shareable_wishes(anna)

    assert checked is ticked


def test_selection_is_shown_once_confirmed(anna):
    account = UserFactory()
    cheap = WishFactory(wisher=account, price_hint=Decimal(5), title="Cheap")
    WishFactory(wisher=account, price_hint=Decimal(6), title="Also cheap")
    participation.attach_account(anna, account)

    participation.save_shared_wishes(anna, account, [cheap.wish_id])

    assert {w.title: c for w, c in participation.shareable_wishes(anna)} == {
        "Cheap": True,
        "Also cheap": False,
    }


def test_save_shared_wishes_ignores_foreign_and_inactive_ids(anna):
    account = UserFactory()
    mine = WishFactory(wisher=account)
    archived = WishFactory(wisher=account, is_archived=True)
    foreign = WishFactory()
    participation.attach_account(anna, account)

    participation.save_shared_wishes(
        anna, account, [mine.wish_id, archived.wish_id, foreign.wish_id]
    )

    anna.refresh_from_db()
    assert list(anna.shared_wishes.all()) == [mine]
    assert anna.wishlist_confirmed
