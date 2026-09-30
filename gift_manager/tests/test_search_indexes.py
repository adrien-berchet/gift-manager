"""Substring search is backed by trigram indexes on PostgreSQL (GM-AUD-017)."""

import pytest
from django.db import connection

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Person
from gift_manager.models import PersonGroup

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="Trigram indexes need PostgreSQL"),
]

SEARCHED_COLUMNS = [
    (Gift, "name"),
    (Gift, "comment"),
    (Person, "first_name"),
    (Person, "family_name"),
    (PersonGroup, "name"),
    (Event, "name"),
    (Event, "comment"),
    (GiftTag, "name"),
]


def _trigram_indexed_columns() -> set[tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename, indexdef FROM pg_indexes WHERE indexdef ILIKE '%%gin_trgm_ops%%'"
        )
        rows = cursor.fetchall()
    return {(table, definition) for table, definition in rows}


@pytest.mark.parametrize(("model", "column"), SEARCHED_COLUMNS)
def test_searched_column_has_a_trigram_index(model, column):
    table = model._meta.db_table
    definitions = [d for t, d in _trigram_indexed_columns() if t == table]

    assert any(f"(upper({column}) gin_trgm_ops)" in d.lower() for d in definitions), (table, column)


@pytest.mark.parametrize(("model", "column"), SEARCHED_COLUMNS)
def test_icontains_search_can_use_the_index(model, column):
    """With sequential scans disabled the planner must pick the trigram index."""
    query = model.objects.filter(**{f"{column}__icontains": "needle"}).query
    sql, params = query.sql_with_params()

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "Index Scan" in plan or "Bitmap" in plan, plan
