from django.db import migrations


def create_birthday_event(apps, schema_editor):
    """Provision the global Birthday event used by birthday gift plans."""
    Event = apps.get_model("gift_manager", "Event")
    if Event.objects.filter(is_birthday=True).exists():
        return
    Event.objects.create(
        name="Birthday",
        schedule_type="unscheduled",
        is_global=True,
        is_birthday=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0031_person_birthday_global_events"),
    ]

    operations = [
        migrations.RunPython(create_birthday_event, migrations.RunPython.noop),
    ]
