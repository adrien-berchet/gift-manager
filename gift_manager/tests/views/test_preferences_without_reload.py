"""The "Save Preferences" forms of the profile page save without reloading the page."""

import json

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gift_manager.models import Profile
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}
VIEW_PREFERENCES = "gift_manager:update_view_preferences"
REMINDER_PREFERENCES = "gift_manager:update_reminder_preferences"


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def _notification(response) -> dict:
    return json.loads(response["HX-Trigger"])["showNotification"]


def test_display_preferences_post_through_htmx_is_answered_with_a_toast(client, user):
    response = client.post(
        reverse(VIEW_PREFERENCES),
        {"default_view_desktop": "card", "default_view_mobile": "list"},
        **HX,
    )

    assert response.status_code == 204  # nothing to swap: the page stays as it is
    assert "Location" not in response.headers
    assert _notification(response) == {
        "message": "Display preferences saved successfully.",
        "type": "success",
    }
    user.profile.refresh_from_db()
    assert (user.profile.default_view_desktop, user.profile.default_view_mobile) == (
        Profile.VIEW_CARD,
        Profile.VIEW_LIST,
    )
    assert list(get_messages(response.wsgi_request)) == []  # nothing queued for a later page


def test_reminder_preferences_post_through_htmx_is_answered_with_a_toast(client, user):
    response = client.post(
        reverse(REMINDER_PREFERENCES),
        {"digest_frequency": "weekly", "digest_lookahead_days": "30", "preferred_language": "fr"},
        **HX,
    )

    assert response.status_code == 204
    assert _notification(response)["type"] == "success"
    assert "Reminder preferences saved" in _notification(response)["message"]
    user.profile.refresh_from_db()
    assert user.profile.digest_frequency == Profile.DIGEST_WEEKLY
    assert list(get_messages(response.wsgi_request)) == []


def test_invalid_reminder_preferences_through_htmx_show_an_error_toast_and_save_nothing(
    client, user
):
    before = user.profile.digest_frequency

    response = client.post(
        reverse(REMINDER_PREFERENCES), {"digest_frequency": "hourly-bogus"}, **HX
    )

    assert response.status_code == 422
    assert _notification(response)["type"] == "error"
    user.profile.refresh_from_db()
    assert user.profile.digest_frequency == before
    assert list(get_messages(response.wsgi_request)) == []


@pytest.mark.parametrize("url_name", [VIEW_PREFERENCES, REMINDER_PREFERENCES])
def test_a_plain_post_still_redirects_with_a_flash_message(client, user, url_name):
    response = client.post(
        reverse(url_name),
        {"default_view_desktop": "list", "digest_frequency": "off", "digest_lookahead_days": "14"},
    )

    assert response.status_code == 302
    assert response.url == reverse("gift_manager:profile_detail")
    assert len(list(get_messages(response.wsgi_request))) == 1


@pytest.mark.parametrize(
    ("form_id", "url_name"),
    [
        ("view-preferences-form", VIEW_PREFERENCES),
        ("reminder-preferences-form", REMINDER_PREFERENCES),
    ],
)
def test_the_profile_forms_are_submitted_through_htmx_without_swapping(
    client, user, form_id, url_name
):
    content = client.get(reverse("gift_manager:profile_detail")).content.decode()

    form = content[content.index(f'id="{form_id}"') - 200 : content.index(f'id="{form_id}"') + 200]
    assert f'hx-post="{reverse(url_name)}"' in form
    assert 'hx-swap="none"' in form
    assert "data-keep-button-label" in form
