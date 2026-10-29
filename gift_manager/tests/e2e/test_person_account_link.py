"""Browser tests of person account linking: friends list, email banner, and mobile layout."""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import RelationFactory


def login_as(page: Page, base_url: str, username: str):
    """Log in as a seed user (testuser password is testpass123; others <username>_password)."""
    password = "testpass123" if username == "testuser" else f"{username}_password"
    page.context.clear_cookies()
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="login"]', username)
    page.fill('input[name="password"]', password)
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
class TestPersonAccountLink:
    def test_create_person_from_friends_list_and_surprise_visibility(
        self, page: Page, live_server, seed_data_e2e
    ):
        alice = seed_data_e2e.alice
        bob = seed_data_e2e.bob
        testuser = User.objects.get(username="testuser")

        # 1. Log in as testuser
        login_as(page, live_server.url, "testuser")

        # 2. Navigate to /profile/
        open_page(page, f"{live_server.url}/profile/")

        # 3. On Bob's friends row, click "Create person"
        bob_row = page.locator(".friends-list .list-group-item").filter(has_text="bob")
        bob_row.get_by_role("link", name=re.compile(r"Create person", re.IGNORECASE)).click()
        page.wait_for_url(lambda url: "/persons/create/" in url, timeout=30_000)

        # 4. Verify initial values prefilled, submit form
        expect(page.locator('input[name="first_name"]')).to_have_value("Bob")
        expect(page.locator('input[name="family_name"]')).to_have_value("Seed")
        expect(page.locator('input[name="email_address"]')).to_have_value("bob@example.com")

        page.get_by_role("button", name="Save").click()
        page.wait_for_url(lambda url: "/profile/" in url, timeout=30_000)

        # 5. Sees "Linked to bob" on the new record
        bob_record = Person.objects.get(account=bob)
        bob_url = f"{live_server.url}{reverse('gift_manager:person_detail', kwargs={'pk': bob_record.person_id})}"
        open_page(page, bob_url)
        expect(page.locator(".badge").filter(has_text="Linked to bob")).to_be_visible()

        # 6. Create a surprise plan by Alice for that record, shared with Bob and testuser
        surprise = RelationFactory(
            person=bob_record,
            gift=GiftFactory(name="Surprise Telescope", shared_with=[alice, bob, testuser]),
            event=None,
            is_surprise=True,
        )
        share(surprise, alice, PermissionLevel.OWNER)
        share(surprise, bob, PermissionLevel.VIEWER)
        share(surprise, testuser, PermissionLevel.VIEWER)

        surprise_url = f"{live_server.url}{surprise.get_absolute_url()}"

        # 7. Verify Bob cannot see it (404)
        login_as(page, live_server.url, "bob")
        bob_response = page.goto(surprise_url, wait_until="domcontentloaded")
        assert bob_response.status == 404

        # 8. Verify testuser can see it
        login_as(page, live_server.url, "testuser")
        open_page(page, surprise_url)
        expect(page.locator("body")).to_contain_text("Surprise Telescope")

    def test_link_from_email_banner(self, page: Page, live_server, seed_data_e2e):
        testuser = User.objects.get(username="testuser")

        # 1. Log in as testuser
        login_as(page, live_server.url, "testuser")

        # 2. Create a person with email alice@example.com
        person = PersonFactory(
            first_name="AliceFriend",
            family_name="Test",
            email_address=encode_email("alice@example.com"),
            owner=testuser,
        )

        # 3. Open the person detail page, verify banner appears, click "Link"
        person_url = f"{live_server.url}{reverse('gift_manager:person_detail', kwargs={'pk': person.person_id})}"
        open_page(page, person_url)
        suggestion_banner = page.locator("[data-link-suggestion]")
        expect(suggestion_banner).to_be_visible()
        expect(suggestion_banner).to_contain_text("alice")

        suggestion_banner.get_by_role("button", name="Link").click()

        # 4. Verify the badge "Linked to alice" appears
        expect(page.locator(".badge").filter(has_text="Linked to alice")).to_be_visible()
        expect(page.locator("[data-link-suggestion]")).to_have_count(0)

    @pytest.mark.mobile
    def test_friends_row_buttons_fit_on_phone(self, page: Page, live_server, seed_data_e2e):
        page.set_viewport_size({"width": 390, "height": 844})
        login_as(page, live_server.url, "testuser")
        open_page(page, f"{live_server.url}/profile/")

        bob_row = page.locator(".friends-list .list-group-item").filter(has_text="bob")
        expect(
            bob_row.get_by_role("link", name=re.compile(r"Link to a person", re.IGNORECASE))
        ).to_be_visible()
        expect(
            bob_row.get_by_role("link", name=re.compile(r"Create person", re.IGNORECASE))
        ).to_be_visible()
        expect(bob_row.locator("[data-remove-friend]")).to_be_visible()

        no_scroll = page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        assert no_scroll is True
