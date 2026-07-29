from importlib import import_module

import pytest
from django.apps import apps

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
