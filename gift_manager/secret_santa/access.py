"""What a Secret Santa participant's page may show.

This is the single place that decides what a Santa sees of their recipient: the recipient's
exchange wishes and note, plus the real wishes the recipient chose to share, read through
``wishlist.guest_wishes`` so a wish archived, received or deleted since disappears and claim or
fulfillment columns are never loaded. Nothing here reads who drew a participant.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from gift_manager import wishlist
from gift_manager.secret_santa.models import ExchangeParticipant

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from gift_manager.models import Wish
    from gift_manager.secret_santa.models import ExchangeWish


@dataclass
class RecipientView:
    """What a Santa sees of the person they give a gift to."""

    name: str
    note: str = ""
    exchange_wishes: list[ExchangeWish] = field(default_factory=list)
    shared_wishes: list[Wish] = field(default_factory=list)
    # Currency of the shared wishes' prices: the recipient account's own currency
    shared_currency: str | None = None

    @property
    def has_content(self) -> bool:
        return bool(self.note.strip() or self.exchange_wishes or self.shared_wishes)


def recipient_view(santa: ExchangeParticipant) -> RecipientView | None:
    """Return what ``santa`` sees of their recipient, or None when there is nothing to see.

    Only a drawn exchange shows anything, and only to a participant who takes part.
    """
    exchange = santa.exchange
    if not exchange.is_drawn or santa.declined or santa.gives_to_id is None:
        return None
    recipient = (
        ExchangeParticipant.objects.filter(pk=santa.gives_to_id, exchange_id=santa.exchange_id)
        .select_related("linked_account__profile")
        .only(
            "name",
            "note_for_santa",
            "wishlist_confirmed",
            "exchange_id",
            "linked_account__id",
            "linked_account__is_active",
            "linked_account__profile__currency",
        )
        .first()
    )
    if recipient is None:
        return None
    view = RecipientView(
        name=recipient.name,
        note=recipient.note_for_santa,
        exchange_wishes=list(recipient.exchange_wishes.all()),
    )
    account = recipient.linked_account
    if recipient.wishlist_confirmed and account is not None and account.is_active:
        selection = recipient.shared_wishes.values("pk")
        view.shared_wishes = list(
            wishlist.guest_wishes(account).filter(pk__in=selection).order_by("-priority", "title")
        )
        view.shared_currency = account.profile.currency
    return view


def viewer_is_linked(participant: ExchangeParticipant, user: User | None) -> bool:
    """Return whether ``user`` is logged in as the account linked to ``participant``.

    Only then may a personal page show anything of that account.
    """
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_active
        and participant.linked_account_id is not None
        and participant.linked_account_id == user.pk
    )
