"""Browser regression: the group details panel loads its gift history in every browser.

A details click used to be handled twice (once through HTMX, once through a raw fetch that
wrote the HTML without processing it). In Firefox the raw write could land last, leaving the
history section on "Loading…" for good, because HTMX never saw its lazy-load element.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.models import RelationStatus
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.base_test import BaseE2ETest
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory


class TestGroupGiftHistoryPanel(BaseE2ETest):
    def test_details_panel_shows_member_plans_without_getting_stuck(
        self, page: Page, live_server, test_user
    ):
        group = PersonGroupFactory(name="History panel group")
        member = PersonFactory(first_name="Ada", family_name="Panel")
        member.groups.add(group)
        given, _ = RelationStatus.objects.get_or_create(
            status_en="Given", defaults={"status": "Given"}
        )
        relation = RelationFactory(person=member, gift=GiftFactory(name="Panel gift"), status=given)
        for obj in (group, member, relation.gift, relation):
            create_or_update_permission(test_user, obj, permission_level=PermissionLevel.VIEWER)

        self.login_as_user(page, live_server, test_user)
        page.goto(f"{live_server.url}/recipients/?view=groups")

        details_button = page.locator(
            f'[data-action="detail"][href*="{group.group_id}"], '
            f'[data-action="detail"][data-detail-url*="{group.group_id}"]'
        ).first
        details_button.click()

        history = page.locator("[data-gift-history-section]")
        expect(history).to_contain_text("Panel gift", timeout=self.ajax_timeout * 2)
        expect(history.locator("[data-gift-history]")).to_contain_text("Ada Panel")
