from django.db import migrations
from django.db import models


def migrate_event_schedule(apps, schema_editor):
    Event = apps.get_model("gift_manager", "Event")

    for event in Event.objects.all().iterator():
        if event.absolute_date:
            event.schedule_type = "one_time"
            event.date = event.absolute_date
            event.recurrence = None
        elif event.usual_date:
            event.date = event.usual_date
            if event.recurrence:
                event.schedule_type = "recurring"
            else:
                event.schedule_type = "one_time"
                event.recurrence = None
        else:
            event.schedule_type = "unscheduled"
            event.date = None
            event.recurrence = None

        event.save(update_fields=["schedule_type", "date", "recurrence"])


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0026_relation_exactly_one_recipient_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="schedule_type",
            field=models.CharField(
                choices=[
                    ("unscheduled", "No date yet"),
                    ("one_time", "One-time"),
                    ("recurring", "Repeating"),
                ],
                default="unscheduled",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(migrate_event_schedule, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="event",
            name="absolute_date",
        ),
        migrations.RemoveField(
            model_name="event",
            name="usual_date",
        ),
    ]
