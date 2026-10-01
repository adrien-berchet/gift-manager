"""Send the reminder digest email to every user who opted in.

Designed to run from a plain scheduler (cron, systemd timer, platform scheduler), once a day::

    python manage.py send_gift_digest

Users who chose the weekly digest receive it on Mondays, or on a later day of the week when
the Monday digest was missed (the command did not run, or the user's digest failed). At most one
email is sent per user and per day: the day is recorded in ``Profile.last_digest_sent_on``, so
running the command again, for instance after a partial failure, only emails the users who did
not get theirs. Nothing is sent when nothing needs a user's attention. Links are built from the
``SITE_BASE_URL`` setting.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
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


def _attention_count(digest: Digest) -> int:
    return len(digest.overdue) + len(digest.due_soon) + len(digest.birthdays) + len(digest.events)


class Command(BaseCommand):
    help = "Send the gift reminder digest email to the users who opted in."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report who would receive an email without sending anything.",
        )
        parser.add_argument(
            "--include-weekly",
            action="store_true",
            help="Send the digest of every weekly user, whatever the weekday.",
        )
        parser.add_argument(
            "--user",
            metavar="USERNAME",
            help="Only consider this user.",
        )

    def handle(self, *args, **options):
        if not settings.SITE_BASE_URL:
            msg = "SITE_BASE_URL must be set (for example https://gifts.example.com)."
            raise CommandError(msg)

        today = timezone.localdate()
        # Weekly digests are due on Mondays. Later in the week they are still due for the users
        # who got none since the last Monday (a missed run), but not for users who never got one:
        # opting in on a Wednesday waits for the next Monday.
        weekly_due = Q(profile__digest_frequency=Profile.DIGEST_WEEKLY)
        if not (options["include_weekly"] or today.weekday() == MONDAY):
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
        if options["user"]:
            users = users.filter(username=options["user"])
        # A user who already got today's digest (an earlier run, possibly a partially failed
        # one) is not emailed again
        already_sent = users.filter(profile__last_digest_sent_on=today).count()
        users = users.exclude(profile__last_digest_sent_on=today)

        sent = skipped = failed = 0
        for user in users:
            try:
                if self._send_digest(user, dry_run=options["dry_run"]):
                    sent += 1
                else:
                    skipped += 1
            except Exception:  # noqa: PERF203
                # One broken recipient must not stop the digests of the others
                logger.exception("Could not send the gift digest to user %s", user.pk)
                failed += 1

        verb = "Would send" if options["dry_run"] else "Sent"
        self.stdout.write(
            f"{verb} {sent} digest(s); {skipped} skipped (nothing to report); "
            f"{already_sent} already sent today."
        )
        if failed:
            msg = f"{failed} digest(s) could not be sent (see the log)."
            raise CommandError(msg)

    def _send_digest(self, user, *, dry_run: bool) -> bool:
        """Send one user's digest; return False when there is nothing to report."""
        recipient = user.profile.email
        if not recipient:
            return False

        with translation.override(user.profile.language):
            digest = build_digest(user)
            if digest.is_empty:
                return False
            if dry_run:
                return True

            link = unsubscribe_url(user)
            context = {
                "user": user,
                "digest": digest,
                "base_url": settings.SITE_BASE_URL,
                "unsubscribe_url": link,
                "LANGUAGE_CODE": translation.get_language(),
            }
            subject = ngettext(
                "Gift Manager: %(count)d item needs your attention",
                "Gift Manager: %(count)d items need your attention",
                _attention_count(digest),
            ) % {"count": _attention_count(digest)}
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
            message.send()
        Profile.objects.filter(pk=user.profile.pk).update(last_digest_sent_on=timezone.localdate())
        return True
