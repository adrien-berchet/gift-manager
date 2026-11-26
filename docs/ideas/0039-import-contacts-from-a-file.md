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

- An "Import contacts" link on the Recipients page (`recipient_list.html`, next to "New
  Person"; every navigation link leads there) and on the plain people list (`person_list.html`,
  next to "Create new person"), leading to a full upload page (not the offcanvas panel) that
  accepts one `.vcf` file (vCard 2.1, 3.0 and 4.0, one or many cards) or one `.csv` file
  (Google Contacts and Outlook exports, plus a simple `first name, family name, email,
  birthday` layout).
- Field mapping:
  - Names from vCard `N` or the CSV name columns. If the given name is empty, use the family
    name as first name and leave the family name empty (`Person.first_name` is required); if
    both are empty, use vCard `FN` (or a single CSV full-name column) as first name; if that is
    empty too, skip the contact and count it in the preview.
  - Email: the preferred address, else the first one, after normalization and validation;
    an invalid address is dropped and the contact is still imported.
  - Birthday from vCard `BDAY` or the CSV birthday column, including the year-less forms
    (`--MMDD`, `--MM-DD`). A date that is invalid under the `Person.clean()` rules is dropped
    with a note in the preview, and the rest of the contact is still imported.
- A preview listing every parsed contact with a checkbox, the mapped fields, and a "possible
  duplicate" marker when a person the user can access (`Person.objects.accessible_by(user)`:
  people they own and people shared with them) has the same email or the same first and family
  name (case- and accent-insensitive). The marker says which kind of match it is: "Already in
  your people" (an owned person matches; this wins when both match) or "Shared with you" (only
  a shared person matches). Duplicates are unchecked by default. Checking shared
  people too avoids a second record for someone a friend already shared, and reveals nothing
  the user cannot already see.
- Select all / select none, and an optional existing group to add every imported person to
  (only groups the user may add people to).
- On confirm, create the selected people in one transaction, each owned by the importing user
  through `PermissionService` (same as `BaseCreateView.form_valid`), redirect to the Recipients
  page people view (`gift_manager:recipients` with `?view=people`), and show a
  `messages.success` flash with the number imported and the number not imported (unchecked in
  the preview plus skipped while parsing), like `secret_santa_participant_import` in
  `gift_manager/views/secret_santa.py`. The toast rule in `docs/ai/architecture.md` allows it
  because the skipped contacts are not visible on the destination page.
- Limits: files up to 2 MB and up to 1,000 contacts per import, with a clear error when
  exceeded. Decode both vCard and CSV files as UTF-8 (`utf-8-sig`, so a BOM is accepted),
  falling back to Windows-1252 (`cp1252`, which Outlook writes and which, unlike Latin-1,
  decodes `œ` and `€`), then Latin-1.
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
- `gift_manager/email_encoding.py`: emails are stored encrypted with Fernet, which gives a
  different ciphertext each time, so emails can never be compared in SQL. Compare decoded
  values (`person.email`) in Python.
- `gift_manager/invitations.py` (`normalize_email`) and `gift_manager/suggestions/names.py`
  (`normalize_gift_name`: ligature expansion, NFKD, mark stripping, casefold): reuse the same
  normalizations for the duplicate check.
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
- `gift_manager/getting_started.py`,
  `gift_manager/templates/gift_manager/includes/getting_started_step.html` and
  `gift_manager/tests/test_getting_started.py` for the checklist link. Do not reuse
  `guided_url`: it is labelled "Guided", opens in the offcanvas panel (`data-action="create"`)
  and a test asserts only the plan step has it. Add an optional secondary link (URL and label)
  to `GettingStartedStep`, rendered as a plain link, and update the tests.
- `gift_manager/templates/gift_manager/help/topics/how-it-works.html` (`#recipients` section)
  for the Help mention; `gift_manager/help_topics.py` needs no change.
- `gift_manager/templates/gift_manager/recipient_list.html` and
  `gift_manager/templates/gift_manager/person_list.html`: the `page-header-actions` where the
  "Import contacts" link belongs (a plain link, no `data-action="create"`).
- `gift_manager/views/secret_santa.py` (`secret_santa_participant_import`): an existing import
  with a counts flash message.

Constraints and suggestions:

