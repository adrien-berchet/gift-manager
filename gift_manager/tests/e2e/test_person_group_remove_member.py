"""Browser regressions for membership changes on the group detail page.

Removing a member goes through a confirmed POST, and the membership section (tab counts
and every grid) is refreshed in place instead of reloading the whole page.
"""

import re

from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.base_test import BaseE2ETest
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import RelationFactory

RELOAD_MARKER = "window.__groupDetailNotReloaded"


def _own(user, *entities):
    for entity in entities:
        create_or_update_permission(user, entity, permission_level=PermissionLevel.OWNER)


class TestPersonGroupRemoveMember(BaseE2ETest):
    def _open_group(self, page: Page, live_server, user, group) -> None:
        self.login_as_user(page, live_server, user)
        detail_path = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        page.goto(f"{live_server.url}{detail_path}")
        page.wait_for_load_state("networkidle")
        # Survives only if the page is not reloaded
        page.evaluate(f"{RELOAD_MARKER} = true")

    def _assert_not_reloaded(self, page: Page) -> None:
        assert page.evaluate(RELOAD_MARKER) is True

    def test_remove_member_confirms_then_posts_and_refreshes_section(
        self, page: Page, live_server, test_user
    ):
        group = PersonGroupFactory(name="Removal regression group")
        leaving = PersonFactory(first_name="Leaving", family_name="Member", groups=[group])
        staying = PersonFactory(first_name="Staying", family_name="Member", groups=[group])
        _own(test_user, group, leaving, staying)

        methods = []
        page.on(
            "request",
            lambda request: "/remove_person/" in request.url and methods.append(request.method),
        )
        self._open_group(page, live_server, test_user, group)
        expect(page.locator("#persons-tab")).to_contain_text("[2]")
        expect(page.locator("#nested-members-tab")).to_contain_text("[2]")

        grid = page.locator("#persons-grid")
        leaving_row = grid.locator("tbody tr", has_text="Leaving")
        expect(leaving_row).to_be_visible()
        leaving_row.locator('[data-action="delete"]').click()

        self.wait_for_modal(page)
        expect(page.locator("#modalBody")).to_contain_text("Remove Leaving Member")
        # Opening the confirmation must not change anything
        assert group.person_set.filter(pk=leaving.pk).exists()

        page.locator("#confirmAction").click()

        expect(page.locator("#persons-tab")).to_contain_text("[1]")
        expect(page.locator("#nested-members-tab")).to_contain_text("[1]")
        expect(page.locator("#persons-grid tbody tr", has_text="Staying")).to_be_visible()
        expect(page.locator("#persons-grid")).not_to_contain_text("Leaving")
        expect(page.locator(".toast", has_text="Person removed from group")).to_be_visible()
        self._assert_not_reloaded(page)
        assert not group.person_set.filter(pk=leaving.pk).exists()
        assert group.person_set.filter(pk=staying.pk).exists()
        assert methods == ["GET", "POST"]

    def test_refreshed_section_keeps_the_active_tab(self, page: Page, live_server, test_user):
        group = PersonGroupFactory(name="Tab regression group")
        relation = RelationFactory(person=None, group=group, gift__name="Doomed gift")
        kept = RelationFactory(person=None, group=group, gift__name="Kept gift")
        _own(test_user, group, relation, relation.gift, relation.event, kept, kept.gift, kept.event)

        self._open_group(page, live_server, test_user, group)
        page.locator("#gifts-tab").click()
        expect(page.locator("#gifts-list")).to_be_visible()
        expect(page.locator("#gifts-tab")).to_contain_text("[2]")

        doomed_row = page.locator("#gifts-grid tbody tr", has_text="Doomed gift")
        doomed_row.locator('[data-action="delete"]').click()
        self.wait_for_modal(page)
        page.locator("#confirmAction").click()

        expect(page.locator("#gifts-tab")).to_contain_text("[1]")
        expect(page.locator("#gifts-tab")).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator("#gifts-list")).to_be_visible()
        expect(page.locator("#persons-list")).to_be_hidden()
        expect(page.locator("#gifts-grid tbody tr", has_text="Kept gift")).to_be_visible()
        expect(page.locator("#gifts-grid")).not_to_contain_text("Doomed gift")
        self._assert_not_reloaded(page)

    def test_contextual_create_refreshes_section_without_reload(
        self, page: Page, live_server, test_user
    ):
        group = PersonGroupFactory(name="Create regression group")
        _own(test_user, group)

        self._open_group(page, live_server, test_user, group)
        expect(page.locator("#persons-tab")).to_contain_text("[0]")

        page.locator("#persons-list [data-group-detail-create]").click()
        form = page.locator(".offcanvas.show form")
        expect(form).to_be_visible()
        form.locator('[name="first_name"]').fill("Freshly")
        form.locator('[name="family_name"]').fill("Created")
        form.locator('[type="submit"]').first.click()

        expect(page.locator("#persons-tab")).to_contain_text("[1]")
        expect(page.locator("#persons-grid tbody tr", has_text="Freshly")).to_be_visible()
        self._assert_not_reloaded(page)
