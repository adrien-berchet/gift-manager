"""Global search over the signed-in user's own received gifts and wishes."""

from datetime import date

import pytest
from django.urls import reverse

from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.factories import EventFactory
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import ReceivedGiftFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.tests.factories import WishFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def _received(user, **kwargs):
    defaults = {"description": "", "occasion_text": "", "giver_label": ""}
    return ReceivedGiftFactory(recipient_user=user, **(defaults | kwargs))


def _search(client, query, result_type=None):
    response = client.get(reverse("gift_manager:global_search"), {"q": query})
    assert response.status_code == 200
    results = response.json()["results"]
    if result_type is None:
        return results
    return [result for result in results if result["type"] == result_type]


def test_received_gift_payload(client, user):
    gift = _received(
        user,
        title="Zebra Telescope",
        giver_label="Aunt Marie",
        occasion_text="QA Party",
        received_on=date(2024, 5, 2),
    )

    results = _search(client, "zebra tele", "received_gift")

    assert results == [
        {
            "type": "received_gift",
            "icon": "fa-box-open",
            "title": "Zebra Telescope",
            "subtitle": "Aunt Marie · QA Party · 2024",
            "url": reverse("gift_manager:received_gift_detail", kwargs={"pk": gift.received_gift_id}),
        }
    ]


@pytest.mark.parametrize(
    ("field", "query"),
    [
        ("title", "quokka"),
        ("description", "quokka"),
        ("occasion_text", "quokka"),
        ("giver_label", "quokka"),
    ],
)
def test_received_gift_matches_its_text_fields(client, user, field, query):
    _received(user, **({"title": "Present"} | {field: "A Quokka thing"}))
    _received(user, title="Unrelated")

    assert [r["title"] for r in _search(client, query, "received_gift")] in (
        ["Present"],
        ["A Quokka thing"],
    )


def test_received_gift_matches_event_and_address_book_givers(client, user):
    event = EventFactory(name="Quokka Gala")
    person = PersonFactory(first_name="Wombatina", family_name="Smith")
    group = PersonGroupFactory(name="Numbat Club")
    for obj in (event, person, group):
        PermissionService.create_or_update_permission(
            user, obj, permission_level=PermissionLevel.OWNER
        )
    _received(user, title="From event", event=event)
    by_person = _received(user, title="From person")
    by_person.giver_persons.add(person, PersonFactory(first_name="Wombatina", family_name="Jones"))
    _received(user, title="From group").giver_groups.add(group)

    assert [r["title"] for r in _search(client, "quokka", "received_gift")] == ["From event"]
    # Two matching givers on one gift still give a single result
    assert [r["title"] for r in _search(client, "wombatina", "received_gift")] == ["From person"]
    assert [r["title"] for r in _search(client, "numbat", "received_gift")] == ["From group"]


def test_received_gift_does_not_match_givers_the_user_cannot_access(client, user):
    hidden = PersonFactory(first_name="Wombatina")
    _received(user, title="From hidden contact").giver_persons.add(hidden)

    assert _search(client, "wombatina", "received_gift") == []


def test_received_gift_does_not_match_givers_kept_from_a_revealed_plan(client, user):
    owner = UserFactory(username="platypus_owner", first_name="Platypus", last_name="Owner")
    gift = _received(user, title="Revealed", source_givers_text="Platypus Owner")
    gift.giver_accounts.add(owner)

    assert _search(client, "platypus") == []


def test_wish_payload_and_matching(client, user):
    wish = WishFactory(wisher=user, title="Zebra Mug", notes="Blue, large")
    WishFactory(wisher=user, title="Teapot", notes="With a zebra pattern " + "x" * 60)
    WishFactory(wisher=user, title="Unrelated", notes="")

    results = _search(client, "zebra", "wish")

    assert {r["title"] for r in results} == {"Zebra Mug", "Teapot"}
    by_title = {r["title"]: r for r in results}
    assert by_title["Zebra Mug"] == {
        "type": "wish",
        "icon": "fa-star",
        "title": "Zebra Mug",
        "subtitle": "Blue, large",
        "url": reverse("gift_manager:wish_edit", kwargs={"wish_id": wish.wish_id}),
    }
    assert by_title["Teapot"]["subtitle"].endswith("...")
    assert len(by_title["Teapot"]["subtitle"]) == 53


def test_wish_search_keeps_archived_and_skips_deleted(client, user):
    WishFactory(wisher=user, title="Zebra archived", is_archived=True)
    WishFactory(wisher=user, title="Zebra deleted", is_deleted_by_wisher=True)

    assert [r["title"] for r in _search(client, "zebra", "wish")] == ["Zebra archived"]


def test_other_users_received_gifts_and_wishes_never_appear(client, user):
    other = UserFactory()
    _received(other, title="Zebra secret gift", giver_label="Zebra giver")
    WishFactory(wisher=other, title="Zebra secret wish", notes="zebra")
    # Even a confirmed friend's wishes stay on their person page
    user.profile.friends.add(other.profile)
    other.profile.friends.add(user.profile)

    assert _search(client, "zebra") == []

    client.force_login(other)
    assert {r["title"] for r in _search(client, "zebra")} == {
        "Zebra secret gift",
        "Zebra secret wish",
    }


def test_results_are_limited_per_category(client, user):
    for index in range(7):
        _received(user, title=f"Zebra gift {index}")
        WishFactory(wisher=user, title=f"Zebra wish {index}", notes="")

    assert len(_search(client, "zebra", "received_gift")) == 5
    assert len(_search(client, "zebra", "wish")) == 5


def test_new_types_come_after_the_existing_ones(client, user):
    gift = GiftFactory(name="Zebra gift", shared_with=[user])
    tag = GiftTagFactory(name="Zebra tag")
    PermissionService.create_or_update_permission(user, tag, permission_level=PermissionLevel.OWNER)
    _received(user, title="Zebra received")
    WishFactory(wisher=user, title="Zebra wish", notes="")

    types = [result["type"] for result in _search(client, "zebra")]

    assert gift.name == "Zebra gift"
    assert types == ["gift", "tag", "received_gift", "wish"]
