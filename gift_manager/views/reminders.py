"""Reminder views: preferences, digest unsubscribe link and the private calendar feed."""

import hmac
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_safe
from django.views.generic import View

from gift_manager.calendar_feed import CONTENT_TYPE
from gift_manager.calendar_feed import build_calendar
from gift_manager.digest_sending import send_digests
from gift_manager.forms import ReminderPreferencesForm
from gift_manager.mixins.notifications import settings_form_response
from gift_manager.models import Profile
from gift_manager.reminders import read_unsubscribe_token

logger = logging.getLogger(__name__)


class UpdateReminderPreferencesView(LoginRequiredMixin, View):
    """Save the language and reminder email preferences of the current user."""

    def post(self, request, *args, **kwargs):
        form = ReminderPreferencesForm(request.POST, instance=request.user.profile)
        ok = form.is_valid()
        if ok:
            form.save()
        return settings_form_response(
            request,
            gettext("Reminder preferences saved successfully.")
            if ok
            else gettext("Choose valid reminder preferences."),
            redirect_to="gift_manager:profile_detail",
            ok=ok,
        )


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


def _has_valid_cron_secret(request) -> bool:
    """Return whether the request carries ``Authorization: Bearer <CRON_SECRET>``."""
    expected = settings.CRON_SECRET
    scheme, _, provided = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


@require_GET
def cron_send_gift_digest(request):
    """Send the due reminder digests; called by Vercel Cron, which cannot run commands.

    The endpoint is disabled (404) until a ``CRON_SECRET`` of a sensible length is configured,
    and answers 401 to any request without it. Vercel does not follow redirects, so the URL lives
    outside the language prefix. The response only holds counts, and is a 500 when a digest
    failed or the site is not configured, so the failure shows in the Vercel logs. Running it
    again is safe: users who already got today's digest are skipped.
    """
    if len(settings.CRON_SECRET) < settings.MIN_CRON_SECRET_LENGTH:
        raise Http404
    if not _has_valid_cron_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        run = send_digests()
    except ImproperlyConfigured:
        logger.exception("The gift digest cron endpoint is not configured")
        return JsonResponse({"error": "SITE_BASE_URL is not configured"}, status=500)

    response = JsonResponse(
        {
            "sent": run.sent,
            "skipped": run.skipped,
            "already_sent": run.already_sent,
            "failed": run.failed,
        },
        status=500 if run.failed else 200,
    )
    response["Cache-Control"] = "no-store"
    return response
