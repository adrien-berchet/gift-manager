# Generated manually for GiftTag optimization

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0017_alter_persongroup_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gifttag",
            name="name",
            field=models.TextField(db_index=True),
        ),
    ]
