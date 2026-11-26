"""Tests for the contact file parser (vCard and CSV) of the contact import."""

import json
import logging
import time
from pathlib import Path

import pytest
from django.utils import timezone

from gift_manager.contact_import import MAX_CONTACTS
from gift_manager.contact_import import MAX_FILE_BYTES
from gift_manager.contact_import import ContactImportError
from gift_manager.contact_import import parse_birthday
from gift_manager.contact_import import parse_contacts

DATA_DIR = Path(__file__).parent / "data" / "contact_import"
EXPECTED = json.loads((DATA_DIR / "expected.json").read_text(encoding="utf-8"))
KEYS = ("given", "family", "emails", "bday")

# Skipped records per fixture: cards or rows without any name, and malformed cards
SKIPPED = {
    "edge_cases.vcf": 2,
    "google.csv": 1,
    "outlook_en.csv": 1,
    "simple.csv": 1,
}
# Fixtures whose slash dates are day/month/year (exported in French)
DAY_FIRST = {"outlook_fr.csv"}
INVALID_BIRTHDAYS = {
    "edge_cases.vcf": {"Anne-Sophie"},
    "vcard4.vcf": {"Lina"},
    "google.csv": {"Hélène"},
    "outlook_en.csv": {"Zoé"},
}


def _parse_fixture(name):
    return parse_contacts((DATA_DIR / name).read_bytes(), name, day_first=name in DAY_FIRST)


def _card(index, extra=""):
    return (
        f"BEGIN:VCARD\r\nVERSION:3.0\r\nN:Family{index};Given{index};;;\r\n"
        f"EMAIL:p{index}@example.com\r\n{extra}END:VCARD\r\n"
    )


class TestFixtures:
    """Every fixture parses to exactly the contacts listed in expected.json."""

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_contacts_match_expected(self, name):
        contacts, skipped = _parse_fixture(name)

        assert [{key: contact[key] for key in KEYS} for contact in contacts] == EXPECTED[name]
        assert skipped == SKIPPED.get(name, 0)

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_invalid_birthday_flag(self, name):
        contacts, _ = _parse_fixture(name)

        flagged = {contact["given"] for contact in contacts if contact["invalid_birthday"]}
        assert flagged == INVALID_BIRTHDAYS.get(name, set())

    def test_every_fixture_is_covered(self):
        files = {path.name for path in DATA_DIR.iterdir() if path.suffix in {".vcf", ".csv"}}
        assert files == set(EXPECTED)

    def test_records_are_plain_json(self):
        contacts, _ = _parse_fixture("google.vcf")

        assert json.loads(json.dumps(contacts)) == contacts


class TestVcard:
    """vCard specifics beyond the fixtures."""

    def test_bare_pref_comes_first(self):
        data = (
            b"BEGIN:VCARD\r\nVERSION:2.1\r\nN:Doe;Jane\r\nEMAIL;INTERNET:second@example.com\r\n"
            b"EMAIL;PREF;INTERNET:first@example.com\r\nEND:VCARD\r\n"
        )

        contacts, _ = parse_contacts(data, "a.vcf")

        assert contacts[0]["emails"] == ["first@example.com", "second@example.com"]

    def test_duplicate_emails_are_kept_once(self):
        data = (
            b"BEGIN:VCARD\r\nVERSION:3.0\r\nN:Doe;Jane;;;\r\nEMAIL:jane@example.com\r\n"
            b"EMAIL;TYPE=pref:JANE@example.com\r\nEND:VCARD\r\n"
        )

        contacts, _ = parse_contacts(data, "a.vcf")

        assert contacts[0]["emails"] == ["jane@example.com"]

    def test_unescaped_comma_in_name_is_joined(self):
        data = b"BEGIN:VCARD\r\nVERSION:3.0\r\nN:Dupont,Martin;Jean;;;\r\nEND:VCARD\r\n"

        contacts, _ = parse_contacts(data, "a.vcf")

        assert (contacts[0]["given"], contacts[0]["family"]) == ("Jean", "Dupont Martin")

    def test_unreadable_card_does_not_lose_the_others(self):
        data = (
            _card(1) + "BEGIN:VCARD\r\nVERSION:3.0\r\nN;=:x\r\nEND:VCARD\r\n" + _card(2)
        ).encode()

        contacts, skipped = parse_contacts(data, "a.vcf")

        assert [contact["given"] for contact in contacts] == ["Given1", "Given2"]
        assert skipped == 1

    def test_vobject_does_not_log_contact_data(self, caplog):
        data = (
            _card(1)
            + "BEGIN:VCARD\r\nVERSION:3.0\r\nN:Secret;Name;;;\r\nEMAIL;=:secret@example.com\r\n"
            "BDAY:not a date\r\nEND:VCARD\r\n"
        ).encode()

        with caplog.at_level(logging.DEBUG):
            parse_contacts(data, "a.vcf")

        assert "secret" not in caplog.text.lower()

    def test_vcard_content_is_detected_without_extension(self):
        contacts, _ = parse_contacts(_card(1).encode(), "contacts.txt")

        assert contacts[0]["given"] == "Given1"

    def test_hostile_card_with_many_properties_is_fast(self):
        noise = "X-NOISE:x\r\n" * 150_000
        data = _card(1, extra=noise).encode()
        assert len(data) <= MAX_FILE_BYTES

        start = time.perf_counter()
        contacts, _ = parse_contacts(data, "a.vcf")

        assert time.perf_counter() - start < 2
        assert contacts[0]["given"] == "Given1"


