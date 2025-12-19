"""Custom allauth adapters for handling email encoding."""

from allauth.account.adapter import DefaultAccountAdapter

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email


class EncodedEmailAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter that encodes email addresses for privacy."""

    def save_user(self, request, user, form, commit=True):
        """Save user with encoded email address."""
        # Get the plain email from the form
        plain_email = form.cleaned_data.get("email")

        # Call the parent save_user to set all fields
        user = super().save_user(request, user, form, commit=False)

        # Encode the email before saving
        if plain_email:
            user.email = encode_email(plain_email)

        if commit:
            user.save()
        return user

    def confirm_email(self, request, email_address):
        """Confirm email address, handling encoded emails."""
        super().confirm_email(request, email_address)

    def send_mail(self, template_prefix, email, context):
        """Send mail using decoded email address."""
        # Decode the email for sending
        decoded_email = decode_email(email) if email else email
        super().send_mail(template_prefix, decoded_email, context)

    def get_email_confirmation_url(self, request, emailconfirmation):
        """Get email confirmation URL."""
        return super().get_email_confirmation_url(request, emailconfirmation)
