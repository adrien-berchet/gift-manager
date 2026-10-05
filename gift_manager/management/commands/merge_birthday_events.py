"""Move the gift plans of users' own "Birthday" events to the global Birthday event.

Before the global Birthday event existed, users created their own "Birthday" event and
attached gift plans to it. Gift plans for a birthday now point at one global event that
every user can view (``Event.objects.get_birthday_event``), so those plans can be moved.

Nothing changes unless ``--apply`` is given: the default is a dry run that lists what would
be moved. Gift plans keep their due date, status and sharing: every user can already view the
global event, so nobody loses sight of the event shown on a plan.

Usage::

    python manage.py merge_birthday_events                      # dry run
    python manage.py merge_birthday_events --apply              # move the gift plans
    python manage.py merge_birthday_events --apply --delete-old-events
    python manage.py merge_birthday_events --name Birthday --name Anniversaire
    python manage.py merge_birthday_events --event-id <uuid> --apply

Events are selected by name (case-insensitive, default ``Birthday``) or by ``--event-id``;
with ``--event-id`` alone, only those events are selected.
Events with a different name, such as "Mom Birthday", are never merged automatically: they
are listed so you can pass their id explicitly if they should be merged too. Running the
command again is safe: events that were already merged have no gift plan left to move.
"""

import uuid

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.db.models.functions import Lower
from django.db.models.functions import Trim

from gift_manager.models import Event
from gift_manager.models import Relation

DEFAULT_NAMES = ("Birthday",)
KEYWORDS = ("birthday", "anniversaire")


class Command(BaseCommand):
    help = "Move the gift plans of users' own Birthday events to the global Birthday event."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Move the gift plans. Without it, only report what would be moved.",
        )
        parser.add_argument(
            "--name",
            action="append",
            dest="names",
            help=(
                "Name of the events to merge, case-insensitive. Repeat for several names "
                f"(default: {', '.join(DEFAULT_NAMES)}, unless --event-id is given)."
            ),
        )
        parser.add_argument(
            "--event-id",
            action="append",
            dest="event_ids",
            default=[],
            help="Merge this event (UUID) whatever its name. Repeat for several events.",
        )
        parser.add_argument(
            "--delete-old-events",
            action="store_true",
            help="With --apply, also delete the merged events once they have no gift plan left.",
        )

    def handle(self, *args, **options):
        if options["delete_old_events"] and not options["apply"]:
            message = "--delete-old-events needs --apply."
            raise CommandError(message)

        # The default name only applies when nothing else selects events: with --event-id alone,
        # exactly those events are merged
        requested = options["names"] or (None if options["event_ids"] else DEFAULT_NAMES)
        names = [name.strip() for name in (requested or []) if name.strip()]
        if not names and not options["event_ids"]:
            message = "Give at least one non-empty --name or an --event-id."
            raise CommandError(message)
        event_ids = [self._parse_event_id(raw_id) for raw_id in options["event_ids"]]

        candidates = self._candidates(names, event_ids)
        self._report_candidates(candidates)
        self._report_similar(candidates)
        if not candidates:
            return

        target = Event.objects.filter(is_birthday=True).first()
        total = sum(event.relation_count for event in candidates)
        if not options["apply"]:
            self._report_dry_run(target, total, len(candidates))
            return

        self._apply(candidates, delete_old=options["delete_old_events"])

    @staticmethod
    def _parse_event_id(raw_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(raw_id)
        except ValueError:
            message = f"Not a valid event id: {raw_id}"
            raise CommandError(message) from None

    @staticmethod
    def _candidates(names: list[str], event_ids: list[uuid.UUID]) -> list[Event]:
        """Return the events to merge: never the global Birthday event itself.

        Names match case-insensitively and ignore padding around the stored name.
        """
        wanted = [name.lower() for name in names]
        return list(
            Event.objects.annotate(normalized_name=Lower(Trim("name")))
            .filter(Q(event_id__in=event_ids) | Q(normalized_name__in=wanted), is_birthday=False)
            .annotate(relation_count=Count("relations", distinct=True))
            .order_by("name", "creation_date")
        )

    def _report_candidates(self, candidates: list[Event]) -> None:
        if not candidates:
            self.stdout.write("No Birthday event to merge.")
            return
        self.stdout.write(f"{len(candidates)} Birthday event(s) to merge:")
        for event in candidates:
            self.stdout.write(
                f"  {event.event_id}  {event.name!r}  {event.date_summary}  "
                f"{event.relation_count} gift plan(s)"
            )

    def _report_similar(self, candidates: list[Event]) -> None:
        """List events that look like birthdays but were not selected, for the admin to judge."""
        similar = Q()
        for keyword in KEYWORDS:
            similar |= Q(name__icontains=keyword)
        others = (
            Event.objects.filter(similar, is_birthday=False)
            .exclude(pk__in=[event.pk for event in candidates])
            .annotate(relation_count=Count("relations", distinct=True))
            .order_by("name")
        )
        if not others:
            return
        self.stdout.write("Not merged (the name differs; pass --event-id to merge one):")
        for event in others:
            self.stdout.write(
                f"  {event.event_id}  {event.name!r}  {event.relation_count} gift plan(s)"
            )

    def _report_dry_run(self, target: Event | None, total: int, event_count: int) -> None:
        destination = (
            f"the global Birthday event ({target.event_id})"
            if target
            else "the global Birthday event (created when you apply)"
        )
        self.stdout.write(
            self.style.WARNING(
                f"Dry run: {total} gift plan(s) from {event_count} event(s) would move to "
                f"{destination}. Re-run with --apply to do it."
            )
        )

    def _apply(self, candidates: list[Event], *, delete_old: bool) -> None:
        with transaction.atomic():
            target = Event.objects.get_birthday_event()
            moved = 0
            deleted = 0
            for event in candidates:
                count = Relation.objects.filter(event=event).update(event=target)
                moved += count
                self.stdout.write(
                    f"  {event.name!r} ({event.event_id}): moved {count} gift plan(s)"
                )
                # Only delete an event nothing refers to any more
                if delete_old and not Relation.objects.filter(event=event).exists():
                    event.delete()
                    deleted += 1

        message = f"Moved {moved} gift plan(s) to the global Birthday event."
        if delete_old:
            message += f" Deleted {deleted} old event(s)."
        self.stdout.write(self.style.SUCCESS(message))
