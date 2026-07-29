"""Dashboard layout end-to-end tests."""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def remove_scripts(content: str) -> str:
    """Remove blocking scripts from static HTML used for layout assertions."""
    return SCRIPT_TAG_RE.sub("", content)


@pytest.mark.django_db
@pytest.mark.frontend
@pytest.mark.e2e
class TestDashboardLayout:
    """Browser checks for dashboard-specific responsive layout."""

    def test_incomplete_action_cards_use_responsive_compact_layout(
        self, page: Page, client, seed_data_e2e
    ):
        """Incomplete gift plans should render as responsive compact task rows."""
        page.set_viewport_size({"width": 1280, "height": 900})

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
