"""Profile-related views."""

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.forms import EmailField
from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.views.generic import DetailView
from django.views.generic import TemplateView
from django.views.generic import View

from gift_manager.email_encoding import decode_email
from gift_manager.email_encoding import encode_email
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import GiftTag
from gift_manager.models import Invitation
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Profile
from gift_manager.models import Relation
from gift_manager.services import PermissionService

INVITATION_TOKEN_SESSION_KEY = "pending_invitation_token"  # noqa: S105


def _normalize_invitation_email(email: str | None) -> str:
    """Validate and normalize an invitation email for comparison."""
    return EmailField().clean(email or "").casefold()


def _decoded_user_email(user) -> str:
    """Return the app-level user email in plain text."""
    return decode_email(user.email or "")


def _user_has_email(user, email: str) -> bool:
    """Return whether the user account owns the normalized invitation email."""
    normalized_email = email.casefold()
    account_emails = EmailAddress.objects.filter(user=user).values_list("email", flat=True)
    if any(stored_email.casefold() == normalized_email for stored_email in account_emails):
        return True
    return _decoded_user_email(user).casefold() == normalized_email


def _user_can_accept_invitation(user, email: str) -> bool:
    """Return whether the user has proven control of the invited email."""
    normalized_email = email.casefold()
    verified_account_emails = EmailAddress.objects.filter(user=user, verified=True).values_list(
        "email", flat=True
    )
    if any(stored_email.casefold() == normalized_email for stored_email in verified_account_emails):
        return True

    # Legacy programmatic accounts in tests/data may not have allauth EmailAddress rows.
    has_account_email_records = EmailAddress.objects.filter(user=user).exists()
    return (
        not has_account_email_records and _decoded_user_email(user).casefold() == normalized_email
    )


def _user_is_friends_with_email(user, email: str) -> bool:
    """Return whether the account is already friends with an owner of this email."""
    friend_profiles = user.profile.friends.select_related("user").prefetch_related(
        "user__emailaddress_set"
    )
    return any(_user_has_email(friend_profile.user, email) for friend_profile in friend_profiles)


def _pending_invitation_for(sender, recipient_email: str) -> Invitation | None:
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


def _invitation_send_limit_exceeded(user) -> bool:
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


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "gift_manager/profile_detail.html"
    context_object_name = "profile"

    def get_object(self, *args):
        return Profile.objects.get(user=self.request.user)


class SendInvitationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, "gift_manager/send_invitation.html")

    def post(self, request, *args, **kwargs):
        try:
            recipient_email = _normalize_invitation_email(request.POST.get("recipient_email"))
        except ValidationError:
            messages.error(request, gettext("Enter a valid email address."))
            return render(request, "gift_manager/send_invitation.html", status=400)

        if _user_has_email(request.user, recipient_email):
            messages.error(request, gettext("You cannot send an invitation to yourself."))
            return redirect("gift_manager:profile_detail")

        if _user_is_friends_with_email(request.user, recipient_email):
            messages.error(request, gettext("You are already friends with this user."))
            return redirect("gift_manager:profile_detail")

        if _invitation_send_limit_exceeded(request.user):
            messages.error(
                request,
                gettext("You have sent too many invitations recently. Please try again later."),
            )
            return render(request, "gift_manager/send_invitation.html", status=429)

        invitation = _pending_invitation_for(request.user, recipient_email)
        if invitation is None:
            # Store the email encoded for privacy
            encoded_email = encode_email(recipient_email)
            invitation = Invitation.objects.create(
                sender=request.user, recipient_email=encoded_email
            )
        invitation_link = request.build_absolute_uri(
            reverse("gift_manager:accept_invitation", args=[invitation.token])
        )
        # Use the plain email for sending
        send_mail(
            subject=gettext("Join my friends on Gift Manager"),
            message=(
                f"{gettext('To accept the invitation, click on the following link:')} "
                f"{invitation_link}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
        )
        return redirect("gift_manager:profile_detail")


class AcceptInvitationView(View):
    def get(self, request, *args, **kwargs):
        token = self.kwargs.get("token")
        invitation = get_pending_invitation(token)
        if invitation is None:
            return redirect("gift_manager:invitation_expired")

        # If the user is already logged in, establish the friendship relationship
        if request.user.is_authenticated:
            if not accept_invitation_for_user(invitation, request.user):
                messages.error(
                    request,
                    gettext("This invitation can only be accepted by the invited email address."),
                )
                return redirect("gift_manager:profile_detail")
            messages.success(
                request, gettext("You are now friend with {}").format(invitation.sender.username)
            )
            return redirect("gift_manager:profile_detail")
        # Otherwise, redirect to the registration with the token
        # (to be handled in the registration process)
        store_pending_invitation_token(request, token)
        return redirect(f"{reverse('account_signup')}?invitation_token={token}")


class InvitationExpiredView(TemplateView):
    """View to display the expired invitation page."""

    template_name = "gift_manager/invitation_expired.html"


class UpdateViewPreferencesView(LoginRequiredMixin, View):
    """View to update user view preferences."""

    def post(self, request, *args, **kwargs):
        profile = request.user.profile
        default_view_desktop = request.POST.get("default_view_desktop", "list")
        default_view_mobile = request.POST.get("default_view_mobile", "card")

        # Validate values
        valid_views = [Profile.VIEW_LIST, Profile.VIEW_CARD]
        if default_view_desktop in valid_views:
            profile.default_view_desktop = default_view_desktop
        if default_view_mobile in valid_views:
            profile.default_view_mobile = default_view_mobile

        profile.save()
        messages.success(request, gettext("Display preferences saved successfully."))
        return redirect("gift_manager:profile_detail")


class RemoveFriendView(LoginRequiredMixin, View):
    shared_object_models = (Person, PersonGroup, Gift, GiftTag, Event, Relation)

    def post(self, request, friend_id, *args, **kwargs):
        with transaction.atomic():
            friend_profile = get_object_or_404(Profile, pk=friend_id)
            friend = friend_profile.user
            user_profile = get_object_or_404(Profile, user=request.user)

            is_confirmed_friend = user_profile.friends.filter(pk=friend_profile.pk).exists()
            if not is_confirmed_friend:
                return redirect("gift_manager:profile_detail")

            # Remove the friend relationship (symmetric)
            user_profile.friends.remove(friend_profile)

            # Symmetric removal
            if friend_profile.friends.filter(pk=user_profile.pk).exists():
                friend_profile.friends.remove(user_profile)

            self._cleanup_former_friend_permissions(request.user, friend)

        return redirect("gift_manager:profile_detail")

    def _cleanup_former_friend_permissions(self, user, friend) -> None:
        """Remove cross-access between former friends without revoking owners."""
        for model in self.shared_object_models:
            for obj in self._former_friend_cleanup_candidates(model, user, friend):
                self._cleanup_former_friend_permission(user, friend, obj)

    def _former_friend_cleanup_candidates(self, model, user, friend) -> object:
        """Return objects where either former friend has a direct sharing row."""
        return model.objects.filter(shared_with__in=(user, friend)).distinct()

    def _cleanup_former_friend_permission(self, user, friend, obj) -> None:
        """Remove the non-owner side of a two-user sharing relationship."""
        user_permission = PermissionService.get_effective_permission(obj, user)
        friend_permission = PermissionService.get_effective_permission(obj, friend)

        if user_permission == PermissionLevel.OWNER and friend_permission < PermissionLevel.OWNER:
            self._delete_direct_non_owner_permission(friend, obj)
        elif friend_permission == PermissionLevel.OWNER and user_permission < PermissionLevel.OWNER:
            self._delete_direct_non_owner_permission(user, obj)

    def _delete_direct_non_owner_permission(self, user, obj) -> None:
        """Delete a direct permission row only when it is not an owner row."""
        permission = PermissionService.get_permission(obj, user)
        if PermissionLevel.NONE < permission < PermissionLevel.OWNER:
            PermissionService.delete_permission(user, obj)

    def get(self, *args, **kwargs):
        # Redirect to the profile detail page
        return redirect("gift_manager:profile_detail")
