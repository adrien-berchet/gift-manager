"""Gift-plan workspace section pagination end-to-end tests."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory


def login(page: Page, base_url: str):
    """Log in as Alice."""
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="login"]', "alice")
    page.fill('input[name="password"]', "alice_password")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=10_000)
    assert "/accounts/login/" not in page.url, f"Still on login page: {page.url}"


def create_idea_plans(seed_data_e2e, *, person_key: str, prefix: str, count: int):
    """Create undated Idea plans for one recipient, shared with Alice."""
    for index in range(count):
        RelationFactory(
            person=seed_data_e2e.persons[person_key],
            gift=GiftFactory(name=f"{prefix} {index:02d}"),
            event=None,
            status=seed_data_e2e.statuses["idea"],
            due_date=None,
            comment="",
            shared_with=[seed_data_e2e.alice],
        )


def section_metrics(page: Page, group_key: str) -> dict:
    """Return the paging state of a workspace urgency section."""
    return page.locator(f"#gift-plan-group-{group_key}").evaluate(
        """section => {
            const list = section.querySelector('[data-gift-plan-group-list]');
            const cards = Array.from(list.querySelectorAll('.gift-plan-card'));
            const shown = cards.filter((card) => card.getBoundingClientRect().height > 0);
            const columns = getComputedStyle(list).gridTemplateColumns
                .split(' ')
                .filter((column) => column && column !== 'none').length;
            const pagination = section.querySelector('[data-gift-plan-group-pagination]');
            return {
                cardCount: cards.length,
                columns,
                shownTitles: shown.map((card) =>
                    card.querySelector('.gift-plan-card-title').textContent.trim()
                ),
                shownRecipients: shown.map((card) => card.dataset.recipientKey),
                paginationHidden: pagination.hidden,
                status: section.querySelector('[data-gift-plan-group-page-status]')
                    .textContent.trim(),
            };
        }"""
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestRelationWorkspacePagination:
    """Browser checks for paged workspace sections."""

    def test_sections_page_through_every_card(self, page: Page, live_server, seed_data_e2e):
        """A long section shows two rows per page and still reaches every card."""
        create_idea_plans(seed_data_e2e, person_key="dad", prefix="Paged idea", count=20)
        page.set_viewport_size({"width": 1280, "height": 900})
        login(page, live_server.url)
        page.goto(f"{live_server.url}{reverse('gift_manager:relations')}", wait_until="networkidle")

        metrics = section_metrics(page, "ideas")
        page_size = metrics["columns"] * 2
        assert metrics["columns"] >= 2
        assert metrics["cardCount"] > page_size
        assert len(metrics["shownTitles"]) == page_size
        assert metrics["paginationHidden"] is False
        page_count = -(-metrics["cardCount"] // page_size)
        assert metrics["status"] == f"1 / {page_count}"

        section = page.locator("#gift-plan-group-ideas")
        seen_titles = list(metrics["shownTitles"])
        for page_number in range(2, page_count + 1):
            section.locator("[data-gift-plan-group-page='next']").click()
            metrics = section_metrics(page, "ideas")
            assert metrics["status"] == f"{page_number} / {page_count}"
            seen_titles.extend(metrics["shownTitles"])

        expect(section.locator("[data-gift-plan-group-page='next']")).to_be_disabled()
        assert len(seen_titles) == len(set(seen_titles)) == metrics["cardCount"]

        last_section = page.locator(".gift-plan-urgency-section").last
        last_section.scroll_into_view_if_needed()
        expect(last_section).to_be_in_viewport()

    def test_short_last_page_keeps_the_layout_still(self, page: Page, live_server, seed_data_e2e):
        """A last page with a single row still reserves both rows, so nothing below moves."""
        page.set_viewport_size({"width": 1280, "height": 900})
        login(page, live_server.url)
        page.goto(f"{live_server.url}{reverse('gift_manager:relations')}", wait_until="networkidle")
        columns = section_metrics(page, "ideas")["columns"]
        # One full page plus a single card: the last page holds one row with one card.
        existing = section_metrics(page, "ideas")["cardCount"]
        create_idea_plans(
            seed_data_e2e, person_key="dad", prefix="Still idea", count=columns * 2 + 1 - existing
        )
        page.reload(wait_until="networkidle")

        section = page.locator("#gift-plan-group-ideas")
        pagination = section.locator("[data-gift-plan-group-pagination]")
        next_section = page.locator("#gift-plan-group-ideas + .gift-plan-urgency-section")

        def positions():
            return {
                "section": section.evaluate("el => el.getBoundingClientRect().height"),
                "pagination": pagination.evaluate(
                    "el => el.getBoundingClientRect().top + window.scrollY"
                ),
                "next": next_section.evaluate(
                    "el => el.getBoundingClientRect().top + window.scrollY"
                ),
            }

        first = positions()
        section.locator("[data-gift-plan-group-page='next']").click()
        metrics = section_metrics(page, "ideas")
        assert metrics["status"] == "2 / 2"
        assert len(metrics["shownTitles"]) == 1
        last = positions()
        for key, value in first.items():
            assert abs(last[key] - value) <= 1, (key, first, last)

    def test_recipient_filter_pages_matching_cards_only(
        self, page: Page, live_server, seed_data_e2e
    ):
        """Filtering restarts on page one and pages only the matching recipient's cards."""
        create_idea_plans(seed_data_e2e, person_key="dad", prefix="Dad idea", count=20)
        create_idea_plans(seed_data_e2e, person_key="mom", prefix="Mom idea", count=3)
        mom_key = f"person:{seed_data_e2e.persons['mom'].person_id}"
        page.set_viewport_size({"width": 1280, "height": 900})
        login(page, live_server.url)
        page.goto(f"{live_server.url}{reverse('gift_manager:relations')}", wait_until="networkidle")

        section = page.locator("#gift-plan-group-ideas")
        section.locator("[data-gift-plan-group-page='next']").click()
        assert section_metrics(page, "ideas")["status"].startswith("2 / ")

        section.locator(".gift-plan-recipient-filter-trigger").click()
        page.locator(".gift-plan-recipient-filter-option", has_text="Mom").first.click()

        metrics = section_metrics(page, "ideas")
        assert metrics["paginationHidden"] is True
        assert metrics["status"] == "1 / 1"
        assert set(metrics["shownRecipients"]) == {mom_key}
        assert {"Mom idea 00", "Mom idea 01", "Mom idea 02"} <= set(metrics["shownTitles"])

    def test_focused_section_lists_all_cards(self, page: Page, live_server, seed_data_e2e):
        """The dashboard's focused view keeps a single, unpaged section."""
        create_idea_plans(seed_data_e2e, person_key="dad", prefix="Focused idea", count=20)
        page.set_viewport_size({"width": 1280, "height": 900})
        login(page, live_server.url)
        page.goto(
            f"{live_server.url}{reverse('gift_manager:relations')}?focus=ideas",
            wait_until="networkidle",
        )

        section = page.locator("#gift-plan-group-ideas")
        expect(section.locator("[data-gift-plan-group-pagination]")).to_have_count(0)
        cards = section.locator(".gift-plan-card")
        assert cards.count() >= 20
        for index in range(cards.count()):
            expect(cards.nth(index)).to_be_attached()
            assert cards.nth(index).get_attribute("hidden") is None
