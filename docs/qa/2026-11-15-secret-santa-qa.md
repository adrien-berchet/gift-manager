# Secret Santa, capture and guest link QA report — 2026-11-15

Branch `ai_implementation` at `727bc44`, compared with `origin/main` (`a6cecfc`; the local `main`
is stale). Local Docker app on `localhost:8000`, data reset with `seed_data --flush` first.
Accounts: `alice` (organizer, linked participant) and `bob` (participant who attaches his
account, outsider for access tests), plus logged-out visitors for personal and guest pages.
`testuser` was not used.

## Summary

The new features work end to end and keep their secrets: no blocker or high finding. The
Secret Santa draw, emails, personal pages, account linking, wishlist sharing, repairs, closing
and the "start from a previous exchange" flow all behave as the design says, and every
organizer URL returns 404 to another user. The findings are small: one information leak to a
visitor who already holds someone else's personal link, a cosmetic button, and an older Edit
link in the group explorer that leads viewers to a 403. Four product questions are listed.

## Scope and method

Commits since the last QA pass (`fd1c6fc`): Secret Santa (17 commits), the capture bookmarklet
and read-only wishlist share link (`a685df5`), received-gift search and giver filter (`eb2c21a`).

- **Playwright scripts, one context per user:** create an exchange, import a group, type
  participants, exclusion set, draw; personal pages logged out, as the linked account and as
  another account; exchange wishes and note; sharing real wishes; attaching an account; dashboard
  card and "Plan a gift"; pairings and "Show link" warnings; remove and repair (refused and
  valid), add a latecomer, "Send again", new link, close with reveal; copy with "no repeat",
  invitations, decline from the personal page, draw; impossible draw; delete.
- **HTTP checks:** every organizer URL as `bob` (GET and POST); POSTs to a closed personal page;
  response headers of personal, reveal and guest pages; capture page with hostile query strings;
  received-gift filters with hostile values.
- **Emails:** read from the console backend (`docker logs`): content, stop link,
  `List-Unsubscribe`, who receives one after each repair.
- **Layout:** 390 px phone and dark theme for the list, detail, form, dashboard, personal and
  guest pages, in English and French.
- **Scripts of the skill:** `crawl.py alice bob --langs en fr` (976 pages) and
  `cross_user_access.py alice bob`.
- Pairings were checked in the database after every draw and repair.

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| R1 | Low | A visitor holding another participant's link learns that the participant has an account |
| R2 | Low | "Remove" in a drawn exchange's participant row has no button border |
| A1 | Medium | The group explorer offers Edit to viewers of a person, which ends in a 403 |

**R1 — Attaching to an already linked participation reveals it (Low).** Log in as `bob`, open
Alice's personal link (Alice's participation is linked to `alice`), click "I have a Gift
Manager account". Bob gets the confirmation "Link your account to participant Alice Seed…?",
and only after confirming: "This participation is already linked to an account." Expected:
logged-out and other visitors cannot tell a linked participant from an unlinked one (design,
"Secrecy rules in code"). Actual: the refusal tells them. The link stayed on `alice` (checked
in the database). It needs a leaked personal link, so the impact is small; any refusal at that
point reveals the state, so the fix is a product choice (see Q4).
Code: `secret_santa_attach_start` and `secret_santa_attach_confirm`,
`gift_manager/views/secret_santa.py:242` and `:298`. Evidence: `s6_hijack_confirm.png`.

**R2 — "Remove" looks like a link, not a button (Low).** In a drawn exchange, each participant
row shows Send again, Show link, Edit, New link as outlined buttons, and "Remove" as red text
without the outline, though it has the same `btn btn-sm btn-outline-danger` classes
(`gift_manager/templates/gift_manager/includes/secret_santa_participants.html:84`). Evidence:
`s10_01_show_link.png`.

**A1 — Group explorer offers Edit to a viewer (Medium, older than this branch).** As `bob`
(viewer of Mom and Dad), open `/en/person_groups/explore/<Close Family>/`: each member row has
an Edit button to `/en/persons/<id>/edit/`, which answers 403. The crawl found it in both
languages. Cause: the Edit link has no permission check,
`gift_manager/templates/gift_manager/person_group_explorer.html:224` (unchanged since August).
The "Row menus" journey in `scenarios.md` expects lists not to offer actions the user may not use.

