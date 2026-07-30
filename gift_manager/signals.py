"""Signal handlers for account and invitation lifecycle events."""

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.dispatch import receiver

from gift_manager.adapters import ensure_user_email_encoded
from gift_manager.views.profile import accept_pending_invitation_for_verified_email


@receiver(email_confirmed, sender=EmailAddress)
def accept_invitation_after_email_confirmation(sender, request, email_address, **kwargs):  # noqa: ARG001
    """Accept a pending invitation only when allauth verifies the invited email."""
    if request is not None:
        accept_pending_invitation_for_verified_email(request, email_address)

    user = email_address.user
    ensure_user_email_encoded(user)
