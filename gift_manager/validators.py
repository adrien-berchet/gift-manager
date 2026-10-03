"""Reusable field validators."""

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def validate_http_url(value: str) -> None:
    """Reject anything that is not an absolute http(s) URL with a host."""
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
    except ValueError:
        raise ValidationError(gettext_lazy("Enter a valid http or https URL.")) from None
    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES or not hostname:
        raise ValidationError(gettext_lazy("Enter a valid http or https URL."))
