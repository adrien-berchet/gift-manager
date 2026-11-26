# Idea: Import Contacts From A File

## Status

Ready

## Summary

Let a user import their existing contacts as people (recipients) instead of creating them one
by one. The user uploads a contacts file exported from their phone, mail client or address
book (vCard `.vcf` or CSV), reviews the parsed contacts in a preview, picks the ones to keep,
and Gift Manager creates one person per selected contact, owned by that user.

The import maps only what a person already stores: first name, family name, email address and
birthday (day and month, year optional). Contacts that look like people the user already has
are flagged in the preview and left unchecked by default, so re-importing the same file does
not create duplicates.

A later slice can let users pick contacts directly from their phone's address book instead of
exporting a file (see Dependencies Or Related Ideas).

## Motivation

Adding recipients is the first step of the getting-started checklist ("Add a recipient"), and
today it means filling in the person form once per person. Most users already keep these
people, often with emails and birthdays, in Google Contacts, Apple Contacts or Outlook. Typing
them again is slow and error-prone, and it delays the moment the app becomes useful (birthday
reminders, calendar feed, gift plans).

## User Value

- New users fill their address book in a minute instead of person by person.
- Birthdays come along with the contacts, so birthday reminders, the dashboard section and the
  calendar feed (ideas `0002`, `0003`) work right away.
- Emails come along too, which helps the existing person-to-account link suggestions when those
  people later join or are invited.
- The preview keeps the user in control: nothing is created before they confirm, and their
  hundreds of work contacts do not flood the address book.

## Possible Scope

- An "Import contacts" action on the people page next to "Create new person", leading to an
  upload page that accepts one `.vcf` file (vCard 3.0 and 4.0, one or many cards) or one `.csv`
  file (Google Contacts and Outlook export headers, plus a simple
  `first name, family name, email, birthday` layout).
- Field mapping:
  - First and family name from vCard `N` (falling back to `FN`) or the CSV name columns.
    Contacts without any name are skipped and counted in the preview.
  - Email: the first (or preferred) address only.
  - Birthday from vCard `BDAY` or the CSV birthday column, including the year-less forms
    (`--MMDD`, `--MM-DD`). An invalid or partial date is dropped with a note in the preview, the
    rest of the contact is still imported.
