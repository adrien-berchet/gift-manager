from django.db import migrations
from django.db.models import Q


def normalize_abandoned_status_spelling(apps, schema_editor):
    Relation = apps.get_model("gift_manager", "Relation")
    RelationStatus = apps.get_model("gift_manager", "RelationStatus")

    matching_statuses = list(
        RelationStatus.objects.filter(
            Q(status__in=["Abandoned", "Abandonned"]) | Q(status_en__in=["Abandoned", "Abandonned"])
        ).order_by("pk")
    )

    if matching_statuses:
        canonical = next(
            (
                status
                for status in matching_statuses
                if status.status == "Abandoned" or status.status_en == "Abandoned"
            ),
            matching_statuses[0],
        )

        for duplicate in matching_statuses:
            if duplicate.pk == canonical.pk:
                continue
            Relation.objects.filter(status_id=duplicate.pk).update(status_id=canonical.pk)
            duplicate.delete()
    else:
        canonical = RelationStatus()

    canonical.status = "Abandoned"
    canonical.status_en = "Abandoned"
    canonical.status_fr = "Abandonné"
    canonical.save()


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0024_restore_abandoned_relation_status"),
    ]

    operations = [
        migrations.RunPython(
            normalize_abandoned_status_spelling,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
