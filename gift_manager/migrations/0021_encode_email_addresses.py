"""Migration to encrypt email addresses for privacy using Fernet encryption."""

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.db import migrations
from django.db import models


def _get_cipher() -> Fernet:
    """Get the Fernet cipher using the configured encryption key."""
    key = getattr(settings, "EMAIL_ENCRYPTION_KEY", None)
    if not key:
        msg = (
            "EMAIL_ENCRYPTION_KEY must be configured in Django settings before running this "
            "migration."
        )
        raise ValueError(msg)
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_email(email) -> str | None:
    """Encrypt an email address using Fernet encryption."""
    if email is None or email == "":
        return email
    cipher = _get_cipher()
    encrypted = cipher.encrypt(email.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_email(encrypted_email) -> str | None:
    """Decrypt an encrypted email address."""
    if encrypted_email is None or encrypted_email == "":
        return encrypted_email
    try:
        cipher = _get_cipher()
        decrypted = cipher.decrypt(encrypted_email.encode("utf-8"))
        return decrypted.decode("utf-8")
    except (InvalidToken, ValueError):
        return encrypted_email


def encrypt_existing_emails(apps, schema_editor) -> None:  # noqa: ARG001
    """Encrypt all existing email addresses in the database."""
    Person = apps.get_model("gift_manager", "Person")
    Invitation = apps.get_model("gift_manager", "Invitation")
    User = apps.get_model("auth", "User")

    # Encrypt Person email addresses
    for person in Person.objects.all():
        if person.email_address:
            person.email_address = encrypt_email(person.email_address)
            person.save(update_fields=["email_address"])

    # Encrypt Invitation recipient emails
    for invitation in Invitation.objects.all():
        if invitation.recipient_email:
            invitation.recipient_email = encrypt_email(invitation.recipient_email)
            invitation.save(update_fields=["recipient_email"])

    # Encrypt User emails
    for user in User.objects.all():
        if user.email:
            user.email = encrypt_email(user.email)
            user.save(update_fields=["email"])


def decrypt_existing_emails(apps, schema_editor) -> None:  # noqa: ARG001
    """Decrypt all existing email addresses in the database (for reverse migration)."""
    Person = apps.get_model("gift_manager", "Person")
    Invitation = apps.get_model("gift_manager", "Invitation")
    User = apps.get_model("auth", "User")

    # Decrypt Person email addresses
    for person in Person.objects.all():
        if person.email_address:
            person.email_address = decrypt_email(person.email_address)
            person.save(update_fields=["email_address"])

    # Decrypt Invitation recipient emails
    for invitation in Invitation.objects.all():
        if invitation.recipient_email:
            invitation.recipient_email = decrypt_email(invitation.recipient_email)
            invitation.save(update_fields=["recipient_email"])

    # Decrypt User emails
    for user in User.objects.all():
        if user.email:
            user.email = decrypt_email(user.email)
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
        # Encrypt existing email addresses
        migrations.RunPython(encrypt_existing_emails, decrypt_existing_emails),
    ]
