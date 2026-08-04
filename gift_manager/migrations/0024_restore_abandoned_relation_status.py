from django.db import migrations
from django.db.models import Q


def restore_abandoned_relation_status(apps, schema_editor):
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

        canonical.status = "Abandoned"
        canonical.status_en = "Abandoned"
        canonical.status_fr = "Abandonné"
        canonical.save(update_fields=["status", "status_en", "status_fr"])
        return

    RelationStatus.objects.create(
        status="Abandoned",
        status_en="Abandoned",
        status_fr="Abandonné",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0023_remove_extra_fields"),
    ]

    operations = [
        migrations.RunPython(
            restore_abandoned_relation_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
