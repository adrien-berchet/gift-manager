"""Text contrast of the screens fixed after the 2026-11-13 UX review (A1, A2, A7, A8)."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page

from gift_manager.models import PermissionLevel
from gift_manager.models import Relation
from gift_manager.services import PermissionService
from gift_manager.tests.e2e.test_qa_second_pass_e2e import _contrast
from gift_manager.tests.e2e.test_received_gift_e2e import login_as
from gift_manager.tests.e2e.test_received_gift_e2e import open_page

MIN_CONTRAST = 4.5

# Colour and first opaque background behind every visible element matching the selector
COLORS_JS = """(selector) => [...document.querySelectorAll(selector)]
    .filter(el => el.getClientRects().length && el.textContent.trim())
    .map(el => {
        let node = el, bg = 'rgba(0, 0, 0, 0)';
        while (node && bg === 'rgba(0, 0, 0, 0)') {
            bg = getComputedStyle(node).backgroundColor; node = node.parentElement;
        }
        return [el.textContent.trim().slice(0, 30), getComputedStyle(el).color, bg];
    })"""


def _assert_readable(page: Page, url: str, selectors: list[str]) -> None:
    for theme in ("light", "dark"):
        open_page(page, url)
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        page.wait_for_timeout(600)  # colours transition
        for selector in selectors:
            page.wait_for_selector(selector, state="visible")
            cells = page.evaluate(COLORS_JS, selector)
            assert cells, (theme, selector)
            unreadable = [
                (text, fg, bg, round(_contrast(fg, bg), 2))
                for text, fg, bg in cells
                if _contrast(fg, bg) < MIN_CONTRAST
            ]
            assert not unreadable, (theme, selector, unreadable)


@pytest.mark.frontend
@pytest.mark.e2e
def test_shared_with_permission_label_is_readable(page: Page, live_server, seed_data_e2e):
    mom = seed_data_e2e.persons["mom"]
    PermissionService.create_or_update_permission(
        seed_data_e2e.bob, mom, permission_level=PermissionLevel.VIEWER
    )
    login_as(page, live_server.url, "alice")
    url = f"{live_server.url}{reverse('gift_manager:person_detail', args=[mom.person_id])}"
    _assert_readable(page, url, [".badge.bg-outline-secondary"])


@pytest.mark.frontend
@pytest.mark.e2e
def test_group_gift_tip_is_readable(page: Page, live_server, seed_data_e2e):
    plan = (
        Relation.objects.accessible_by(seed_data_e2e.alice)
        .filter(price__isnull=True, gift__price__isnull=True)
        .first()
    )
    assert plan is not None
    login_as(page, live_server.url, "alice")
    url = f"{live_server.url}{reverse('gift_manager:relation_detail', args=[plan.relation_id])}"
    _assert_readable(page, url, [".text-warning-emphasis"])


@pytest.mark.frontend
@pytest.mark.e2e
def test_share_page_section_titles_are_readable(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    url = f"{live_server.url}{reverse('gift_manager:share_objects')}"
    _assert_readable(page, url, ["#shareAccordion .card-header .fw-semibold", ".card-header h5"])


@pytest.mark.frontend
@pytest.mark.e2e
def test_gift_plan_workspace_badges_are_readable(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    url = f"{live_server.url}{reverse('gift_manager:relations')}"
    _assert_readable(
        page,
        url,
        [
            ".gift-plan-summary-item--attention span",
            ".gift-plan-status-badge",
            ".gift-plan-due-badge",
        ],
    )


@pytest.mark.frontend
@pytest.mark.e2e
def test_grid_filter_panel_buttons_are_readable(page: Page, live_server, seed_data_e2e):
    login_as(page, live_server.url, "alice")
    url = f"{live_server.url}{reverse('gift_manager:gifts')}"
    for theme in ("light", "dark"):
        open_page(page, url)
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        page.locator(".advanced-list-tools-summary").first.click()
        page.wait_for_timeout(600)
        for selector in ("[id^=toggle-selection-]", ".gridjs-td .badge"):
            cells = page.evaluate(COLORS_JS, selector)
            assert cells, (theme, selector)
            unreadable = [cell for cell in cells if _contrast(cell[1], cell[2]) < MIN_CONTRAST]
            assert not unreadable, (theme, selector, unreadable)


@pytest.mark.frontend
@pytest.mark.e2e
def test_needs_attention_chip_is_highlighted_only_when_not_zero(
    page: Page, live_server, seed_data_e2e
):
    login_as(page, live_server.url, "alice")
    open_page(page, f"{live_server.url}{reverse('gift_manager:relations')}")
    chips = page.locator(".gift-plan-summary-item", has_text="Needs attention")
    count = int(chips.locator("strong").inner_text())
    highlighted = chips.evaluate("el => el.classList.contains('gift-plan-summary-item--attention')")
    assert highlighted == (count > 0)

    login_as(page, live_server.url, "testuser")
    open_page(page, f"{live_server.url}{reverse('gift_manager:relations')}")
    chips = page.locator(".gift-plan-summary-item", has_text="Needs attention")
    if int(chips.locator("strong").inner_text()) == 0:
        assert not chips.evaluate(
            "el => el.classList.contains('gift-plan-summary-item--attention')"
        )
