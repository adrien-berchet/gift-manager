"""Invitation handling: token resolution, verification, rate limiting, and acceptance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import EmailField
from django.utils import timezone

from gift_manager.email_encoding import decode_email
from gift_manager.models import Invitation
from gift_manager.models import Profile

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.contrib.auth.models import User

INVITATION_TOKEN_SESSION_KEY = "pending_invitation_token"  # noqa: S105


def normalize_email(email: str | None) -> str:
    """Validate and normalize an invitation email for comparison."""
    return EmailField().clean(email or "").casefold()


_normalize_invitation_email = normalize_email


def _decoded_user_email(user) -> str:
    """Return the app-level user email in plain text."""
    return decode_email(user.email or "")


def accounts_owning_email(users: Iterable[User], email: str) -> list[User]:
    """Return users among ``users`` who own ``email`` (verified or legacy)."""
    user_list = [u for u in users if u and u.pk]
    if not user_list:
        return []

    try:
        clean_email = normalize_email(email)
    except ValidationError:
        return []

    if not clean_email:
        return []

    user_ids = [u.pk for u in user_list]
    rows = EmailAddress.objects.filter(user_id__in=user_ids).values_list(
        "user_id", "email", "verified"
    )

    verified_emails_by_user: dict[int, set[str]] = {uid: set() for uid in user_ids}
    user_has_any_rows: set[int] = set()

    for uid, row_email, verified in rows:
        user_has_any_rows.add(uid)
        if verified and row_email:
            verified_emails_by_user[uid].add(row_email.casefold())

    matches: list[User] = []
    for user in user_list:
        if clean_email in verified_emails_by_user.get(user.pk, set()):
            matches.append(user)
        elif (
            user.pk not in user_has_any_rows and _decoded_user_email(user).casefold() == clean_email
        ):
            # Legacy programmatic accounts in tests/data may not have allauth EmailAddress rows.
            matches.append(user)

    return matches


def user_has_email(user, email: str) -> bool:
    """Return whether the user account owns the normalized invitation email."""
    normalized_email = email.casefold()
    account_emails = EmailAddress.objects.filter(user=user).values_list("email", flat=True)
    if any(stored_email.casefold() == normalized_email for stored_email in account_emails):
        return True
    return _decoded_user_email(user).casefold() == normalized_email


def _user_can_accept_invitation(user, email: str) -> bool:
    """Return whether the user has proven control of the invited email."""
    return bool(accounts_owning_email([user], email))


def user_is_friends_with_email(user, email: str) -> bool:
    """Return whether the account is already friends with an owner of this email."""
    friend_profiles = user.profile.friends.select_related("user").prefetch_related(
        "user__emailaddress_set"
    )
    return any(user_has_email(friend_profile.user, email) for friend_profile in friend_profiles)


def pending_invitation_for(sender, recipient_email: str) -> Invitation | None:
    """Find an unaccepted, unexpired invitation for this sender/email pair."""
    pending_invitations = Invitation.objects.filter(sender=sender, accepted=False).order_by(
        "-created_at"
    )
    for invitation in pending_invitations:
        if invitation.is_expired():
            continue
        try:
            invitation_email = _normalize_invitation_email(invitation.email)
        except ValidationError:
            continue
        if invitation_email == recipient_email:
            return invitation
    return None


def invitation_send_limit_exceeded(user) -> bool:
    """Return whether the user has exceeded the invitation email send limit."""
    limit = getattr(settings, "INVITATION_SEND_LIMIT", 10)
    if limit is None or limit <= 0:
        return False

    window_seconds = getattr(settings, "INVITATION_SEND_WINDOW_SECONDS", 3600)
    cache_key = f"gift_manager:invitation-send:{user.pk}"
    if cache.add(cache_key, 1, window_seconds):
        return False

    try:
        send_count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, window_seconds)
        return False
    return send_count > limit


def get_pending_invitation(token) -> Invitation | None:
    """Return an active invitation for a token, or None when it cannot be accepted."""
    if not token:
        return None

    try:
        invitation = Invitation.objects.select_related("sender").get(token=token, accepted=False)
    except (Invitation.DoesNotExist, ValidationError, ValueError):
        return None
    if invitation.is_expired():
        return None
    return invitation


def store_pending_invitation_token(request, token) -> None:
    """Persist an invitation token across signup and email confirmation."""
    request.session[INVITATION_TOKEN_SESSION_KEY] = str(token)


def get_request_pending_invitation(request) -> Invitation | None:
    """Resolve a pending invitation from query/form data or the signup session."""
    query_params = getattr(request, "GET", {})
    form_data = getattr(request, "POST", {})
    token = (
        query_params.get("invitation_token")
        or form_data.get("invitation_token")
        or request.session.get(INVITATION_TOKEN_SESSION_KEY)
    )
    invitation = get_pending_invitation(token)
    if invitation is not None:
        store_pending_invitation_token(request, invitation.token)
    elif token and request.session.get(INVITATION_TOKEN_SESSION_KEY) == str(token):
        request.session.pop(INVITATION_TOKEN_SESSION_KEY, None)
    return invitation


def invitation_matches_email(invitation: Invitation, email: str | None) -> bool:
    """Return whether a submitted/confirmed email matches the invitation recipient."""
    try:
        return _normalize_invitation_email(invitation.email) == _normalize_invitation_email(email)
    except ValidationError:
        return False


def accept_invitation_for_user(invitation: Invitation, user) -> bool:
    """Accept an invitation for a user after recipient ownership has been proven."""
    try:
        recipient_email = _normalize_invitation_email(invitation.email)
    except ValidationError:
        return False
    if not _user_can_accept_invitation(user, recipient_email):
        return False

    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if invitation.accepted or invitation.is_expired():
            return False

        invitation.accepted = True
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted", "accepted_at"])
        user_profile, _ = Profile.objects.get_or_create(user=user)
        sender_profile, _ = Profile.objects.get_or_create(user=invitation.sender)
        user_profile.friends.add(sender_profile)
        sender_profile.friends.add(user_profile)
    return True


def accept_pending_invitation_for_verified_email(request, email_address) -> bool:
    """Accept the session invitation when allauth verifies the invited email."""
    invitation = get_request_pending_invitation(request)
    if invitation is None:
        return False

    if not invitation_matches_email(invitation, email_address.email):
        return False

    if accept_invitation_for_user(invitation, email_address.user):
        request.session.pop(INVITATION_TOKEN_SESSION_KEY, None)
        return True
    return False
