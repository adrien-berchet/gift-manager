"""Profile-related views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.views.generic import DetailView
from django.views.generic import TemplateView
from django.views.generic import View

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
        recipient_email = request.POST.get("recipient_email")
        # Store the email encoded for privacy
        encoded_email = encode_email(recipient_email)
        invitation = Invitation.objects.create(sender=request.user, recipient_email=encoded_email)
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

        try:
            invitation = get_object_or_404(Invitation, token=token, accepted=False)
        except Http404:
            # The invitation doesn't exist or has already been accepted
            return redirect("gift_manager:invitation_expired")

        # Check if the invitation has expired
        if invitation.is_expired():
            return redirect("gift_manager:invitation_expired")

        # If the user is already logged in, establish the friendship relationship
        if request.user.is_authenticated:
            invitation.accepted = True
            invitation.accepted_at = timezone.now()
            invitation.save()
            # Create or get the user's profile
            user_profile, _ = Profile.objects.get_or_create(user=request.user)
            sender_profile, _ = Profile.objects.get_or_create(user=invitation.sender)
            # Add the sender to the user's friends and vice versa
            user_profile.friends.add(sender_profile)
            sender_profile.friends.add(user_profile)
            user_profile.save()
            sender_profile.save()
            messages.success(
                request, gettext("You are now friend with {}").format(invitation.sender.username)
            )
            return redirect("gift_manager:profile_detail")
        # Otherwise, redirect to the registration with the token
        # (to be handled in the registration process)
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
            shared_objects = (
                model.objects.accessible_by(user)
                .filter(shared_with=friend)
                .prefetch_related("shared_with")
                .distinct()
            )
            for obj in shared_objects:
                self._cleanup_former_friend_permission(user, friend, obj)

    def _cleanup_former_friend_permission(self, user, friend, obj) -> None:
        """Remove the non-owner side of a two-user sharing relationship."""
        user_permission = PermissionService.get_effective_permission(obj, user)
        friend_permission = PermissionService.get_effective_permission(obj, friend)

        if user_permission == PermissionLevel.OWNER and friend_permission < PermissionLevel.OWNER:
            PermissionService.delete_permission(friend, obj)
        elif friend_permission == PermissionLevel.OWNER and user_permission < PermissionLevel.OWNER:
            PermissionService.delete_permission(user, obj)

    def get(self, *args, **kwargs):
        # Redirect to the profile detail page
        return redirect("gift_manager:profile_detail")
