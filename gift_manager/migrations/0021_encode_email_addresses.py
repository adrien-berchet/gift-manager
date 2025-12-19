"""Migration to encode email addresses for privacy."""

import base64

from django.db import migrations
from django.db import models


def encode_email(email):
    """Encode an email address using base64."""
    if email is None or email == "":
        return email
    return base64.b64encode(email.encode("utf-8")).decode("utf-8")


def decode_email(encoded_email):
    """Decode a base64-encoded email address."""
    if encoded_email is None or encoded_email == "":
        return encoded_email
    try:
        return base64.b64decode(encoded_email.encode("utf-8")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return encoded_email


def encode_existing_emails(apps, schema_editor):
    """Encode all existing email addresses in the database."""
    Person = apps.get_model("gift_manager", "Person")
    Invitation = apps.get_model("gift_manager", "Invitation")
    User = apps.get_model("auth", "User")

    # Encode Person email addresses
    for person in Person.objects.all():
        if person.email_address:
            person.email_address = encode_email(person.email_address)
            person.save(update_fields=["email_address"])

    # Encode Invitation recipient emails
    for invitation in Invitation.objects.all():
        if invitation.recipient_email:
            invitation.recipient_email = encode_email(invitation.recipient_email)
            invitation.save(update_fields=["recipient_email"])

    # Encode User emails
    for user in User.objects.all():
        if user.email:
            user.email = encode_email(user.email)
            user.save(update_fields=["email"])


def decode_existing_emails(apps, schema_editor):
    """Decode all existing email addresses in the database (for reverse migration)."""
    Person = apps.get_model("gift_manager", "Person")
    Invitation = apps.get_model("gift_manager", "Invitation")
    User = apps.get_model("auth", "User")

    # Decode Person email addresses
    for person in Person.objects.all():
        if person.email_address:
            person.email_address = decode_email(person.email_address)
            person.save(update_fields=["email_address"])

    # Decode Invitation recipient emails
    for invitation in Invitation.objects.all():
        if invitation.recipient_email:
            invitation.recipient_email = decode_email(invitation.recipient_email)
            invitation.save(update_fields=["recipient_email"])

    # Decode User emails
    for user in User.objects.all():
        if user.email:
            user.email = decode_email(user.email)
            user.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [
        ("gift_manager", "0020_add_inherit_permissions_to_persongr"),
    ]

    operations = [
        # Change Person.email_address from EmailField to TextField
        migrations.AlterField(
            model_name="person",
            name="email_address",
            field=models.TextField(blank=True, null=True),
        ),
        # Change Invitation.recipient_email from EmailField to TextField
        migrations.AlterField(
            model_name="invitation",
            name="recipient_email",
            field=models.TextField(),
        ),
        # Encode existing email addresses
        migrations.RunPython(encode_existing_emails, decode_existing_emails),
    ]
