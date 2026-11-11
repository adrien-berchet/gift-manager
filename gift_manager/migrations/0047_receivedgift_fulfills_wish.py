"""Let a received gift link a wish without marking it as received (wishes received often)."""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0046_receivedgift_giver_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="receivedgift",
            name="fulfills_wish",
            field=models.BooleanField(default=True, verbose_name="Mark the wish as received"),
        ),
    ]
