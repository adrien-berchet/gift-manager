"""Send the reminder digest emails to the users who opted in.

Shared by the ``send_gift_digest`` management command and by the Vercel Cron endpoint, so both
select recipients and send emails the same way.

Weekly digests are due on Mondays. Later in the week they are still due for the users who got
none since the last Monday (a missed run), but not for users who never got one: opting in on a
Wednesday waits for the next Monday. At most one email is sent per user and per day. The day is
recorded in ``Profile.last_digest_sent_on`` *before* sending, with a conditional update, so two
runs that overlap (a scheduler that delivers twice) cannot both email the same user; the day is
restored when sending fails, so the next run retries that user.
"""

import logging
from dataclasses import dataclass
from datetime import date
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils import translation
from django.utils.translation import ngettext

from gift_manager.models import Profile
from gift_manager.reminders import Digest
from gift_manager.reminders import build_digest
from gift_manager.reminders import unsubscribe_url

logger = logging.getLogger(__name__)

MONDAY = 0

SENT = "sent"
EMPTY = "empty"
ALREADY_SENT = "already_sent"


@dataclass
class DigestRun:
    """Outcome of one run: how many users got, skipped or failed their digest."""

    sent: int = 0
    skipped: int = 0
    already_sent: int = 0
    failed: int = 0
    dry_run: bool = False


def _attention_count(digest: Digest) -> int:
    return len(digest.overdue) + len(digest.due_soon) + len(digest.birthdays) + len(digest.events)


def due_users(today: date, *, include_weekly: bool = False, username: str | None = None):
    """Return the active users whose digest is due today, whether or not it was sent already."""
    weekly_due = Q(profile__digest_frequency=Profile.DIGEST_WEEKLY)
    if not (include_weekly or today.weekday() == MONDAY):
        last_monday = today - timedelta(days=today.weekday())
        weekly_due &= Q(profile__last_digest_sent_on__lt=last_monday)

    users = (
        User.objects.filter(
            Q(profile__digest_frequency=Profile.DIGEST_DAILY) | weekly_due,
            is_active=True,
        )
        .select_related("profile")
        .order_by("pk")
    )
    if username:
        users = users.filter(username=username)
    return users


def _claim_day(profile: Profile, today: date) -> bool:
    """Record today as the digest day of a profile; False when someone else already did."""
    claimed = (
        Profile.objects.filter(pk=profile.pk)
        .exclude(last_digest_sent_on=today)
        .update(last_digest_sent_on=today)
    )
    return bool(claimed)


def _release_day(profile: Profile, previous: date | None, today: date) -> None:
    """Undo ``_claim_day`` after a failed send so the next run retries the user."""
    Profile.objects.filter(pk=profile.pk, last_digest_sent_on=today).update(
        last_digest_sent_on=previous
    )


def _build_message(user, digest: Digest, recipient: str) -> EmailMultiAlternatives:
    link = unsubscribe_url(user)
    context = {
        "user": user,
        "digest": digest,
        "base_url": settings.SITE_BASE_URL,
        "unsubscribe_url": link,
        "LANGUAGE_CODE": translation.get_language(),
    }
    count = _attention_count(digest)
    subject = ngettext(
        "Gift Manager: %(count)d item needs your attention",
        "Gift Manager: %(count)d items need your attention",
        count,
    ) % {"count": count}
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("gift_manager/email/digest.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        headers={
            "List-Unsubscribe": f"<{link}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(
        render_to_string("gift_manager/email/digest.html", context), "text/html"
    )
    return message


def _send_digest(user, today: date, *, dry_run: bool) -> str:
    """Send one user's digest; return SENT, EMPTY (nothing to report) or ALREADY_SENT."""
    recipient = user.profile.email
    if not recipient:
        return EMPTY

    with translation.override(user.profile.language):
        digest = build_digest(user, today)
        if digest.is_empty:
            return EMPTY
        if dry_run:
            return SENT

        previous = user.profile.last_digest_sent_on
        if not _claim_day(user.profile, today):
            return ALREADY_SENT
        try:
            _build_message(user, digest, recipient).send()
        except Exception:
            _release_day(user.profile, previous, today)
            raise
    return SENT


def send_digests(
    *,
    today: date | None = None,
    include_weekly: bool = False,
    username: str | None = None,
    dry_run: bool = False,
) -> DigestRun:
    """Send the digests that are due today; one failing recipient does not stop the others."""
    if not settings.SITE_BASE_URL:
        msg = "SITE_BASE_URL must be set (for example https://gifts.example.com)."
        raise ImproperlyConfigured(msg)

    today = today or timezone.localdate()
    users = due_users(today, include_weekly=include_weekly, username=username)
    # A user who already got today's digest (an earlier run, possibly a partially failed one)
    # is not emailed again
    run = DigestRun(
        dry_run=dry_run, already_sent=users.filter(profile__last_digest_sent_on=today).count()
    )

    for user in users.exclude(profile__last_digest_sent_on=today):
        try:
            outcome = _send_digest(user, today, dry_run=dry_run)
        except Exception:
            # One broken recipient must not stop the digests of the others
            logger.exception("Could not send the gift digest to user %s", user.pk)
            run.failed += 1
            continue
        if outcome == SENT:
            run.sent += 1
        elif outcome == ALREADY_SENT:
            run.already_sent += 1
        else:
            run.skipped += 1
    return run
