"""Browser checks for application fixes from the 2026-11-12 QA pass."""

import re
from datetime import date
from datetime import timedelta

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.e2e.test_received_gift_e2e import login_as
from gift_manager.tests.e2e.test_received_gift_e2e import open_page


def _own(user, *objects):
    for obj in objects:
        PermissionService.create_or_update_permission(
            user, obj, permission_level=PermissionLevel.OWNER
        )


@pytest.mark.frontend
@pytest.mark.e2e
def test_person_page_refreshes_after_editing_a_plan_in_the_side_panel(
    page: Page, live_server, seed_data_e2e
):
    alice = seed_data_e2e.alice
    person = seed_data_e2e.persons["best_friend"]
    gift = Gift.objects.create(name="Refreshing Teapot")
    plan = Relation.objects.create(
        gift=gift,
        person=person,
        status=seed_data_e2e.statuses["planned"],
        due_date=date.today() + timedelta(days=10),
    )
    _own(alice, person, gift, plan)

    login_as(page, live_server.url, "alice")
    open_page(
        page, f"{live_server.url}{reverse('gift_manager:person_detail', args=[person.person_id])}"
    )
    in_progress = page.locator(".relations-list .relation-item", has_text="Refreshing Teapot")
    expect(in_progress).to_contain_text("Planned")

    in_progress.locator('a[data-action="edit"]').click()
    panel = page.locator("#editPanel")
    panel.locator('select[name="status"]').select_option(str(seed_data_e2e.statuses["given"].pk))
    with page.expect_response(lambda r: f"/relations/{plan.relation_id}/edit/" in r.url):
        panel.locator('button[type="submit"].btn-primary').click()
    expect(panel).not_to_be_visible()

    # Without a reload, the plan leaves "in progress" and shows up in the gift history
    expect(
        page.locator(".relations-list .relation-item", has_text="Refreshing Teapot")
    ).to_have_count(0)
    expect(page.locator(".gift-history-item", has_text="Refreshing Teapot")).to_contain_text(
        "Given"
    )


@pytest.mark.frontend
@pytest.mark.e2e
def test_inline_rating_on_the_person_page_updates_only_the_gift_history(
    page: Page, live_server, seed_data_e2e
):
    alice = seed_data_e2e.alice
    person = seed_data_e2e.persons["best_friend"]
    gift = Gift.objects.create(name="Rated Kettle")
    plan = Relation.objects.create(
        gift=gift,
        person=person,
        status=seed_data_e2e.statuses["given"],
        due_date=date.today(),
    )
    _own(alice, person, gift, plan)

    login_as(page, live_server.url, "alice")
    open_page(
        page, f"{live_server.url}{reverse('gift_manager:person_detail', args=[person.person_id])}"
    )
    page.evaluate("document.querySelector('.detail-page-shell > *').dataset.marker = 'kept'")
    item = page.locator(".gift-history-item", has_text="Rated Kettle")
    with page.expect_response(lambda r: f"/relations/{plan.relation_id}/reaction/" in r.url):
        item.locator(f"label[for='rating-{plan.relation_id}-4']").click()

    expect(item.locator("[data-rating-inline]")).to_have_count(0)
    expect(item.locator(".rating-stars-filled")).to_have_count(4)
    # The page shell itself was not reloaded
    marker = page.evaluate("document.querySelector('.detail-page-shell > *').dataset.marker")
    assert marker == "kept"
    plan.refresh_from_db()
    assert plan.reaction_rating == 4


@pytest.mark.frontend
@pytest.mark.e2e
def test_gift_plan_panel_selects_are_full_width(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")

    page.locator('a[data-action="create"][href$="/relations/create/"]:visible').first.click()
    form = page.locator("#editPanel form.relation-form")
    expect(form).to_be_visible()

    recipient_width = form.locator('select[name="recipient"]').evaluate("el => el.offsetWidth")
    for name in ("gift", "event", "status"):
        select = form.locator(f'select[name="{name}"]')
        expect(select).to_have_class(re.compile(r"\bform-select\b"))
        assert select.evaluate("el => el.offsetWidth") >= recipient_width * 0.9, name