- A preview listing every parsed contact with a checkbox, the mapped fields, and a "possible
  duplicate" marker when a person the user can access (`Person.objects.accessible_by(user)`:
  people they own and people shared with them) has the same email or the same first and family
  name (case- and accent-insensitive). The marker says which kind of match it is ("Already in
  your people" or "Shared with you"). Duplicates are unchecked by default. Checking shared
  people too avoids a second record for someone a friend already shared, and reveals nothing
  the user cannot already see.
- Select all / select none, and an optional existing group to add every imported person to
  (only groups the user may add people to).
- On confirm, create the selected people in one transaction, each owned by the importing user
  through `PermissionService` (same as `BaseCreateView.form_valid`), then show a summary
  ("12 people imported, 3 skipped") and return to the people page.
- Limits: files up to 2 MB and up to 1,000 contacts per import, with a clear error when
  exceeded; text decoding of UTF-8 (with or without BOM) and a Latin-1 fallback for CSV.
- A short mention in the Help "Recipients" section (`how-it-works#recipients`) and a link to
  the import from the getting-started "Add a recipient" step.
- French translations for all new strings.

## Out Of Scope

- Live synchronization with Google, Apple or Microsoft accounts (OAuth People API, CardDAV),
  and any background re-import.
- Updating or merging existing people from the file; the first slice only creates new people.
- Fields a person does not store: phone numbers, postal addresses, photos, organization,
  contact notes. Importing contact notes into `Person.notes` is deliberately left out because
  those notes are shared with everyone the person is shared with.
- Automatically sharing imported people with friends or linking them to accounts.
- Exporting people to vCard or CSV (a possible separate idea).
- Picking contacts from the phone with the browser Contact Picker API: a follow-up slice
  described under Dependencies Or Related Ideas.

## Implementation Notes For AI Agent

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/models.py`: `Person` (`first_name`, `family_name`, `email_address` stored
  encoded, `set_email()`, `birthday_day` / `birthday_month` / `birthday_year` and the birthday
  check constraint plus `Person.clean()`), `PersonGroup`, `PersonPermission`.
- `gift_manager/email_encoding.py`: emails are stored encoded; compare duplicates on decoded
  values or through the existing helpers, never on raw `email_address`.
- `gift_manager/views/person.py`: `PersonCreateView` and the people list view, for URL,
  template and permission patterns.
- `gift_manager/views/base.py`: `BaseCreateView.form_valid` shows how a new object gets its
  OWNER permission through `PermissionService.create_or_update_permission`.
- `gift_manager/forms.py`: `PersonForm` (birthday selects, groups saved through
  `GroupHierarchyService` with authority checks); reuse the same group authority rule for the
  optional target group.
- `gift_manager/group_hierarchy_service.py`: adding people to a group.
- `gift_manager/account_links.py`: existing person/account email matching, useful context for
  the duplicate check.
- `gift_manager/getting_started.py` and `gift_manager/help_topics.py` plus
  `gift_manager/templates/gift_manager/help/topics/how-it-works.html` for the checklist link
  and the Help mention.
- `gift_manager/templates/gift_manager/person_list.html`: the page header actions where the
  "Import contacts" button belongs.

Constraints and suggestions:

- Put parsing in a small, pure module (e.g. `gift_manager/contact_import.py`) that turns file
  bytes into a list of plain contact records, independent of Django views, so it can be unit
  tested with fixture files. Put creation and duplicate detection in a service function, not
  in the view or templates.
- CSV parsing uses the standard `csv` module. vCard parsing uses a library rather than a
  hand-written parser: line unfolding, escaping, `CHARSET` and quoted-printable values from old
  vCard 2.1 exports, and the 3.0 / 4.0 differences are easy to get wrong.
- **Library decision (spike of 2026-11-26): use `vobject`.** Candidates seen on PyPI:
  `vobject` (Apache-2.0, about 2.5 M downloads a month, 0.9.9 released December 2024, commits
  on `py-vobject/vobject` in August 2026, no known vulnerability in OSV), `vobjectx` (a fork),
  `pythonvCard4`, and, rejected without testing, `PyContactFile` (small, documented vCard
  limitations), `vcard` (a validator under AGPL-3.0) and `vcf_parser` / `pyvcf3` (genomics
  "VCF" files).
- Spike method: fixture files reproducing Google (3.0, grouped `item1.EMAIL`, `--MM-DD`), Apple
  (3.0, `X-APPLE-OMIT-YEAR=1604`, folded base64 photo, company card), Android (2.1,
  `CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE` with soft line breaks), Outlook (2.1, Windows-1252
  bytes, `BDAY:YYYYMMDD`) and vCard 4.0 (`PREF=1`, `--MMDD`, text birthday) exports, plus edge
  cases (BOM, LF endings, lowercase keywords, tab folding, escaped `\,`, invalid date, card
  without a name, garbage line, card missing `END:VCARD`) and a 2 MB file of 1,000 cards. The
  fixtures were hand-written from the known formats, not taken from real exports, so check
  against a real export from each source during implementation.
- Results (18 expected contacts):
  - `vobject`: 18/18 with the two pre-processing steps below; it decodes quoted-printable and
    charsets, unescapes `N` components, keeps groups and parameters (`TYPE=pref`,
    `X-APPLE-OMIT-YEAR`), parses 1,000 cards in about 0.4 s, and runs without warnings on
    Python 3.12 and 3.13.
  - `vobjectx`: same results as `vobject`, but small (about 190 downloads a month) and
    presented by its authors as not meant for production.
  - `pythonvCard4`: unusable. It imports Pillow without declaring it, merges every card of a
    file into one contact, does not decode quoted-printable, drops grouped emails, and a
    year-less birthday raises and loses the card.
- Use `vobject` with these rules, all inside the parsing module:
  - Split the file into cards ourselves (on `BEGIN:VCARD` lines) and parse each card
    separately. Parsed whole, one card missing `END:VCARD` makes `vobject` reject the entire
    file (`ParseError: Component VCARD was never closed`); split, only that card is affected.
  - Unfold lines and join vCard 2.1 quoted-printable soft line breaks (a trailing `=`)
    before parsing; `vobject` does not, and loses the end of long Android values.
  - Keep only the properties we import (`BEGIN`, `END`, `VERSION`, `N`, `FN`, `EMAIL`, `BDAY`)
    before parsing. On the 2 MB file this cut parse time from 0.39 s to 0.23 s and peak
    memory from 10.6 MB to 0.7 MB; on a hostile card with 200,000 properties, from several
    seconds and 110 MB to under a millisecond.
  - Silence the `vobject` logger: it logs unreadable lines verbatim at ERROR level, which
    would put contact data in the logs.
  - `vobject` returns `BDAY` as a raw string: parse it ourselves (`YYYY-MM-DD`, `YYYYMMDD`,
    `--MMDD`, `--MM-DD`, an optional time part) and drop the year when
    `X-APPLE-OMIT-YEAR` is present. Order emails with the preferred one first (`TYPE=pref`
    or `PREF=1`).
  - Hostile 2 MB inputs (a 2 MB line, 100k parameters, 1-character folded lines, a 2 MB
    photo or quoted-printable value) all finished in under 0.6 s without the filter; malformed
    ones raise `ParseError`, which must be caught per card.
- Add `vobject` with `uv` and mention the new production dependency in the PR, as `AGENTS.md`
  asks. It brings `pytz` as a new transitive dependency (`six` and `python-dateutil` are
  already in `uv.lock`). Keep it behind the parsing module so the rest of the code only sees
  plain contact records, and swapping libraries later touches one file.
- The spike fixtures are in `gift_manager/tests/data/contact_import/` (fake contact details
  only): one `.vcf` file per source plus `edge_cases.vcf`, and `expected.json` listing, per
  file and in file order, the contacts that must be imported as
  `{given, family, emails (preferred first), bday: [day, month, year or null] or null}`.
  Contacts absent from `expected.json` must be skipped (the card without a name); the card
  missing `END:VCARD` (Léa Roux) may be recovered or skipped, but the card after it must be
  imported. The files are byte-exact (CRLF or LF endings, a UTF-8 BOM, Windows-1252 bytes in
  `outlook.vcf`) and a local `.gitattributes` keeps Git from normalizing them. Use them as the
  parser's unit test data; generate the 2 MB / 1,000-card file inside the size-limit test
  rather than committing it (it is over the `check-added-large-files` limit).
- Enforce the 2 MB limit before parsing (check the upload size, do not read more than the
  limit) and stop at 1,000 contacts, so a large or malicious file cannot exhaust memory.
- Design the preview step so it takes a list of contact records, not a file, so the Contact
  Picker follow-up can reuse it.
- Do not store the uploaded file. Keep the parsed preview between the two steps in the session
  or in a signed form payload, and drop it after confirmation or cancellation.
- Contacts are third-party personal data: never log names, emails or birthdays, and do not
  include them in error reports.
- Validate each created person with the same rules as the person form (`full_clean()`), so the
  birthday constraint cannot be bypassed.
- The upload and confirm steps must work as plain form posts; HTMX can enhance the preview.

## Acceptance Criteria

- From the people page, a user uploads a vCard file exported from Google Contacts or Apple
  Contacts and a Google Contacts CSV, sees a preview of the parsed contacts, and after
  confirming finds the selected contacts as new people they own.
- Names, emails and birthdays (with and without a year) are imported correctly; contacts with
  an invalid birthday are imported without the birthday and the preview says so; contacts
  without a name are skipped and counted.
- Contacts matching a person the user owns or that is shared with them, by email or by first
  and family name, are marked as possible duplicates with the kind of match and unchecked by
  default; importing the same file twice with the defaults creates no duplicate.
- vCard files are parsed with `vobject` card by card, so a malformed card is skipped and
  counted without losing the rest of the file, and the PR states the new dependency.
- Imported people are visible only to the importing user until shared, have an OWNER
  permission for that user, and are added to the chosen group only when the user may add
  people to it.
- Files over 2 MB or with more than 1,000 contacts, empty files, and files in an unsupported
  format are rejected with a translated error and create nothing.
- Unit tests cover the parser with fixture files (vCard 2.1, 3.0 and 4.0, folded lines,
  year-less birthdays, UTF-8 with BOM, Google and Outlook CSV headers); integration tests cover
  the upload, preview, confirm, permission and duplicate behavior on PostgreSQL; one Playwright
  test covers the upload-preview-import flow.
- Existing person creation, editing and the getting-started checklist keep working.

## Dependencies Or Related Ideas

- `0002` Person Birthdays And Personal Occasions and `0003` Reminders And Calendar Feed:
  imported birthdays feed these directly.
- `0028` Wishlists And Collaborative Gift Giving: imported emails can help link people to
  accounts later through the existing suggestions.
- Follow-up slice, decided but not part of the first one: on browsers that support the Contact
  Picker API (`navigator.contacts.select`, mainly Chrome on Android), a "Pick from my phone
  contacts" button next to the file upload, hidden where the API is missing. Picked names and
  emails go through the same preview and duplicate check. The button and the preview must say
  clearly that birthdays are not imported this way (the API does not expose them) and point to
  the file import for birthdays. The picker returns the name as one string: put it in the first
  name unless a simple split proves reliable. Phone numbers and addresses it can return are
  ignored.
- Other follow-ups: contact export and optional live sync with an address book provider.

## Open Questions

- None blocking. Check one real export from each source (Google, Apple, Android, Outlook)
  against the spike results early in implementation.
