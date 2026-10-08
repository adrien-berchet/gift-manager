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


def choose_mode(panel, label: str):
    """Pick one of a step's paths ("New person", "Existing gift", "No event", ...)."""
    panel.locator("label", has_text=label).click()


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

        expect(panel.get_by_text("New gift", exact=True)).to_be_visible()
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("Guided Scarf")
        click_next(panel)

        expect(panel.get_by_text("New event", exact=True)).to_be_visible()
        choose_mode(panel, "New event")
        panel.locator("#id_new_event-name").fill("Guided Housewarming")
        # The date input is replaced by a flatpickr widget: set the date through its API
        page.evaluate(
            "document.getElementById('id_new_event-date')._flatpickr.setDate('2031-05-04', true)"
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

        expect(panel.get_by_text("Select a gift.").first).to_be_visible()
        expect(panel.locator("li[aria-current='step']")).to_contain_text("Gift")

    def test_enter_advances_and_back_keeps_values(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)

        choose_mode(panel, "New gift")

        panel.locator("#id_new_gift-name").fill("Keyboard Gift")
        panel.locator("#id_new_gift-name").press("Enter")

        expect(panel.get_by_text("New event", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Back").click()
        expect(panel.locator("#id_new_gift-name")).to_have_value("Keyboard Gift")
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
        expect(panel.get_by_text("New gift", exact=True)).to_be_visible()

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
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("Prompt Free Gift")
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


def open_details(panel, label: str = "More details"):
    """Open the "More details" disclosure of the current step named ``label``."""
    panel.get_by_text(label, exact=True).click()


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGuidedPlanFullData:
    def test_guided_flow_creates_new_person_gift_and_event_with_details(
        self, page: Page, live_server, seed_data_e2e
    ):
        panel = open_guided_flow(page, live_server)

        choose_mode(panel, "New person")

        panel.locator("#id_new_person-first_name").fill("Anna")
        open_details(panel)
        panel.locator("#id_new_person-family_name").fill("Martin")
        panel.locator("#id_new_person-email_address").fill("anna@example.com")
        panel.locator("#id_new_person-notes").fill("Likes tea")
        panel.locator("#id_new_person-groups").select_option(label="Friends")
        click_next(panel)

        expect(panel.get_by_text("New gift", exact=True)).to_be_visible()
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("Guided Scarf")
        open_details(panel)
        panel.locator("#id_new_gift-comment").fill("Soft wool")
        panel.locator("#id_new_gift-url").fill("https://example.com/scarf")
        panel.locator("#id_new_gift-price").fill("19.90")
        click_next(panel)

        expect(panel.get_by_text("New event", exact=True)).to_be_visible()
        choose_mode(panel, "New event")
        panel.locator("#id_new_event-name").fill("Guided Anniversary")
        page.evaluate(
            "document.getElementById('id_new_event-date')._flatpickr.setDate('2031-05-04', true)"
        )
        open_details(panel, "More event details")
        panel.get_by_label("Repeating").check()
        panel.locator("#id_new_event-recurrence").select_option("yearly")
        open_details(panel, "More gift plan details")
        panel.locator("#id_status").select_option(label="Planned")
        panel.locator("#id_is_surprise").uncheck()
        panel.get_by_role("button", name="Create gift plan").click()

        expect(panel).to_be_hidden()
        plan = Relation.objects.get(gift__name="Guided Scarf")
        person = plan.person
        assert (person.first_name, person.family_name, person.notes) == (
            "Anna",
            "Martin",
            "Likes tea",
        )
        assert list(person.groups.values_list("name", flat=True)) == ["Friends"]
        assert (str(plan.gift.price), plan.gift.url, plan.gift.comment) == (
            "19.90",
            "https://example.com/scarf",
            "Soft wool",
        )
        assert (plan.event.schedule_type, plan.event.recurrence) == (
            Event.ScheduleType.RECURRING,
            "yearly",
        )
        assert plan.status.status_en == "Planned"
        assert plan.is_surprise is False

    def test_back_keeps_multi_valued_selection(self, page: Page, live_server, seed_data_e2e):
        panel = open_guided_flow(page, live_server)
        choose_mode(panel, "New person")
        panel.locator("#id_new_person-first_name").fill("Anna")
        open_details(panel)
        panel.locator("#id_new_person-groups").select_option(label=["Family", "Friends"])
        click_next(panel)
        expect(panel.get_by_text("New gift", exact=True)).to_be_visible()

        panel.get_by_role("button", name="Back").click()

        expect(panel.locator("#id_new_person-first_name")).to_have_value("Anna")
        selected = panel.locator("#id_new_person-groups").evaluate(
            "select => [...select.selectedOptions].map(option => option.textContent.trim())"
        )
        assert sorted(selected) == ["Family", "Friends"]

    def test_new_object_error_opens_details(self, page: Page, live_server, seed_data_e2e):
        panel = open_guided_flow(page, live_server)
        choose_mode(panel, "New person")
        panel.locator("#id_new_person-first_name").fill("Anna")
        open_details(panel)
        panel.locator("#id_new_person-birthday_day").select_option("31")
        panel.locator("#id_new_person-birthday_month").select_option("2")

        click_next(panel)

        expect(panel.locator("details.guided-new-details")).to_have_attribute("open", "")
        expect(panel.get_by_text("Enter a valid date.").first).to_be_visible()

    def test_step_three_separates_the_event_from_the_gift_plan(
        self, page: Page, live_server, seed_data_e2e
    ):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("Sections Gift")
        click_next(panel)

        event_section = panel.locator(".guided-section--event")
        plan_section = panel.locator(".guided-section--plan")
        expect(event_section.get_by_role("heading", name="Event")).to_be_visible()
        expect(plan_section.get_by_role("heading", name="Gift Plan")).to_be_visible()
        expect(event_section.locator("#id_new_event-comment")).to_have_count(1)
        expect(plan_section.locator("#id_comment")).to_have_count(1)
        expect(event_section.get_by_text("Event comment")).to_have_count(1)
        expect(plan_section.get_by_text("Gift plan comment")).to_have_count(1)
        expect(plan_section.locator("#id_status")).to_be_visible()
        expect(plan_section.locator("#id_is_surprise")).to_be_hidden()
        expect(panel.locator("li[aria-current='step']")).to_contain_text("Event and gift plan")


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGuidedPlanChoice:
    def test_only_the_chosen_path_is_shown(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)

        expect(panel.locator("#id_gift")).to_be_visible()
        expect(panel.locator("#id_new_gift-name")).to_be_hidden()

        choose_mode(panel, "New gift")

        expect(panel.locator("#id_new_gift-name")).to_be_visible()
        expect(panel.locator("#id_gift")).to_be_hidden()

        choose_mode(panel, "Existing gift")

        expect(panel.locator("#id_gift")).to_be_visible()
        expect(panel.locator("#id_new_gift-name")).to_be_hidden()

    def test_typed_values_survive_switching_paths(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("Kept Gift")

        choose_mode(panel, "Existing gift")
        choose_mode(panel, "New gift")

        expect(panel.locator("#id_new_gift-name")).to_have_value("Kept Gift")

    def test_no_event_creates_a_plan_without_event(self, page: Page, live_server, seed_data_e2e):
        dad = seed_data_e2e.persons["dad"]
        panel = open_guided_flow(page, live_server)
        panel.locator("#id_recipient").select_option(f"person:{dad.person_id}")
        click_next(panel)
        choose_mode(panel, "New gift")
        panel.locator("#id_new_gift-name").fill("No Event Gift")
        click_next(panel)

        choose_mode(panel, "No event")
        expect(panel.locator("#id_event")).to_be_hidden()
        expect(panel.locator("#id_new_event-name")).to_be_hidden()
        panel.get_by_role("button", name="Create gift plan").click()

        expect(panel).to_be_hidden()
        plan = Relation.objects.get(gift__name="No Event Gift")
        assert plan.event is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGuidedPlanErrors:
    def test_validation_error_focuses_the_summary_and_keeps_the_input_protected(
        self, page: Page, live_server, seed_data_e2e
    ):
        panel = open_guided_flow(page, live_server)
        choose_mode(panel, "New person")
        panel.locator("#id_new_person-first_name").fill("Anna")
        open_details(panel)
        panel.locator("#id_new_person-birthday_day").select_option("31")
        panel.locator("#id_new_person-birthday_month").select_option("2")

        click_next(panel)

        summary = panel.locator(".form-error-summary").first
        expect(summary).to_be_visible()
        expect(summary).to_be_focused()
        panel.get_by_role("button", name="Cancel").click()
        expect(page.locator("#unsaved-changes-modal")).to_be_visible()