class TestCsv:
    """CSV specifics beyond the fixtures."""

    @pytest.mark.parametrize(
        ("day_first", "expected"), [(True, [3, 4, 1990]), (False, [4, 3, 1990])]
    )
    def test_slash_dates_follow_the_language(self, day_first, expected):
        data = b"First Name,Birthday\nAna,03/04/1990\n"

        contacts, _ = parse_contacts(data, "a.csv", day_first=day_first)

        assert contacts[0]["bday"] == expected

    def test_semicolon_delimiter(self):
        data = "Prénom;Nom;E-mail\nAna;Silva;ana@example.com\n".encode()

        contacts, _ = parse_contacts(data, "a.csv")

        assert contacts[0]["family"] == "Silva"
        assert contacts[0]["emails"] == ["ana@example.com"]

    def test_single_column(self):
        contacts, _ = parse_contacts(b"Name\nAna Silva\n", "a.csv")

        assert contacts[0]["given"] == "Ana Silva"

    def test_utf16_export(self):
        data = "Given Name,Family Name\r\nAna,Silva\r\n".encode("utf-16")

        contacts, _ = parse_contacts(data, "a.csv")

        assert (contacts[0]["given"], contacts[0]["family"]) == ("Ana", "Silva")

    def test_short_rows_are_read(self):
        contacts, _ = parse_contacts(b"First Name,Last Name,Email\nAna\n", "a.csv")

        assert contacts[0] == {
            "given": "Ana",
            "family": "",
            "emails": [],
            "bday": None,
            "invalid_birthday": False,
        }

    def test_headers_without_contact_columns_are_unsupported(self):
        with pytest.raises(ContactImportError) as error:
            parse_contacts(b"Product,Price\nTea,3\n", "a.csv")

        assert error.value.code == "unsupported"

    def test_header_only_file_is_empty(self):
        with pytest.raises(ContactImportError) as error:
            parse_contacts(b"First Name,Last Name\n", "a.csv")

        assert error.value.code == "empty"


class TestDecoding:
    """Files are decoded as UTF-8, then Windows-1252, then Latin-1."""

    def test_windows_1252(self):
        data = "First Name,Last Name\nŒdipe,Prix 5 €\n".encode("cp1252")

        contacts, _ = parse_contacts(data, "a.csv")

        assert (contacts[0]["given"], contacts[0]["family"]) == ("Œdipe", "Prix 5 €")

    def test_latin1_fallback(self):
        # 0x81 is undefined in Windows-1252 (and a control character, so it is dropped)
        data = b"First Name,Last Name\nAna,Silva\x81\xe9\n"

        contacts, _ = parse_contacts(data, "a.csv")

        assert contacts[0]["family"] == "Silva é"


