"""Browser checks for the reveal panel and received-date fixes from the 2026-11-12 QA pass."""

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
from gift_manager.tests.e2e.test_received_gift_e2e import _setup_friend_recipient
from gift_manager.tests.e2e.test_received_gift_e2e import login_as
from gift_manager.tests.e2e.test_received_gift_e2e import open_page


def _given_plan(seed_data_e2e, name):
    alice, _bob, best_friend = _setup_friend_recipient(seed_data_e2e)
    gift = Gift.objects.create(name=name)
    plan = Relation.objects.create(
        gift=gift, person=best_friend, status=seed_data_e2e.statuses["given"]
    )
    for obj in (gift, plan):
        PermissionService.create_or_update_permission(
            alice, obj, permission_level=PermissionLevel.OWNER
        )
    return plan


@pytest.mark.frontend
@pytest.mark.e2e
def test_reveal_panel_is_readable_in_dark_mode_and_does_not_scroll_sideways(
    page: Page, live_server, seed_data_e2e
):
    plan = _given_plan(seed_data_e2e, "Dark Mode Lantern")
    login_as(page, live_server.url, "alice")
    open_page(
        page, f"{live_server.url}{reverse('gift_manager:relation_detail', args=[plan.relation_id])}"
    )
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")

    page.locator('a[data-action="edit"]', has_text="Reveal to recipient").click()
    panel = page.locator("#editPanel")
    form = panel.locator("#relation-reveal-form")
    expect(form).to_be_visible()

    summary = form.locator(".reveal-snapshot-summary")
    expect(summary).to_contain_text("Dark Mode Lantern")
    colors = summary.evaluate(
        """el => {
            const title = el.querySelector('.fw-semibold');
            return [getComputedStyle(el).backgroundColor, getComputedStyle(title).color];
        }"""
    )
    assert colors[0] != colors[1], colors

    form.locator("details summary").click()
    expect(form.locator('input[name="occasion_text"]')).to_be_visible()
    body = panel.locator(".offcanvas-body")
    overflow = body.evaluate("el => el.scrollWidth - el.clientWidth")
    assert overflow <= 0, f"Reveal panel scrolls sideways by {overflow}px"


@pytest.mark.frontend
@pytest.mark.e2e
def test_reveal_toast_link_stays_until_closed(page: Page, live_server, seed_data_e2e):
    plan = _given_plan(seed_data_e2e, "Lingering Toast Mug")
    plan.status = seed_data_e2e.statuses["planned"]
    plan.due_date = date.today() - timedelta(days=1)
    plan.event = seed_data_e2e.events["christmas"]
    plan.save()
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:relations')}")

    card = page.locator(".gift-plan-card", has_text="Lingering Toast Mug")
    card.locator('a[data-action="edit"][aria-label="Edit"]').click()
    panel = page.locator("#editPanel")
    panel.locator('select[name="status"]').select_option(str(seed_data_e2e.statuses["given"].pk))
    panel.locator('button[type="submit"].btn-primary').click()

    toast_link = page.locator("#toastContainer [data-toast-action]", has_text="Reveal to recipient")
    expect(toast_link).to_be_visible()
    page.wait_for_timeout(6000)
    expect(toast_link).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
def test_future_received_date_shows_a_warning_but_saves(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_list')}")

    page.locator('[data-action="create"]:visible').first.click()
    panel = page.locator("#editPanel")
    form = panel.locator("form")
    expect(form.locator('input[name="received_on"]')).to_be_attached()
    warning = form.locator(".future-date-warning")
    expect(warning).to_be_hidden()

    future = (date.today() + timedelta(days=30)).isoformat()
    form.locator('input[name="received_on"]').evaluate(
        "(input, value) => { input._flatpickr ? input._flatpickr.setDate(value, true)"
        " : (input.value = value, input.dispatchEvent(new Event('change'))); }",
        future,
    )
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("This date is in the future.")

    today = date.today().isoformat()
    form.locator('input[name="received_on"]').evaluate(
        "(input, value) => { input._flatpickr ? input._flatpickr.setDate(value, true)"
        " : (input.value = value, input.dispatchEvent(new Event('change'))); }",
        today,
    )
    expect(warning).to_be_hidden()
