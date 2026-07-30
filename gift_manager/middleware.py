"""Security middleware for project-specific response headers."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest
from django.http import HttpResponse


class ContentSecurityPolicyMiddleware:
    """Attach a configured Content-Security-Policy header to responses."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        return response
