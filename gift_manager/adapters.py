"""Custom allauth adapters for handling email encryption."""

from allauth.account.adapter import DefaultAccountAdapter

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email


class EncodedEmailAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter that encrypts email addresses for privacy."""

    def save_user(self, request, user, form, commit=True):
        """Save user with encrypted email address."""
        # Get the plain email from the form
        plain_email = form.cleaned_data.get("email")

        # Call the parent save_user to set all fields
        user = super().save_user(request, user, form, commit=False)

        # Encrypt the email before saving
        if plain_email:
            user.email = encode_email(plain_email)

        if commit:
            user.save()
        return user

    def send_mail(self, template_prefix, email, context):
        """Send mail using decrypted email address."""
        # Decrypt the email for sending
        decrypted_email = decode_email(email) if email else email
        super().send_mail(template_prefix, decrypted_email, context)
