from allauth.account.forms import LoginForm as AllAuthLoginForm
from allauth.account.views import LoginView
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.generic import View

from gift_manager.models import Event
from gift_manager.models import Gift
from gift_manager.models import Person
from gift_manager.models import PersonGroup
from gift_manager.models import Relation


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
        return render(request, self.template_name)

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
