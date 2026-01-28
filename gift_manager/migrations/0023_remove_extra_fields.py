# Generated manually to remove extra fields from database

from django.db import migrations


def remove_columns_if_exist(apps, schema_editor):
    """Remove columns if they exist (SQLite compatible)."""
    db_alias = schema_editor.connection.alias

    # Check if we're using SQLite
    if 'sqlite' in schema_editor.connection.vendor:
        # For SQLite, we need to check if columns exist first
        with schema_editor.connection.cursor() as cursor:
            # Get table info
            cursor.execute("PRAGMA table_info(gift_manager_person);")
            columns = [row[1] for row in cursor.fetchall()]

            # Only attempt to drop columns if they exist
            # Note: SQLite doesn't support DROP COLUMN until version 3.35.0
            # For older SQLite versions, we'll just skip this operation
            try:
                if 'updated_at' in columns:
                    cursor.execute("ALTER TABLE gift_manager_person DROP COLUMN updated_at;")
                if 'version' in columns:
                    cursor.execute("ALTER TABLE gift_manager_person DROP COLUMN version;")
            except Exception:
                # If DROP COLUMN is not supported, just pass
                pass
    else:
        # For other databases, use IF EXISTS syntax
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE gift_manager_person DROP COLUMN IF EXISTS updated_at;")
            cursor.execute("ALTER TABLE gift_manager_person DROP COLUMN IF EXISTS version;")


def add_columns_back(apps, schema_editor):
    """Add columns back (reverse operation)."""
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("ALTER TABLE gift_manager_person ADD COLUMN updated_at timestamp with time zone;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE gift_manager_person ADD COLUMN version integer;")
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('gift_manager', '0022_add_view_preferences_to_profile'),
    ]

    operations = [
        migrations.RunPython(
            remove_columns_if_exist,
            reverse_code=add_columns_back
        ),
    ]
