# Pre-release QA report — 2026-11-12

Branch: `received_log` (commits `860ca52` "Add received gift logs" and `98f32af` "Harden received
gifts, streamline reveal flows, and unify warning colors"), running locally with `docker compose`.

## Summary

The main flows work end to end and access between the two test accounts is enforced on the server.
No blocker was found. The most important problems are in the new reveal and received-gift features:
co-givers can be dropped from the recipient's copy, two display bugs on the reveal form, and a wish
toggle that has no effect for revealed gifts.

**Caveat:** `testuser` is a **superuser**, which bypasses most permission checks. Access tests were
only meaningful from Alice's side. Use two ordinary accounts for the next round.

## Scope and method

- **Browser (Chrome, both accounts in turn):** reveal of a person plan and of a group plan;
  wish → plan → given → reveal; received-gift log create / edit / delete; reaction rating and note;
  share reaction with giver; thank-you toggle; list filters; wishlist; gifts, gift plans,
  recipients, events and profile pages.
- **Scripts:**
  - visited every link reachable from the home page as both users, in English and French;
  - requested and posted to one user's objects as the other user;
  - posted invalid values to forms (unsafe links, out-of-range ratings, other users' IDs, long text);
  - scanned French pages for untranslated text;
  - Playwright screenshots at 390 px wide of 8 main pages (no horizontal scrolling on any of them)
    and of the reveal page in light and dark theme.

## Findings

Severity: High / Medium / Low. "New" means introduced by this branch.

### New features (received gifts and reveal)

| ID | Severity | Finding |
|----|----------|---------|
| R1 | Medium | Co-givers disappear from the recipient's copy |
| R2 | Medium | The recipient cannot undo "wish received" on a revealed gift |
| R3 | Medium | Gift title invisible in dark mode on the reveal form |
| R4 | Low/Medium | Reveal side panel scrolls horizontally |
| R5 | Low/Medium | The "Reveal to recipient" shortcut is easy to miss |
| R6 | Low | Received date has no limits |
| R7 | Low | Out-of-range year filter returns a 500 |
| R8 | Low | Smaller issues (duplicate error, bare 403, wish count, filters, search) |

**R1 — Co-givers disappear from the recipient's copy (Medium).**
A group plan owned by `testuser` and Bob was revealed to Alice. The reveal form announced
"Givers shown on snapshot: Bob Seed, testuser", but Alice's received gift only shows
"Colleague Work" (her own contact linked to `testuser`); Bob is lost.
Cause: `_create_revealed_gift_for_target` in `gift_manager/received_gifts.py` (around line 236)
clears the free-text giver label as soon as one owner matches a contact, and
`includes/received_gift_givers.html` only falls back to `source_givers_text` when no persons,
groups or label are set.

**R2 — The recipient cannot undo "wish received" on a revealed gift (Medium).**
Turning off "Mark the wish as received", or deleting the received gift, leaves the wish marked as
received, because the giver's linked plan is "Given" and `recompute_wish_fulfilled` in
`gift_manager/wishlist.py` (lines 235–237) treats a given plan as fulfilling the wish. A wish that
can be received again and again (e.g. food) can therefore never become available again once a
friend's plan for it is given. The toggle reports success but changes nothing.

**R3 — Gift title invisible in dark mode on the reveal form (Medium).**
The snapshot summary card is near-white (`rgb(248,249,250)`) and so is its title text
(`rgb(248,250,252)`). The card uses Bootstrap's `bg-body-tertiary`, which follows
`data-bs-theme`, while the app switches theme with `data-theme`. Affects both the side panel and
the full page. File: `includes/forms/relation_reveal_fields.html` (around line 41).

**R4 — Reveal side panel scrolls horizontally (Low/Medium).**
In "Adjust snapshot details", the Date given / Occasion row is 444 px wide inside a 352 px panel,
so the Occasion field is cut off and a horizontal scrollbar appears. `col-md-6` reacts to the
window width, not the panel width. On the full page, the "Occasion" label sits beside its field
while "Date given" sits above, so the two fields are misaligned.

**R5 — The "Reveal to recipient" shortcut is easy to miss (Low/Medium).**
It only appears as an action in a toast that closes after 5 s
(`static/gift_manager/js/app-shell.js`, `delay: 5000`); I missed it twice. It is only offered when
an existing plan is edited to "Given" (`RelationUpdateView.form_valid` in `views/relation.py`),
not when a plan is created directly as "Given" or marked given by a quick action. Card and
history "Reveal" buttons remain available as alternatives.

**R6 — Received date has no limits (Low).**
`received_on` accepted 2027-06-01 (future) and 1800-01-01.

**R7 — Out-of-range year filter returns a 500 (Low).**
`/profile/received-gifts/?year=99999999999` → Internal Server Error. `int(filter_year)` is not
range-checked before filtering (`views/received_gift.py`, around line 97). Non-numeric values are
handled correctly.

**R8 — Smaller issues (Low).**
- An invalid link on the reveal form shows two errors for the same field ("Enter a valid URL." and
  "Enter a valid http or https URL.").
- Opening the reveal URL of an already-revealed plan shows a bare 403 page (e.g. from a stale
  toast or an old tab).
- The profile page counts received wishes as active: "3 active wishes" while only one is active
  (`views/profile.py`, line 62, filters only on `is_archived`).
- The giver filter on the received-gift list has no entry for free-text givers.
- Global search returns neither received gifts nor wishes.

### Rest of the application

| ID | Severity | Finding |
|----|----------|---------|
| A1 | Medium | Person page does not refresh after editing a plan in its side panel |
| A2 | Medium (admins) | A superuser can delete the shared "Birthday" event from the normal UI |
| A3 | Low | Debug log line records session cookies |
| A4 | Low | Broken Cancel link on the delete-account page |
| A5 | Low | Visual inconsistencies |

**A1 — Person page does not refresh after editing a plan in its side panel (Medium).**
On a person's detail page, editing a plan in the side panel and saving it as "Given" left the card
on "Idea", the wish on "Planned" and the in-progress / given counters unchanged until a manual
reload.

**A2 — A superuser can delete the shared "Birthday" event from the normal UI (Medium, admins only).**
The events list shows Edit / Delete for the global event to a superuser, and deleting it sets the
event to empty on every plan of every user. The event is recreated lazily, under a new ID.
Ordinary users are correctly refused (403 on edit, delete and leave, checked as Alice).

**A3 — Debug log line records session cookies (Low).**
`BaseDeleteView.post` (`views/base.py`, line 806) logs `request.headers` at DEBUG level, including
the `Cookie` header with `sessionid` and `csrftoken`. Production logs at WARNING by default, so
this only matters when `LOG_LEVEL=DEBUG` is set.

**A4 — Broken Cancel link on the delete-account page (Low).**
Without a Referer, Cancel links to the literal string `gift_manager:user_account` and returns a 404
(`GiftManager/views.py`, line 151). That URL name does not exist either.

**A5 — Visual inconsistencies (Low).**
- The Gift, Event and Status dropdowns in the gift-plan side panel have no `form-select` class and
  render as unstyled browser controls.
- The "Needs attention" dashboard tile is always orange, even at 0, while the section below can
  list an "Awaiting reaction" card that the counter does not include.
- Prices are formatted two ways ("€24.50" in the gifts list, "24.50 €" in budgets and wishes).
- The Household group shows "1 member" in the recipients list but "2 members" in the group
  explorer (the user's own person is counted in one place only).

### Open question

**Q1 — Co-owner names shown to non-friends.** A revealed group gift shows co-owners' full names
(Bob Seed) to a recipient who is not their friend. Is that intended?

## Decisions (2026-11-12)

| Finding | Decision |
|---------|----------|
| R2 | The recipient's choice wins: turning off "Mark the wish as received" or deleting the received gift makes the wish available again, even if the giver's plan is "Given". |
| Q1 | Do not show the names of co-owners the recipient does not know; show "and N other(s)" instead. |
| R5 | Make the "Reveal to recipient" toast stay until closed; also offer the reveal when a plan is created as "Given" and after the quick "mark as given" action. |
| A2 | Block editing and deleting the global "Birthday" event entirely, superusers included. |
| R6 | No limits on the received date; show a non-blocking warning when the date is in the future. |
| R8 / A5 | Global search coverage, free-text giver filter and price formatting are recorded as ideas 0035, 0036 and 0037. |
| A5 | "Needs attention" tile: orange only when its count is not 0. Its count keeps excluding "Awaiting reaction" plans. |
| R8 | The profile's active wish count excludes wishes already received. |
| A5 | Member counts are the same on every page and always include every member, the user's own person included. |
| R8 | Opening the reveal URL of an already-revealed plan redirects to the plan with an "Already revealed" message. |
| Setup | `testuser` is a superuser on purpose. The dev database was reset with `seed_data --flush` after this pass. |

## Verified as working

- Reveal rules: only explicit owners who are friends with the recipient can reveal; a second reveal
  is refused (403); for a group, only member accounts that are friends receive a copy and owners
  are excluded.
- The recipient's copy holds the right title, link (falls back to the gift link), date, occasion,
  note from the giver, linked wish, and marks the wish as received.
- Sharing a reaction fills the giver plan's empty rating and note; the button then disappears.
- Deleting a revealed plan keeps the recipient's copy (source link cleared).
- Cross-user access: received gifts and reveal URLs of the other user return 404 on read, edit,
  delete and every toggle; prefilled create pages (`?duplicate_of=`, `?giver=`, `?wish=`,
  `?person=`) leak no data.
- Server-side validation rejects other users' givers, a rating of 9, `javascript:` links and
  over-long titles. Script tags are escaped everywhere they were tried.
- New screens are fully translated into French.
- Received-gift create works without JavaScript (plain POST redirects to the list).
- Thank-you toggle updates the card and the pending counter.
- Gift creation with tag, price and link; inline editing in the gifts grid.
- No horizontal overflow at 390 px on: received gifts list, detail and form, wishlist, profile,
  reveal page, gift plans, dashboard.

## Test environment notes

- Parallel requests sometimes return 500 "dictionary changed size during iteration". This comes
  from django-debug-toolbar (template panel), not from the app.
- The debug toolbar also logs a JS error (`ensureHandleVisibility`) on every page.

## Data changed in the development database

- **Deleted the global "Birthday" event** (finding A2) and recreated it with
  `Event.objects.get_birthday_event()`; its ID changed, and plans that pointed to the old one
  (e.g. "test guided") no longer have an event.
- **Created:**
  - plans: QA Headphones (Alice, given, revealed), aaaa (Household group, given, revealed, co-owned
    by Bob), aaaa (Alice, idea), QA Board Game (Alice, given, not revealed);
  - Alice's wish "QA Headphones";
  - received gifts: "QA future gift", "QA nojs", "QA post", group reveal "aaaa";
  - gift "QA Board Game" with the Books tag.
- **Deleted:** plan `a5818b58-8731-4ca6-89f7-20f03f1c14c9` and Alice's received gift for
  QA Headphones.

## Second pass (after commits 2efed5d and 806e9fd)

Method: link crawl as testuser, alice and bob (English and French), cross-user access checks
between alice and bob, then browser scenarios with Playwright against the live Docker app
(the Chrome extension stopped delivering clicks during this pass).

### All decided fixes verified

Reveal from a plan created as Given (toast stays open), readable reveal summary in dark mode,
stacked snapshot fields without sideways scrolling, future-date warning, one error for an unsafe
link, co-givers shown as "testuser and 1 other" (no unknown name), editing a revealed gift
without contacts, wish reopened by the recipient becoming "Available" with Claim and Plan
again, person page refreshing after a side-panel save, stale reveal link redirecting to the plan
with "This gift plan was already revealed.", Birthday event locked for the superuser (detail,
grid, edit URL 403), Household shown with 2 members on both pages, account Cancel links to the
profile, French "En attente de réaction" section, no horizontal overflow at 390 px. No 500 in
the crawl and no cross-user data leak.

### New findings

| ID | Severity | Finding |
|----|----------|---------|
| N1 | Medium | The future-date warning is unreadable in dark mode (contrast 1.83:1): `text-warning-emphasis` follows Bootstrap's `data-bs-theme`, not the app's `data-theme` (introduced by the R6 fix). |
| N2 | Medium | For a viewer (bob on Mom), the Delete button on person, gift and event pages leads to a bare 403, although its tooltip says the object "will only be unshared with you". The leave flow only works with `?intent=leave_access`, and its confirmation page still says "Are you sure you want to delete this item?". |
| N3 | Low | Plan lists on event and gift pages show Edit links to viewers, which lead to a 403. |
| N4 | Low | The "Needs attention" tile also counts unassigned gifts: it shows an orange "2" while the section below says "No gift plans need attention." |
| N5 | Low | On a recipient's wishlist, the giver still sees "Claimed by you · Planned" after marking the plan Given (until it is revealed). |
| N6 | Low | The person page says "No gift plans found for this person. Add one?" when the person has given plans (only the in-progress list is empty). |
| N7 | Low | Creating a plan directly as Given shows "Gift plan marked as given." instead of a creation message. |

### Decisions on the second pass

| Finding | Decision |
|---------|----------|
| N1 | Fix the warning colour (regression from R6). |
| N2 | A viewer's Delete becomes "Remove my access". |
| N4 | Unassigned gifts are ideas kept for later, not attention items; the Gifts page gets a "Not in a plan yet" view, linked from the dashboard tile. |
| N3, N5-N7 | Fix. |

### Notes from the review of the N1-N7 fixes

- "Delete" now always does what the button says: while someone else holds access, deleting
  only removes the user's own access (this was already the server rule for editors and
  co-owners too), so those users also see "Remove my access".
- **Open question:** the only owner of an object shared with others cannot delete it (the
  server refuses with "At least one owner is required."). The button is now disabled with that
  reason instead of failing after confirmation. Should the sole owner be able to delete it for
  everyone, or hand ownership over first?
- Known limitations, left as they are: a user who has both a direct share and an inherited
  access to a group keeps seeing it after "Remove my access"; grid rows and bulk delete still
  offer no "Remove my access" for viewers; on every grid page, search and filters keep their
  initial data after a background refresh (pre-existing, not specific to the new gift filter).
