"""Browser test of plan coordination: claim, comment, release and a hidden surprise."""

import pytest
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager import plan_coordination
from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory


def login_as(page: Page, base_url: str, username: str):
    """Log in as a seed user (their password is ``<username>_password``)."""
    page.context.clear_cookies()
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="login"]', username)
    page.fill('input[name="password"]', f"{username}_password")
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=30_000)


def open_page(page: Page, url: str):
    """Open a page and wait for HTMX; slow third-party assets must not decide the outcome."""
    response = page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.htmx?.process === 'function'", timeout=30_000)
    return response


def share(relation, user, level):
    create_or_update_permission(user, relation, permission_level=level)


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestPlanCoordination:
    def test_claim_comment_release_and_hidden_surprise(
        self, page: Page, live_server, seed_data_e2e
    ):
        alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
        gift = GiftFactory(name="Coordinated Gift", shared_with=[alice, bob])
        plan = RelationFactory(person=seed_data_e2e.persons["dad"], gift=gift, event=None)
        share(plan, alice, PermissionLevel.OWNER)
        share(plan, bob, PermissionLevel.EDITOR)
        detail = f"{live_server.url}{plan.get_absolute_url()}"

        # Bob claims the plan and leaves a comment
        login_as(page, live_server.url, "bob")
        open_page(page, detail)
        page.get_by_role("button", name="I'll take this").click()
        expect(page.locator("#relation-coordination")).to_contain_text("Claimed by bob")
        page.fill("#relation-comment-text", "I know a shop that has it")
        page.get_by_role("button", name="Send").click()
        expect(page.locator("#relation-coordination")).to_contain_text("I know a shop that has it")

        # Alice sees who claimed it and the comment, then releases the claim as an owner
        login_as(page, live_server.url, "alice")
        open_page(page, detail)
        coordination = page.locator("#relation-coordination")
        expect(coordination).to_contain_text("Claimed by bob")
        expect(coordination).to_contain_text("I know a shop that has it")
        page.get_by_role("button", name="Release").click()
        expect(page.get_by_role("button", name="I'll take this")).to_be_visible()

        # A surprise plan for Bob is invisible to Bob and still visible to Alice
        surprise = RelationFactory(
            person=PersonFactory(first_name="Bobby", user_link=bob),
            gift=GiftFactory(name="Hidden Surprise Gift", shared_with=[alice, bob]),
            event=None,
            is_surprise=True,
        )
        share(surprise, alice, PermissionLevel.OWNER)
        share(surprise, bob, PermissionLevel.VIEWER)
        surprise_url = f"{live_server.url}{surprise.get_absolute_url()}"

        open_page(page, surprise_url)
        expect(page.locator("#relation-coordination")).to_contain_text("Coordination")

        login_as(page, live_server.url, "bob")
        response = page.goto(surprise_url, wait_until="domcontentloaded")
        assert response.status == 404
        open_page(page, f"{live_server.url}/relations/")
        expect(page.get_by_text("Coordinated Gift").first).to_be_visible()
        expect(page.get_by_text("Hidden Surprise Gift")).to_have_count(0)

    def test_refusals_are_shown_in_the_page(self, page: Page, live_server, seed_data_e2e):
        """A claim conflict and an invalid comment answer with 4xx: the alert must still show."""
        alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
        gift = GiftFactory(name="Contested Gift", shared_with=[alice, bob])
        plan = RelationFactory(person=seed_data_e2e.persons["dad"], gift=gift, event=None)
        share(plan, alice, PermissionLevel.OWNER)
        share(plan, bob, PermissionLevel.EDITOR)

        login_as(page, live_server.url, "bob")
        open_page(page, f"{live_server.url}{plan.get_absolute_url()}")
        coordination = page.locator("#relation-coordination")
        expect(page.get_by_role("button", name="I'll take this")).to_be_visible()

        # Alice claims the plan while Bob's page still offers it
        plan.claimed_by = alice
        plan.claimed_at = timezone.now()
        plan.save()
        page.get_by_role("button", name="I'll take this").click()
        expect(coordination.get_by_role("alert")).to_contain_text(
            "alice has already claimed this gift plan"
        )
        expect(coordination).to_contain_text("Claimed by alice")

        # The browser limits the comment length; the server still refuses a longer one (422)
        page.evaluate(
            "document.querySelector('#relation-comment-text').removeAttribute('maxlength')"
        )
        page.fill("#relation-comment-text", "x" * 2001)
        page.get_by_role("button", name="Send").click()
        expect(coordination.get_by_role("alert")).to_contain_text("at most 2000 characters")

    def test_opening_a_plan_does_not_focus_or_scroll_to_the_comment_box(
        self, page: Page, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        dad = seed_data_e2e.persons["dad"]
        gift = GiftFactory(name="Quiet Gift", shared_with=[alice])
        plan = RelationFactory(person=dad, gift=gift, event=None)
        share(plan, alice, PermissionLevel.OWNER)
        for _ in range(8):  # make the detail long enough to scroll
            plan_coordination.add_comment(plan, alice, "A comment that takes some room.\n" * 3)
        active = "document.activeElement && document.activeElement.id"

        # Full page
        login_as(page, live_server.url, "alice")
        open_page(page, f"{live_server.url}{plan.get_absolute_url()}")
        expect(page.locator("#relation-coordination")).to_be_visible()
        assert page.evaluate(active) != "relation-comment-text"
        assert page.evaluate("window.scrollY") == 0

        # Side panel opened from the person's page
        open_page(
            page,
            live_server.url + reverse("gift_manager:person_detail", kwargs={"pk": dad.person_id}),
        )
        page.locator(f'a[data-detail-url*="{plan.relation_id}"]').first.click()
        expect(page.locator("#detailPanel #relation-coordination")).to_be_visible()
        page.wait_for_timeout(1000)  # let the panel's focus handling run
        assert page.evaluate(active) != "relation-comment-text"
        assert page.evaluate("document.querySelector('#detailPanelBody').scrollTop") == 0
