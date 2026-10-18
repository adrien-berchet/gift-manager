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
