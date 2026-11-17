"""End-to-end journey for the getting-started checklist and the Help pages."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}

# A phone menu row is full when it holds two items or one item as wide as the menu
UTILITY_ROWS_ARE_FULL = """menu => {
    const items = [...menu.querySelectorAll(':scope > .nav-item')]
        .filter(item => item.getBoundingClientRect().height > 0);
    const rows = new Map();
    for (const item of items) {
        const top = Math.round(item.getBoundingClientRect().top);
        rows.set(top, [...(rows.get(top) || []), item]);
    }
    const width = menu.clientWidth;
    return [...rows.values()].every(row => row.length === 2
        || (row.length === 1 && row[0].getBoundingClientRect().width > width * 0.9));
}"""


def _sign_in(page, client, live_server, settings, user):
    client.force_login(user)
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )


@pytest.fixture
def new_user(seed_data_e2e):
    """A brand-new account with nothing in it."""
    user = get_user_model().objects.create_user(
        username="newcomer", email="newcomer@example.com", password="newcomer_password"
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def _open_menu_if_collapsed(page):
    toggler = page.locator(".navbar-toggler")
    if toggler.is_visible():
        toggler.click()
        expect(page.locator(".navbar-collapse.show")).to_be_visible()


def _assert_no_horizontal_scroll(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGettingStartedJourney:
    """A new user reads Help from the checklist, hides it and brings it back."""

    @pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
    def test_new_user_hides_and_restores_checklist(
        self, page, client, live_server, settings, new_user, viewport
    ):
        page.set_viewport_size(viewport)
        _sign_in(page, client, live_server, settings, new_user)

        # 1. The dashboard shows the checklist with the first step unticked
        page.goto(f"{live_server.url}/en/")
        card = page.locator("#getting-started")
        expect(card).to_be_visible()
        recipient_step = card.locator(".getting-started-step").filter(has_text="Add a recipient")
        expect(recipient_step.locator(".far.fa-circle")).to_have_count(1)
        _assert_no_horizontal_scroll(page)

        # 2. "What's this?" leads to the matching section of the core Help page
        recipient_step.locator(".getting-started-help").click()
        expect(page).to_have_url(f"{live_server.url}/en/help/how-it-works/#recipients")
        expect(page.locator("section#recipients")).to_be_in_viewport()
        _assert_no_horizontal_scroll(page)

        # 3. Back on the dashboard, Hide removes the card
        page.goto(f"{live_server.url}/en/")
        page.locator("#getting-started .getting-started-hide button").click()
        expect(page).to_have_url(f"{live_server.url}/en/")
        expect(page.locator("#getting-started")).to_have_count(0)

        # 4. Help from the navbar offers to show the checklist again
        _open_menu_if_collapsed(page)
        page.locator('.navbar-utilities a[href="/en/help/"]').click()
        expect(page).to_have_url(f"{live_server.url}/en/help/")
        _assert_no_horizontal_scroll(page)
        page.get_by_role(
            "button", name="Show the getting-started checklist on my dashboard"
        ).click()

        # 5. The dashboard shows the checklist again
        expect(page).to_have_url(f"{live_server.url}/en/")
        expect(page.locator("#getting-started")).to_be_visible()
        _assert_no_horizontal_scroll(page)


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.mobile
class TestPhoneMenuWithHelp:
    """The Help link keeps the phone menu's two-column grid free of half-empty rows."""

    def test_signed_out_menu_rows_are_full(self, page, live_server):
        page.set_viewport_size(PHONE)
        page.goto(f"{live_server.url}/en/")
        page.locator(".navbar-toggler").click()
        menu = page.locator(".navbar-collapse.show .navbar-utilities")
        expect(menu).to_be_visible()

        assert menu.evaluate(UTILITY_ROWS_ARE_FULL)

    def test_signed_in_menu_rows_are_full(self, page, client, live_server, settings, new_user):
        page.set_viewport_size(PHONE)
        _sign_in(page, client, live_server, settings, new_user)
        page.goto(f"{live_server.url}/en/")
        page.locator(".navbar-toggler").click()
        menu = page.locator(".navbar-collapse.show .navbar-utilities")
        expect(menu).to_be_visible()

        assert menu.evaluate(UTILITY_ROWS_ARE_FULL)


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestGiftEmptyStateIcons:
    """Only the large icon of an empty state is styled large; button and link icons stay small."""

    def test_learn_more_and_button_icons_keep_their_size_and_colour(
        self, page, client, live_server, settings, new_user
    ):
        page.set_viewport_size(DESKTOP)
        _sign_in(page, client, live_server, settings, new_user)
        page.goto(f"{live_server.url}/en/gifts/")
        empty_state = page.locator("#gift-empty-state")
        expect(empty_state).to_be_visible()

        learn_more = empty_state.locator(".help-learn-more")
        icon_size = learn_more.locator("i").evaluate(
            "i => parseFloat(getComputedStyle(i).fontSize)"
        )
        text_size = learn_more.evaluate("a => parseFloat(getComputedStyle(a).fontSize)")
        assert icon_size == text_size

        button = empty_state.locator("a.btn-primary")
        plus_colour = button.locator("i").evaluate("i => getComputedStyle(i).color")
        button_background = button.evaluate("b => getComputedStyle(b).backgroundColor")
        assert plus_colour != button_background
