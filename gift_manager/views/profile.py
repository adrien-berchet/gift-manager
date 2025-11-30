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

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import Invitation
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Profile
from gift_manager.models import Relation


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "gift_manager/profile_detail.html"
    context_object_name = "profile"

    def get_object(self):
        return Profile.objects.get(user=self.request.user)


class SendInvitationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, "gift_manager/send_invitation.html")

    def post(self, request, *args, **kwargs):
        recipient_email = request.POST.get("recipient_email")
        invitation = Invitation.objects.create(sender=request.user, recipient_email=recipient_email)
        invitation_link = request.build_absolute_uri(
            reverse("gift_manager:accept_invitation", args=[invitation.token])
        )
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


class RemoveFriendView(LoginRequiredMixin, View):
    def post(self, request, friend_id, *args, **kwargs):  # noqa: C901
        with transaction.atomic():
            friend_profile = get_object_or_404(Profile, pk=friend_id)
            friend = friend_profile.user
            user_profile = get_object_or_404(Profile, user=request.user)

            # Remove the friend relationship (symmetric)
            if friend_profile in user_profile.friends.all():
                user_profile.friends.remove(friend_profile)

            # Symmetric removal
            if user_profile in friend_profile.friends.all():
                friend_profile.friends.remove(user_profile)

            # Remove all shared objects between the two users
            # Using prefetch_related to avoid N+1 queries

            # Persons
            persons_shared = Person.objects.filter(shared_with=request.user).prefetch_related(
                "shared_with"
            )
            for person in persons_shared:
                if friend in person.shared_with.all():
                    person.shared_with.remove(friend)

            # PersonGroups
            person_groups_shared = PersonGroup.objects.filter(
                shared_with=request.user
            ).prefetch_related("shared_with")
            for group in person_groups_shared:
                if friend in group.shared_with.all():
                    group.shared_with.remove(friend)

            # Gifts
            gifts_shared = Gift.objects.filter(shared_with=request.user).prefetch_related(
                "shared_with"
            )
            for gift in gifts_shared:
                if friend in gift.shared_with.all():
                    gift.shared_with.remove(friend)

            # Events
            events_shared = Event.objects.filter(shared_with=request.user).prefetch_related(
                "shared_with"
            )
            for event in events_shared:
                if friend in event.shared_with.all():
                    event.shared_with.remove(friend)

            # Relations
            relations_shared = Relation.objects.filter(shared_with=request.user).prefetch_related(
                "shared_with"
            )
            for relation in relations_shared:
                if friend in relation.shared_with.all():
                    relation.shared_with.remove(friend)

        return redirect("gift_manager:profile_detail")

    def get(self, *args, **kwargs):
        # Redirect to the profile detail page
        return redirect("gift_manager:profile_detail")
