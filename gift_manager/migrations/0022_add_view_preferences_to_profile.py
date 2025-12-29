"""Migration to add view preferences to Profile model."""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0021_encode_email_addresses"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="default_view_desktop",
            field=models.CharField(
                choices=[("list", "List"), ("card", "Card")],
                default="list",
                help_text="Default view mode for desktop/large screens",
                max_length=10,
                verbose_name="Default view for desktop",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="default_view_mobile",
            field=models.CharField(
                choices=[("list", "List"), ("card", "Card")],
                default="card",
                help_text="Default view mode for mobile/small screens",
                max_length=10,
                verbose_name="Default view for mobile",
            ),
        ),
    ]
