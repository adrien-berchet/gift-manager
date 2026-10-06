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

    def test_sharing_a_surprise_with_its_recipient_warns(
        self, page: Page, live_server, seed_data_e2e
    ):
        alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
        alice.profile.friends.add(bob.profile)
        gift = GiftFactory(name="Warned Gift")
        share(gift, alice, PermissionLevel.OWNER)
        bobby = PersonFactory(first_name="Bobby", user_link=bob)
        share(bobby, alice, PermissionLevel.OWNER)
        plan = RelationFactory(person=bobby, gift=gift, event=None, is_surprise=True)
        share(plan, alice, PermissionLevel.OWNER)
        share(plan, bob, PermissionLevel.VIEWER)

        login_as(page, live_server.url, "alice")
        open_page(
            page,
            f"{live_server.url}{reverse('gift_manager:relation_detail', kwargs={'pk': plan.relation_id})}",
        )
        shared_with = page.locator("#relation-coordination ~ .detail-section")
        expect(shared_with).to_contain_text("Can't see it")

        # Change Bob's level from the edit panel, opened from the person's page like a user does
        person_url = reverse("gift_manager:person_detail", kwargs={"pk": bobby.person_id})
        open_page(page, live_server.url + person_url)
        page.locator(f'a[data-edit-url*="{plan.relation_id}"]').first.click()
        panel = page.locator("#editPanel")
        panel.locator("summary", has_text="Sharing").click()
        panel.locator(f"#permission-{bob.id}").select_option(str(PermissionLevel.EDITOR))
        panel.locator("button[type='submit']").first.click()
        expect(
            page.locator(".toast").filter(has_text="bob will not be able to see")
        ).to_be_visible()

    def test_flash_messages_are_toasts_over_the_page_that_disappear(
        self, page: Page, live_server, seed_data_e2e
    ):
        alice, bob = seed_data_e2e.alice, seed_data_e2e.bob
        alice.profile.friends.add(bob.profile)
        gift = GiftFactory(name="Shared Gift")
        share(gift, alice, PermissionLevel.OWNER)
        person = PersonFactory(first_name="Pat")
        share(person, alice, PermissionLevel.OWNER)
        plan = RelationFactory(person=person, gift=gift, event=None)
        share(plan, alice, PermissionLevel.OWNER)
        share_url = live_server.url + reverse("gift_manager:share_objects")

        login_as(page, live_server.url, "alice")
        open_page(page, share_url)
        page.locator(f"#friend-{bob.id}").check()
        page.eval_on_selector(
            f"#relation-{plan.relation_id}",
            "box => { box.checked = true; box.dispatchEvent(new Event('change', {bubbles: true})); }",
        )
        page.locator("#share-button").click()

        toast = page.locator(".toast").filter(has_text="Successfully shared items")
        expect(toast).to_be_visible()
        # "Visible" to the browser is not enough: it must be on screen, readable, top right
        page.wait_for_function(  # it slides in: wait until it has settled inside the viewport
            """() => {
                const toast = document.querySelector('.toast.show');
                const box = toast && toast.getBoundingClientRect();
                return box && box.right <= window.innerWidth && box.height > 24;
            }""",
            timeout=3_000,
        )
        box = toast.bounding_box()
        viewport = page.viewport_size
        assert box["height"] > 24, f"toast squashed to {box['height']}px"
        assert box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"], f"off screen: {box}"
        assert box["x"] > viewport["width"] / 2 and box["y"] < 200, f"not top right: {box}"
        # It floats over the page instead of taking room in it
        assert (
            page.evaluate("getComputedStyle(document.querySelector('#toastContainer')).position")
            == "fixed"
        )
        title_with_toast = page.locator("h1").first.bounding_box()["y"]
        expect(toast).to_be_hidden(timeout=15_000)  # hides itself after a few seconds

        open_page(page, share_url)  # the message was shown once: nothing queued any more
        assert page.locator(".toast").count() == 0
        assert page.locator("h1").first.bounding_box()["y"] == title_with_toast
