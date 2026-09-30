import logging

from django.db import migrations
from django.db import models

logger = logging.getLogger(__name__)

ARCHIVE_TABLE = "gift_manager_relation_0026_archive"
RELATION_TABLE = "gift_manager_relation"


def _archive_dirty_rows(schema_editor, *, reason: str, condition: str) -> None:
    """Copy the rows matching condition, with their reason, into the archive table."""
    quote = schema_editor.quote_name
    # reason and condition are literals from normalize_relation_recipients, never user input
    columns = (
        f"SELECT r.*, '{reason}' AS reason FROM {quote(RELATION_TABLE)} r "  # noqa: S608
        f"WHERE {condition}"
    )
    if ARCHIVE_TABLE in schema_editor.connection.introspection.table_names():
        schema_editor.execute(f"INSERT INTO {quote(ARCHIVE_TABLE)} {columns}")
    else:
        schema_editor.execute(f"CREATE TABLE {quote(ARCHIVE_TABLE)} AS {columns}")


def normalize_relation_recipients(apps, schema_editor):
    """Repair relations that do not have exactly one recipient, keeping a copy of each.

    A relation with both a person and a group loses its group; a relation with neither is
    deleted. Both choices are irreversible, so the affected rows are first copied, with the
    reason, into ``gift_manager_relation_0026_archive`` for an operator to review or restore.
    """
    Relation = apps.get_model("gift_manager", "Relation")
    both = Relation.objects.filter(person__isnull=False, group__isnull=False)
    neither = Relation.objects.filter(person__isnull=True, group__isnull=True)
    both_count, neither_count = both.count(), neither.count()

    if both_count:
        _archive_dirty_rows(
            schema_editor,
            reason="both person and group set: group cleared",
            condition="r.person_id IS NOT NULL AND r.group_id IS NOT NULL",
        )
    if neither_count:
        _archive_dirty_rows(
            schema_editor,
            reason="no recipient: relation deleted",
            condition="r.person_id IS NULL AND r.group_id IS NULL",
        )
    if both_count or neither_count:
        logger.warning(
            "Migration 0026 repaired dirty relations (%s with two recipients, %s with none). "
            "Original rows are kept in %s.",
            both_count,
            neither_count,
            ARCHIVE_TABLE,
        )

    both.update(group=None)
    neither.delete()

    if schema_editor.connection.vendor == "postgresql":
        # The updates and deletes above leave deferred foreign-key checks pending, and
        # PostgreSQL refuses to ALTER TABLE (the constraint below) while any are pending.
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0025_normalize_abandoned_status_spelling"),
    ]

    operations = [
        migrations.RunPython(normalize_relation_recipients, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="relation",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(person__isnull=False, group__isnull=True)
                    | models.Q(person__isnull=True, group__isnull=False)
                ),
                name="relation_exactly_one_recipient",
            ),
        ),
    ]
