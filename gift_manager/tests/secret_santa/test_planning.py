"""Tests of the Secret Santa "Plan a gift" shortcut."""

import random
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from django.test import Client
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.secret_santa import planning
from gift_manager.secret_santa import service
from gift_manager.secret_santa.models import ExchangeParticipant
from gift_manager.tests.factories import ExchangeFactory
from gift_manager.tests.factories import ExchangeParticipantFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def santa_user():
    return UserFactory()


@pytest.fixture
def exchange(santa_user):
    exchange = ExchangeFactory()
    ExchangeParticipantFactory(exchange=exchange, name="Santa", linked_account=santa_user)
    for name in ("Chloe Martin", "Bob", "Dora"):
        ExchangeParticipantFactory(exchange=exchange, name=name)
    service.run_draw(exchange, rng=random.Random(1))  # noqa: S311 - reproducible test
    return exchange


@pytest.fixture
def santa(exchange):
    return ExchangeParticipant.objects.select_related("exchange").get(
        exchange=exchange, name="Santa"
    )


@pytest.fixture
def recipient(santa):
    return ExchangeParticipant.objects.get(pk=santa.gives_to_id)


def test_editable_source_person_is_used(santa, recipient, santa_user):
    person = PersonFactory()
    create_or_update_permission(santa_user, person, permission_level=PermissionLevel.EDITOR)
    ExchangeParticipant.objects.filter(pk=recipient.pk).update(source_person=person)

    assert planning.plan_prefill(santa, santa_user) == {"recipient": f"person:{person.person_id}"}


def test_viewer_only_source_person_is_not_used(santa, recipient, santa_user):
    person = PersonFactory()
    create_or_update_permission(santa_user, person, permission_level=PermissionLevel.VIEWER)
    ExchangeParticipant.objects.filter(pk=recipient.pk).update(source_person=person)

    assert "recipient" not in planning.plan_prefill(santa, santa_user)


def test_owned_person_linked_to_the_account(santa, recipient, santa_user):
    account = UserFactory()
    ExchangeParticipant.objects.filter(pk=recipient.pk).update(linked_account=account)
    PersonFactory(account=account)  # someone else's record of that account
    mine = PersonFactory(account=account, owner=santa_user)

    assert planning.plan_prefill(santa, santa_user) == {"recipient": f"person:{mine.person_id}"}


def test_new_person_names(santa, recipient, santa_user):
    ExchangeParticipant.objects.filter(pk=recipient.pk).update(name="Chloe Anne Martin")
    assert planning.plan_prefill(santa, santa_user) == {
        "new_person-first_name": "Chloe",
        "new_person-family_name": "Anne Martin",
    }
    ExchangeParticipant.objects.filter(pk=recipient.pk).update(name="Zed")
    assert planning.plan_prefill(santa, santa_user) == {"new_person-first_name": "Zed"}


def test_plan_gift_view_redirects_to_the_guided_plan(santa, santa_user):
    client = Client()
    client.force_login(santa_user)

    response = client.get(
        reverse("gift_manager:secret_santa_plan_gift", args=[santa.participant_id])
    )

    assert response.status_code == 302
    target = urlparse(response["Location"])
    assert target.path == reverse("gift_manager:relation_guided_create")
    assert "new_person-first_name" in parse_qs(target.query)


def test_plan_gift_view_scoping(santa, exchange, santa_user):
    target = reverse("gift_manager:secret_santa_plan_gift", args=[santa.participant_id])
    other = Client()
    other.force_login(UserFactory())
    assert other.get(target).status_code == 404

    mine = Client()
    mine.force_login(santa_user)
    ExchangeParticipant.objects.filter(pk=santa.pk).update(declined=True)
    assert mine.get(target).status_code == 404

    ExchangeParticipant.objects.filter(pk=santa.pk).update(declined=False)
    exchange.status = exchange.Status.DRAFT
    exchange.save()
    assert mine.get(target).status_code == 404

    assert Client().get(target).status_code == 302  # login
