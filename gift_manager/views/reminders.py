"""Reminder views: preferences, digest unsubscribe link and the private calendar feed."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe
from django.views.generic import View

from gift_manager.calendar_feed import CONTENT_TYPE
from gift_manager.calendar_feed import build_calendar
from gift_manager.forms import ReminderPreferencesForm
from gift_manager.models import Profile
from gift_manager.reminders import read_unsubscribe_token


class UpdateReminderPreferencesView(LoginRequiredMixin, View):
    """Save the language and reminder email preferences of the current user."""

    def post(self, request, *args, **kwargs):
        form = ReminderPreferencesForm(request.POST, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, gettext("Reminder preferences saved successfully."))
        else:
            messages.error(request, gettext("Choose valid reminder preferences."))
        return redirect("gift_manager:profile_detail")


class RegenerateCalendarFeedView(LoginRequiredMixin, View):
    """Enable the calendar feed, or replace its secret (the old URL stops working)."""

    def post(self, request, *args, **kwargs):
        request.user.profile.regenerate_calendar_token()
        messages.success(request, gettext("Your calendar feed link has been updated."))
        return redirect("gift_manager:profile_detail")


class DisableCalendarFeedView(LoginRequiredMixin, View):
    """Disable the calendar feed."""

    def post(self, request, *args, **kwargs):
        request.user.profile.clear_calendar_token()
        messages.success(request, gettext("Your calendar feed has been disabled."))
        return redirect("gift_manager:profile_detail")


@method_decorator(csrf_exempt, name="dispatch")
class DigestUnsubscribeView(View):
    """Turn the digest email off from the signed link of an email.

    GET only asks for confirmation (mail scanners follow links); POST changes the setting.
    The POST is exempt from CSRF so a mail client can do an RFC 8058 one-click unsubscribe;
    the signed token is the only credential and only allows turning the emails off.
    """

    template_name = "gift_manager/digest_unsubscribe.html"

    def _get_profile(self, token) -> Profile | None:
        user_id = read_unsubscribe_token(token)
        if user_id is None:
            return None
        return Profile.objects.filter(user_id=user_id).first()

    def get(self, request, token, *args, **kwargs):
        profile = self._get_profile(token)
        return render(
            request,
            self.template_name,
            {"valid": profile is not None, "done": False},
            status=200 if profile else 400,
        )

    def post(self, request, token, *args, **kwargs):
        profile = self._get_profile(token)
        if profile is None:
            return render(request, self.template_name, {"valid": False, "done": False}, status=400)
        profile.digest_frequency = Profile.DIGEST_OFF
        profile.save(update_fields=["digest_frequency"])
        return render(request, self.template_name, {"valid": True, "done": True})


@require_safe
def calendar_feed(request, token):  # noqa: ARG001
    """Serve the iCalendar feed of the user who owns this secret token."""
    profile = get_object_or_404(
        Profile.objects.select_related("user"), calendar_token=token, user__is_active=True
    )
    if not profile.calendar_token:  # defensive: a null token must never match
        raise Http404
    response = HttpResponse(build_calendar(profile.user), content_type=CONTENT_TYPE)
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Content-Disposition"] = 'inline; filename="gift-manager.ics"'
    return response
