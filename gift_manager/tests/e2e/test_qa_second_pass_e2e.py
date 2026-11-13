"""Browser checks for the second 2026-11-12 QA pass fixes (N1, N2, N4)."""

import re
from datetime import date
from datetime import timedelta

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Gift
from gift_manager.models import PermissionLevel
from gift_manager.services import PermissionService
from gift_manager.tests.e2e.test_received_gift_e2e import login_as
from gift_manager.tests.e2e.test_received_gift_e2e import open_page


def _relative_luminance(rgb: str) -> float:
    def channel(value: int) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(part) for part in re.findall(r"\d+", rgb)[:3])
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.frontend
@pytest.mark.e2e
def test_future_date_warning_is_readable_in_both_themes(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    future = (date.today() + timedelta(days=30)).isoformat()
    for theme in ("light", "dark"):
        open_page(page, f"{live_server.url}{reverse('gift_manager:received_gift_create')}")
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        page.locator('input[name="received_on"]').evaluate(
            "(input, value) => { input._flatpickr ? input._flatpickr.setDate(value, true)"
            " : (input.value = value, input.dispatchEvent(new Event('change'))); }",
            future,
        )
        warning = page.locator(".future-date-warning")
        expect(warning).to_be_visible()
        colors = warning.evaluate(
            """el => {
                let node = el, bg = 'rgba(0, 0, 0, 0)';
                while (node && bg === 'rgba(0, 0, 0, 0)') {
                    bg = getComputedStyle(node).backgroundColor; node = node.parentElement;
                }
                return [getComputedStyle(el).color, bg];
            }"""
        )
        assert _contrast(*colors) >= 4.5, (theme, colors)


@pytest.mark.frontend
@pytest.mark.e2e
def test_viewer_removes_their_access_from_the_detail_page(page: Page, live_server, seed_data_e2e):
    mom = seed_data_e2e.persons["mom"]
    bob = seed_data_e2e.bob
    PermissionService.create_or_update_permission(bob, mom, permission_level=PermissionLevel.VIEWER)

    login_as(page, live_server.url, "bob")
    open_page(
        page, f"{live_server.url}{reverse('gift_manager:person_detail', args=[mom.person_id])}"
    )
    page.get_by_role("link", name="Remove my access").click()
    expect(page.get_by_role("heading", name="Remove my access")).to_be_visible()
    page.get_by_role("button", name="Remove my access").click()

    page.wait_for_url(lambda url: str(mom.person_id) not in url)
    assert PermissionService.get_permission(mom, bob) == PermissionLevel.NONE
    mom.refresh_from_db()
    assert PermissionService.get_permission(mom, seed_data_e2e.alice) == PermissionLevel.OWNER


@pytest.mark.frontend
@pytest.mark.e2e
def test_gift_list_switches_to_gifts_not_in_a_plan(page: Page, live_server, seed_data_e2e):
    alice = seed_data_e2e.alice
    idle = Gift.objects.create(name="Idle Jigsaw")
    PermissionService.create_or_update_permission(
        alice, idle, permission_level=PermissionLevel.OWNER
    )

    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")
    page.locator(".dashboard-summary-tile", has_text="Unassigned gifts").click()

    page.wait_for_url(re.compile(r"/gifts/\?unassigned=1$"))
    grid = page.locator("#gift-grid")
    expect(grid.get_by_text("Idle Jigsaw")).to_be_visible()
    expect(grid.get_by_text("Novel")).to_have_count(0)
    expect(page.get_by_role("link", name="Not in a plan yet")).to_have_attribute(
        "aria-current", "page"
    )

    page.get_by_role("link", name="All gifts").click()
    expect(grid.get_by_text("Novel")).to_be_visible()


@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("surface", ["page", "modal"])
def test_only_owner_hands_over_before_leaving(page: Page, live_server, seed_data_e2e, surface):
    alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
    alice.profile.friends.add(bob.profile)
    sister = seed_data_e2e.persons["sister"]
    PermissionService.create_or_update_permission(
        bob, sister, permission_level=PermissionLevel.VIEWER
    )

    login_as(page, live_server.url, "alice")
    if surface == "page":
        open_page(
            page,
            f"{live_server.url}{reverse('gift_manager:person_detail', args=[sister.person_id])}",
        )
        page.get_by_role("link", name="Hand over and remove my access").click()
        page.get_by_label("New owner").select_option(str(bob.pk))
        page.get_by_role("button", name="Hand over and remove my access").click()
        page.wait_for_url(lambda url: str(sister.person_id) not in url)
    else:
        open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")
        page.evaluate(
            "url => window.GiftManager.confirmDelete(url)",
            reverse("gift_manager:person_delete", args=[sister.person_id]) + "?intent=leave_access",
        )
        modal = page.locator("#confirmModal")
        expect(modal).to_be_visible()
        modal.get_by_label("New owner").select_option(str(bob.pk))
        with page.expect_response(lambda r: "/delete/" in r.url and r.request.method == "POST"):
            modal.locator("#confirmAction").click()
        expect(modal).not_to_be_visible()

    assert PermissionService.get_permission(sister, bob) == PermissionLevel.OWNER
    assert PermissionService.get_permission(sister, alice) == PermissionLevel.NONE


@pytest.mark.frontend
@pytest.mark.e2e
def test_viewer_removes_their_access_from_the_detail_panel(page: Page, live_server, seed_data_e2e):
    mom, bob = seed_data_e2e.persons["mom"], seed_data_e2e.bob
    PermissionService.create_or_update_permission(bob, mom, permission_level=PermissionLevel.VIEWER)

    login_as(page, live_server.url, "bob")
    open_page(page, f"{live_server.url}{reverse('gift_manager:home')}")
    page.evaluate(
        "url => window.GiftManager.confirmDelete(url)",
        reverse("gift_manager:person_delete", args=[mom.person_id]) + "?intent=leave_access",
    )
    modal = page.locator("#confirmModal")
    expect(modal.locator("#confirmAction")).to_have_text("Remove my access")
    with page.expect_response(lambda r: "/delete/" in r.url and r.request.method == "POST"):
        modal.locator("#confirmAction").click()
    expect(modal).not_to_be_visible()

    assert PermissionService.get_permission(mom, bob) == PermissionLevel.NONE
