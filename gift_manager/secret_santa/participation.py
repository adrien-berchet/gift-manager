"""What a participant does from their personal page.

The page needs no login: the secret token is the only credential, so everything here acts on
the participant's own data only, within fixed limits. Only the account linked to a
participant (``access.viewer_is_linked``) may share its real wishes or undo the link.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError
from django.db import transaction
from django.utils.translation import gettext

from gift_manager import wishlist
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import MAX_EXCHANGE_WISHES
from gift_manager.secret_santa.models import MAX_NOTE_LENGTH
from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.models import ExchangeWish
from gift_manager.secret_santa.service import ExchangeError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from decimal import Decimal

    from django.contrib.auth.models import User

    from gift_manager.models import Wish


def _check_takes_part(participant: ExchangeParticipant) -> None:
    if participant.declined:
        raise ExchangeError(gettext("You do not take part in this exchange."))


def _check_before_draw(exchange: Exchange) -> None:
    if exchange.status != Exchange.Status.DRAFT:
        raise ExchangeError(
            gettext("The draw is done: tell the organizer if you cannot take part.")
        )


def add_exchange_wish(
    participant: ExchangeParticipant,
    *,
    title: str,
    url: str = "",
    price: Decimal | None = None,
) -> ExchangeWish:
    """Add a wish for this exchange only, within the limit per participant."""
    with transaction.atomic():
        service.lock_open(participant.exchange)
        _check_takes_part(participant)
        if participant.exchange_wishes.count() >= MAX_EXCHANGE_WISHES:
            raise ExchangeError(
                gettext("You can add at most %(count)d wishes.") % {"count": MAX_EXCHANGE_WISHES}
            )
        return ExchangeWish.objects.create(
            participant=participant, title=title.strip(), url=url or "", price=price
        )


def delete_exchange_wish(participant: ExchangeParticipant, wish_id) -> None:
    """Delete one of the participant's own exchange wishes (DoesNotExist for any other)."""
    with transaction.atomic():
        service.lock_open(participant.exchange)
        wish = ExchangeWish.objects.get(participant=participant, wish_id=wish_id)
        wish.delete()


def save_note(participant: ExchangeParticipant, note: str) -> None:
    """Save the participant's note for their Santa."""
    note = (note or "").strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise ExchangeError(
            gettext("The note can have at most %(count)d characters.") % {"count": MAX_NOTE_LENGTH}
        )
    with transaction.atomic():
        service.lock_open(participant.exchange)
        _check_takes_part(participant)
        ExchangeParticipant.objects.filter(pk=participant.pk).update(note_for_santa=note)
    participant.note_for_santa = note


def decline(participant: ExchangeParticipant) -> None:
    """Before the draw, say that one cannot take part: the draw leaves them out."""
    with transaction.atomic():
        _check_before_draw(service.lock_open(participant.exchange))
        ExchangeParticipant.objects.filter(pk=participant.pk).update(declined=True)
    participant.declined = True


def rejoin(participant: ExchangeParticipant) -> None:
    """Before the draw, take part again after having declined."""
    with transaction.atomic():
        _check_before_draw(service.lock_open(participant.exchange))
        ExchangeParticipant.objects.filter(pk=participant.pk).update(declined=False)
    participant.declined = False


def attach_account(participant: ExchangeParticipant, user: User) -> None:
    """Link the participation to the account of the logged-in participant."""
    with transaction.atomic():
        service.lock_open(participant.exchange)
        current = ExchangeParticipant.objects.select_for_update().get(pk=participant.pk)
        if current.linked_account_id == user.pk:
            return
        if current.linked_account_id is not None:
            raise ExchangeError(gettext("This participation is already linked to an account."))
        taken = ExchangeParticipant.objects.filter(
            exchange_id=current.exchange_id, linked_account=user
        ).exists()
        if taken:
            raise ExchangeError(
                gettext("Your account is already linked to another participant of this exchange.")
            )
        try:
            with transaction.atomic():
                ExchangeParticipant.objects.filter(pk=current.pk).update(
                    linked_account=user, account_attached_by_participant=True
                )
        except IntegrityError as error:
            raise ExchangeError(
                gettext("Your account is already linked to another participant of this exchange.")
            ) from error
    participant.linked_account = user
    participant.account_attached_by_participant = True


def _check_linked(participant: ExchangeParticipant, user: User) -> None:
    if participant.linked_account_id is None or participant.linked_account_id != user.pk:
        raise ExchangeError(gettext("This participation is not linked to your account."))


def detach_account(participant: ExchangeParticipant, user: User) -> None:
    """Undo the link: the Santa no longer sees any real wish."""
    with transaction.atomic():
        service.lock_open(participant.exchange)
        _check_linked(participant, user)
        ExchangeParticipant.objects.filter(pk=participant.pk).update(
            linked_account=None, account_attached_by_participant=False, wishlist_confirmed=False
        )
        participant.shared_wishes.clear()
    participant.linked_account = None
    participant.account_attached_by_participant = False
    participant.wishlist_confirmed = False


def shareable_wishes(participant: ExchangeParticipant) -> list[tuple[Wish, bool]]:
    """Return the linked account's active wishes, each with whether its box is ticked.

    Once the participant confirmed, the boxes show the current selection. Before that, a
    wish is pre-ticked when its price hint is within the budget, in the same currency.
    """
    account = participant.linked_account
    if account is None:
        return []
    wishes = list(wishlist.guest_wishes(account).order_by("-priority", "title"))
    if participant.wishlist_confirmed:
        selected = set(participant.shared_wishes.values_list("pk", flat=True))
        return [(wish, wish.pk in selected) for wish in wishes]
    exchange = participant.exchange
    same_currency = account.profile.currency == exchange.currency
    return [
        (
            wish,
            exchange.budget is not None
            and same_currency
            and wish.price_hint is not None
            and wish.price_hint <= exchange.budget,
        )
        for wish in wishes
    ]


def save_shared_wishes(participant: ExchangeParticipant, user: User, wish_ids: Iterable) -> None:
    """Share the chosen active wishes with the Santa; ids of other wishes are ignored."""
    with transaction.atomic():
        service.lock_open(participant.exchange)
        _check_linked(participant, user)
        chosen = list(
            wishlist.active_wishes(user)
            .filter(wish_id__in=[str(wish_id) for wish_id in wish_ids])
            .values_list("pk", flat=True)
        )
        participant.shared_wishes.set(chosen)
        ExchangeParticipant.objects.filter(pk=participant.pk).update(wishlist_confirmed=True)
    participant.wishlist_confirmed = True
