"""Notification helpers for Django views."""

import json

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect


def settings_form_response(request, message, *, redirect_to, ok=True):
    """Answer a settings form post.

    An HTMX post gets a toast and no content to swap, so the page is neither reloaded nor
    moved (204 on success, 422 for refused values). Any other post keeps the classic behaviour:
    a flash message and a redirect.
    """
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204 if ok else 422)
        response["HX-Trigger"] = json.dumps(
            {"showNotification": {"message": str(message), "type": "success" if ok else "error"}}
        )
        return response
    (messages.success if ok else messages.error)(request, message)
    return redirect(redirect_to)
