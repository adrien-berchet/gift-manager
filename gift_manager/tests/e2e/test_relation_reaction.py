"""Browser tests for rating how a recipient reacted to a gift plan."""

from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.test_dashboard_layout import login
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import RelationFactory


def make_plan(seed_data_e2e, *, gift_name, status, due_in_days=None, event=True):
    relation = RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name=gift_name, shared_with=[seed_data_e2e.alice]),
        event=seed_data_e2e.events["christmas"] if event else None,
        status=seed_data_e2e.statuses[status],
        due_date=None
        if due_in_days is None
        else timezone.localdate() + timedelta(days=due_in_days),
        comment="",
    )
    create_or_update_permission(
        seed_data_e2e.alice, relation, permission_level=PermissionLevel.OWNER
    )
    return relation


def open_page(page: Page, live_server, path: str):
    login(page, live_server.url)
    page.goto(f"{live_server.url}{path}", wait_until="networkidle")
    page.wait_for_function("typeof window.htmx?.process === 'function'")


def pick_stars(page: Page, rating: int):
    page.locator(f"#editPanel label[for$='reaction_rating_{rating}']").click()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestRelationReactionWorkflow:
    def test_given_prompt_saves_rating_and_note(self, page: Page, live_server, seed_data_e2e):
        relation = make_plan(
            seed_data_e2e, gift_name="Reaction Gift", status="planned", due_in_days=1
        )
        open_page(page, live_server, "/")

        card = page.locator(
            ".dashboard-action-group--upcoming .gift-plan-card", has_text="Reaction Gift"
        )
        card.locator("[data-action='quick-given']").click()

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("Their reaction")
        pick_stars(page, 4)
        panel.locator("textarea[name='reaction_note']").fill("Big smile")
        panel.locator("button[type='submit']").click()

        expect(panel).not_to_be_visible()
        relation.refresh_from_db()
        assert relation.reaction_rating == 4
        assert relation.reaction_note == "Big smile"
        # A rated plan does not wait for a reaction anymore.
        expect(page.locator(".dashboard-action-group--reaction")).to_have_count(0)

    def test_skipped_prompt_leaves_plan_awaiting_reaction(
        self, page: Page, live_server, seed_data_e2e
    ):
        relation = make_plan(
            seed_data_e2e, gift_name="Skipped Gift", status="planned", due_in_days=1
        )
        open_page(page, live_server, "/")

        page.locator(
            ".dashboard-action-group--upcoming .gift-plan-card", has_text="Skipped Gift"
        ).locator("[data-action='quick-given']").click()
        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()
        panel.get_by_role("button", name="Skip").click()
        expect(panel).not_to_be_visible()

        relation.refresh_from_db()
        assert relation.reaction_rating is None

        group = page.locator(".dashboard-action-group--reaction")
        card = group.locator(".gift-plan-card", has_text="Skipped Gift")
        expect(card).to_be_visible()
        # The card itself offers one-click stars, no panel needed.
        card.locator("label[for$='-5']").click()
        expect(group.locator(".gift-plan-card", has_text="Skipped Gift")).to_have_count(0)
        expect(panel).not_to_be_visible()
        relation.refresh_from_db()
        assert relation.reaction_rating == 5

    def test_abandon_prompt_uses_estimate_wording(self, page: Page, live_server, seed_data_e2e):
        relation = make_plan(seed_data_e2e, gift_name="Abandoned Gift", status="idea", event=False)
        open_page(page, live_server, "/relations/")

        card = page.locator(".gift-plan-card", has_text="Abandoned Gift").first
        card.locator("[data-action='quick-abandoned']").click()

        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("How much would they have liked it?")
        pick_stars(page, 1)
        panel.locator("textarea[name='reaction_note']").fill("Too expensive")
        panel.locator("button[type='submit']").click()

        expect(panel).not_to_be_visible()
        relation.refresh_from_db()
        assert relation.reaction_rating == 1
        assert relation.reaction_note == "Too expensive"

    def test_edit_form_toggles_reaction_section_with_status(
        self, page: Page, live_server, seed_data_e2e
    ):
        relation = make_plan(
            seed_data_e2e, gift_name="Toggle Gift", status="planned", due_in_days=20
        )
        open_page(page, live_server, "/relations/")

        page.locator(".gift-plan-card", has_text="Toggle Gift").first.locator(
            "[data-action='edit']"
        ).first.click()
        panel = page.locator("#editPanel")
        section = panel.locator("[data-reaction-fields]")
        expect(panel.locator("select[name='status']")).to_be_visible()
        expect(section).to_be_hidden()

        panel.locator("select[name='status']").select_option(
            label=str(seed_data_e2e.statuses["given"])
        )
        expect(section).to_be_visible()
        pick_stars(page, 3)
        panel.locator("button[type='submit']").first.click()

        expect(panel).not_to_be_visible()
        relation.refresh_from_db()
        assert relation.status == seed_data_e2e.statuses["given"]
        assert relation.reaction_rating == 3

    def test_workspace_card_rates_once_then_edits_through_the_panel(
        self, page: Page, live_server, seed_data_e2e
    ):
        relation = make_plan(seed_data_e2e, gift_name="Card Rated Gift", status="given")
        open_page(page, live_server, "/relations/")

        card = page.locator(".gift-plan-card", has_text="Card Rated Gift")
        card.locator("label[for$='-4']").click()

        expect(card.locator("[data-rating-inline]")).to_have_count(0)
        expect(card.locator(".rating-stars")).to_have_attribute("aria-label", "4 out of 5")
        relation.refresh_from_db()
        assert relation.reaction_rating == 4

        # A rated card cannot be re-rated by a stray click; it needs the panel.
        card.get_by_role("link", name="Edit reaction").click()
        panel = page.locator("#editPanel")
        expect(panel).to_be_visible()
        pick_stars(page, 2)
        panel.locator("button[type='submit']").click()
        expect(panel).not_to_be_visible()
        relation.refresh_from_db()
        assert relation.reaction_rating == 2

    def test_abandoned_card_stars_use_estimate_tooltip(
        self, page: Page, live_server, seed_data_e2e
    ):
        make_plan(seed_data_e2e, gift_name="Abandoned Card", status="abandoned")
        open_page(page, live_server, "/relations/")

        card = page.locator(".gift-plan-card", has_text="Abandoned Card")
        expect(card.locator(".rating-input-stars")).to_have_attribute(
            "title", "How much would they have liked it?"
        )
