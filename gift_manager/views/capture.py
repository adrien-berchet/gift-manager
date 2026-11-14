"""Landing page of the browser bookmarklet."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import View

from gift_manager.capture import clean_capture
from gift_manager.capture import target_urls


class CaptureView(LoginRequiredMixin, View):
    """Show the product captured by the bookmarklet and offer where to save it.

    Reading the page changes nothing: the user still fills and submits the chosen form.
    """

    template_name = "gift_manager/capture.html"

    def get(self, request, *args, **kwargs):
        capture = clean_capture(request.GET, request.user.profile.currency)
        response = render(
            request,
            self.template_name,
            {"capture": capture, "targets": target_urls(capture)},
        )
        # The query string holds the page the user was browsing: keep it on this site
        response["Referrer-Policy"] = "same-origin"
        return response
