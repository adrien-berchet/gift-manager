"""Only self-deactivated accounts may reactivate themselves (GM-AUD-005)."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

PASSWORD = "TestPassword123!"

pytestmark = pytest.mark.django_db


def _user(*, is_active=True):
    user = User.objects.create_user(
        username="someone", email="someone@example.com", password=PASSWORD
    )
    EmailAddress.objects.create(user=user, email="someone@example.com", primary=True, verified=True)
    if not is_active:
        user.is_active = False
        user.save()
    return user


def _login(client):
    return client.post(reverse("account_login"), {"login": "someone", "password": PASSWORD})


def _self_deactivate():
    client = Client()
    user = _user()
    client.force_login(user)
    client.post(reverse("deactivate_account"))
    user.refresh_from_db()
    return client, user


def test_self_deactivation_is_recorded():
    _client, user = _self_deactivate()

    assert user.is_active is False
    assert user.profile.self_deactivated_at is not None


def test_self_deactivated_user_reaches_reactivation_after_login():
    _client, user = _self_deactivate()
    client = Client()

    response = _login(client)

    assert response.status_code == 302
    assert response.url == reverse("reactivate_account")
    assert client.session["inactive_user_id"] == user.pk


def test_self_deactivated_user_can_reactivate_and_flag_is_cleared():
    _client, user = _self_deactivate()
    client = Client()
    _login(client)

    client.post(reverse("reactivate_account"))

    user.refresh_from_db()
    assert user.is_active is True
    assert user.profile.self_deactivated_at is None


def test_administratively_disabled_user_cannot_reach_reactivation():
    user = _user(is_active=False)
    client = Client()

    response = _login(client)

    assert "inactive_user_id" not in client.session
    assert response.status_code == 302
    assert response.url != reverse("reactivate_account")
    user.refresh_from_db()
    assert user.is_active is False


def test_administratively_disabled_user_cannot_reactivate_with_forged_session():
    user = _user(is_active=False)
    client = Client()
    session = client.session
    session["inactive_user_id"] = user.pk
    session.save()

    client.post(reverse("reactivate_account"))

    user.refresh_from_db()
    assert user.is_active is False


def test_admin_disabling_a_previously_self_deactivated_user_is_not_reactivatable():
    """Reactivating clears the flag, so a later admin disable stays disabled."""
    _client, user = _self_deactivate()
    client = Client()
    _login(client)
    client.post(reverse("reactivate_account"))
    user.refresh_from_db()
    user.is_active = False
    user.save()

    fresh = Client()
    _login(fresh)

    assert "inactive_user_id" not in fresh.session