class TestLimitsAndErrors:
    """Files are rejected as a whole with a clear error code."""

    def test_largest_accepted_file(self):
        padding = "NOTE:" + "x" * 2000 + "\r\n"
        card_size = len(_card(0, extra=padding).encode())
        cards = [_card(i, extra=padding) for i in range(MAX_CONTACTS)]
        data = "".join(cards).encode()
        filler = MAX_FILE_BYTES - len(data)
        assert filler >= 0, card_size
        data += b"\r\n" * (filler // 2)

        start = time.perf_counter()
        contacts, skipped = parse_contacts(data, "big.vcf")

        assert len(contacts) == MAX_CONTACTS
        assert skipped == 0
        assert time.perf_counter() - start < 5

    def test_too_large(self):
        with pytest.raises(ContactImportError) as error:
            parse_contacts(b"x" * (MAX_FILE_BYTES + 1), "a.csv")

        assert error.value.code == "too_large"

    def test_too_many_vcards(self):
        data = "".join(_card(i) for i in range(MAX_CONTACTS + 1)).encode()

        with pytest.raises(ContactImportError) as error:
            parse_contacts(data, "a.vcf")

        assert error.value.code == "too_many"

    def test_too_many_csv_rows(self):
        rows = "".join(f"Given{i},Family{i}\n" for i in range(MAX_CONTACTS + 1))

        with pytest.raises(ContactImportError) as error:
            parse_contacts(("First Name,Last Name\n" + rows).encode(), "a.csv")

        assert error.value.code == "too_many"

    def test_blank_csv_rows_do_not_count(self):
        rows = "".join(f"Given{i},Family{i}\n,\n" for i in range(MAX_CONTACTS))

        contacts, _ = parse_contacts(("First Name,Last Name\n" + rows).encode(), "a.csv")

        assert len(contacts) == MAX_CONTACTS

    @pytest.mark.parametrize("data", [b"", b"   \r\n\n", b"\xef\xbb\xbf"])
    def test_empty(self, data):
        with pytest.raises(ContactImportError) as error:
            parse_contacts(data, "a.vcf")

        assert error.value.code == "empty"

    @pytest.mark.parametrize(
        ("data", "filename"),
        [
            (b"hello world", "a.vcf"),
            (b"hello world", "notes.txt"),
            (b"\x89PNG\r\n\x1a\n\x00\x00", "photo.png"),
        ],
    )
    def test_unsupported(self, data, filename):
        with pytest.raises(ContactImportError) as error:
            parse_contacts(data, filename)

        assert error.value.code == "unsupported"

    def test_no_named_contact(self):
        data = b"BEGIN:VCARD\r\nVERSION:3.0\r\nEMAIL:a@example.com\r\nEND:VCARD\r\n"

        with pytest.raises(ContactImportError) as error:
            parse_contacts(data, "a.vcf")

        assert error.value.code == "no_contacts"

    def test_error_message_is_translated(self):
        error = ContactImportError("empty")

        assert str(error.message)


class TestParseBirthday:
    """Birthday values: ISO forms, year-less forms and slash dates."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1987-03-14", ((14, 3, 1987), False)),
            ("19870314", ((14, 3, 1987), False)),
            ("1987-03-14T00:00:00Z", ((14, 3, 1987), False)),
            ("--05-09", ((9, 5, None), False)),
            ("--0509", ((9, 5, None), False)),
            ("--02-29", ((29, 2, None), False)),
            ("1985-02-29", (None, True)),
            ("1985-13-01", (None, True)),
            ("0000-05-10", (None, True)),
            ("circa 1980", (None, True)),
            ("", (None, False)),
            ("  ", (None, False)),
        ],
    )
    def test_vcard_values(self, raw, expected):
        assert parse_birthday(raw) == expected

    def test_future_year_is_invalid(self):
        next_year = timezone.localdate().year + 1

        assert parse_birthday(f"{next_year}-01-01") == (None, True)

    def test_omitted_year(self):
        assert parse_birthday("1604-07-22", omit_year=True) == ((22, 7, None), False)

    def test_slash_dates_need_a_csv_context(self):
        assert parse_birthday("6/21/1985") == (None, True)
        assert parse_birthday("6/21/1985", day_first=False) == ((21, 6, 1985), False)
        assert parse_birthday("21/06/1985", day_first=True) == ((21, 6, 1985), False)

    @pytest.mark.parametrize("raw", ["0/0/00", "0/0/0000", "00/00/00"])
    def test_outlook_empty_date(self, raw):
        assert parse_birthday(raw, day_first=False) == (None, False)

    def test_two_digit_years(self):
        this_year = timezone.localdate().year % 100

        assert parse_birthday(f"1/2/{this_year:02d}", day_first=True)[0][2] == 2000 + this_year
        later = (this_year + 1) % 100
        assert parse_birthday(f"1/2/{later:02d}", day_first=True)[0][2] == 1900 + later


class TestControlCharacters:
    """Control characters (NUL included) never reach a name: the database rejects NUL."""

    def test_control_characters_are_removed_from_names(self):
        data = b"First Name,Last Name\nA\x00na,Sil\tva\x07\n"

        contacts, _ = parse_contacts(data, "a.csv")

        assert (contacts[0]["given"], contacts[0]["family"]) == ("A na", "Sil va")

    def test_name_made_of_control_characters_is_skipped(self):
        data = b"First Name,Last Name\n\x00\x01,\x02\nAna,Silva\n"

        contacts, skipped = parse_contacts(data, "a.csv")

        assert [contact["given"] for contact in contacts] == ["Ana"]
        assert skipped == 1

    def test_email_with_control_characters_is_dropped(self):
        data = b"First Name,Email\nAna,ana\x00@example.com\n"

        contacts, _ = parse_contacts(data, "a.csv")

        assert contacts[0]["emails"] == []
