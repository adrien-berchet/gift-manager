# Generated manually to remove extra fields from database

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gift_manager', '0022_add_view_preferences_to_profile'),
    ]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE gift_manager_person DROP COLUMN IF EXISTS updated_at;",
            reverse_sql="ALTER TABLE gift_manager_person ADD COLUMN updated_at timestamp with time zone;"
        ),
        migrations.RunSQL(
            "ALTER TABLE gift_manager_person DROP COLUMN IF EXISTS version;",
            reverse_sql="ALTER TABLE gift_manager_person ADD COLUMN version integer;"
        ),
    ]
