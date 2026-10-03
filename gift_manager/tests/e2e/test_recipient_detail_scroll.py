"""Each group of a recipient panel scrolls on its own, so a long group hides no other."""

import pytest
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory

pytestmark = [pytest.mark.frontend, pytest.mark.django_db(transaction=True)]

PLANS_PER_GROUP = 14


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


@pytest.fixture
def busy_person(seed_data_e2e):
    person = next(iter(seed_data_e2e.persons.values()))
    create_or_update_permission(seed_data_e2e.alice, person, permission_level=PermissionLevel.OWNER)
    for status in ("Planned", "Abandoned", "Given"):
        for index in range(PLANS_PER_GROUP):
            relation = RelationFactory(
                person=person,
                status=_status(status),
                gift=GiftFactory(name=f"{status} gift {index}"),
                comment=f"{status} comment {index}",
            )
            create_or_update_permission(
                seed_data_e2e.alice, relation, permission_level=PermissionLevel.OWNER
            )
    return person


@pytest.fixture
def alice_page(page, client, live_server, seed_data_e2e, settings):
    client.force_login(seed_data_e2e.alice)
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    return page


def test_groups_scroll_independently(alice_page, live_server, busy_person):
    page = alice_page
    page.goto(f"{live_server.url}/en/persons/{busy_person.person_id}/")
    page.locator("[data-abandoned-ideas] summary").click()
    expect(page.locator("[data-gift-history] .gift-history-item").first).to_be_visible()

    groups = page.locator(".detail-scroll-group")
    expect(groups).to_have_count(3)
    metrics = groups.evaluate_all(
        "els => els.map(el => ({scrollable: el.scrollHeight > el.clientHeight + 1,"
        " height: el.clientHeight}))"
    )
    assert all(metric["scrollable"] for metric in metrics)
    # Capped: far shorter than the 14 entries they hold
    assert all(metric["height"] <= 24 * 16 + 1 for metric in metrics)

    history = page.locator("[data-gift-history]")
    history.evaluate("el => { el.scrollTop = el.scrollHeight }")
    assert history.evaluate("el => el.scrollTop") > 0
    others = page.locator(".detail-scroll-group:not([data-gift-history])")
    assert others.evaluate_all("els => els.every(el => el.scrollTop === 0)")
