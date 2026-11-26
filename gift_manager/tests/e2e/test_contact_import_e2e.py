"""End-to-end journey for importing contacts from a file: upload, preview, import."""

from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from gift_manager.models import Person

DATA_DIR = Path(__file__).parent.parent / "data" / "contact_import"
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}


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
def importer(seed_data_e2e):
    user = get_user_model().objects.create_user(
        username="importer", email="importer@example.com", password="importer_password"
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
class TestContactImportJourney:
    """A user imports two of the three contacts of a Google Contacts export."""

    @pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
    def test_upload_preview_import(self, page, client, live_server, settings, importer, viewport):
        page.set_viewport_size(viewport)
        _sign_in(page, client, live_server, settings, importer)

        # 1. The Recipients page links to the import page
        page.goto(f"{live_server.url}/en/recipients/")
        page.get_by_role("link", name="Import contacts").first.click()
        expect(page.get_by_role("heading", name="Import contacts")).to_be_visible()

        # 2. Upload a vCard export
        page.locator('input[type="file"]').set_input_files(str(DATA_DIR / "google.vcf"))
        page.get_by_role("button", name="Continue").click()

        # 3. The preview lists the contacts, all selected; the controls work
        expect(page.get_by_role("heading", name="Choose the contacts to import")).to_be_visible()
        boxes = page.locator('input[name="selected"]')
        expect(boxes).to_have_count(3)
        count = page.locator("[data-selected-count]")
        expect(count).to_have_text("3")
        page.get_by_role("button", name="Select none").click()
        expect(count).to_have_text("0")
        page.get_by_label("Import Élodie Marchand").check()
        page.get_by_label("Import Thomas Nguyen").check()
        expect(count).to_have_text("2")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # 4. Import: back on the people view with a summary, the people are there
        page.get_by_role("button", name="Import selected contacts").click()
        page.wait_for_url("**/recipients/?view=people")
        expect(page.get_by_text("Contacts imported: 2. Not imported: 1.")).to_be_visible()
        expect(page.locator("body")).to_contain_text("Nguyen")
        assert sorted(Person.objects.owned_by(importer).values_list("first_name", flat=True)) == [
            "Thomas",
            "Élodie",
        ]
