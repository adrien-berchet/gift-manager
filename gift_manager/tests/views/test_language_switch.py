"""Tests for language switcher in navigation bar and internationalization settings."""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
def test_navbar_form_rendered_with_next_and_accessibility():
    """Navbar language switcher form contains next input with current path and accessible labels."""
    user = UserFactory()
    client = Client()
    client.force_login(user)

    response = client.get("/en/profile/")
    assert response.status_code == 200
    content = response.content.decode()

    # Form target and next input
    assert f'action="{reverse("set_language")}"' in content
    assert '<input type="hidden" name="next" value="/en/profile/">' in content

    # Accessible labels
    assert 'id="language-select"' in content
    assert 'aria-label="Select Language"' in content
    assert '<label for="language-select" class="visually-hidden">Select Language</label>' in content

    # Safe submit execution
    assert "this.form.requestSubmit()" in content


@pytest.mark.django_db
def test_navbar_language_switch_from_en_to_fr_with_next():
    """Switching language from English to French redirects to translated URL and sets cookie."""
    client = Client()
    set_lang_url = reverse("set_language")

    response = client.post(
        set_lang_url,
        {"language": "fr", "next": "/en/gifts/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/fr/gifts/"
    assert client.cookies.get(settings.LANGUAGE_COOKIE_NAME).value == "fr"


@pytest.mark.django_db
def test_navbar_language_switch_from_fr_to_en_with_next():
    """Switching language from French to English redirects to translated URL and sets cookie."""
    client = Client()
    client.cookies.load({settings.LANGUAGE_COOKIE_NAME: "fr"})
    set_lang_url = reverse("set_language")

    response = client.post(
        set_lang_url,
        {"language": "en", "next": "/fr/recipients/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/en/recipients/"
    assert client.cookies.get(settings.LANGUAGE_COOKIE_NAME).value == "en"


@pytest.mark.django_db
def test_navbar_language_switch_preserves_query_string():
    """Switching language preserves query parameters in next URL."""
    client = Client()
    set_lang_url = reverse("set_language")

    response = client.post(
        set_lang_url,
        {"language": "fr", "next": "/en/gifts/?page=2&sort=name"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/fr/gifts/?page=2&sort=name"
    assert client.cookies.get(settings.LANGUAGE_COOKIE_NAME).value == "fr"


@pytest.mark.django_db
def test_navbar_language_switch_on_non_prefixed_account_url():
    """Switching language on accounts URL (without i18n prefix) redirects back and sets cookie."""
    client = Client()
    set_lang_url = reverse("set_language")

    response = client.post(
        set_lang_url,
        {"language": "fr", "next": "/accounts/login/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/accounts/login/"
    assert client.cookies.get(settings.LANGUAGE_COOKIE_NAME).value == "fr"


def test_locale_middleware_ordered_before_common_middleware():
    """LocaleMiddleware must run after SessionMiddleware and before CommonMiddleware."""
    middleware = list(settings.MIDDLEWARE)
    session_idx = middleware.index("django.contrib.sessions.middleware.SessionMiddleware")
    locale_idx = middleware.index("django.middleware.locale.LocaleMiddleware")
    common_idx = middleware.index("django.middleware.common.CommonMiddleware")

    assert session_idx < locale_idx < common_idx
