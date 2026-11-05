import django.db.models.deletion
from django.conf import settings
from django.db import migrations
from django.db import models


def backfill_owner_permissions(apps, schema_editor):
    Person = apps.get_model("gift_manager", "Person")
    PersonPermission = apps.get_model("gift_manager", "PersonPermission")

    for pk, account_id in Person.objects.filter(account__isnull=False).values_list(
        "pk", "account_id"
    ):
        PersonPermission.objects.update_or_create(
            person_id=pk,
            user_id=account_id,
            defaults={"permission_type": 30},
        )


def clear_accounts(apps, schema_editor):
    Person = apps.get_model("gift_manager", "Person")
    Person.objects.filter(account__isnull=False).update(account=None)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("gift_manager", "0040_giftsuggestion_dismiss_comment_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="person",
            old_name="user_link",
            new_name="account",
        ),
        migrations.AlterField(
            model_name="person",
            name="account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_persons",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="link_suggestion_dismissed_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="invitation",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invitations",
                to="gift_manager.person",
            ),
        ),
        migrations.RunPython(
            backfill_owner_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            clear_accounts,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
