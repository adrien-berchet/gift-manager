"""Dashboard layout end-to-end tests."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def remove_scripts(content: str) -> str:
    """Remove blocking scripts from static HTML used for layout assertions."""
    return SCRIPT_TAG_RE.sub("", content)


def login(page: Page, base_url: str):
    """Log in as Alice for live dashboard checks."""
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="login"]', "alice")
    page.fill('input[name="password"]', "alice_password")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=10_000)
    assert "/accounts/login/" not in page.url, f"Still on login page: {page.url}"


def create_dashboard_action_plans(
    seed_data_e2e,
    *,
    prefix: str,
    count: int,
    due_soon: bool,
    first_comment: str = "",
):
    """Create deterministic dashboard action cards for layout checks."""
    today = timezone.localdate()
    for index in range(count):
        RelationFactory(
            person=seed_data_e2e.persons["dad"],
            gift=GiftFactory(name=f"{prefix} {index}"),
            event=None,
            status=seed_data_e2e.statuses["planned"],
            due_date=today + timedelta(days=index + 1) if due_soon else None,
            comment=first_comment if index == 0 else "",
            shared_with=[seed_data_e2e.alice],
        )


def get_paginated_layout_metrics(page: Page, group_key: str) -> dict:
    """Return rendered pagination metrics for a dashboard action group."""
    group = page.locator(f".dashboard-action-group--{group_key}").first
    list_grid = group.locator(".dashboard-action-list--paginated").first

    expect(group).to_be_visible()
    expect(list_grid).to_be_visible()

    return list_grid.evaluate(
        """list => {
            const group = list.closest('[data-dashboard-action-paginated]');
            const cards = Array.from(list.querySelectorAll('[data-dashboard-action-card]'));
            const visibleCards = cards.filter((card) => !card.hidden);
            const styles = getComputedStyle(list);
            const groupRect = group.getBoundingClientRect();
            const positions = visibleCards.map((card) => {
                const rect = card.getBoundingClientRect();
                return { x: rect.x, y: rect.y };
            });
            const visibleHeights = visibleCards.map((card) =>
                card.getBoundingClientRect().height
            );
            const noteMetrics = visibleCards.map((card) => {
                const note = card.querySelector('.dashboard-action-note');
                if (!note) return null;
                return {
                    clientHeight: note.clientHeight,
                    scrollHeight: note.scrollHeight,
                    lineHeight: Number.parseFloat(getComputedStyle(note).lineHeight),
                    text: note.textContent.trim(),
                };
            }).filter(Boolean);

            return {
                cardCount: cards.length,
                visibleCount: visibleCards.length,
                hiddenCount: cards.length - visibleCards.length,
                columnCount: styles.gridTemplateColumns
                    .split(' ')
                    .filter((column) => column && column !== 'none').length,
                overflowY: styles.overflowY,
                scrollHeight: list.scrollHeight,
                clientHeight: list.clientHeight,
                minHeight: styles.minHeight,
                groupHeight: groupRect.height,
                pageSize: Number.parseInt(group.dataset.dashboardPageSize || '0', 10),
                paginationHidden: group.querySelector('[data-dashboard-pagination]')?.hidden,
                pageStatus: group.querySelector('[data-dashboard-page-status]')?.textContent.trim(),
                previousDisabled: group.querySelector('[data-dashboard-page="previous"]')?.disabled,
                nextDisabled: group.querySelector('[data-dashboard-page="next"]')?.disabled,
                visibleTitles: visibleCards.map((card) =>
                    card.querySelector('.dashboard-action-title')?.textContent.trim()
                ),
                positions,
                visibleHeights,
                noteMetrics,
            };
        }"""
    )


def assert_paginated_action_layout(page: Page, group_key: str):
    """Assert a dashboard action group uses two-row pagination."""
    pagination = page.locator(f".dashboard-action-group--{group_key} [data-dashboard-pagination]")
    expect(pagination).to_be_visible()

    metrics = get_paginated_layout_metrics(page, group_key)
    assert metrics["columnCount"] >= 2
    assert metrics["cardCount"] > metrics["columnCount"] * 2
    assert metrics["visibleCount"] == metrics["columnCount"] * 2
    assert metrics["hiddenCount"] > 0
    assert metrics["overflowY"] != "auto"
    assert metrics["scrollHeight"] <= metrics["clientHeight"] + 1
    assert metrics["previousDisabled"] is True
    assert metrics["nextDisabled"] is False
    assert metrics["pageStatus"].startswith("1 / ")
    assert metrics["minHeight"] == "0px"
    assert max(metrics["visibleHeights"]) - min(metrics["visibleHeights"]) <= 1
    assert any(note["scrollHeight"] > note["clientHeight"] for note in metrics["noteMetrics"])
    assert all(note["clientHeight"] <= note["lineHeight"] + 1 for note in metrics["noteMetrics"])

    positions = metrics["positions"]
    assert positions[1]["x"] > positions[0]["x"]
    assert abs(positions[1]["y"] - positions[0]["y"]) <= 2
    assert positions[metrics["columnCount"]]["y"] > positions[0]["y"]

    first_page_title = metrics["visibleTitles"][0]
    page.locator(f".dashboard-action-group--{group_key} [data-dashboard-page='next']").click()

    next_metrics = get_paginated_layout_metrics(page, group_key)
    assert next_metrics["visibleTitles"][0] != first_page_title
    assert next_metrics["previousDisabled"] is False
    assert next_metrics["pageStatus"].startswith("2 / ")
    assert next_metrics["scrollHeight"] <= next_metrics["clientHeight"] + 1
    assert next_metrics["minHeight"] == "0px"
    assert max(next_metrics["visibleHeights"]) - min(next_metrics["visibleHeights"]) <= 1

    page.locator(f".dashboard-action-group--{group_key} [data-dashboard-page='previous']").click()
    previous_metrics = get_paginated_layout_metrics(page, group_key)
    assert previous_metrics["visibleTitles"][0] == first_page_title
    assert previous_metrics["minHeight"] == "0px"

    last_metrics = previous_metrics
    before_last_metrics = previous_metrics
    for _ in range(10):
        if last_metrics["nextDisabled"]:
            break
        before_last_metrics = last_metrics
        page.locator(f".dashboard-action-group--{group_key} [data-dashboard-page='next']").click()
        last_metrics = get_paginated_layout_metrics(page, group_key)

    assert last_metrics["nextDisabled"] is True
    assert last_metrics["visibleCount"] == 1
    assert last_metrics["minHeight"] != "0px"
    assert abs(last_metrics["clientHeight"] - before_last_metrics["clientHeight"]) <= 1
    assert abs(last_metrics["groupHeight"] - before_last_metrics["groupHeight"]) <= 1
    assert max(last_metrics["visibleHeights"]) < last_metrics["clientHeight"] - 1

    page.locator(f".dashboard-action-group--{group_key} [data-dashboard-page='previous']").click()
    unlocked_metrics = get_paginated_layout_metrics(page, group_key)
    assert unlocked_metrics["minHeight"] == "0px"


@pytest.mark.django_db
@pytest.mark.frontend
@pytest.mark.e2e
class TestDashboardLayout:
    """Browser checks for dashboard-specific responsive layout."""

    @pytest.mark.django_db(transaction=True)
    def test_paginated_action_groups_wrap_and_page(self, page: Page, live_server, seed_data_e2e):
        """Due soon and needs-details groups should wrap, then paginate."""
        page.set_viewport_size({"width": 1280, "height": 900})
        tall_card_comment = (
            "This deliberately long note should be clipped inside the fixed-size "
            "dashboard card instead of expanding the row. "
            "ExtremelyLongUnbrokenCommentSegmentForDashboardCardClippingVerification"
        )

        create_dashboard_action_plans(
            seed_data_e2e,
            prefix="Due soon dashboard gift",
            count=16,
            due_soon=True,
            first_comment=tall_card_comment,
        )
        create_dashboard_action_plans(
            seed_data_e2e,
            prefix="Needs details dashboard gift",
            count=16,
            due_soon=False,
            first_comment=tall_card_comment,
        )

        login(page, live_server.url)
        page.goto(f"{live_server.url}/", wait_until="domcontentloaded")

        initial_upcoming_metrics = get_paginated_layout_metrics(page, "upcoming")
        initial_incomplete_metrics = get_paginated_layout_metrics(page, "incomplete")
        assert initial_upcoming_metrics["pageSize"] > 0
        assert initial_incomplete_metrics["pageSize"] > 0

        upcoming_additions = (1 - initial_upcoming_metrics["cardCount"]) % initial_upcoming_metrics[
            "pageSize"
        ]
        incomplete_additions = (
            1 - initial_incomplete_metrics["cardCount"]
        ) % initial_incomplete_metrics["pageSize"]

        if upcoming_additions:
            create_dashboard_action_plans(
                seed_data_e2e,
                prefix="Due soon short final page gift",
                count=upcoming_additions,
                due_soon=True,
            )

        if incomplete_additions:
            create_dashboard_action_plans(
                seed_data_e2e,
                prefix="Needs details short final page gift",
                count=incomplete_additions,
                due_soon=False,
            )

        if upcoming_additions or incomplete_additions:
            page.reload(wait_until="domcontentloaded")

        action_grid = page.locator(".action-group-grid").first
        upcoming_group = page.locator(".dashboard-action-group--upcoming").first
        incomplete_group = page.locator(".dashboard-action-group--incomplete").first

        expect(action_grid).to_be_visible()
        expect(upcoming_group).to_be_visible()
        expect(incomplete_group).to_be_visible()

        grid_box = action_grid.bounding_box()
        group_box = upcoming_group.bounding_box()
        incomplete_box = incomplete_group.bounding_box()
        assert grid_box is not None
        assert group_box is not None
        assert incomplete_box is not None
        assert group_box["width"] >= grid_box["width"] - 2
        assert incomplete_box["width"] >= grid_box["width"] - 2

        assert_paginated_action_layout(page, "upcoming")
        assert_paginated_action_layout(page, "incomplete")

    @pytest.mark.django_db(transaction=True)
    def test_dashboard_refreshes_after_list_update_for_new_gift_plan(
        self, page: Page, live_server, seed_data_e2e
    ):
        """A new dashboard-relevant gift plan should appear without a reload."""
        login(page, live_server.url)
        page.goto(f"{live_server.url}/", wait_until="domcontentloaded")

        dashboard_live = page.locator("#dashboard-live")
        expect(dashboard_live).to_be_visible()
        expect(dashboard_live).not_to_contain_text("Dashboard Refresh Kite")

        RelationFactory(
            person=seed_data_e2e.persons["dad"],
            gift=GiftFactory(name="Dashboard Refresh Kite"),
            event=None,
            status=seed_data_e2e.statuses["planned"],
            due_date=None,
            comment="Created after the dashboard loaded",
            shared_with=[seed_data_e2e.alice],
        )

        refreshed = page.evaluate(
            """() => new Promise((resolve) => {
                window.htmx = {
                    trigger(container, eventName) {
                        if (eventName !== 'refresh') return;

                        const url = new URL(
                            container.getAttribute('hx-get') || window.location.href,
                            window.location.href
                        );
                        const selector = container.getAttribute('hx-select');

                        fetch(url.toString(), {
                            credentials: 'same-origin',
                            headers: { 'HX-Request': 'true' }
                        })
                            .then((response) => response.text())
                            .then((html) => {
                                const parsed = new DOMParser().parseFromString(html, 'text/html');
                                const replacement = parsed.querySelector(selector);
                                if (replacement) {
                                    container.replaceWith(replacement);
                                    window.GiftManagerDashboardPagination?.init(replacement);
                                    document.dispatchEvent(
                                        new CustomEvent('dashboard-live:refreshed')
                                    );
                                }
                            })
                            .catch(() => resolve(false));
                    }
                };

                const timeout = setTimeout(() => resolve(false), 5000);
                document.addEventListener('dashboard-live:refreshed', () => {
                    clearTimeout(timeout);
                    resolve(true);
                }, { once: true });
                document.dispatchEvent(new CustomEvent('list:update'));
            })"""
        )

        assert refreshed is True
        expect(page.locator("#dashboard-live")).to_contain_text("Dashboard Refresh Kite")

    def test_incomplete_action_cards_use_responsive_compact_layout(
        self, page: Page, client, seed_data_e2e
    ):
        """Incomplete gift plans should render as responsive compact task rows."""
        page.set_viewport_size({"width": 1280, "height": 900})
        create_dashboard_action_plans(
            seed_data_e2e,
            prefix="Compact layout gift",
            count=2,
            due_soon=False,
        )

        client.force_login(seed_data_e2e.alice)
        response = client.get(reverse("gift_manager:home"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "dashboard-action-group--incomplete" in content
        assert "dashboard-action-list dashboard-action-list--responsive" in content
        page.set_content(remove_scripts(content), wait_until="domcontentloaded")

        list_grid = page.locator(
            ".dashboard-action-group--incomplete .dashboard-action-list--responsive"
        ).first
        cards = list_grid.locator(".dashboard-action-item--incomplete")
        card = cards.first
        title = card.locator(".dashboard-action-title")
        detail_action = card.locator("[data-action='detail']")

        expect(list_grid).to_be_visible()
        expect(card).to_be_visible()
        expect(title).to_be_visible()
        expect(detail_action).to_be_visible()
        assert cards.count() >= 2

        desktop_columns = list_grid.evaluate(
            "el => getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length"
        )
        assert desktop_columns >= 2

        desktop_areas = card.evaluate("el => getComputedStyle(el).gridTemplateAreas")
        assert '"title footer"' in desktop_areas
        assert '"badges footer"' in desktop_areas

        first_card_box = cards.nth(0).bounding_box()
        second_card_box = cards.nth(1).bounding_box()
        title_box = title.bounding_box()
        detail_box = detail_action.bounding_box()
        assert first_card_box is not None
        assert second_card_box is not None
        assert title_box is not None
        assert detail_box is not None
        assert second_card_box["x"] > first_card_box["x"]
        assert abs(second_card_box["y"] - first_card_box["y"]) <= 2
        assert title_box["x"] + title_box["width"] <= detail_box["x"] + 1

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(100)

        mobile_columns = list_grid.evaluate(
            "el => getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length"
        )
        assert mobile_columns == 1

        mobile_areas = card.evaluate("el => getComputedStyle(el).gridTemplateAreas")
        assert '"title"' in mobile_areas
        assert '"footer"' in mobile_areas

        mobile_first_card_box = cards.nth(0).bounding_box()
        mobile_second_card_box = cards.nth(1).bounding_box()
        mobile_title_box = title.bounding_box()
        mobile_detail_box = detail_action.bounding_box()
        assert mobile_first_card_box is not None
        assert mobile_second_card_box is not None
        assert mobile_title_box is not None
        assert mobile_detail_box is not None
        assert mobile_second_card_box["y"] > mobile_first_card_box["y"]
        assert mobile_detail_box["y"] > mobile_title_box["y"]
