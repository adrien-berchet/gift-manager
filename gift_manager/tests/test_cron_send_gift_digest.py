"""Tests for the Vercel Cron endpoint that sends the reminder digests."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from gift_manager.models import Profile
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory

SECRET = "a-long-enough-cron-secret"
BASE_URL = "https://gifts.example.com"


@pytest.fixture(autouse=True)
def cron_settings(settings):
    settings.CRON_SECRET = SECRET
    settings.SITE_BASE_URL = BASE_URL


def call(client, secret=SECRET, **extra):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {secret}"} if secret is not None else {}
    return client.get(reverse("cron_send_gift_digest"), **headers, **extra)


def opted_in_user_with_overdue_plan(user=None):
    user = user or UserFactory()
    Profile.objects.filter(user=user).update(digest_frequency=Profile.DIGEST_DAILY)
    RelationFactory(
        due_date=timezone.localdate() - timedelta(days=3),
        status=RelationStatusFactory(status="Planned"),
        shared_with=[user],
    )
    return user


@pytest.mark.django_db
class TestAuthorization:
    def test_url_is_not_under_the_language_prefix(self):
        # Vercel Cron does not follow redirects
        assert reverse("cron_send_gift_digest") == "/cron/send-gift-digest/"

    def test_valid_secret_runs_the_digest(self, client):
        opted_in_user_with_overdue_plan()

        response = call(client)

        assert response.status_code == 200
        assert response.json() == {"sent": 1, "skipped": 0, "already_sent": 0, "failed": 0}
        assert len(mail.outbox) == 1
        assert response["Cache-Control"] == "no-store"

    @pytest.mark.parametrize(
        "secret", [None, "", "wrong-secret-value-123", SECRET + "x", SECRET[:-1]]
    )
    def test_missing_or_wrong_secret_is_rejected_and_sends_nothing(self, client, secret):
        opted_in_user_with_overdue_plan()

        response = call(client, secret=secret)

        assert response.status_code == 401
        assert mail.outbox == []

    def test_other_authorization_scheme_is_rejected(self, client):
        opted_in_user_with_overdue_plan()

        response = client.get(
            reverse("cron_send_gift_digest"), HTTP_AUTHORIZATION=f"Basic {SECRET}"
        )

        assert response.status_code == 401
        assert mail.outbox == []

    def test_secret_in_the_query_string_is_not_accepted(self, client):
        response = client.get(reverse("cron_send_gift_digest"), {"secret": SECRET})

        assert response.status_code == 401

    @pytest.mark.parametrize("secret", ["", "short"])
    def test_endpoint_does_not_exist_without_a_proper_secret(self, client, settings, secret):
        settings.CRON_SECRET = secret
        opted_in_user_with_overdue_plan()

        # Even a request that sends the configured (too short or empty) value is refused
        assert call(client, secret=secret or "x").status_code == 404
        assert mail.outbox == []

    @pytest.mark.parametrize("method", ["post", "put", "delete"])
    def test_only_get_is_allowed(self, client, method):
        response = getattr(client, method)(
            reverse("cron_send_gift_digest"), HTTP_AUTHORIZATION=f"Bearer {SECRET}"
        )

        assert response.status_code == 405

    def test_a_logged_in_user_cannot_call_it_without_the_secret(self, authenticated_client):
        response = authenticated_client.get(reverse("cron_send_gift_digest"))

        assert response.status_code == 401


@pytest.mark.django_db
class TestBehaviour:
    def test_calling_it_twice_the_same_day_sends_once(self, client):
        opted_in_user_with_overdue_plan()

        first = call(client).json()
        second = call(client).json()

        assert first["sent"] == 1
        assert second == {"sent": 0, "skipped": 0, "already_sent": 1, "failed": 0}
        assert len(mail.outbox) == 1

    def test_nothing_to_report_sends_nothing(self, client):
        Profile.objects.filter(user=UserFactory()).update(digest_frequency=Profile.DIGEST_DAILY)

        response = call(client)

        assert response.json() == {"sent": 0, "skipped": 1, "already_sent": 0, "failed": 0}
        assert mail.outbox == []

    def test_a_failing_recipient_gives_a_500_and_the_others_are_still_sent(self, client):
        broken = opted_in_user_with_overdue_plan()
        opted_in_user_with_overdue_plan()
        real_send = mail.EmailMultiAlternatives.send

        def flaky_send(message, *args, **kwargs):
            if message.to == [broken.profile.email]:
                msg = "smtp down"
                raise OSError(msg)
            return real_send(message, *args, **kwargs)

        with mock.patch.object(mail.EmailMultiAlternatives, "send", flaky_send):
            response = call(client)

        assert response.status_code == 500
        assert response.json()["failed"] == 1
        assert response.json()["sent"] == 1
        # The failed user is retried by the next call
        response = call(client)
        assert response.status_code == 200
        assert len(mail.outbox) == 2

    def test_missing_site_base_url_gives_a_500_without_sending(self, client, settings):
        settings.SITE_BASE_URL = ""
        opted_in_user_with_overdue_plan()

        response = call(client)

        assert response.status_code == 500
        assert mail.outbox == []

    def test_response_does_not_expose_any_user_data(self, client):
        user = opted_in_user_with_overdue_plan()

        body = call(client).content.decode()

        assert user.username not in body
        assert user.profile.email not in body
