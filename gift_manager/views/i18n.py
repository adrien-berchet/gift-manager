"""Internationalization and language switcher views."""

import contextlib
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from django.conf import settings
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.urls import NoReverseMatch
from django.urls import Resolver404
from django.urls import resolve
from django.urls import reverse
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.i18n import LANGUAGE_QUERY_PARAMETER


def translate_url_safe(url: str, target_lang: str) -> str:
    """Translate a URL to the target language.

    Unlike Django's default translate_url, this function inspects the URL's
    language prefix and activates that source language during resolve(). This
    prevents Resolver404 when the active thread language in a non-i18n endpoint
    (like /i18n/setlang/) does not match the source URL's language prefix.
    """
    if not url:
        return f"/{target_lang}/"

    parsed = urlsplit(url)
    path = parsed.path

    # Root paths translate directly to the target language root
    if path in ("", "/"):
        translated_path = f"/{target_lang}/"
        return urlunsplit(
            (parsed.scheme, parsed.netloc, translated_path, parsed.query, parsed.fragment)
        )

    source_lang = translation.get_language_from_path(path)
    match = None

    if source_lang:
        with translation.override(source_lang), contextlib.suppress(Resolver404):
            match = resolve(unquote(path))

    if not match:
        with contextlib.suppress(Resolver404):
            match = resolve(unquote(path))

    if not match:
        return url

    to_be_reversed = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name

    translated_path = None
    with translation.override(target_lang), contextlib.suppress(NoReverseMatch):
        translated_path = reverse(to_be_reversed, args=match.args, kwargs=match.kwargs)

    if not translated_path:
        return url
    return urlunsplit(
        (parsed.scheme, parsed.netloc, translated_path, parsed.query, parsed.fragment)
    )


@require_POST
def set_language(request: HttpRequest) -> HttpResponse:
    """Redirect to a given URL while setting the chosen language in the session and cookie.

    The URL and language code are specified using POST parameters 'language' and 'next'.
    If 'next' is not given, the referer or root URL is used.
    """
    next_url = request.POST.get("next", request.GET.get("next"))
    if (next_url or request.accepts("text/html")) and not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = request.META.get("HTTP_REFERER")
        if not url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = "/"

    response = HttpResponseRedirect(next_url) if next_url else HttpResponse(status=204)

    lang_code = request.POST.get(LANGUAGE_QUERY_PARAMETER)
    if lang_code and translation.check_for_language(lang_code):
        if next_url:
            next_trans = translate_url_safe(next_url, lang_code)
            if next_trans != next_url:
                response = HttpResponseRedirect(next_trans)

        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            lang_code,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )

    return response
