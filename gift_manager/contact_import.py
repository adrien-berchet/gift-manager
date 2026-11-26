"""Parse contact files (vCard or CSV) into plain contact records.

Pure parsing: no database access, no request. A record is a JSON-serializable dict::

    {"given": str, "family": str, "emails": [str], "bday": [day, month, year|None] | None,
     "invalid_birthday": bool}

``emails`` holds every valid address, normalized, the preferred one first. ``invalid_birthday``
is true when a non-empty birthday was dropped because it is not a valid date.

Contacts are third-party personal data: nothing here logs names, emails or birthdays, and the
``vobject`` logger (which logs unreadable lines verbatim) is silenced.
"""

import codecs
import csv
import io
import logging
import re
import unicodedata
from typing import NamedTuple

import vobject
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.translation import gettext

from gift_manager.invitations import normalize_email
from gift_manager.models import birthday_parts_error

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CONTACTS = 1000

# vobject logs unreadable lines verbatim, which would put contact data in the logs
logging.getLogger("vobject").setLevel(logging.CRITICAL + 1)


# Why a file is rejected as a whole (ContactImportError.code)
TOO_LARGE = "too_large"
TOO_MANY = "too_many"
EMPTY = "empty"
UNSUPPORTED = "unsupported"
NO_CONTACTS = "no_contacts"
UNREADABLE = "unreadable"


class ContactImportError(Exception):
    """A file rejected as a whole. ``code`` says why; ``message`` is for the user."""

    CODES = (TOO_LARGE, TOO_MANY, EMPTY, UNSUPPORTED, NO_CONTACTS, UNREADABLE)

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError(code)
        super().__init__(code)
        self.code = code

    @property
    def message(self) -> str:
        """Return the user-facing message, translated in the active language."""
        messages = {
            "too_large": gettext("This file is too large: files are limited to 2 MB."),
            "too_many": gettext(
                "This file contains more than %(count)s contacts. Split it into smaller files "
                "and import them one by one."
            )
            % {"count": number_format(MAX_CONTACTS, force_grouping=True)},
            "empty": gettext("This file is empty or contains no contacts."),
            "unsupported": gettext(
                "This file is not a contacts file. Export your contacts as a vCard (.vcf) or "
                "CSV (.csv) file and try again."
            ),
            "no_contacts": gettext("No contact with a name was found in this file."),
            "unreadable": gettext("This file could not be read."),
        }
        return messages[self.code]


class ParseResult(NamedTuple):
    """The contacts read from a file, and the number of records skipped."""

    contacts: list[dict]
    skipped: int


def parse_contacts(data: bytes, filename: str = "", *, day_first: bool = False) -> ParseResult:
    """Parse the bytes of a contacts file.

    ``day_first`` decides how ambiguous CSV slash dates are read (day/month/year when true).
    Raises ``ContactImportError`` when the file is rejected as a whole.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ContactImportError(TOO_LARGE)
    text = _decode(data)
    if not text.strip():
        raise ContactImportError(EMPTY)
    if _is_vcard(text, filename):
        contacts, skipped, records = _parse_vcard(text)
        if not records:
            raise ContactImportError(UNSUPPORTED)
    elif filename.lower().endswith(".csv"):
        contacts, skipped, records = _parse_csv(text, day_first=day_first)
        if not records:
            raise ContactImportError(EMPTY)
    else:
        raise ContactImportError(UNSUPPORTED)
    if not contacts:
        raise ContactImportError(NO_CONTACTS)
    return ParseResult(contacts, skipped)


def _decode(data: bytes) -> str:
    """Decode as UTF-16 when it has a BOM, else UTF-8, Windows-1252, then Latin-1."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            raise ContactImportError(UNSUPPORTED) from None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_BEGIN = re.compile(r"\s*begin\s*:\s*vcard\s*", re.IGNORECASE)
_END = re.compile(r"\s*end\s*:\s*vcard\s*", re.IGNORECASE)


def _is_vcard(text: str, filename: str) -> bool:
    if filename.lower().endswith((".vcf", ".vcard")):
        return True
    first_line = next((line for line in _LINE_BREAK.split(text) if line.strip()), "")
    return bool(_BEGIN.fullmatch(first_line))


# ---------------------------------------------------------------------------
# Contact records
# ---------------------------------------------------------------------------


def _make_contact(
    given: str,
    family: str,
    full_name: str,
    email_candidates: list[str],
    birthday: str,
    *,
    day_first: bool | None,
    omit_year: bool = False,
) -> dict | None:
    """Build a contact record, or return None when the contact has no name at all."""
    given, family, full_name = _clean_name(given), _clean_name(family), _clean_name(full_name)
    if not given:
        given, family = family, ""
    if not given:
        given = full_name
    if not given:
        return None
    bday, invalid_birthday = parse_birthday(birthday, day_first=day_first, omit_year=omit_year)
    return {
        "given": given,
        "family": family,
        "emails": _valid_emails(email_candidates),
        "bday": list(bday) if bday else None,
        "invalid_birthday": invalid_birthday,
    }


