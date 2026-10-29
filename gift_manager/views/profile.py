"""Profile-related views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import DetailView
from django.views.generic import TemplateView
from django.views.generic import View

from gift_manager import account_links
from gift_manager.account_links import remove_links_after_unfriending
from gift_manager.email_encoding import encode_email
from gift_manager.forms import InvitationForm
from gift_manager.forms import ReminderPreferencesForm
from gift_manager.invitations import accept_invitation_for_user
from gift_manager.invitations import get_pending_invitation
from gift_manager.invitations import invitation_send_limit_exceeded
from gift_manager.invitations import pending_invitation_for
from gift_manager.invitations import store_pending_invitation_token
from gift_manager.invitations import user_has_email
from gift_manager.invitations import user_is_friends_with_email
from gift_manager.mixins.notifications import settings_form_response
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
        return Profile.objects.prefetch_related("friends__user").get(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = context["profile"]
        context["reminder_form"] = ReminderPreferencesForm(instance=profile)
        if profile.calendar_token:
            context["calendar_feed_url"] = self.request.build_absolute_uri(
                reverse("gift_manager:calendar_feed", kwargs={"token": profile.calendar_token})
            )
        context["friend_link_rows"] = account_links.friend_link_rows(self.request.user)
        context["own_records"] = account_links.own_records(self.request.user)
        return context


class SendInvitationView(LoginRequiredMixin, View):
    template_name = "gift_manager/send_invitation.html"

    def _render(self, request, form, status=200) -> HttpResponse:
        pending = [
            invitation
            for invitation in Invitation.objects.filter(
                sender=request.user, accepted=False
            ).order_by("-created_at")
            if not invitation.is_expired()
        ]
        return render(
            request,
            self.template_name,
            {"form": form, "pending_invitations": pending},
            status=status,
        )

    def get(self, request, *args, **kwargs):
        return self._render(request, InvitationForm())

    def post(self, request, *args, **kwargs):
        form = InvitationForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, status=400)
        recipient_email = form.cleaned_data["recipient_email"]

        if user_has_email(request.user, recipient_email):
            form.add_error("recipient_email", gettext("You cannot send an invitation to yourself."))
            return self._render(request, form, status=400)

        if user_is_friends_with_email(request.user, recipient_email):
            form.add_error("recipient_email", gettext("You are already friends with this user."))
            return self._render(request, form, status=400)

        if pending_invitation_for(request.user, recipient_email) is not None:
            form.add_error(
                "recipient_email",
                gettext(
                    "An invitation to this address is already pending. "
                    "Cancel it below, then send a new one."
                ),
            )
            return self._render(request, form, status=400)

        if invitation_send_limit_exceeded(request.user):
            form.add_error(
                None,
                gettext("You have sent too many invitations recently. Please try again later."),
            )
            return self._render(request, form, status=429)

        # Store the email encoded for privacy
        invitation = Invitation.objects.create(
            sender=request.user, recipient_email=encode_email(recipient_email)
        )
        invitation_link = request.build_absolute_uri(
            reverse("gift_manager:accept_invitation", args=[invitation.token])
        )
        # Use the plain email for sending
        invitation_prompt = gettext("To accept the invitation, click on the following link:")
        send_mail(
            subject=gettext("Join my friends on Gift Manager"),
            message=f"{invitation_prompt} {invitation_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
        )
        return redirect("gift_manager:send_invitation")


class CancelInvitationView(LoginRequiredMixin, View):
    """Let a sender withdraw one of their own pending invitations."""

    def post(self, request, invitation_id, *args, **kwargs):
        invitation = get_object_or_404(
            Invitation, pk=invitation_id, sender=request.user, accepted=False
        )
        invitation.delete()
        messages.success(request, gettext("Invitation cancelled."))
        return redirect("gift_manager:send_invitation")


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
        return settings_form_response(
            request,
            gettext("Display preferences saved successfully."),
            redirect_to="gift_manager:profile_detail",
        )


class ConfirmRemoveFriendView(LoginRequiredMixin, View):
    """Non-JavaScript fallback page asking for confirmation before removing a friend."""

    def get(self, request, friend_id, *args, **kwargs):
        friend_profile = get_object_or_404(
            Profile.objects.select_related("user"),
            pk=friend_id,
            friends=request.user.profile,
        )
        return render(
            request,
            "gift_manager/confirm_remove_friend.html",
            {"friend": friend_profile},
        )


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
            remove_links_after_unfriending(request.user, friend)

        messages.success(
            request,
            gettext("{username} was removed from your friends.").format(username=friend.username),
        )
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
