"""Report relations that migration 0026 may have repaired or deleted.

Migration 0026 enforces "exactly one recipient (person or group)" on relations. Before it,
a relation with both a person and a group lost its group, and a relation with neither was
deleted, without any record. Two ways to check whether data was affected:

* Run this command against a restore of a backup taken *before* migration 0026 (before
  migrating it): it lists the relations that the migration would repair or delete.
* Run it against a database migrated with the current 0026: it summarizes the rows the
  migration archived in ``gift_manager_relation_0026_archive``.

Usage::

    python manage.py audit_relation_recipients
    python manage.py audit_relation_recipients --fail-on-findings   # non-zero exit for CI/scripts
"""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import connection

from gift_manager.models import Relation

ARCHIVE_TABLE = "gift_manager_relation_0026_archive"


class Command(BaseCommand):
    help = "Report relations without exactly one recipient and rows archived by migration 0026."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-findings",
            action="store_true",
            help="Exit with an error when something needs review.",
        )

    def handle(self, *args, **options):
        findings = self._report_current_rows() + self._report_archive()

        if findings and options["fail_on_findings"]:
            message = f"{findings} relation(s) need review (see above)."
            raise CommandError(message)

    def _report_current_rows(self) -> int:
        both = Relation.objects.filter(person__isnull=False, group__isnull=False)
        neither = Relation.objects.filter(person__isnull=True, group__isnull=True)
        both_count, neither_count = both.count(), neither.count()

        if not (both_count or neither_count):
            self.stdout.write("No relation without exactly one recipient.")
            return 0

        self.stdout.write(
            self.style.WARNING(
                f"{both_count} relation(s) with both a person and a group (migration 0026 "
                f"would clear the group), {neither_count} with no recipient (would be deleted)."
            )
        )
        for label, queryset in (("both recipients", both), ("no recipient", neither)):
            for relation_id in queryset.values_list("relation_id", flat=True):
                self.stdout.write(f"  {label}: {relation_id}")
        return both_count + neither_count

    def _report_archive(self) -> int:
        if ARCHIVE_TABLE not in connection.introspection.table_names():
            self.stdout.write("No archive from migration 0026.")
            return 0

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT reason, COUNT(*) FROM {ARCHIVE_TABLE} GROUP BY reason ORDER BY reason"  # noqa: S608
            )
            counts = cursor.fetchall()

        total = sum(count for _reason, count in counts)
        self.stdout.write(
            self.style.WARNING(
                f"Migration 0026 archived {total} row(s) in {ARCHIVE_TABLE}, "
                "review them and restore what is still relevant:"
            )
        )
        for reason, count in counts:
            self.stdout.write(f"  {reason}: {count}")
        return total