- Put parsing in a small, pure module (e.g. `gift_manager/contact_import.py`) that turns file
  bytes into `(contacts, skipped_count)`, independent of Django views, so it can be unit
  tested with fixture files. Each contact record has `given`, `family`, `emails` (all valid
  addresses, preferred first), `bday` (`[day, month, year or None]` or `None`) and
  `invalid_birthday` (true when a non-empty birthday value was dropped). The first four keys
  are exactly what `expected.json` lists. Put creation and duplicate detection in a service
  function, not in the view or templates.
- Emails: normalize with `invitations.normalize_email`, validate with
  `django.core.validators.validate_email`, and drop invalid ones. `Person.email_address` is a
  plain encrypted text field, so `full_clean()` does not check the email format; an invalid
  stored address would later fail `PersonForm`. Person creation and the duplicate check use
  `emails[0]`.
- Birthdays: valid when they pass the `Person.clean()` rules (a real calendar date, year 2000
  used for the leap-year check when there is no year, year not in the future).
- Duplicate check: load `Person.objects.accessible_by(user)` once and the owned primary keys
  once (`set(Person.objects.owned_by(user).values_list("pk", flat=True))`), then match in
  Python on the normalized decoded email or on the normalized first and family name. No query
  per contact.
- CSV parsing uses the standard `csv` module (sniff `,` or `;` as the delimiter). Match headers
  case-insensitively after trimming spaces. The aliases below are a starting point to check
  against real exports; Outlook translates its CSV headers into the user's language, so French
  aliases are needed:
  - First name: `First Name`, `Given Name`, `Prénom`.
  - Family name: `Last Name`, `Family Name`, `Nom`.
  - Full name, used only when both are missing: `Name`, `Full Name`, `Nom complet`.
  - Email: `E-mail 1 - Value`, `Email 1 - Value`, `E-mail Address`, `Email Address`, `E-mail`,
    `Email`, `Adresse de messagerie`.
  - Birthday: `Birthday`, `Anniversaire`, `Date de naissance`.
  Birthday values: `YYYY-MM-DD`, `YYYYMMDD`, `--MM-DD`, `--MMDD`, and slash dates. Slash
  dates are ambiguous: read them as day/month/year when the active language is French and
  month/day/year otherwise, and show the parsed date in the preview. Outlook writes `0/0/00`
  for an empty date: treat it as no birthday. No CSV fixture exists yet: add hand-written ones
  (Google current, Google legacy `Given Name` / `Family Name`, Outlook in English, Outlook in
  French, the simple layout) with their expected results in the same format as
  `expected.json`.
- vCard parsing uses a library rather than a
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
  - `vobject`: 18/18 with the pre-processing rules below (re-checked with exact equality and
    the skipped counts against the committed fixtures); it decodes quoted-printable and
    charsets, unescapes `N` components, keeps groups and parameters (`TYPE=pref`,
    `X-APPLE-OMIT-YEAR`), parses 1,000 cards in about 0.4 s, and runs without warnings on
    Python 3.12 and 3.13.
  - `vobjectx`: same results as `vobject`, but small (about 190 downloads a month) and
    presented by its authors as not meant for production.
  - `pythonvCard4`: unusable. It imports Pillow without declaring it, merges every card of a
    file into one contact, does not decode quoted-printable, drops grouped emails, and a
    year-less birthday raises and loses the card.
