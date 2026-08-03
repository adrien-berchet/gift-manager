from datetime import date
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from gift_manager.models import RelationStatus


@pytest.mark.django_db
class TestNormalizeAbandonedStatusSpellingMigration:
    """Regression tests for the abandoned-status data repair migration."""

    @staticmethod
    def _run_migration():
        migration = import_module(
            "gift_manager.migrations.0025_normalize_abandoned_status_spelling"
        )
        migration.normalize_abandoned_status_spelling(apps, None)

    def test_renames_existing_typo_status(self):
        typo_status = RelationStatus.objects.get(status_en="Abandoned")
        typo_status.status = "Abandonned"
        typo_status.status_en = "Abandonned"
        typo_status.save()

        self._run_migration()

        typo_status.refresh_from_db()
        assert typo_status.status == "Abandoned"
        assert typo_status.status_en == "Abandoned"
        assert typo_status.status_fr == "Abandonné"

    def test_keeps_existing_canonical_status(self):
        status = RelationStatus.objects.get(status_en="Abandoned")

        self._run_migration()

        status.refresh_from_db()
        assert status.status == "Abandoned"
        assert status.status_en == "Abandoned"
        assert status.status_fr == "Abandonné"
        assert RelationStatus.objects.filter(status="Abandoned").count() == 1

    def test_merges_typo_duplicate_and_repoints_relations(self, relation_factory):
        canonical = RelationStatus.objects.get(status_en="Abandoned")
        typo_status = RelationStatus.objects.create(
            status="Abandonned",
            status_en="Abandonned",
            status_fr="Legacy abandoned",
        )
        canonical_relation = relation_factory(status=canonical)
        typo_relation = relation_factory(status=typo_status)

        self._run_migration()

        canonical_relation.refresh_from_db()
        typo_relation.refresh_from_db()
        assert canonical_relation.status_id == canonical.pk
        assert typo_relation.status_id == canonical.pk
        assert not RelationStatus.objects.filter(status="Abandonned").exists()
        assert not RelationStatus.objects.filter(status_en="Abandonned").exists()
        assert RelationStatus.objects.filter(status="Abandoned").count() == 1


@pytest.mark.django_db(transaction=True)
class TestEventScheduleModelMigration:
    """Regression tests for the event schedule data migration."""

    migrate_from = [("gift_manager", "0026_relation_exactly_one_recipient_constraint")]
    migrate_to = [("gift_manager", "0027_event_schedule_model")]

    def test_maps_legacy_event_dates_to_schedule_contract(self):
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()

        try:
            executor.migrate(self.migrate_from)
            old_apps = executor.loader.project_state(self.migrate_from).apps
            legacy_event = old_apps.get_model("gift_manager", "Event")

            legacy_event.objects.create(
                name="Graduation",
                usual_date=date(2026, 6, 1),
                absolute_date=date(2026, 6, 20),
                recurrence="yearly",
            )
            legacy_event.objects.create(
                name="Birthday",
                usual_date=date(2000, 5, 15),
                recurrence="yearly",
            )
            legacy_event.objects.create(
                name="Visit",
                usual_date=date(2026, 8, 2),
            )
            legacy_event.objects.create(name="Someday")

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            Event = new_apps.get_model("gift_manager", "Event")

            schedules = {
                event.name: (event.schedule_type, event.date, event.recurrence)
                for event in Event.objects.order_by("name")
            }

            assert schedules == {
                "Birthday": ("recurring", date(2000, 5, 15), "yearly"),
                "Graduation": ("one_time", date(2026, 6, 20), None),
                "Someday": ("unscheduled", None, None),
                "Visit": ("one_time", date(2026, 8, 2), None),
            }
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(leaf_nodes)
