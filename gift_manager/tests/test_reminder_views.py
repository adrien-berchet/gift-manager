"""Tests for the reminder preferences, calendar feed management and unsubscribe views."""

import pytest
from django.urls import reverse

from gift_manager.models import Profile
from gift_manager.reminders import make_unsubscribe_token
from gift_manager.tests.factories import UserFactory


@pytest.mark.django_db
class TestDefaults:
    def test_digest_is_off_by_default(self, user):
        profile = user.profile

        assert profile.digest_frequency == Profile.DIGEST_OFF
        assert profile.digest_lookahead_days == 14
        assert profile.calendar_token is None

    def test_language_falls_back_to_the_site_language(self, user):
        assert user.profile.language == "en"

        user.profile.preferred_language = "fr"
        assert user.profile.language == "fr"

        user.profile.preferred_language = "xx"
        assert user.profile.language == "en"


@pytest.mark.django_db
class TestProfilePage:
    def test_page_shows_the_reminder_form_and_no_feed_link_by_default(self, authenticated_client):
        response = authenticated_client.get(reverse("gift_manager:profile_detail"))

        assert response.status_code == 200
        assert "reminder_form" in response.context
        assert "calendar_feed_url" not in response.context

    def test_page_shows_the_feed_url_once_enabled(self, authenticated_client, user):
        token = user.profile.regenerate_calendar_token()

        response = authenticated_client.get(reverse("gift_manager:profile_detail"))

        feed_path = reverse("gift_manager:calendar_feed", kwargs={"token": token})
        assert response.context["calendar_feed_url"].endswith(feed_path)
        assert token in response.content.decode()


@pytest.mark.django_db
class TestPreferences:
    url = "gift_manager:update_reminder_preferences"

    def test_user_can_opt_in(self, authenticated_client, user):
        response = authenticated_client.post(
            reverse(self.url),
            {
                "digest_frequency": "weekly",
                "digest_lookahead_days": "30",
                "preferred_language": "fr",
            },
        )

        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_WEEKLY
        assert user.profile.digest_lookahead_days == 30
        assert user.profile.preferred_language == "fr"

    def test_user_can_opt_out_again(self, authenticated_client, user):
        Profile.objects.filter(user=user).update(digest_frequency=Profile.DIGEST_DAILY)

        authenticated_client.post(
            reverse(self.url),
            {"digest_frequency": "off", "digest_lookahead_days": "14", "preferred_language": ""},
        )

        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_OFF

    @pytest.mark.parametrize(
        "data",
        [
            {"digest_frequency": "hourly", "digest_lookahead_days": "14"},
            {"digest_frequency": "daily", "digest_lookahead_days": "365"},
            {
                "digest_frequency": "daily",
                "digest_lookahead_days": "14",
                "preferred_language": "xx",
            },
        ],
    )
    def test_invalid_values_are_rejected(self, authenticated_client, user, data):
        authenticated_client.post(reverse(self.url), data)

        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_OFF
        assert user.profile.digest_lookahead_days == 14
        assert user.profile.preferred_language == ""

    def test_login_is_required(self, client, user):
        response = client.post(reverse(self.url), {"digest_frequency": "daily"})

        assert response.status_code == 302
        assert "login" in response["Location"]
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_OFF

    def test_user_cannot_change_the_preferences_of_someone_else(self, authenticated_client):
        other = UserFactory()

        authenticated_client.post(
            reverse(self.url),
            {"digest_frequency": "daily", "digest_lookahead_days": "7", "preferred_language": ""},
        )

        other.profile.refresh_from_db()
        assert other.profile.digest_frequency == Profile.DIGEST_OFF


@pytest.mark.django_db
class TestCalendarFeedManagement:
    def test_enable_creates_a_token(self, authenticated_client, user):
        authenticated_client.post(reverse("gift_manager:calendar_feed_regenerate"))

        user.profile.refresh_from_db()
        assert user.profile.calendar_token

    def test_regenerate_replaces_the_token(self, authenticated_client, user):
        old = user.profile.regenerate_calendar_token()

        authenticated_client.post(reverse("gift_manager:calendar_feed_regenerate"))

        user.profile.refresh_from_db()
        assert user.profile.calendar_token not in (None, old)

    def test_disable_clears_the_token(self, authenticated_client, user):
        user.profile.regenerate_calendar_token()

        authenticated_client.post(reverse("gift_manager:calendar_feed_disable"))

        user.profile.refresh_from_db()
        assert user.profile.calendar_token is None

    @pytest.mark.parametrize("name", ["calendar_feed_regenerate", "calendar_feed_disable"])
    def test_management_requires_login_and_post(self, client, authenticated_client, name):
        assert client.post(reverse(f"gift_manager:{name}")).status_code == 302
        assert authenticated_client.get(reverse(f"gift_manager:{name}")).status_code == 405


@pytest.mark.django_db
class TestUnsubscribe:
    def url(self, user):
        return reverse("gift_manager:digest_unsubscribe", args=[make_unsubscribe_token(user)])

    def opted_in(self, user):
        Profile.objects.filter(user=user).update(digest_frequency=Profile.DIGEST_DAILY)
        return user

    def test_get_asks_for_confirmation_without_changing_anything(self, client, user):
        self.opted_in(user)

        response = client.get(self.url(user))

        assert response.status_code == 200
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_DAILY

    def test_post_turns_the_digest_off_without_login(self, client, user):
        self.opted_in(user)

        response = client.post(self.url(user))

        assert response.status_code == 200
        assert response.context["done"] is True
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_OFF

    def test_one_click_post_works_without_a_csrf_token(self, user):
        from django.test import Client

        self.opted_in(user)
        strict_client = Client(enforce_csrf_checks=True)

        response = strict_client.post(
            self.url(user),
            "List-Unsubscribe=One-Click",
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == 200
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_OFF

    def test_other_preferences_are_kept(self, client, user):
        Profile.objects.filter(user=user).update(
            digest_frequency=Profile.DIGEST_DAILY, digest_lookahead_days=30, preferred_language="fr"
        )

        client.post(self.url(user))

        user.profile.refresh_from_db()
        assert user.profile.digest_lookahead_days == 30
        assert user.profile.preferred_language == "fr"

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_invalid_token_changes_nothing(self, client, user, method):
        self.opted_in(user)
        url = reverse("gift_manager:digest_unsubscribe", args=["tampered"])

        response = getattr(client, method)(url)

        assert response.status_code == 400
        user.profile.refresh_from_db()
        assert user.profile.digest_frequency == Profile.DIGEST_DAILY

    def test_token_only_affects_its_own_user(self, client, user):
        other = self.opted_in(UserFactory())

        client.post(self.url(user))

        other.profile.refresh_from_db()
        assert other.profile.digest_frequency == Profile.DIGEST_DAILY
