from django.db import migrations
from django.db import models


def normalize_relation_recipients(apps, schema_editor):
    Relation = apps.get_model("gift_manager", "Relation")

    Relation.objects.filter(person__isnull=False, group__isnull=False).update(group=None)
    Relation.objects.filter(person__isnull=True, group__isnull=True).delete()


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
