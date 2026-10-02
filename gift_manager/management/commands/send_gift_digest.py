"""Send the reminder digest email to every user who opted in.

Designed to run from a plain scheduler (cron, systemd timer), once a day::

    python manage.py send_gift_digest

On Vercel, where no command can be scheduled, the same work is triggered by the cron endpoint
``/cron/send-gift-digest/`` (see ``docs/operations/reminders.md``). The rules (weekly digests on
Mondays with a catch-up, at most one email per user and per day, links built from
``SITE_BASE_URL``) live in ``gift_manager.digest_sending``.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from gift_manager.digest_sending import send_digests


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
        username = options["user"]
        if username and not User.objects.filter(username=username).exists():
            msg = f"User {username!r} does not exist."
            raise CommandError(msg)

        try:
            run = send_digests(
                include_weekly=options["include_weekly"],
                username=username,
                dry_run=options["dry_run"],
            )
        except ImproperlyConfigured as error:
            raise CommandError(str(error)) from error

        verb = "Would send" if run.dry_run else "Sent"
        self.stdout.write(
            f"{verb} {run.sent} digest(s); {run.skipped} skipped (nothing to report); "
            f"{run.already_sent} already sent today."
        )
        if run.failed:
            msg = f"{run.failed} digest(s) could not be sent (see the log)."
            raise CommandError(msg)