def _clean_name(value: str) -> str:
    """Replace control characters (NUL, tabs, line breaks) by spaces and collapse spaces.

    PostgreSQL refuses NUL characters in text, and a name is one line of text.
    """
    cleaned = "".join(" " if unicodedata.category(char) == "Cc" else char for char in value)
    return " ".join(cleaned.split())


def _valid_emails(candidates: list[str]) -> list[str]:
    """Normalize and validate addresses, dropping invalid ones and repeats, keeping order."""
    emails: list[str] = []
    for candidate in candidates:
        try:
            email = normalize_email(candidate.strip())
        except ValidationError:
            continue
        if email and email not in emails:
            emails.append(email)
    return emails


_ISO_DATE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})(?:T.*)?", re.IGNORECASE)
_NO_YEAR_DATE = re.compile(r"--(\d{2})-?(\d{2})")
_SLASH_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})")


def parse_birthday(
    raw: str, *, day_first: bool | None = None, omit_year: bool = False
) -> tuple[tuple[int, int, int | None] | None, bool]:
    """Parse a birthday value into ``((day, month, year or None), invalid)``.

    Accepts ``YYYY-MM-DD``, ``YYYYMMDD`` (both with an optional time part), ``--MM-DD`` and
    ``--MMDD``. Slash dates (CSV only) are read day first when ``day_first`` is true, month
    first when false, and refused when None; ``0/0/00`` means no birthday. A value that is not
    a valid birthday under the ``Person`` rules returns ``(None, True)``; an empty one
    returns ``(None, False)``.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, False
    parts = _birthday_parts(raw, day_first=day_first)
    if parts == (0, 0, None):
        return None, False
    if parts is None:
        return None, True
    day, month, year = parts
    if omit_year:
        year = None
    if birthday_parts_error(day, month, year):
        return None, True
    return (day, month, year), False


def _birthday_parts(raw: str, *, day_first: bool | None) -> tuple[int, int, int | None] | None:
    if match := _ISO_DATE.fullmatch(raw):
        year, month, day = (int(group) for group in match.groups())
        return day, month, year
    if match := _NO_YEAR_DATE.fullmatch(raw):
        month, day = (int(group) for group in match.groups())
        return day, month, None
    if day_first is not None and (match := _SLASH_DATE.fullmatch(raw)):
        first, second, year_text = match.groups()
        day, month = (int(first), int(second)) if day_first else (int(second), int(first))
        if day == 0 and month == 0:
            return 0, 0, None
        return day, month, _full_year(year_text)
    return None


def _full_year(year_text: str) -> int:
    """Return a four-digit year; two-digit years up to this year's are in this century."""
    year = int(year_text)
    if len(year_text) == 4:
        return year
    this_year = timezone.localdate().year
    century = this_year - this_year % 100
    return century + year if year <= this_year % 100 else century - 100 + year


# ---------------------------------------------------------------------------
# vCard
# ---------------------------------------------------------------------------

# BEGIN and END are added back around the kept lines
_KEPT_PROPERTIES = {"VERSION", "N", "FN", "EMAIL", "BDAY"}


def _parse_vcard(text: str) -> tuple[list[dict], int, int]:
    """Return (contacts, skipped, records) for vCard text, parsing card by card.

    Cards are split here, so a malformed card (or one missing ``END:VCARD``) is skipped
    without losing the rest of the file.
    """
    contacts: list[dict] = []
    skipped = records = 0
    card: list[str] | None = None
    for line in _LINE_BREAK.split(text):
        if _BEGIN.fullmatch(line):
            records += 1
            if records > MAX_CONTACTS:
                raise ContactImportError(TOO_MANY)
            if card is not None:
                skipped += 1  # the previous card never ended
            card = []
        elif card is not None and _END.fullmatch(line):
            contact = _read_card(card)
            if contact is None:
                skipped += 1
            else:
                contacts.append(contact)
            card = None
        elif card is not None:
            card.append(line)
    if card is not None:
        skipped += 1
    return contacts, skipped, records


def _read_card(lines: list[str]) -> dict | None:
    """Return the contact of one card's inner lines, or None when it is unusable."""
    kept = _kept_lines(_unfold(lines))
    try:
        card = vobject.readOne("\r\n".join(["BEGIN:VCARD", *kept, "END:VCARD", ""]))
        return _card_contact(card)
    except Exception:
        return None


def _unfold(lines: list[str]) -> list[str]:
    """Join folded lines and quoted-printable soft line breaks into logical lines."""
    logical: list[str] = []
    for line in lines:
        if logical and _continues_quoted_printable(logical[-1]):
            logical[-1] = logical[-1][:-1] + line
        elif logical and line[:1] in {" ", "\t"}:
            logical[-1] += line[1:]
        else:
            logical.append(line)
    return logical


def _continues_quoted_printable(line: str) -> bool:
    head, sep, _ = line.partition(":")
    return bool(sep) and line.endswith("=") and "QUOTED-PRINTABLE" in head.upper()


