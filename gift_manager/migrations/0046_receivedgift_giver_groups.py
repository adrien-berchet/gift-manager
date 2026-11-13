"""Let a received gift name several giver groups (the giver selector mixes people and groups)."""

from django.db import migrations
from django.db import models


def copy_group_to_groups(apps, schema_editor):
    ReceivedGift = apps.get_model("gift_manager", "ReceivedGift")
    through_model = ReceivedGift.giver_groups.through
    through_model.objects.bulk_create(
        [
            through_model(receivedgift_id=gift_id, persongroup_id=group_id)
            for gift_id, group_id in ReceivedGift.objects.filter(
                giver_group__isnull=False
            ).values_list("pk", "giver_group_id")
        ]
    )


def copy_groups_to_group(apps, schema_editor):
    """Reverse: keep one group per gift (the first one linked)."""
    ReceivedGift = apps.get_model("gift_manager", "ReceivedGift")
    through_model = ReceivedGift.giver_groups.through
    first_group = {}
    for gift_id, group_id in through_model.objects.order_by("pk").values_list(
        "receivedgift_id", "persongroup_id"
    ):
        first_group.setdefault(gift_id, group_id)
    for gift_id, group_id in first_group.items():
        ReceivedGift.objects.filter(pk=gift_id).update(giver_group_id=group_id)


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0045_relation_revealed_at_receivedgift"),
    ]

    operations = [
        migrations.AddField(
            model_name="receivedgift",
            name="giver_groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to="gift_manager.persongroup",
                verbose_name="Giver groups",
            ),
        ),
        migrations.RunPython(copy_group_to_groups, copy_groups_to_group),
        migrations.RemoveField(
            model_name="receivedgift",
            name="giver_group",
        ),
    ]
