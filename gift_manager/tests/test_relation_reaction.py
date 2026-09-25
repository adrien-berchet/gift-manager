"""Model and status-helper tests for gift plan reaction ratings."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from gift_manager.models import RelationStatus
from gift_manager.statuses import can_rate_status
from gift_manager.statuses import is_abandoned_status
from gift_manager.statuses import is_terminal_status
from gift_manager.tests.factories import RelationFactory


def _status(name: str) -> RelationStatus:
    status, _ = RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})
    return status


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Given", True),
        ("Abandoned", True),
        ("Idea", False),
        ("Planned", False),
        ("Purchased", False),
        # Given and Abandoned are the only terminal (and rateable) statuses.
        ("Received", False),
        ("Done", False),
        ("Completed", False),
    ],
)
def test_can_rate_status(name, expected):
    assert can_rate_status(RelationStatus(status=name, status_en=name)) is expected


@pytest.mark.parametrize("name", ["Received", "Done", "Completed"])
def test_legacy_slugs_are_not_terminal(name):
    assert is_terminal_status(RelationStatus(status=name, status_en=name)) is False


def test_is_abandoned_status():
    assert is_abandoned_status(RelationStatus(status="Abandoned", status_en="Abandoned"))
    assert not is_abandoned_status(RelationStatus(status="Given", status_en="Given"))
    assert not is_abandoned_status(None)


@pytest.mark.django_db
class TestRelationReactionFields:
    def test_reaction_is_empty_by_default(self):
        relation = RelationFactory()

        assert relation.reaction_rating is None
        assert relation.reaction_note is None

    @pytest.mark.parametrize("rating", [1, 3, 5])
    def test_valid_rating_is_saved(self, rating):
        relation = RelationFactory(status=_status("Given"), reaction_rating=rating)
        relation.full_clean()

        relation.refresh_from_db()
        assert relation.reaction_rating == rating

    @pytest.mark.parametrize("rating", [0, 6])
    def test_full_clean_rejects_out_of_range_rating(self, rating):
        relation = RelationFactory(status=_status("Given"))
        relation.reaction_rating = rating

        with pytest.raises(ValidationError) as exc_info:
            relation.full_clean()

        assert "reaction_rating" in exc_info.value.message_dict

    @pytest.mark.parametrize("rating", [0, 6])
    def test_database_rejects_out_of_range_rating(self, rating):
        relation = RelationFactory(status=_status("Given"))

        with pytest.raises(IntegrityError), transaction.atomic():
            type(relation).objects.filter(pk=relation.pk).update(reaction_rating=rating)

    def test_rating_is_kept_when_status_leaves_terminal(self):
        relation = RelationFactory(status=_status("Given"), reaction_rating=4)

        relation.status = _status("Planned")
        relation.save()

        relation.refresh_from_db()
        assert relation.reaction_rating == 4
        assert relation.has_visible_reaction is False

    def test_visible_reaction_requires_terminal_status_and_rating(self):
        relation = RelationFactory(status=_status("Given"), reaction_rating=4)
        assert relation.has_visible_reaction is True

        relation.reaction_rating = None
        assert relation.has_visible_reaction is False


@pytest.mark.django_db
class TestRelationStatusChangedAt:
    def test_set_on_creation(self):
        relation = RelationFactory()

        assert relation.status_changed_at is not None

    def test_updated_when_status_changes(self):
        relation = RelationFactory(status=_status("Planned"))
        type(relation).objects.filter(pk=relation.pk).update(
            status_changed_at=timezone.now() - timezone.timedelta(days=10)
        )
        relation.refresh_from_db()
        before = relation.status_changed_at

        relation.status = _status("Given")
        relation.save(update_fields=["status"])

        relation.refresh_from_db()
        assert relation.status_changed_at > before

    def test_unchanged_when_other_fields_change(self):
        relation = RelationFactory(status=_status("Planned"))
        before = relation.status_changed_at

        relation.comment = "Updated"
        relation.save()

        relation.refresh_from_db()
        assert relation.status_changed_at == before


@pytest.mark.django_db
class TestRelationStatusTrackingEdgeCases:
    def test_refresh_from_db_resyncs_tracked_status(self):
        relation = RelationFactory(status=_status("Planned"))
        loaded = type(relation).objects.get(pk=relation.pk)
        type(relation).objects.filter(pk=relation.pk).update(
            status=_status("Given"),
            status_changed_at=timezone.now() - timezone.timedelta(days=40),
        )
        loaded.refresh_from_db()
        before = loaded.status_changed_at

        loaded.comment = "Unrelated edit"
        loaded.save(update_fields=["comment"])

        loaded.refresh_from_db()
        assert loaded.status_changed_at == before