- Use `vobject` with these rules, all inside the parsing module:
  - Split the file into cards ourselves (on `BEGIN:VCARD` lines, case-insensitive) and parse
    each card separately. Parsed whole, one card missing `END:VCARD` makes `vobject` reject
    the entire file (`ParseError: Component VCARD was never closed`); split, only that card
    fails. Do not auto-close it: a card missing `END:VCARD` is skipped as malformed and
    counted.
  - Unfold lines (a line starting with a space or a tab continues the previous one), and join
    vCard 2.1 quoted-printable soft line breaks (a trailing `=`) only on lines whose parameters
    include `ENCODING=QUOTED-PRINTABLE`; `vobject` does not do the latter, and loses the end of
    long Android values.
  - After unfolding, keep only the properties we import (`BEGIN`, `END`, `VERSION`, `N`, `FN`,
    `EMAIL`, `BDAY`), matched case-insensitively after removing an optional group prefix
    (`item1.EMAIL`), and drop lines without a `:`. On the 2 MB file this cut parse time from
    0.39 s to 0.23 s and peak memory from 10.6 MB to 0.7 MB; on a hostile card with 200,000
    properties, from several seconds and 110 MB to under a millisecond.
  - Silence the `vobject` logger: it logs unreadable lines verbatim at ERROR level, which
    would put contact data in the logs.
  - `vobject` returns `BDAY` as a raw string: parse it ourselves (`YYYY-MM-DD`, `YYYYMMDD`,
    `--MMDD`, `--MM-DD`, an optional time part) and drop the year when
    `X-APPLE-OMIT-YEAR` is present. Order emails with the preferred one first: `TYPE=pref`
    (any case), `PREF=1` (vCard 4.0) or a bare `PREF` parameter (vCard 2.1, as in
    `EMAIL;PREF;INTERNET:`).
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
  Tests compare each file's parsed contacts (those four keys) with `expected.json` for exact
  equality. Contacts absent from it must be skipped: in `edge_cases.vcf`, the card without a
  name (`nobody@example.com`) and the card missing `END:VCARD` (Léa Roux), while the card
  after it (Marc Faure) is imported; the skipped count for that file is 2. The files are
  byte-exact (CRLF or LF endings, a UTF-8 BOM, Windows-1252 bytes in
  `outlook.vcf`) and a local `.gitattributes` keeps Git from normalizing them. Use them as the
  parser's unit test data; generate the 2 MB / 1,000-card file inside the size-limit test
  rather than committing it (it is over the `check-added-large-files` limit).
- Enforce the 2 MB limit before parsing (check the upload size, do not read more than the
  limit) and stop at 1,000 contacts, so a large or malicious file cannot exhaust memory.
- Design the preview step so it takes a list of contact records, not a file, so the Contact
  Picker follow-up can reuse it.
- Do not store the uploaded file. Keep the parsed contacts in the session under a random import
  id, and delete them after confirmation or cancellation. The confirm form posts only the
  import id, the indexes of the selected contacts and the optional group, never per-contact
  hidden fields or a formset.
- Selecting all 1,000 contacts posts more than 1,000 fields, which Django rejects with
  `TooManyFieldsSent` under the default `DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000`. It is not set
  in `GiftManager/settings/`: set it to 2000 in `GiftManager/settings/base.py`, say so in the PR
  (it is a global setting), and test a confirmation with 1,000 selected contacts.
- Contacts are third-party personal data: never log names, emails or birthdays, and do not
  include them in error reports.
- Validate each created person with the same rules as the person form (`full_clean()`), so the
  birthday constraint cannot be bypassed.
- The upload and confirm steps must work as plain form posts; HTMX can enhance the preview.

## Acceptance Criteria

- From the Recipients page (and the plain people list), a user opens "Import contacts",
  uploads a vCard file exported from Google Contacts or Apple Contacts and a Google Contacts
  CSV, sees a preview of the parsed contacts, and after confirming lands on the Recipients
  people view with a flash giving the imported and not-imported counts, and finds the selected
  contacts as new people they own.
- Names, emails and birthdays (with and without a year) are imported correctly; contacts with
  an invalid birthday or email are imported without it and the preview says so for the
  birthday; contacts without any name are skipped and counted; a contact with only a family
  name is imported with it as first name.
- Contacts matching a person the user owns or that is shared with them, by email or by first
  and family name, are marked "Already in your people" or "Shared with you" (owned wins) and
  unchecked by default; importing the same file twice with the defaults creates no duplicate.
- The parser returns exactly the contacts in `expected.json` for every `.vcf` fixture and for
  the new CSV fixtures, and the skipped counts described in the implementation notes.
- vCard files are parsed with `vobject` card by card, so a malformed card is skipped and
  counted without losing the rest of the file, and the PR states the new dependency and the
  `DATA_UPLOAD_MAX_NUMBER_FIELDS` change.
- Confirming an import with 1,000 selected contacts succeeds.
- Imported people are visible only to the importing user until shared, have an OWNER
  permission for that user, and are added to the chosen group only when the user may add
  people to it.
- Files over 2 MB or with more than 1,000 contacts, empty files, and files in an unsupported
  format are rejected with a translated error and create nothing.
- Unit tests cover the parser with fixture files (vCard 2.1, 3.0 and 4.0, folded lines,
  year-less birthdays, UTF-8 with BOM, Google and Outlook CSV headers); integration tests cover
  the upload, preview, confirm, permission and duplicate behavior on PostgreSQL; one Playwright
  test covers the upload-preview-import flow.
- The getting-started "Add a recipient" step shows a plain link to the import, and the existing
  plan step's "Guided" link is unchanged.
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
