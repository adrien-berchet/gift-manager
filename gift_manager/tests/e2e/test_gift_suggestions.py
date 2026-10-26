"""End-to-end browser tests for gift plan suggestions.

Covers:
- Accepting a catalogue suggestion on a recipient's full detail page.
- Dismissing a suggestion on a recipient's detail page.
- Accepting a suggestion inside the offcanvas/modal detail panel opened from /recipients/.
- Responsive rendering and theme styling.
"""

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.base_test import BaseE2ETest
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory


def _status(name: str) -> RelationStatus:
    return RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})[0]


def _share(user, *objects, level=PermissionLevel.OWNER):
    for obj in objects:
        create_or_update_permission(user, obj, permission_level=level)


class TestGiftSuggestions(BaseE2ETest):
    """E2E suite for catalogue suggestions accept and dismiss workflows."""

    def test_accept_suggestion_on_person_page(self, page: Page, live_server, test_user):
        """Accepting a suggestion on the full detail page reloads and moves it to in-progress plans."""
        tag = GiftTagFactory(name="Books")
        person = PersonFactory(first_name="Alice", family_name="Reader")
        past_gift = GiftFactory(name="Past Book", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        novel = GiftFactory(name="Novel", tags=[tag])
        atlas = GiftFactory(name="Atlas", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, novel, atlas)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/en/persons/{person.person_id}/")

        # Suggestions section loads lazily via HTMX
        suggestions_section = page.locator("[data-gift-suggestions-section]")
        expect(suggestions_section).to_be_visible(timeout=self.ajax_timeout * 2)

        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        # Confirm screenshots for light, dark, and phone width layout verification
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        suggestions.screenshot(path=str(reports_dir / "suggestions_light.png"))

        # Dark theme
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        suggestions.screenshot(path=str(reports_dir / "suggestions_dark.png"))
        page.evaluate("document.documentElement.removeAttribute('data-theme')")

        # Phone viewport
        page.set_viewport_size({"width": 375, "height": 667})
        suggestions.screenshot(path=str(reports_dir / "suggestions_phone.png"))
        page.set_viewport_size({"width": 1920, "height": 1080})

        # Locate Novel suggestion
        novel_item = suggestions.locator("[data-gift-suggestion]").filter(has_text="Novel")
        expect(novel_item).to_be_visible()

        accept_btn = novel_item.locator("[data-suggestion-accept]")
        expect(accept_btn).to_be_visible()
        accept_btn.click()

        # Surface 'page' responds with HX-Refresh: true; wait for page reload to complete
        page.wait_for_load_state("networkidle", timeout=self.page_load_timeout)

        # 'Novel' is now in the relations list
        relations_list = page.locator(".relations-list")
        expect(relations_list).to_be_visible(timeout=self.ajax_timeout * 2)
        expect(relations_list).to_contain_text("Novel")

        # 'Novel' is no longer in suggestions
        expect(page.locator("[data-gift-suggestions]")).not_to_contain_text("Novel")

    def test_dismiss_suggestion_on_person_page(self, page: Page, live_server, test_user):
        """Dismissing a suggestion immediately removes it, persisting across page reload."""
        tag = GiftTagFactory(name="Cooking")
        person = PersonFactory(first_name="Chef", family_name="Gourmet")
        past_gift = GiftFactory(name="Past Pan", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        pan = GiftFactory(name="Cast Iron Skillet", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, pan)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/en/persons/{person.person_id}/")

        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        pan_item = suggestions.locator("[data-gift-suggestion]").filter(
            has_text="Cast Iron Skillet"
        )
        expect(pan_item).to_be_visible()

        dismiss_btn = pan_item.locator("[data-suggestion-dismiss]")
        expect(dismiss_btn).to_be_visible()
        dismiss_btn.click()

        # Item is removed from the DOM
        expect(pan_item).not_to_be_attached(timeout=self.ajax_timeout)

        # Reload the page to verify dismissal was persisted
        page.reload()
        page.wait_for_load_state("networkidle", timeout=self.page_load_timeout)

        expect(page.locator("[data-gift-suggestions]")).not_to_contain_text("Cast Iron Skillet")

    def test_accept_suggestion_in_detail_panel(self, page: Page, live_server, test_user):
        """Accepting a suggestion in the offcanvas/modal detail panel updates the panel via list:update."""
        tag = GiftTagFactory(name="Music")
        person = PersonFactory(first_name="Bob", family_name="Panel")
        past_gift = GiftFactory(name="Past Guitar", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        headphones = GiftFactory(name="Studio Headphones", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, headphones)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/recipients/?view=people")

        # Click the details action on Bob's row
        details_button = page.locator(
            f'[data-action="detail"][href*="{person.person_id}"], '
            f'[data-action="detail"][data-detail-url*="{person.person_id}"]'
        ).first
        expect(details_button).to_be_visible(timeout=self.ajax_timeout * 2)
        details_button.click()

        # Detail panel opens and loads content
        detail_content = page.locator("#detailContent")
        expect(detail_content).to_be_visible(timeout=self.ajax_timeout * 2)

        suggestions = detail_content.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        headphones_item = suggestions.locator("[data-gift-suggestion]").filter(
            has_text="Studio Headphones"
        )
        expect(headphones_item).to_be_visible()

        accept_btn = headphones_item.locator("[data-suggestion-accept]")
        expect(accept_btn).to_be_visible()
        accept_btn.click()

        # Server sends HX-Trigger: {"list:update": null}; detailPanel reloads via detail-views.js
        relations_list = detail_content.locator(".relations-list")
        expect(relations_list).to_contain_text("Studio Headphones", timeout=self.ajax_timeout * 2)
        expect(detail_content.locator("[data-gift-suggestions]")).not_to_contain_text(
            "Studio Headphones"
        )

    def test_accept_ai_idea_on_group_page(self, page: Page, live_server, test_user, monkeypatch):
        """AI ideas load lazily on group detail page, can be accepted into group plans, and 'More ideas' works."""
        from datetime import timedelta

        from django.utils import timezone

        from gift_manager.models import Event
        from gift_manager.tests.factories import EventFactory
        from gift_manager.tests.factories import PersonGroupFactory
        from gift_manager.tests.suggestions.conftest import FakeAIClient

        group = PersonGroupFactory(name="Stargazers")
        upcoming_event = EventFactory(
            name="Solstice Party",
            schedule_type=Event.ScheduleType.ONE_TIME,
            date=timezone.localdate() + timedelta(days=10),
            is_birthday=False,
        )
        _share(test_user, group, upcoming_event)

        batch1 = {
            "ideas": [
                {
                    "name": "Telescope",
                    "description": "Astronomical telescope for night sky",
                    "reason": "Great for group star watching",
                    "tags": [],
                }
            ]
        }
        batch2 = {
            "ideas": [
                {
                    "name": "Star Map",
                    "description": "Glow in the dark constellation map",
                    "reason": "Complements astronomy",
                    "tags": [],
                }
            ]
        }
        fake = FakeAIClient(canned_responses=[batch1, batch2])
        monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: fake)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/en/person_groups/{group.group_id}/")

        # Suggestions section loads lazily via HTMX
        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        # AI block loads lazily inside suggestions with generate button
        generate_btn = suggestions.locator("[data-suggestion-more-ideas]")
        expect(generate_btn).to_be_visible(timeout=self.ajax_timeout * 2)

        # Tabbing into the occasion and budget pill groups shows a visible focus ring on each pill
        ai_scroll = suggestions.locator(
            "[data-gift-suggestions-ai] .gift-suggestions-scroll-container"
        )
        ai_scroll.focus()
        page.keyboard.press("Tab")
        occ_any_radio = suggestions.locator('input.btn-check[name="occasion"][value=""]')
        occ_any_label = suggestions.locator('label[for$="_occ_' + str(group.pk) + '_any"]')
        expect(occ_any_radio).to_be_focused()
        occ_outline = occ_any_label.evaluate(
            "el => ({ style: getComputedStyle(el).outlineStyle, width: getComputedStyle(el).outlineWidth })"
        )
        assert occ_outline["style"] == "solid" and occ_outline["width"] != "0px"

        page.keyboard.press("Tab")
        budget_any_radio = suggestions.locator('input.btn-check[name="budget"][value=""]')
        budget_any_label = suggestions.locator('label[for$="_budget_' + str(group.pk) + '_any"]')
        expect(budget_any_radio).to_be_focused()
        budget_outline = budget_any_label.evaluate(
            "el => ({ style: getComputedStyle(el).outlineStyle, width: getComputedStyle(el).outlineWidth })"
        )
        assert budget_outline["style"] == "solid" and budget_outline["width"] != "0px"

        # Clicking a steering pill highlights the button without unclipping its hidden .btn-check radio input
        # and does not show a focus ring for mouse clicks
        budget_radio = suggestions.locator('input.btn-check[name="budget"][value="under_30"]')
        budget_label = suggestions.locator('label[for$="_under_30"]')
        budget_label.click()
        expect(budget_radio).to_be_checked()
        radio_style = budget_radio.evaluate(
            """el => {
                const cs = window.getComputedStyle(el);
                return { position: cs.position, clip: cs.clip };
            }"""
        )
        assert radio_style["position"] == "absolute"
        assert radio_style["clip"] == "rect(0px, 0px, 0px, 0px)"
        assert budget_label.evaluate("el => getComputedStyle(el).outlineStyle") == "none"

        # Emulate high-contrast mode: clicking a pill keeps its checked fill, and tabbing shows a 3px outline
        expect(budget_label).to_have_css("background-color", "rgb(79, 70, 229)")
        cdp = page.context.new_cdp_session(page)
        cdp.send(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-contrast", "value": "more"}]},
        )
        budget_label.click()
        expect(budget_label).to_have_css("background-color", "rgb(79, 70, 229)")
        ai_scroll.focus()
        page.keyboard.press("Tab")
        hc_outline = occ_any_label.evaluate(
            "el => ({ style: getComputedStyle(el).outlineStyle, width: getComputedStyle(el).outlineWidth })"
        )
        assert hc_outline["style"] == "solid" and hc_outline["width"] == "3px"

        # Emulate touch device (hover: none): hovering an unchecked pill keeps a transparent background
        cdp.send("Emulation.setEmulatedMedia", {"features": []})
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
        )
        cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        assert page.evaluate("window.matchMedia('(hover: none)').matches")
        occ_event_label = suggestions.locator('label[for$="_occ_' + str(group.pk) + '_1"]')
        for dark in (False, True):
            if dark:
                page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
            occ_event_label.hover()
            assert (
                occ_event_label.evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgba(0, 0, 0, 0)"
            )
            budget_any_label.hover()
            assert (
                budget_any_label.evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgba(0, 0, 0, 0)"
            )
            assert (
                budget_label.evaluate("el => getComputedStyle(el).backgroundColor")
                != "rgba(0, 0, 0, 0)"
            )
        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        cdp.send("Emulation.clearDeviceMetricsOverride")
        cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": False})
        cdp.detach()

        generate_btn.click()

        # Batch 1 'Telescope' appears in AI block
        ai_item = suggestions.locator('[data-suggestion-source="ai"]').filter(has_text="Telescope")
        expect(ai_item).to_be_visible(timeout=self.ajax_timeout * 2)

        # Accept Telescope
        accept_btn = ai_item.locator("[data-suggestion-accept]")
        expect(accept_btn).to_be_visible()
        accept_btn.click()

        # Surface 'page' responds with HX-Refresh: true; wait for page reload to complete
        page.wait_for_load_state("networkidle", timeout=self.page_load_timeout)

        # Telescope is now listed in group's gift plans tab
        gifts_tab = page.locator("#gifts-tab")
        expect(gifts_tab).to_contain_text(
            "Gift Plans for this group [1]", timeout=self.ajax_timeout * 2
        )
        gifts_tab.click()

        gifts_grid = page.locator("#gifts-grid")
        expect(gifts_grid).to_be_visible(timeout=self.ajax_timeout * 2)
        expect(gifts_grid).to_contain_text("Telescope")

        # Now click 'More ideas' to load batch 2
        more_btn = page.locator("[data-suggestion-more-ideas]")
        expect(more_btn).to_be_visible(timeout=self.ajax_timeout * 2)
        more_btn.click()

        # Batch 2 idea 'Star Map' appears in AI block
        star_map_item = page.locator('[data-suggestion-source="ai"]').filter(has_text="Star Map")
        expect(star_map_item).to_be_visible(timeout=self.ajax_timeout * 2)

    def test_review_and_restore_dismissed_suggestions(self, page: Page, live_server, test_user):
        """Dismissing a suggestion updates the badge count; opening the dismissed panel allows restoring it."""
        tag = GiftTagFactory(name="Stationery")
        person = PersonFactory(first_name="Diana", family_name="Writer")
        past_gift = GiftFactory(name="Notebook", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        pen = GiftFactory(name="Fountain Pen", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, pen)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/en/persons/{person.person_id}/")

        # Suggestions section loads lazily
        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        # Fountain Pen is in suggestions
        pen_item = suggestions.locator("[data-gift-suggestion]").filter(has_text="Fountain Pen")
        expect(pen_item).to_be_visible()

        # Dismiss Fountain Pen
        dismiss_btn = pen_item.locator("[data-suggestion-dismiss]")
        expect(dismiss_btn).to_be_visible()
        dismiss_btn.click()

        # Item is removed from the DOM
        expect(pen_item).not_to_be_attached(timeout=self.ajax_timeout)

        # Review button now has badge with count 1
        review_btn = page.locator("[data-suggestions-review-dismissed]")
        expect(review_btn).to_be_visible()
        badge = review_btn.locator("[data-dismissed-count]")
        expect(badge).to_have_text("1")

        # Click to open dismissed suggestions offcanvas panel
        review_btn.click()

        panel = page.locator("#dismissedSuggestionsPanel")
        expect(panel).to_be_visible(timeout=self.ajax_timeout * 2)

        content = panel.locator("#dismissedSuggestionsContent")
        dismissed_pen = content.locator("[data-dismissed-item]").filter(has_text="Fountain Pen")
        expect(dismissed_pen).to_be_visible(timeout=self.ajax_timeout * 2)

        # Review button restores its label and is enabled
        expect(review_btn).to_contain_text("Dismissed suggestions")
        expect(review_btn).to_be_enabled()

        # Restore the suggestion
        restore_btn = dismissed_pen.locator('[data-action="restore"]')
        expect(restore_btn).to_be_visible()
        restore_btn.click()

        # Panel content updates in-place to empty state
        expect(dismissed_pen).not_to_be_attached(timeout=self.ajax_timeout)
        expect(content.locator("[data-dismissed-empty]")).to_be_visible(timeout=self.ajax_timeout)

        # Close the panel
        panel.locator(".btn-close").click()
        expect(panel).not_to_be_visible(timeout=self.ajax_timeout)

        # Active suggestions section on the page reloaded via suggestions:refresh trigger
        # Fountain Pen is back in the active suggestions
        restored_pen = (
            page.locator("[data-gift-suggestions]")
            .locator("[data-gift-suggestion]")
            .filter(has_text="Fountain Pen")
        )
        expect(restored_pen).to_be_visible(timeout=self.ajax_timeout * 2)

    def test_dismissed_panel_stacked_over_detail_modal_escape_isolation(
        self, page: Page, live_server, test_user
    ):
        """When opening the dismissed panel from inside a detail modal, pressing Escape closes only the offcanvas."""
        tag = GiftTagFactory(name="Art")
        person = PersonFactory(first_name="Elena", family_name="Painter")
        past_gift = GiftFactory(name="Easel", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        canvas = GiftFactory(name="Oil Canvas", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, canvas)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/recipients/?view=people")

        # Open Elena's detail panel modal
        details_button = page.locator(
            f'[data-action="detail"][href*="{person.person_id}"], '
            f'[data-action="detail"][data-detail-url*="{person.person_id}"]'
        ).first
        expect(details_button).to_be_visible(timeout=self.ajax_timeout * 2)
        details_button.click()

        detail_modal = page.locator("#detailPanel")
        expect(detail_modal).to_be_visible(timeout=self.ajax_timeout * 2)

        # In detail modal, suggestions load
        detail_content = page.locator("#detailContent")
        suggestions = detail_content.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        # Dismiss Oil Canvas
        canvas_item = suggestions.locator("[data-gift-suggestion]").filter(has_text="Oil Canvas")
        expect(canvas_item).to_be_visible()
        canvas_item.locator("[data-suggestion-dismiss]").click()
        expect(canvas_item).not_to_be_attached(timeout=self.ajax_timeout)

        # Open dismissed suggestions panel from inside the modal
        review_btn = suggestions.locator("[data-suggestions-review-dismissed]")
        expect(review_btn).to_be_visible()
        review_btn.click()

        offcanvas_panel = page.locator("#dismissedSuggestionsPanel")
        expect(offcanvas_panel).to_be_visible(timeout=self.ajax_timeout * 2)

        # Wait for dismissed item content to be loaded in the offcanvas
        dismissed_canvas = offcanvas_panel.locator(
            "#dismissedSuggestionsContent [data-dismissed-item]"
        ).filter(has_text="Oil Canvas")
        expect(dismissed_canvas).to_be_visible(timeout=self.ajax_timeout * 2)

        # Press Escape: should close the offcanvas panel, NOT the underlying detail modal
        page.keyboard.press("Escape")

        expect(offcanvas_panel).not_to_be_visible(timeout=self.ajax_timeout)
        # Detail modal is still open and visible!
        expect(detail_modal).to_be_visible()

    def test_dismiss_with_dropdown_reason_and_custom_note(self, page: Page, live_server, test_user):
        """Dismissing via dropdown with a custom note preserves the reason and note in dismissed panel."""
        tag = GiftTagFactory(name="Paragliding")
        person = PersonFactory(first_name="Sophie", family_name="Flyer")
        past_gift = GiftFactory(name="Past Flight Book", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        tandem = GiftFactory(name="Tandem Paragliding Flight", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, tandem)

        self.login_as_user(page, live_server, test_user)

        # Set mobile viewport 360x740 to verify layout and clipping on small screens
        page.set_viewport_size({"width": 360, "height": 740})
        page.goto(f"{live_server.url}/en/persons/{person.person_id}/")

        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        item = suggestions.locator("[data-gift-suggestion]").filter(
            has_text="Tandem Paragliding Flight"
        )
        expect(item).to_be_visible()

        # Open the split dropdown caret
        dropdown_toggle = item.locator(".dropdown-toggle-split")
        expect(dropdown_toggle).to_be_visible()
        dropdown_toggle.click()

        # Dropdown menu is visible
        dropdown_menu = item.locator(".gift-suggestion-dropdown-menu")
        expect(dropdown_menu).to_be_visible()

        # Input is visible and not clipped
        note_input = dropdown_menu.locator('input[name="comment"]')
        expect(note_input).to_be_visible()

        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        page.screenshot(path=str(reports_dir / "suggestions_dropdown_360px.png"))

        # Click into input (verifying it is not clipped or obstructed) and type custom note
        note_input.click()
        note_input.fill("Already practices solo paragliding")
        note_input.press("Enter")

        # Item is removed from the active suggestions
        expect(item).not_to_be_attached(timeout=self.ajax_timeout)

        # Open dismissed suggestions panel
        review_btn = suggestions.locator("[data-suggestions-review-dismissed]")
        expect(review_btn).to_be_visible()
        review_btn.click()

        panel = page.locator("#dismissedSuggestionsPanel")
        expect(panel).to_be_visible(timeout=self.ajax_timeout * 2)

        content = panel.locator("#dismissedSuggestionsContent")
        dismissed_item = content.locator("[data-dismissed-item]").filter(
            has_text="Tandem Paragliding Flight"
        )
        expect(dismissed_item).to_be_visible(timeout=self.ajax_timeout * 2)

        # Reason badge shows "Other reason" and note text is rendered outside badge
        expect(dismissed_item).to_contain_text("Other reason")
        expect(dismissed_item).to_contain_text("Already practices solo paragliding")

        # Take full page screenshot of dismissed panel on 360px
        page.screenshot(path=str(reports_dir / "dismissed_panel_360px.png"))

        # Reset viewport
        page.set_viewport_size({"width": 1920, "height": 1080})

    def test_dismiss_suggestion_with_promote_to_profile(self, page: Page, live_server, test_user):
        """Dismissing a suggestion with 'promote_to_profile' checked adds tags and note to person."""
        tag = GiftTagFactory(name="Robotics")
        person = PersonFactory(first_name="Ada", family_name="Lovelace", notes="")
        past_gift = GiftFactory(name="Past Robot", tags=[tag])
        given_plan = RelationFactory(
            person=person,
            gift=past_gift,
            status=_status("Given"),
            reaction_rating=5,
        )
        kit = GiftFactory(name="Arduino Starter Kit", tags=[tag])
        _share(test_user, tag, person, past_gift, given_plan, kit)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/en/persons/{person.person_id}/")

        suggestions = page.locator("[data-gift-suggestions]")
        expect(suggestions).to_be_visible(timeout=self.ajax_timeout * 2)

        kit_item = suggestions.locator("[data-gift-suggestion]").filter(
            has_text="Arduino Starter Kit"
        )
        expect(kit_item).to_be_visible()

        # Open dropdown
        dropdown_toggle = kit_item.locator(".dropdown-toggle")
        expect(dropdown_toggle).to_be_visible()
        dropdown_toggle.click()

        dropdown_menu = kit_item.locator(".dropdown-menu")
        expect(dropdown_menu).to_be_visible()

        # Check promote_to_profile checkbox
        promote_checkbox = dropdown_menu.locator('input[name="promote_to_profile"]')
        expect(promote_checkbox).to_be_visible()
        promote_checkbox.check()

        # Click "Already owned or practiced"
        owned_btn = dropdown_menu.locator('button[value="already_owned_or_practiced"]')
        expect(owned_btn).to_be_visible()
        owned_btn.click()

        # Item should be removed from DOM
        expect(kit_item).not_to_be_attached(timeout=self.ajax_timeout)

        # Verify DB changes
        person.refresh_from_db()
        assert person.interests.filter(name="Robotics").exists()
        assert "Suggestion: Arduino Starter Kit" in person.notes
