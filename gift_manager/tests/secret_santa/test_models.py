"""Tests of the Secret Santa models."""

import pytest
from django.db import IntegrityError
from django.db import transaction

from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExchangeWish
from gift_manager.secret_santa.models import ExclusionSet
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import ExchangeWishFactory
from gift_manager.tests.factories import ExclusionSetFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


def test_participant_gets_a_token_and_regenerating_changes_it():
    participant = ExchangeParticipantFactory()
    old = participant.token
    assert len(old) >= 43

    new = participant.regenerate_token()

    assert new != old
    participant.refresh_from_db()
    assert participant.token == new


def test_email_is_stored_encoded_and_read_decoded():
    participant = ExchangeParticipantFactory()
    participant.set_email("a@example.com")
    participant.save()
    participant.refresh_from_db()

    assert "a@example.com" not in participant.email_address
    assert participant.email == "a@example.com"


def test_an_empty_email_is_stored_as_null():
    participant = ExchangeParticipantFactory()
    participant.set_email("")
    participant.save()
    participant.refresh_from_db()

    assert participant.email_address is None
    assert participant.email is None


def test_names_are_unique_in_an_exchange_ignoring_case():
    exchange = ExchangeFactory()
    ExchangeParticipantFactory(exchange=exchange, name="Anna")

    with pytest.raises(IntegrityError), transaction.atomic():
        ExchangeParticipantFactory(exchange=exchange, name="anna")

    ExchangeParticipantFactory(name="anna")  # another exchange


def test_a_source_person_or_an_account_appears_once_per_exchange():
    exchange = ExchangeFactory()
    person = PersonFactory()
    account = UserFactory()
    ExchangeParticipantFactory(exchange=exchange, source_person=person, linked_account=account)

    with pytest.raises(IntegrityError), transaction.atomic():
        ExchangeParticipantFactory(exchange=exchange, source_person=person)
    with pytest.raises(IntegrityError), transaction.atomic():
        ExchangeParticipantFactory(exchange=exchange, linked_account=account)

    # Several participants without a source person or an account are fine
    ExchangeParticipantFactory(exchange=exchange)
    ExchangeParticipantFactory(exchange=exchange)
    # And the same person may take part in another exchange
    ExchangeParticipantFactory(source_person=person, linked_account=account)


def test_two_participants_may_share_an_email():
    exchange = ExchangeFactory()
    first = ExchangeParticipantFactory(exchange=exchange)
    second = ExchangeParticipantFactory(exchange=exchange)
    first.set_email("family@example.com")
    second.set_email("family@example.com")
    first.save()
    second.save()

    assert {p.email for p in exchange.participants.all()} == {"family@example.com"}


def test_deleting_the_exchange_deletes_participants_and_sets():
    exchange = ExchangeFactory()
    participants = ExchangeParticipantFactory.create_batch(3, exchange=exchange)
    ExclusionSetFactory(exchange=exchange, participants=participants[:2])

    exchange.delete()

    assert not ExchangeParticipant.objects.exists()
    assert not ExclusionSet.objects.exists()


def test_deleting_a_linked_user_or_source_person_keeps_the_participant():
    person = PersonFactory()
    account = UserFactory()
    participant = ExchangeParticipantFactory(source_person=person, linked_account=account)

    person.delete()
    account.delete()
    participant.refresh_from_db()

    assert participant.source_person is None
    assert participant.linked_account is None


def test_deleting_the_organizer_deletes_the_exchange():
    exchange = ExchangeFactory()
    ExchangeParticipantFactory(exchange=exchange)

    exchange.organizer.delete()

    assert not Exchange.objects.exists()
    assert not ExchangeParticipant.objects.exists()


def test_exchange_status_helpers():
    exchange = ExchangeFactory()
    assert exchange.is_draft
    assert not exchange.is_drawn
    exchange.status = Exchange.Status.CLOSED
    assert exchange.is_closed
    assert str(exchange) == exchange.name


def test_new_participant_defaults():
    participant = ExchangeParticipantFactory()
    assert not participant.declined
    assert participant.invited_at is None
    assert not participant.account_attached_by_participant
    assert not participant.wishlist_confirmed
    assert participant.note_for_santa == ""
    assert not participant.shared_wishes.exists()


def test_exchange_wishes_are_deleted_with_the_participant():
    wish = ExchangeWishFactory()
    wish.participant.delete()
    assert not ExchangeWish.objects.exists()


def test_deleting_a_shared_wish_removes_it_from_the_selection():
    participant = ExchangeParticipantFactory()
    wish = WishFactory()
    participant.shared_wishes.add(wish)

    wish.delete()

    assert not participant.shared_wishes.exists()


def test_deleting_the_previous_exchange_keeps_the_copy():
    previous = ExchangeFactory()
    old = ExchangeParticipantFactory(exchange=previous)
    copy = ExchangeFactory(previous_exchange=previous, organizer=previous.organizer)
    new = ExchangeParticipantFactory(exchange=copy, previous_participant=old)

    previous.delete()
    copy.refresh_from_db()
    new.refresh_from_db()

    assert copy.previous_exchange is None
    assert new.previous_participant is None
