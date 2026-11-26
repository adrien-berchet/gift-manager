"""Tests for the contact import pages: upload, preview, confirm and cancel."""

import re
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import translation

from gift_manager.contact_import import MAX_CONTACTS
from gift_manager.contact_import import MAX_FILE_BYTES
from gift_manager.email_encoding import encode_email
from gift_manager.models import PermissionLevel
from gift_manager.models import Person
from gift_manager.models import PersonPermission
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory
from gift_manager.views.contact_import import PENDING_IMPORT_TTL_SECONDS
from gift_manager.views.contact_import import SESSION_KEY

pytestmark = pytest.mark.django_db

DATA_DIR = Path(__file__).parent.parent / "data" / "contact_import"
UPLOAD_URL = reverse("gift_manager:contact_import")


def _fixture(name):
    return SimpleUploadedFile(name, (DATA_DIR / name).read_bytes())


def _upload(client, upload):
    return client.post(UPLOAD_URL, {"file": upload})


def _preview_url(response):
    match = re.search(r"/persons/import/([0-9a-f]+)/$", response["Location"])
    assert match, response["Location"]
    return response["Location"]


def _people_view():
    return reverse("gift_manager:recipients") + "?view=people"


def _checked_indexes(html):
    return sorted(
        int(value)
        for value in re.findall(r'<input[^>]*name="selected"[^>]*value="(\d+)"[^>]*checked', html)
    )


