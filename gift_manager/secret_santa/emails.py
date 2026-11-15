"""Secret Santa emails: the personal link of each participant, with a stop link.

Emails go to addresses typed by the organizer, so they hold only the exchange name, the
organizer's name, the participant's name and the two links; never the guidelines nor who the
participant drew. Every organizer has a quota of emails per window. Sending happens after the
draw is committed: one failing recipient does not stop the others, and is reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.mail import get_connection
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils import translation
from django.utils.translation import gettext

from gift_manager.secret_santa.models import Exchange
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.secret_santa.service import ExchangeError

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable
    from datetime import datetime

logger = logging.getLogger(__name__)

STOP_SALT = "gift_manager.secret_santa.stop"


@dataclass
class SendReport:
    """What happened to each participant of one sending."""

    sent: list[ExchangeParticipant] = field(default_factory=list)
    no_email: list[ExchangeParticipant] = field(default_factory=list)
    stopped: list[ExchangeParticipant] = field(default_factory=list)
    failed: list[ExchangeParticipant] = field(default_factory=list)
    over_limit: list[ExchangeParticipant] = field(default_factory=list)


def organizer_name(exchange: Exchange) -> str:
    organizer = exchange.organizer
    return organizer.get_full_name().strip() or organizer.username


def participant_path(participant: ExchangeParticipant) -> str:
    """Return the path of the personal page, under the organizer's language prefix."""
    with translation.override(participant.exchange.organizer.profile.language):
        return reverse("gift_manager:secret_santa_participant", args=[participant.token])


def make_stop_token(participant: ExchangeParticipant) -> str:
    """Return the signed token of the "stop emails for this exchange" link."""
    return signing.dumps(participant.pk, salt=STOP_SALT)


def read_stop_token(token: str) -> int | None:
    """Return the participant id held by a stop token, or None when it is not valid."""
    try:
        participant_id = signing.loads(token, salt=STOP_SALT)
    except signing.BadSignature:
        return None
    return participant_id if isinstance(participant_id, int) else None


def stop_path(participant: ExchangeParticipant) -> str:
    with translation.override(participant.exchange.organizer.profile.language):
        return reverse("gift_manager:secret_santa_stop_emails", args=[make_stop_token(participant)])


def _quota_key(exchange: Exchange) -> str:
    return f"gift_manager:secret-santa-emails:{exchange.organizer_id}"


def _reserve_quota(exchange: Exchange) -> bool:
    """Count one email for the organizer; False once the quota of the window is used up.

    The window starts with the first email and lasts ``SECRET_SANTA_EMAIL_WINDOW_SECONDS``.
    """
    limit = settings.SECRET_SANTA_EMAIL_LIMIT
    window = settings.SECRET_SANTA_EMAIL_WINDOW_SECONDS
    key = _quota_key(exchange)
    if cache.add(key, 1, window):
        return limit >= 1
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window)
        count = 1
    return count <= limit


def _language(participant: ExchangeParticipant) -> str:
    account = participant.linked_account
    if account is not None:
        return account.profile.language
    return participant.exchange.organizer.profile.language


def _build_message(
    participant: ExchangeParticipant,
    recipient: str,
    build_absolute_uri: Callable[[str], str],
    connection,
) -> EmailMultiAlternatives:
    exchange = participant.exchange
    personal_url = build_absolute_uri(participant_path(participant))
    stop_url = build_absolute_uri(stop_path(participant))
    with translation.override(_language(participant)):
        context = {
            "participant_name": participant.name,
            "exchange_name": exchange.name,
            "organizer_name": organizer_name(exchange),
            "personal_url": personal_url,
            "stop_url": stop_url,
            "LANGUAGE_CODE": translation.get_language(),
        }
        subject = gettext('Secret Santa "%(exchange)s": your link, %(participant)s') % {
            "exchange": exchange.name,
            "participant": participant.name,
        }
        message = EmailMultiAlternatives(
            subject=subject,
            body=render_to_string("gift_manager/email/secret_santa_assignment.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            headers={
                "List-Unsubscribe": f"<{stop_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
            connection=connection,
        )
        message.attach_alternative(
            render_to_string("gift_manager/email/secret_santa_assignment.html", context),
            "text/html",
        )
    return message


def _sort_out(
    exchange: Exchange, participants: Iterable[ExchangeParticipant], report: SendReport
) -> list[tuple[ExchangeParticipant, str]]:
    """Report the participants who get no email; return the others with their address."""
    wanted = [participant.pk for participant in participants]
    rows = {
        participant.pk: participant
        for participant in ExchangeParticipant.objects.filter(exchange=exchange, pk__in=wanted)
        .select_related("exchange__organizer__profile", "linked_account__profile")
        .defer("gives_to")
    }
    eligible: list[tuple[ExchangeParticipant, str]] = []
    for participant in (rows[pk] for pk in dict.fromkeys(wanted) if pk in rows):
        address = participant.email
        if not address:
            report.no_email.append(participant)
        elif participant.emails_stopped:
            report.stopped.append(participant)
        else:
            eligible.append((participant, address))
    return eligible


def _send_each(
    exchange: Exchange,
    eligible: list[tuple[ExchangeParticipant, str]],
    build_absolute_uri: Callable[[str], str],
    connection,
    report: SendReport,
) -> None:
    for index, (participant, address) in enumerate(eligible):
        if not _reserve_quota(exchange):
            report.over_limit.extend(rest for rest, _ in eligible[index:])
            return
        try:
            _build_message(participant, address, build_absolute_uri, connection).send()
        except Exception:
            # One broken recipient must not stop the emails of the others
            logger.exception("Could not send the Secret Santa email to %s", participant.pk)
            report.failed.append(participant)
        else:
            report.sent.append(participant)


def send_assignments(
    exchange: Exchange,
    participants: Iterable[ExchangeParticipant],
    build_absolute_uri: Callable[[str], str],
) -> SendReport:
    """Email each participant their personal link; return what happened to each of them."""
    report = SendReport()
    eligible = _sort_out(exchange, participants, report)
    if not eligible:
        return report

    connection = get_connection()
    try:
        connection.open()
    except Exception:
        logger.exception("Could not open the mail connection for Secret Santa %s", exchange.pk)
        report.failed.extend(participant for participant, _ in eligible)
        return report
    try:
        _send_each(exchange, eligible, build_absolute_uri, connection, report)
    finally:
        try:
            connection.close()
        except Exception:
            logger.exception("Could not close the mail connection")

    now = timezone.now()
    ExchangeParticipant.objects.filter(pk__in=[p.pk for p in report.sent]).update(
        last_emailed_at=now
    )
    for participant in report.sent:
        participant.last_emailed_at = now
    return report


def can_send_again(participant: ExchangeParticipant, now: datetime | None = None) -> bool:
    """Return whether the "Send again" cooldown of this participant is over."""
    if participant.last_emailed_at is None:
        return True
    cooldown = timedelta(seconds=settings.SECRET_SANTA_RESEND_COOLDOWN_SECONDS)
    return (now or timezone.now()) - participant.last_emailed_at >= cooldown


def send_again(
    participant: ExchangeParticipant, build_absolute_uri: Callable[[str], str]
) -> SendReport:
    """Send a participant's email again, after the draw and outside the cooldown."""
    exchange = participant.exchange
    if exchange.status != Exchange.Status.DRAWN:
        raise ExchangeError(gettext("The draw has not been done yet."))
    if not can_send_again(participant):
        raise ExchangeError(gettext("Wait a few minutes before sending this email again."))
    return send_assignments(exchange, [participant], build_absolute_uri)