## Decisions and fixes

Decided by the user the same day and fixed on the branch (tests first, reviewed by a
reviewer agent, journeys re-run on the live app):

| Item | Decision | Fix |
|------|----------|-----|
| Q1 | Carry a self-attached account over to a copy | `copy_exchange` keeps it, without the self-attached flag (shown once invited or drawn) and with an empty wishlist selection; a self-attached account wins over a stale address-book link |
| Q2 | No automatic email; a checkbox instead | "Send the new link by email" under "New link", shown when "Send again" is; same cooldown and limits |
| Q3 | Show the guidelines to the organizer | Under the summary line of the exchange page |
| Q4 / R1 | Keep the plain refusal, but say it before the confirmation | The confirmation page shows "This page is already linked to another Gift Manager account. If it is yours, log in with that account." The limit, including that the organizer can learn it through "Show link", is written in the design |
| R2 | Fix | Light-theme `.btn-outline-danger` had no border anywhere in the app (`.btn { border: none }`); it now has a red outline like the other outlined buttons, and the dark pressed state keeps a readable fill |
| A1 | Fix | The explorer shows Edit only for members the user can edit (`PersonQuerySet.with_edit_flag`) |

Found while fixing R2 and fixed too: light-theme `.btn-outline-warning` ("Redraw everything")
had no border and Bootstrap's yellow text (about 1.6:1 on white); the dark-theme
`.btn-outline-danger` hover put white text on a pale red (about 1.9:1). Left open: the
`btn-outline-success`, `-info`, `-dark` and `-light` variants (one use each) have no border in
the light theme either.

The QA scripts default to port 8001 while `docker-compose.yml` publishes `${WEB_PORT:-8000}`:
a machine without `WEB_PORT=8001` in its `.env` needs `QA_BASE_URL`.

The original questions follow.

## Decisions needed

- **Q1 — Copying an exchange drops self-attached accounts.** "Start a new exchange from this
  one" keeps the organizer's link and links that come from an address-book person, but not an
  account the participant attached themselves (`gift_manager/secret_santa/service.py:225`).
  Bob attached his account in 2026; in the 2027 copy he is unlinked, does not see the exchange
  on his dashboard after the invitation, and must attach again. Keep (consent per exchange), or
  carry the link over?
- **Q2 — "New link" sends nothing.** After "Create a new link", the participant's old link is
  dead and they get no email; the organizer must also press "Send again". Should a new link be
  emailed automatically when the participant has an address?
- **Q3 — Guidelines are not shown on the organizer page.** The organizer sees date, budget and
  rules on the exchange page, but the guidelines only in Edit and on personal pages.
- **Q4 — Wording of the R1 refusal.** Refuse at the first step with a generic message, keep the
  current behaviour, or let the link holder decide nothing until the owner detaches?
- **Dashboard card shows the assignment** ("You give a gift to: Dad Seed") on the dashboard,
  not just on the personal page. It is the user's own dashboard, so probably fine; noted for
  shared screens.

## Verified as working

**Secret Santa — organizer**

- Create (flatpickr date, budget, guidelines, rules, "I take part"); navigation entry under More.
- Import a group (re-import reports "0 added, 3 already there"); typed participants; a name
  that differs only by case is refused; exclusion sets.
- Draw respects exclusions and "no mutual draw"; impossible draw says "No draw is possible
  with these exclusions." and leaves the exchange a draft.
- Emails: one per participant with an address, subject and greeting with the name, personal
  link, signed stop link, `List-Unsubscribe` and one-click header; Carol (no email) is marked
  "Link to hand out".
- "Send again" is hidden during the 5-minute cooldown, then sends one email and hides again.
- "Show all pairings" warns, with the stronger text for an organizer who takes part; "Show
  link" warns; both are POST, `private, no-store`, nothing in the URL, 400 without `confirm=1`.
- "New link": the old link returns 404, the new one works.
- Remove and repair: refused when the Santa would inherit someone from their exclusion set
  ("No repair keeps every rule. Redraw everything instead.", nothing changed); valid repair
  changes only the Santa's assignment and sends one email.
