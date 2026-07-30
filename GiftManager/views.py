from allauth.account.forms import LoginForm as AllAuthLoginForm
from allauth.account.views import LoginView
from allauth.account.views import SignupView
from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.generic import View

from gift_manager.adapters import ensure_user_email_encoded
from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation
from gift_manager.views.profile import get_request_pending_invitation
from gift_manager.views.profile import invitation_matches_email
from gift_manager.views.profile import store_pending_invitation_token


class CustomAuthenticationForm(AllAuthLoginForm):
    """Custom login form which allows the connection of inactive accounts.

    We overload confirm_login_allowed to not block the connection.
    """

    def confirm_login_allowed(self, user):
        # Do not raise an exception even if the account is inactive
        pass


class CustomLoginView(LoginView):
    """Custom login view.

    If the user account is not active, redirect to the account reactivation page.
    """

    form_class = CustomAuthenticationForm

    def form_valid(self, form):
        user = form.user
        if not user.is_active:
            # Redirect to the account reactivation page
            self.request.session["inactive_user_id"] = user.pk
            return redirect("reactivate_account")
        return super().form_valid(form)


class InvitationBoundSignupView(SignupView):
    """Signup view that keeps invitations bound to their intended recipient."""

    def dispatch(self, request, *args, **kwargs):
        self.invitation = get_request_pending_invitation(request)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        invitation = getattr(self, "invitation", None)
        if invitation is not None:
            invited_email = invitation.email
            initial["email"] = invited_email
            initial["email2"] = invited_email
        return initial

    def form_valid(self, form):
        invitation = getattr(self, "invitation", None)
        if invitation is not None:
            signup_email = form.cleaned_data.get("email")
            if not invitation_matches_email(invitation, signup_email):
                form.add_error(
                    "email",
                    forms.ValidationError(
                        gettext("Use the email address this invitation was sent to.")
                    ),
                )
                return self.form_invalid(form)
            store_pending_invitation_token(self.request, invitation.token)
        response = super().form_valid(form)
        if user := getattr(self, "user", None):
            ensure_user_email_encoded(user)
        return response


class UserAccountDeactivateView(LoginRequiredMixin, View):
    """View to deactivate the user account."""

    template_name = "account/confirm_deactivate_user_account.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        user = request.user

        # Deactivate the user account
        user.is_active = False
        user.save()

        logout(request)
        messages.success(request, gettext("Your account has been successfully deactivated."))
        return redirect("gift_manager:home")


class UserAccountDeleteView(LoginRequiredMixin, View):
    """View to delete the user account."""

    template_name = "account/confirm_delete_user_account.html"

    def get(self, request, *args, **kwargs):
        # Retrieve the referer URL (previous page) or use a default URL
        referer = request.META.get("HTTP_REFERER")
        cancel_url = referer or "gift_manager:user_account"

        context = {"cancel_url": cancel_url}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        user = request.user

        # Remove objects that are only shared with this user
        for cls in [Person, PersonGroup, Gift, Event, Relation]:
            cls.objects.annotate(user_count=Count("shared_with")).filter(
                user_count=1, shared_with=user
            ).delete()

        # Logout and delete the user account
        logout(request)
        user.delete()
        messages.success(request, gettext("Your account has been successfully deleted."))
        return redirect("gift_manager:home")


class UserAccountReactivateView(View):
    """View to reactivate the user account."""

    template_name = "account/account_inactive.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        uid = request.session.get("inactive_user_id")
        if not uid:
            messages.error(request, gettext("No inactive user found for reactivation."))
            return redirect("account_login")
        try:
            user = User.objects.get(pk=uid)
        except User.DoesNotExist:
            messages.error(request, gettext("This user does not exist."))
            return redirect("account_login")

        # Activate the user account
        user.is_active = True
        user.save()
        messages.success(request, gettext("Your account has been successfully reactivated."))
        del request.session["inactive_user_id"]
        return redirect("gift_manager:profile_detail")