def _messages(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.fixture
def client(client, user):
    client.force_login(user)
    return client


class TestAccess:
    def test_login_required(self, client):
        client.logout()

        assert client.get(UPLOAD_URL).status_code == 302
        assert Person.objects.count() == 0

    def test_upload_page_renders(self, client):
        response = client.get(UPLOAD_URL)

        assert response.status_code == 200
        assert 'type="file"' in response.text


class TestUploadAndPreview:
    def test_upload_redirects_to_a_preview(self, client):
        response = _upload(client, _fixture("google.vcf"))

        assert response.status_code == 302
        preview = client.get(_preview_url(response))
        assert preview.status_code == 200
        assert "Élodie" in preview.text
        assert "elodie.marchand@example.com" in preview.text
        # Nothing is created before confirmation
        assert Person.objects.count() == 0

    def test_new_contacts_are_checked_by_default(self, client):
        response = client.get(_preview_url(_upload(client, _fixture("google.vcf"))))

        assert _checked_indexes(response.text) == [0, 1, 2]

    def test_duplicates_are_flagged_and_unchecked(self, client, user):
        PersonFactory(owner=user, first_name="Élodie", family_name="Marchand")
        shared = PersonFactory(
            first_name="Someone",
            family_name="Else",
            email_address=encode_email("thomas.nguyen@example.com"),
        )
        create_or_update_permission(user, shared, permission_level=PermissionLevel.VIEWER)

        response = client.get(_preview_url(_upload(client, _fixture("google.vcf"))))

        assert _checked_indexes(response.text) == [2]
        assert "Already in your people" in response.text
        assert "Shared with you" in response.text

    def test_invalid_birthday_is_explained(self, client):
        response = client.get(_preview_url(_upload(client, _fixture("vcard4.vcf"))))

        assert "Birthday not recognized" in response.text

    def test_skipped_contacts_are_counted(self, client):
        response = client.get(_preview_url(_upload(client, _fixture("edge_cases.vcf"))))

        assert response.context["skipped"] == 2
        assert len(response.context["rows"]) == 5

    def test_csv_slash_dates_follow_the_language(self, client):
        data = b"First Name,Birthday\nAna,03/04/1990\n"
        with translation.override("fr"):
            url = reverse("gift_manager:contact_import")
        response = client.post(url, {"file": SimpleUploadedFile("a.csv", data)})

        assert client.session[SESSION_KEY]["contacts"][0]["bday"] == [3, 4, 1990]
        assert response.status_code == 302

    def test_new_upload_replaces_the_pending_one(self, client):
        first = _preview_url(_upload(client, _fixture("google.vcf")))
        second = _preview_url(_upload(client, _fixture("apple.vcf")))

        assert first != second
        response = client.get(first)
        assert response.status_code == 302
        assert response["Location"] == UPLOAD_URL

    def test_unknown_import_id_redirects_to_upload(self, client):
        response = client.get(reverse("gift_manager:contact_import_preview", args=["nope"]))

        assert response.status_code == 302
        assert response["Location"] == UPLOAD_URL
        assert _messages(response)

    @pytest.mark.parametrize(
        ("name", "data", "expected"),
        [
            ("a.vcf", b"", "The submitted file is empty."),
            ("a.vcf", b"hello", "This file is not a contacts file"),
            ("a.pdf", b"%PDF-1.4", "This file is not a contacts file"),
            ("a.vcf", b"x" * (MAX_FILE_BYTES + 1), "This file is too large"),
            (
                "a.csv",
                b"First Name\n" + b"Ana\n" * (MAX_CONTACTS + 1),
                "more than 1,000 contacts",
            ),
        ],
    )
    def test_rejected_files(self, client, name, data, expected):
        response = _upload(client, SimpleUploadedFile(name, data))

        assert response.status_code == 200
        assert expected in response.text
        assert SESSION_KEY not in client.session
        assert Person.objects.count() == 0

    def test_unexpected_parser_error_shows_a_generic_message(self, client, monkeypatch, caplog):
        def boom(*args, **kwargs):
            message = "secret@example.com"
            raise RuntimeError(message)

        monkeypatch.setattr("gift_manager.contact_import_forms.parse_contacts", boom)

        response = _upload(client, _fixture("google.vcf"))

        assert response.status_code == 200
        assert "This file could not be read." in response.text
        assert "secret@example.com" not in caplog.text


class TestConfirm:
    def test_import_selected_contacts(self, client, user):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))

        response = client.post(preview, {"selected": ["0", "2"]})

        assert response.status_code == 302
        assert response["Location"] == _people_view()
        assert sorted(Person.objects.values_list("first_name", flat=True)) == ["Sarah", "Élodie"]
        assert set(Person.objects.owned_by(user)) == set(Person.objects.all())
        assert _messages(response) == ["Contacts imported: 2. Not imported: 1."]
        assert SESSION_KEY not in client.session

    def test_not_imported_includes_skipped_contacts(self, client):
        preview = _preview_url(_upload(client, _fixture("edge_cases.vcf")))

        response = client.post(preview, {"selected": ["0"]})

        assert _messages(response) == ["Contacts imported: 1. Not imported: 6."]

    def test_selecting_nothing_is_an_error(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))

        response = client.post(preview, {})

        assert response.status_code == 200
        assert "Select at least one contact" in response.text
        assert Person.objects.count() == 0

    def test_invalid_index_is_an_error(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))

        response = client.post(preview, {"selected": ["99"]})

        assert response.status_code == 200
        assert Person.objects.count() == 0

    def test_add_to_an_editable_group(self, client, user):
        group = PersonGroupFactory()
        create_or_update_permission(user, group, permission_level=PermissionLevel.EDITOR)
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        assert group.name in client.get(preview).text

        client.post(preview, {"selected": ["0", "1"], "group": str(group.pk)})

        assert group.person_set.count() == 2

    @pytest.mark.parametrize("level", [PermissionLevel.VIEWER, None])
    def test_group_the_user_cannot_edit_is_refused(self, client, user, level):
        group = PersonGroupFactory()
        if level is not None:
            create_or_update_permission(user, group, permission_level=level)
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        assert group.name not in client.get(preview).text

        response = client.post(preview, {"selected": ["0"], "group": str(group.pk)})

        assert response.status_code == 200
        assert Person.objects.count() == 0

    def test_thousand_selected_contacts(self, client, user):
        rows = "".join(f"Given{i},Family{i},p{i}@example.com\n" for i in range(MAX_CONTACTS))
        data = ("First Name,Last Name,Email\n" + rows).encode()
        preview = _preview_url(_upload(client, SimpleUploadedFile("big.csv", data)))
        assert len(_checked_indexes(client.get(preview).text)) == MAX_CONTACTS

        response = client.post(
            preview,
            {"selected": [str(index) for index in range(MAX_CONTACTS)], "group": ""},
        )

        assert response.status_code == 302
        assert Person.objects.owned_by(user).count() == MAX_CONTACTS
        assert PersonPermission.objects.filter(user=user).count() == MAX_CONTACTS

    def test_reimport_with_defaults_creates_no_duplicate(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        client.post(preview, {"selected": ["0", "1", "2"]})

        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        selected = _checked_indexes(client.get(preview).text)

        assert selected == []
        assert Person.objects.count() == 3

    def test_imported_people_are_private(self, client):
        other = UserFactory()
        preview = _preview_url(_upload(client, _fixture("google.vcf")))

        client.post(preview, {"selected": ["0"]})

        assert not Person.objects.accessible_by(other).exists()

    def test_cannot_confirm_another_sessions_import(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        intruder = UserFactory()
        client.force_login(intruder)

        response = client.post(preview, {"selected": ["0"]})

        assert response.status_code == 302
        assert Person.objects.count() == 0


class TestRobustness:
    def test_pending_import_expires(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        session = client.session
        pending = session[SESSION_KEY]
        pending["created"] -= PENDING_IMPORT_TTL_SECONDS + 1
        session[SESSION_KEY] = pending
        session.save()

        response = client.post(preview, {"selected": ["0"]})

        assert response.status_code == 302
        assert response["Location"] == UPLOAD_URL
        assert SESSION_KEY not in client.session
        assert Person.objects.count() == 0

    def test_validation_error_while_importing_keeps_the_preview(self, client, monkeypatch):
        def invalid(*args, **kwargs):
            raise ValidationError({"first_name": "secret@example.com"})

        monkeypatch.setattr("gift_manager.views.contact_import.import_contacts", invalid)
        preview = _preview_url(_upload(client, _fixture("google.vcf")))

        response = client.post(preview, {"selected": ["0"]})

        assert response.status_code == 200
        assert "Nothing was imported" in response.text
        assert "secret@example.com" not in response.text
        assert SESSION_KEY in client.session

    def test_nul_in_a_name_imports_cleanly(self, client):
        data = b"First Name,Last Name\nA\x00na,Silva\n"
        preview = _preview_url(_upload(client, SimpleUploadedFile("a.csv", data)))

        response = client.post(preview, {"selected": ["0"]})

        assert response.status_code == 302
        assert Person.objects.get().first_name == "A na"


class TestCancel:
    def test_cancel_forgets_the_import(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        import_id = preview.rstrip("/").rsplit("/", 1)[-1]

        response = client.post(reverse("gift_manager:contact_import_cancel", args=[import_id]))

        assert response.status_code == 302
        assert response["Location"] == _people_view()
        assert SESSION_KEY not in client.session
        assert Person.objects.count() == 0

    def test_cancel_needs_post(self, client):
        preview = _preview_url(_upload(client, _fixture("google.vcf")))
        import_id = preview.rstrip("/").rsplit("/", 1)[-1]

        response = client.get(reverse("gift_manager:contact_import_cancel", args=[import_id]))

        assert response.status_code == 405
        assert SESSION_KEY in client.session


class TestEntryPoints:
    @pytest.mark.parametrize("page", ["gift_manager:recipients", "gift_manager:persons"])
    def test_list_pages_link_to_the_import(self, client, page):
        response = client.get(reverse(page))

        link = re.search(rf'<a href="{UPLOAD_URL}"[^>]*>', response.text)
        assert link
        assert "data-action" not in link.group(0)


class TestFrench:
    def test_preview_is_translated(self, client):
        with translation.override("fr"):
            url = reverse("gift_manager:contact_import")
        response = client.post(url, {"file": _fixture("google.vcf")})

        preview = client.get(response["Location"])

        assert "Choisissez les contacts à importer" in preview.text
        assert "3 contacts trouvés dans le fichier." in preview.text
        translation.activate("en")