- Add a latecomer: the two-pairing insertion from the design, three emails.
- Close with reveal: personal pages show the pairings, no form, and every POST (wish, note,
  decline, attach) returns 400; nothing shared is shown any more; the dashboard card goes.
- Copy with "no repeat": participants, guidelines, budget and the exclusion set copied; the
  new draw repeats no 2026 pair; invitations ("your page") sent; a participant who declined
  is left out and gets no email; the declined row is greyed with "Put back".
- Delete asks for confirmation and removes the exchange.

**Secret Santa — participants and access**

- Personal page headers: `private, no-store`, `noindex, nofollow` (header and meta),
  `Referrer-Policy: strict-origin` (origin only, the token never leaves); bad token 404.
- Logged out and logged in as another user, the page of a linked participant is identical to
  an unlinked one; only the linked account sees its wishlist and "Unlink".
- Wishes within the budget are pre-ticked; nothing is shared before confirming; the Santa then
  sees the shared wish, the exchange wishes and the note.
- Exchange wishes: `javascript:` links, negative and huge prices refused; a 200-character word
  wraps; HTML and `<script>` text are escaped; links open with `noopener noreferrer`.
- Attach: the login URL carries no token; explicit confirmation; the dashboard then shows the
  exchange with "My page" and "Plan a gift".
- "Plan a gift" opens the guided plan with a new person named after the recipient (Bob is
  only a viewer of Dad); another user's participation id returns 404.
- `bob` gets 404 (or 405 for the wrong method) on all 20 organizer URLs of Alice's exchange;
  logged out, the organizer page redirects to login; the organizer page holds no token.

**Capture and guest wishlist**

- Capture page prefills the wish, plan and gift forms; `javascript:` URLs, a price in another
  currency, an over-long URL and an out-of-range price are dropped; HTML title escaped; empty
  capture shows a helpful message. The bookmarklet is on the profile page.
- Guest wishlist link: enable, `private, no-store`, `no-referrer`, `noindex`; no claim state
  or claim button, even for a logged-in user; regenerate kills the old link; disable gives 404.

**Received gifts**

- The list answers 200 to unknown giver accounts and labels, bad years, other users' ids and
  odd occasions. The private-name check found nothing on the 18 pages Bob can open with
  Alice's ids.

**Everywhere**

- No 500 in 976 crawled pages (alice and bob, English and French).
- No horizontal scrolling at 390 px on the Secret Santa list, detail, form, dashboard,
  personal and guest pages; dark theme readable on all of them.
- French Secret Santa pages show no English text.

## Test environment notes

- The app listens on port 8000; the skill scripts default to 8001, so set
  `QA_BASE_URL=http://localhost:8000`. `crawl.py` and `cross_user_access.py` need `requests`,
  which only the `.tox/e2e` Python has.
- The local `main` branch is far behind `origin/main`; `git diff main...HEAD` overstates the scope.
- Docker logs show local time (Europe/Paris) while the database stores UTC: allow for it when
  checking cooldowns.
- The debug toolbar comes back after every navigation; hide it with an init script in each
  Playwright context, not a one-off style tag.
- Screenshots are in the session scratch folder, not committed.

## Data changed

- Database reset with `seed_data --flush` before the pass.
- Alice: exchange "Family Christmas 2026" (closed, pairings revealed; participants Alice, Bob,
  Dad, Mom, Sister, Eve Late; Carol Guest added then removed); exchange wishes "Wool socks", a
  200-character title and `<img src=x onerror=alert(1)>`; a note; Ceramic Teapot shared.
  Mom's link regenerated.
- Bob attached his account to his 2026 participation.
- Alice: exchange "Family Christmas 2027" (copied, invited, drawn; Eve Late declined).
- Alice: exchange "Tiny impossible" created and deleted.
- Alice's wishlist share link enabled, regenerated, then disabled.
- About 25 emails written to the console backend only.
- Fix verification: Mom's 2027 link regenerated with the new email; exchange "Family Christmas
  2028" copied from 2026 and invited (Bob's account carried over); about 7 more emails.
