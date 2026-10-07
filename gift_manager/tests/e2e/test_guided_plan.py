"""Browser tests for the guided gift plan creation flow."""

from datetime import date

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import Event
from gift_manager.models import Relation
from gift_manager.tests.e2e.test_dashboard_layout import login


def open_guided_flow(page: Page, live_server):
    """Open the guided flow in the offcanvas panel from the gift plan list."""
    login(page, live_server.url)
    page.goto(f"{live_server.url}/relations/", wait_until="networkidle")
    page.wait_for_function("typeof window.htmx?.process === 'function'")
    page.locator("a[href$='/relations/guided/']:visible").first.click()
    panel = page.locator("#editPanel")
    expect(panel.locator("#id_recipient")).to_be_visible()
    return panel


def click_next(panel):
    panel.get_by_role("button", name="Next").click()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGuidedPlanWorkflow:
    def test_guided_flow_creates_plan_with_new_gift_and_event(
        self, page: Page, live_server, seed_data_e2e
    ):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)

        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)

        expect(panel.locator("#id_new_gift_name")).to_be_visible()
        panel.locator("#id_new_gift_name").fill("Guided Scarf")
        click_next(panel)

        expect(panel.locator("#id_new_event_name")).to_be_visible()
        panel.locator("#id_new_event_name").fill("Guided Housewarming")
        # The date input is replaced by a flatpickr widget: set the date through its API
        page.evaluate(
            "document.getElementById('id_new_event_date')._flatpickr.setDate('2031-05-04', true)"
        )
        panel.locator("#id_comment").fill("Wrap it nicely")
        panel.get_by_role("button", name="Create gift plan").click()

        expect(panel).to_be_hidden()
        plan = Relation.objects.get(gift__name="Guided Scarf")
        assert plan.person == dad
        assert plan.status.status_en == "Idea"
        assert plan.event.name == "Guided Housewarming"
        assert plan.event.schedule_type == Event.ScheduleType.ONE_TIME
        assert plan.due_date == date(2031, 5, 4)
        assert plan.comment == "Wrap it nicely"

    def test_validation_error_stays_on_step(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)

        click_next(panel)

        expect(panel.get_by_text("Choose a gift or enter a new gift name.").first).to_be_visible()
        expect(panel.locator("li[aria-current='step']")).to_contain_text("Gift")

    def test_enter_advances_and_back_keeps_values(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)

        panel.locator("#id_new_gift_name").fill("Keyboard Gift")
        panel.locator("#id_new_gift_name").press("Enter")

        expect(panel.locator("#id_new_event_name")).to_be_visible()
        panel.get_by_role("button", name="Back").click()
        expect(panel.locator("#id_new_gift_name")).to_have_value("Keyboard Gift")
        panel.get_by_role("button", name="Back").click()
        expect(panel.locator("#id_recipient")).to_have_value(f"person:{dad.person_id}")

    def test_empty_full_form_link_asks_before_discarding(
        self, page: Page, live_server, seed_data_e2e
    ):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        modal = page.locator("#unsaved-changes-modal")

        # Step 2 holds nothing but the answer carried from step 1: it must still be protected
        panel.get_by_role("link", name="Use an empty full form").click()
        expect(modal).to_be_visible()
        expect(modal).to_contain_text("The data you entered will be discarded.")
        expect(modal.locator("#save-changes-btn")).to_be_hidden()

        modal.locator("#keep-editing-btn").click()
        expect(modal).to_be_hidden()
        expect(panel.locator("#id_new_gift_name")).to_be_visible()

        panel.get_by_role("link", name="Use an empty full form").click()
        modal.locator("#discard-changes-btn").click()

        expect(panel.locator("#relation-form")).to_be_visible()
        expect(panel.locator("#id_recipient")).to_have_value("")

    def test_no_unsaved_prompt_after_creating_the_plan(
        self, page: Page, live_server, seed_data_e2e
    ):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        panel.locator("#id_new_gift_name").fill("Prompt Free Gift")
        click_next(panel)
        panel.get_by_role("button", name="Create gift plan").click()
        expect(panel).to_be_hidden()

        # The closed panel still holds the last step; it must not guard leaving the page
        page.locator("nav a.nav-link", has_text="Dashboard").first.click()

        expect(page.locator("#unsaved-changes-modal")).to_be_hidden()
        page.wait_for_url(lambda url: not url.rstrip("/").endswith("/relations"))

    def test_no_unsaved_prompt_after_discarding_a_later_step(
        self, page: Page, live_server, seed_data_e2e
    ):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        panel.get_by_role("button", name="Cancel").click()
        modal = page.locator("#unsaved-changes-modal")
        expect(modal).to_be_visible()
        modal.locator("#discard-changes-btn").click()
        expect(panel).to_be_hidden()

        page.locator("nav a.nav-link", has_text="Dashboard").first.click()

        expect(modal).to_be_hidden()
        page.wait_for_url(lambda url: not url.rstrip("/").endswith("/relations"))
