"""Status badges link to the page listing every gift plan with that status."""

import pytest
from django.urls import reverse

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import RelationStatusFactory
from gift_manager.tests.factories import UserFactory


@pytest.fixture
def plan(client):
    user = UserFactory()
    client.force_login(user)
    status = RelationStatusFactory(status="Planned")
    person = PersonFactory(first_name="Ada", family_name="Lovelace", shared_with=[user])
    gift = GiftFactory(name="Book", shared_with=[user])
    return RelationFactory(person=person, gift=gift, status=status, shared_with=[user])


def _status_link(plan) -> str:
    url = reverse("gift_manager:relation_status_detail", args=[plan.status.pk])
    return f'<a href="{url}" class="status-link"'


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name, pk_attr",
    [
        ("relations", None),
        ("relation_detail", "relation_id"),
        ("person_detail", "person.person_id"),
        ("gift_detail", "gift.gift_id"),
    ],
)
def test_status_badge_links_to_the_status_page(client, plan, url_name, pk_attr):
    args = []
    if pk_attr:
        target = plan
        for part in pk_attr.split("."):
            target = getattr(target, part)
        args = [target]

    response = client.get(reverse(f"gift_manager:{url_name}", args=args))

    assert response.status_code == 200
    assert _status_link(plan) in response.content.decode()
