"""Tests for ``audit_relation_recipients`` (GM-AUD-010)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

ARCHIVE_TABLE = "gift_manager_relation_0026_archive"


def _run(*args) -> str:
    out = StringIO()
    call_command("audit_relation_recipients", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def archive_table():
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {ARCHIVE_TABLE} (id integer, comment text, reason text)")
        cursor.execute(
            f"INSERT INTO {ARCHIVE_TABLE} VALUES (1, 'lost', 'no recipient: relation deleted')"  # noqa: S608
        )
        cursor.execute(
            f"INSERT INTO {ARCHIVE_TABLE} VALUES (2, 'trimmed', "  # noqa: S608
            "'both person and group set: group cleared')"
        )
    yield
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {ARCHIVE_TABLE}")


@pytest.mark.django_db(transaction=True)
def test_clean_database_reports_nothing_to_review():
    output = _run()

    assert "No relation without exactly one recipient" in output
    assert "No archive from migration 0026" in output


@pytest.mark.django_db(transaction=True)
def test_clean_database_passes_with_fail_on_findings():
    _run("--fail-on-findings")


@pytest.mark.django_db(transaction=True)
def test_reports_rows_archived_by_migration_0026(archive_table):
    output = _run()

    assert "2 row(s)" in output
    assert "no recipient: relation deleted: 1" in output
    assert "both person and group set: group cleared: 1" in output


@pytest.mark.django_db(transaction=True)
def test_fail_on_findings_exits_with_an_error_when_rows_were_archived(archive_table):
    with pytest.raises(CommandError, match="review"):
        _run("--fail-on-findings")
