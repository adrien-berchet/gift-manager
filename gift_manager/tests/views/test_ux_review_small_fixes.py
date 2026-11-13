"""Small copy and markup fixes from the 2026-11-13 UX review (A4, A10)."""

import pytest
from django.urls import reverse
from django.utils import translation

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_advanced_list_shows_its_heading_once(client, user):
    content = client.get(reverse("gift_manager:relation_advanced_list")).content.decode()
    assert content.count(">Advanced Gift Plans List<") == 1
    assert 'aria-labelledby="gift-plan-advanced-heading"' in content
    assert 'id="gift-plan-advanced-heading"' in content


@pytest.mark.django_db
def test_share_page_title_names_the_app_once(client, user):
    content = client.get(reverse("gift_manager:share_objects")).content.decode()
    title = content.split("<title>")[1].split("</title>")[0]
    assert title.count("Gift Manager") == 1


@pytest.mark.django_db
def test_dashboard_invites_to_create_a_first_plan_only_without_plans(client, user):
    invitation = "Create a gift plan to start tracking what you will give next."
    assert invitation in client.get(reverse("gift_manager:home")).content.decode()

    RelationFactory(
        person=PersonFactory(shared_with=[user]),
        gift=GiftFactory(shared_with=[user]),
        status=RelationStatusFactory(status="Given"),
        due_date=None,
        shared_with=[user],
    )
    assert invitation not in client.get(reverse("gift_manager:home")).content.decode()


@pytest.mark.django_db
def test_grid_filter_labels_are_translated(client, user):
    with translation.override("fr"):
        content = client.get(reverse("gift_manager:gifts")).content.decode()
    for key, french in (
        ("filters", "Filtres"),
        ("clear", "Effacer"),
        ("filterAll", "Tous"),
        ("filterPlaceholder", "Filtrer…"),
    ):
        assert f'{key}: "{french}"' in content, key
    assert ">Affichage<" in content
    assert ">Lecture<" not in content
