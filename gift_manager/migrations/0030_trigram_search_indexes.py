"""Add pg_trgm GIN indexes so substring (icontains) searches do not scan whole tables.

The search endpoints filter with ``icontains``, which Django compiles to
``UPPER(column) LIKE UPPER('%term%')``. btree indexes cannot serve that, and the index has to
be built on the same ``UPPER(column)`` expression to be used.

Only PostgreSQL supports trigram indexes; on other databases this migration does nothing.
"""

from django.db import migrations

# (table, column) pairs searched with icontains by the global and per-list search views
TRIGRAM_COLUMNS = [
    ("gift_manager_gift", "name"),
    ("gift_manager_gift", "comment"),
    ("gift_manager_person", "first_name"),
    ("gift_manager_person", "family_name"),
    ("gift_manager_persongroup", "name"),
    ("gift_manager_event", "name"),
    ("gift_manager_event", "comment"),
    ("gift_manager_gifttag", "name"),
]


def _index_name(table: str, column: str) -> str:
    return f"{table}_{column}_trgm_idx"


def add_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, column in TRIGRAM_COLUMNS:
        schema_editor.execute(
            f"CREATE INDEX IF NOT EXISTS {_index_name(table, column)} "
            f"ON {table} USING gin (UPPER({column}) gin_trgm_ops)"
        )


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, column in TRIGRAM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS {_index_name(table, column)}")


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0029_profile_self_deactivated_at"),
    ]

    operations = [
        migrations.RunPython(add_trigram_indexes, drop_trigram_indexes),
    ]
