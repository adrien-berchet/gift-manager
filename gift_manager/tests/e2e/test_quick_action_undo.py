"""Browser tests for the Undo toast of gift-plan card quick actions."""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.test_relation_reaction import make_plan
from gift_manager.tests.e2e.test_relation_reaction import open_page


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestQuickActionUndo:
    def test_undo_restores_status_and_closes_reaction_prompt(
        self, page: Page, live_server, seed_data_e2e
    ):
        relation = make_plan(seed_data_e2e, gift_name="Undo Gift", status="planned", due_in_days=1)
        open_page(page, live_server, "/")
        card = page.locator(
            ".dashboard-action-group--upcoming .gift-plan-card", has_text="Undo Gift"
        )
        card.locator("[data-action='quick-given']").click()

        toast = page.locator(".toast", has_text="marked as given")
        undo_button = toast.get_by_role("button", name="Undo")
        expect(undo_button).to_be_visible()
        expect(toast).to_have_attribute("aria-live", "polite")
        expect(page.locator("#editPanel")).to_be_visible()

        undo_button.focus()
        page.keyboard.press("Enter")

        expect(page.locator("#editPanel")).not_to_be_visible()
        expect(page.locator(".toast", has_text="Change undone")).to_be_visible()
        expect(
            page.locator(
                ".dashboard-action-group--upcoming .gift-plan-card", has_text="Undo Gift"
            )
        ).to_be_visible()
        relation.refresh_from_db()
        assert relation.status == seed_data_e2e.statuses["planned"]

    def test_undo_reports_a_plan_changed_meanwhile(self, page: Page, live_server, seed_data_e2e):
        relation = make_plan(seed_data_e2e, gift_name="Stale Gift", status="planned", due_in_days=1)
        open_page(page, live_server, "/")
        card = page.locator(
            ".dashboard-action-group--upcoming .gift-plan-card", has_text="Stale Gift"
        )
        card.locator("[data-action='quick-purchased']").click()
        toast = page.locator(".toast", has_text="marked as purchased")
        expect(toast).to_be_visible()

        relation.refresh_from_db()
        relation.status = seed_data_e2e.statuses["given"]
        relation.save(update_fields=["status"])
        toast.get_by_role("button", name="Undo").click()

        expect(page.locator(".toast", has_text="changed since")).to_be_visible()
        relation.refresh_from_db()
        assert relation.status == seed_data_e2e.statuses["given"]
