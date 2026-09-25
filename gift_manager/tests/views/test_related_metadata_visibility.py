"""Private tag/group metadata must not leak through visible gifts and persons (GM-AUD-002)."""

from datetime import date
from datetime import timedelta

import pytest
from django.urls import reverse

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PRIVATE_TAG = "PrivateTagZzz"
VISIBLE_TAG = "VisibleTagYyy"
PRIVATE_GROUP = "PrivateGroupZzz"
VISIBLE_GROUP = "VisibleGroupYyy"


@pytest.fixture
def viewer(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.fixture
def gift(viewer):
    """A gift visible to the viewer, tagged with a visible and a private tag."""
    owner = UserFactory()
    gift = GiftFactory(name="Shared gift", shared_with=[viewer])
    gift.tags.add(
        GiftTagFactory(name=VISIBLE_TAG, shared_with=[viewer]),
        GiftTagFactory(name=PRIVATE_TAG, shared_with=[owner]),
    )
    return gift


@pytest.fixture
def person(viewer):
    """A person visible to the viewer, in a visible and a private group."""
    owner = UserFactory()
    person = PersonFactory(shared_with=[viewer])
    person.groups.add(
        PersonGroupFactory(name=VISIBLE_GROUP, shared_with=[viewer]),
        PersonGroupFactory(name=PRIVATE_GROUP, shared_with=[owner]),
    )
    return person


def _assert_only_visible_tag(response):
    body = response.content.decode()
    assert response.status_code == 200
    assert PRIVATE_TAG not in body
    assert VISIBLE_TAG in body


def test_gift_detail_hides_private_tags(client, gift):
    response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id}))

    _assert_only_visible_tag(response)


def test_gift_detail_tag_count_matches_visible_tags(client, gift):
    response = client.get(reverse("gift_manager:gift_detail", kwargs={"pk": gift.gift_id}))

    assert 'badge bg-secondary ms-2">1<' in response.content.decode()


def test_gift_list_hides_private_tags(client, gift):
    response = client.get(reverse("gift_manager:gifts"))

    _assert_only_visible_tag(response)


def test_gift_search_hides_private_tags(client, gift):
    response = client.get(reverse("gift_manager:gift_search"), {"search": "Shared"})

    payload = response.json()
    assert [tag["name"] for tag in payload["data"][0]["tags_info"]] == [VISIBLE_TAG]


def test_person_search_hides_private_groups(client, person):
    response = client.get(reverse("gift_manager:person_search"), {"search": person.first_name[:3]})

    payload = response.json()
    assert [g["name"] for g in payload["data"][0]["groups_info"]] == [VISIBLE_GROUP]


def test_person_detail_hides_private_groups(client, person):
    response = client.get(reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}))

    body = response.content.decode()
    assert response.status_code == 200
    assert PRIVATE_GROUP not in body
    assert VISIBLE_GROUP in body


def test_person_detail_hides_private_ancestor_groups(client, viewer, person):
    private_parent = PersonGroupFactory(name="PrivateAncestorZzz", shared_with=[UserFactory()])
    visible_group = person.groups.get(name=VISIBLE_GROUP)
    visible_group.parent_groups.add(private_parent)

    response = client.get(reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}))

    assert "PrivateAncestorZzz" not in response.content.decode()


def test_relation_detail_hides_private_tags(client, viewer, gift):
    relation = RelationFactory(gift=gift, shared_with=[viewer])

    response = client.get(
        reverse("gift_manager:relation_detail", kwargs={"pk": relation.relation_id})
    )

    _assert_only_visible_tag(response)


def test_relation_cards_hide_private_tags(client, viewer, gift):
    RelationFactory(gift=gift, shared_with=[viewer])

    response = client.get(reverse("gift_manager:relations"), {"view": "cards"})

    _assert_only_visible_tag(response)


def test_dashboard_gift_plan_cards_hide_private_tags(client, viewer, gift):
    RelationFactory(gift=gift, shared_with=[viewer], due_date=date.today() + timedelta(days=2))

    response = client.get(reverse("gift_manager:home"))

    _assert_only_visible_tag(response)


def test_person_detail_gift_plan_hides_private_tags(client, viewer, gift, person):
    RelationFactory(gift=gift, person=person, shared_with=[viewer])

    response = client.get(reverse("gift_manager:person_detail", kwargs={"pk": person.person_id}))

    _assert_only_visible_tag(response)


def test_tag_explorer_hides_private_sibling_tags(client, viewer, gift):
    visible_tag = gift.tags.get(name=VISIBLE_TAG)

    response = client.get(
        reverse("gift_manager:gift_tag_explorer_with_tag", kwargs={"pk": visible_tag.tag_id})
    )

    _assert_only_visible_tag(response)
