"""Secret Santa cards of the dashboard.

An exchange shows to its organizer while it is not closed. It shows to a participant linked to
the user who did not decline once it is drawn, or earlier if they were invited or linked their
account themselves: a person silently imported into a draft sees nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Q

from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant

if TYPE_CHECKING:
    from django.contrib.auth.models import User


@dataclass
class DashboardCard:
    """One exchange on the dashboard, for its organizer and/or one of its participants."""

    exchange: Exchange
    is_organizer: bool
    participant: ExchangeParticipant | None = None
    # Only the user's own recipient, once drawn
    recipient_name: str | None = None


def cards(user: User) -> list[DashboardCard]:
    """Return the dashboard cards of ``user``, one per exchange, soonest first."""
    if not user or not user.is_authenticated:
        return []
    by_exchange: dict[int, DashboardCard] = {
        exchange.pk: DashboardCard(exchange=exchange, is_organizer=True)
        for exchange in Exchange.objects.filter(organizer=user).exclude(
            status=Exchange.Status.CLOSED
        )
    }
    visible = (
        Q(exchange__status=Exchange.Status.DRAWN)
        | Q(invited_at__isnull=False)
        | Q(account_attached_by_participant=True)
        | Q(exchange__organizer=user)
    )
    participations = (
        ExchangeParticipant.objects.filter(
            visible, linked_account=user, declined=False, exchange__organizer__is_active=True
        )
        .exclude(exchange__status=Exchange.Status.CLOSED)
        .select_related("exchange")
        .defer("note_for_santa")
    )
    recipients = {}
    for participant in participations:
        card = by_exchange.setdefault(
            participant.exchange_id,
            DashboardCard(exchange=participant.exchange, is_organizer=False),
        )
        card.participant = participant
        if participant.exchange.is_drawn and participant.gives_to_id is not None:
            recipients[participant.gives_to_id] = card
    names = dict(
        ExchangeParticipant.objects.filter(pk__in=list(recipients)).values_list("pk", "name")
    )
    for recipient_pk, card in recipients.items():
        card.recipient_name = names.get(recipient_pk)
    return sorted(
        by_exchange.values(), key=lambda card: (card.exchange.exchange_date, card.exchange.pk)
    )