def _kept_lines(lines: list[str]) -> list[str]:
    """Keep only the properties we import (``item1.EMAIL`` counts as ``EMAIL``)."""
    kept = []
    for line in lines:
        head, sep, _ = line.partition(":")
        if not sep:
            continue
        name = head.split(";", 1)[0].rsplit(".", 1)[-1].strip().upper()
        if name in _KEPT_PROPERTIES:
            kept.append(line)
    return kept


def _text(value) -> str:
    """Return a vobject value as text (structured components can be lists)."""
    if isinstance(value, list | tuple):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "")


def _card_contact(card) -> dict | None:
    given = family = full_name = ""
    if names := card.contents.get("n"):
        name = names[0].value
        given, family = _text(getattr(name, "given", "")), _text(getattr(name, "family", ""))
    if full_names := card.contents.get("fn"):
        full_name = _text(full_names[0].value)
    email_lines = card.contents.get("email", [])
    ordered = sorted(enumerate(email_lines), key=lambda item: (not _is_preferred(item[1]), item[0]))
    birthday, omit_year = "", False
    if birthdays := card.contents.get("bday"):
        birthday = _text(birthdays[0].value)
        omit_year = any(key.upper() == "X-APPLE-OMIT-YEAR" for key in birthdays[0].params)
    return _make_contact(
        given,
        family,
        full_name,
        [_text(line.value) for _, line in ordered],
        birthday,
        day_first=None,
        omit_year=omit_year,
    )


def _is_preferred(line) -> bool:
    """Tell whether an EMAIL line is the preferred one (vCard 2.1, 3.0 or 4.0 syntax)."""
    params = {key.upper(): value for key, value in line.params.items()}
    types = {part.strip().lower() for value in params.get("TYPE", []) for part in value.split(",")}
    if "pref" in types or "1" in params.get("PREF", []):
        return True
    return any(param.upper() == "PREF" for param in getattr(line, "singletonparams", []))


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

_FIRST_NAME = {"first name", "given name", "prénom"}
_FAMILY_NAME = {"last name", "family name", "nom"}
_FULL_NAME = {"name", "full name", "nom complet"}
_EMAIL = {
    "e-mail 1 - value",
    "email 1 - value",
    "e-mail address",
    "email address",
    "e-mail",
    "email",
    "adresse de messagerie",
}
_NUMBERED_EMAIL = re.compile(r"e-?mail \d+ - value|e-?mail \d+ address|adresse de messagerie \d+")
_BIRTHDAY = {"birthday", "anniversaire", "date de naissance"}


class _Columns(NamedTuple):
    first: int | None
    family: int | None
    full: int | None
    emails: list[int]
    birthday: int | None

    @property
    def any(self) -> bool:
        return any(
            index is not None for index in (self.first, self.family, self.full, self.birthday)
        ) or bool(self.emails)


def _header_key(header: str) -> str:
    return " ".join(unicodedata.normalize("NFC", header).split()).casefold()


def _columns(header: list[str]) -> _Columns:
    keys = [_header_key(cell) for cell in header]

    def first_of(aliases: set[str]) -> int | None:
        return next((index for index, key in enumerate(keys) if key in aliases), None)

    return _Columns(
        first=first_of(_FIRST_NAME),
        family=first_of(_FAMILY_NAME),
        full=first_of(_FULL_NAME),
        emails=[
            index
            for index, key in enumerate(keys)
            if key in _EMAIL or _NUMBERED_EMAIL.fullmatch(key)
        ],
        birthday=first_of(_BIRTHDAY),
    )


def _delimiter(text: str) -> str:
    sample = "\n".join(_LINE_BREAK.split(text, maxsplit=20)[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        header = _LINE_BREAK.split(text, maxsplit=1)[0]
        return ";" if header.count(";") > header.count(",") else ","


def _parse_csv(text: str, *, day_first: bool) -> tuple[list[dict], int, int]:
    """Return (contacts, skipped, records) for CSV text with a header row."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    try:
        header = next(reader, None)
        columns = _columns(header or [])
        if not columns.any:
            raise ContactImportError(UNSUPPORTED)
        contacts: list[dict] = []
        skipped = records = 0
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            records += 1
            if records > MAX_CONTACTS:
                raise ContactImportError(TOO_MANY)
            contact = _row_contact(row, columns, day_first=day_first)
            if contact is None:
                skipped += 1
            else:
                contacts.append(contact)
    except csv.Error:
        raise ContactImportError(UNSUPPORTED) from None
    return contacts, skipped, records


def _row_contact(row: list[str], columns: _Columns, *, day_first: bool) -> dict | None:
    def cell(index: int | None) -> str:
        return row[index] if index is not None and index < len(row) else ""

    emails = [part for index in columns.emails for part in cell(index).split(":::")]
    return _make_contact(
        cell(columns.first),
        cell(columns.family),
        cell(columns.full),
        emails,
        cell(columns.birthday),
        day_first=day_first,
    )
