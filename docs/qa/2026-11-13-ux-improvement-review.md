# UX improvement review — 2026-11-13

Branch `received_log` at `0d0c1f7`, local Docker app (`localhost:8001`). Accounts: `testuser`
(superuser, Chrome, desktop, dark and light themes) and `alice` (Playwright, 390 px phone and
contrast sweep; link crawl as `alice` and `bob`, English and French).

## Summary

The app is stable: no 500 in a crawl of about 1,100 page loads, no sideways scrolling at 390 px
on 25 pages, and the main flows read well on a phone. Nothing blocks a release. The most useful
improvements are a handful of unreadable texts (one of them invisible in the light theme), grid
buttons that lead viewers to a bare 403, untranslated filter labels in French, and a general
lack of consistency between screens of the same kind (forms, detail pages, button colours).

This pass was exploratory and read-only: it looks for improvements across the whole app rather
than re-testing the journeys in `scenarios.md`. No form was submitted.

## Scope and method

- **Chrome, as `testuser`:** dashboard, gift plans (workspace, advanced list, guided, side-panel
  form, detail), recipients, person and group pages, group explorer, gifts (grid, detail modal,
  detail page, edit form), events, tags, statuses, received gifts, wishlist, share, profile,
  global search; dark theme, then light theme on the dashboard and a person page; French on the
  gifts, share and profile pages.
- **Scripts:** `crawl.py alice bob --langs en fr`; a Playwright sweep as `alice` over 25 pages
  that takes full-page 390 px screenshots, measures horizontal overflow, and computes the
  contrast of every visible text in both themes.
- **Not covered:** saving forms, the reveal and received-gift journeys (covered on 2026-11-12),
  AI suggestions, emails, the calendar feed, `cross_user_access.py`.

Finding IDs: `A` for defects, `S` for improvement suggestions (new prefix for this report),
`Q` for product questions.

## Findings

### Defects

| ID | Severity | Finding |
|----|----------|---------|
| A1 | Medium | Permission label in "Shared with" is invisible in the light theme |
| A2 | Medium | Three texts are unreadable in the dark theme |
| A3 | Medium | Lists do not follow the delete rules of detail pages (corrected, see below) |
| A4 | Medium | Filter panel is partly untranslated in French and shows an internal "checkbox" sort |
| A5 | Low | Global search drops the first keystrokes |
| A6 | Low | Two grids show a permanent horizontal scrollbar |
| A7 | Low | Light theme: several badges and buttons are below 4.5:1 |
| A8 | Low | "Needs attention" chip on the Gift Plans page is orange at 0 |
| A9 | Low | Dashboard and Recipients page disagree on the recipient count |
| A10 | Low | Small copy and markup slips |

**A1 — Permission label invisible in the light theme (Medium).**
On person, group, gift, gift plan and tag detail pages, the "Shared with" list shows the user
name but not the level (Viewer / Editor / Owner): the label is white on white (contrast 1:1).
It is readable in the dark theme. Cause: the badge uses `bg-outline-secondary`, which is not a
Bootstrap class and has no rule of its own — `includes/person_detail_partial.html:147`,
`person_group_detail_partial.html:217`, `gift_detail_partial.html:176`,
`relation_detail_partial.html:279`, `gift_tag_detail_partial.html:187`.

**A2 — Unreadable texts in the dark theme (Medium).**
Same family as R3 and N1 of the previous report: Bootstrap colours that follow `data-bs-theme`
while the app switches with `data-theme`.
- Gift plan page, "Group gift & contributions": the tip "set an estimated price…" is
  `text-warning-emphasis`, dark brown on dark grey, **1.44:1**.
- Share page: the section titles "Persons", "Groups / Families", "Gifts", "Events", "Gift
  Plans" are Bootstrap blue on slate, **2.3:1**.
- ~~The "Select" button in the filter panel of every grid, 2.36:1.~~ False positive: the
  sweep measured it while its panel was closed; it is readable once the panel is open.
- Also below 4.5:1: tag badges in the gifts grid (3.49), the "Purchased" badge
  `bg-info text-dark` on a person page (3.77), the year heading of received gifts (4.0).

The templates still contain 20 `text-*-emphasis`, 16 `text-dark`, 9 `bg-light` and a few
`bg-body-*` uses; a single audit of these would close the whole family (see S1).

**A3 — Lists do not follow the delete rules of detail pages (Medium).**
*Corrected on 2026-11-13 while fixing it: the first version of this finding said grid rows
showed Edit and Delete to viewers. They do not: the visible rows lock Edit and hide Delete.
The 403 links found by the crawl come from the places below.*
- The tree view of Manage Groups (hidden until "Tree View" is chosen) renders Edit, Delete,
  Share, Move and drag handles for every group, whatever the user's rights.
- In grid rows a viewer has no way to remove their own access, and the only owner of a shared
  object sees a Delete that the server refuses.
- The status page grid shows Edit on every plan, and its "Give" button opens the gift page.
- The plan lists of gift and event pages show Delete to editors of a shared plan, where it
  only removes their own access.

**A4 — Filter panel in French (Medium).**
On `/fr/gifts/` (and the other grids): "Filters", "Clear", "Multi", "All Nom du cadeau",
"All Lien", "Filter Commentaire…", "Filter Tags…" are English or half English. "View" is
translated "Lecture" (should be "Affichage"). In both languages the first sort chip is the
internal column id "checkbox", and the filter labels are built as "All " + column name
("All Gift name", "All Link").

**A5 — Global search drops the first keystrokes (Low).**
Clicking the search box and typing "pen" at once left the field empty; typing again worked.
The input is focused on `shown.bs.modal`, i.e. after the fade animation
(`static/gift_manager/js/global-search.js:147`), so keys typed during the animation are lost.
This matters most for Ctrl+K users.

**A6 — Permanent horizontal scrollbar on two grids (Low).**
The Statuses grid and the "Shared with" grid of a group page show a scrollbar under a table
that fits: the table is 1 px wider than its wrapper (1371 vs 1370 px). The scrollbar is also
the browser's white one, which stands out in the dark theme — as do the scrollbars of the
search results, "Public interests" and the Tags list in the gift form.

**A7 — Light theme contrast (Low).**
"Needs attention" chip 2.86; "Given" and "Group" badges 3.32; active nav link and count pills
3.63; red buttons (`btn-danger`) 3.76; "No date" / "Missing due date" badges 3.95; purple
`btn-secondary` (Cancel, Duplicate, Update) 4.23; indigo links on the page background 4.27.
Darkening three tokens (indigo, emerald, red) by one step would fix most of them.

**A8 — "Needs attention" chip orange at 0 (Low).**
The dashboard tile was fixed after the last pass; the chip in the workspace header of the Gift
Plans page still has the attention style at 0 (`relation_list.html:54`).

**A9 — Recipient counts (Low).**
For `testuser` the dashboard says "3 Recipients" and the Recipients page "All 2" (the user's own
person is counted in one place only). The dashboard tile "Recipients" also includes groups
(alice: 9 = 5 people + 4 groups) next to a separate "Groups" tile, so groups are counted twice.

**A10 — Small slips (Low).**
- Advanced list: the heading "Advanced Gift Plans List" appears twice, one above the other.
- Page title in French: "Gift Manager - Partager des éléments - Gift Manager".
- Nav says "Statuses", the page says "Status".
- Dashboard empty state says "Create a gift plan to start tracking what you will give next"
  to a user who already has plans.
- Dates are written two ways: "Nov. 12, 2026 16:28" (person page) and "Nov. 12, 2026,
  4:28 p.m." (group page).
- A plan that is Given and revealed still shows "Due date: No date", a "Surprise" badge and
  the "I'll take this" coordination button.
- For the superuser, Tag Explorer shows "Books — 1 gift" while none of the listed gifts has
  that tag (the gift belongs to another user). Not checked with an ordinary account.

### Improvement suggestions

| ID | Value | Suggestion |
|----|-------|------------|
| S1 | High | One theme mechanism, and a contrast check in the test suite |
| S2 | High | A friendly 403/404 page |
| S3 | High | Create a gift from inside the gift plan form |
| S4 | Medium | One form style |
| S5 | Medium | One detail-page layout |
| S6 | Medium | A button colour convention |
| S7 | Medium | Navigation: wishlist, statuses, groups |
| S8 | Medium | Profile page split into sections that save on their own |
| S9 | Medium | Share page |
| S10 | Low | Phone layout details |
| S11 | Low | Wording |

**S1 — One theme mechanism.** Setting `data-bs-theme` together with `data-theme` on `<html>`
would make every Bootstrap utility follow the app theme and remove the cause of R3, N1 and A2
at once. The sweep used here (`scratchpad/sweep.py`, about 100 lines) could become an e2e test
that fails under 4.5:1.

**S2 — Error pages.** 403 and 404 are bare browser pages. A page with the navbar, one sentence
("You can view this item but not change it") and a link back would turn A3-type dead ends into
a minor event.

**S3 — Gift inside the plan form.** "Create gift plan" requires choosing an existing gift from
a dropdown, so a new idea takes two forms (gift, then plan) unless the user finds "Guided". A
"New gift…" entry in the dropdown, or a free-text name that creates the gift, would make the
main action one step. The plan form also has its own link and price next to the gift's; say
which one wins, or prefill them from the gift.

**S4 — Forms.** In the gift form, Name and Link are short fields beside their label while
Comment and Price are full-width below theirs; "Due date" in the plan form does the same.
Empty choices read "---------". Suggested: every label above a full-width field, a worded empty
choice ("No event"), and the tag picker used on person pages (chips) instead of a list box
with "Select all / Clear all".

**S5 — Detail pages.** Person, gift and plan pages use a card that stops at about 935 px while
the header and the "back" button span 1150 px, leaving a blank strip on the right; on the
person page the left column ends after "Budget" and stays empty for two screens. The group
page uses an older layout ("Name: Household", a grid for "Shared with"). The name is repeated
(heading "Gift details", card title, "Name" field, and "Gift details" again on a plan).
Suggested: the object's name as the page heading, one full-width card, and the group page
moved to the same partial style.

**S6 — Buttons.** The same action changes colour between screens: Edit is orange on pages,
outlined in the modal and indigo in grids; Cancel is filled purple and competes with Save;
"Explorer View" is filled on one page and outlined on another; "Given" is green on cards and
blue on person and gift pages. Suggested: one filled primary per screen, outlined secondary
actions, red reserved for destructive ones, and one colour per plan status everywhere.

**S7 — Navigation.**
- "Received Gifts" is in the More menu but "My Wishlist" is only reachable through Profile.
  Put both in the same place.
- "Statuses" looks like a read-only list of five fixed values; its purpose (finding every
  plan with a given status) is not visible from the grid. See the decision on Q4.
- Groups have three entry points (Recipients tab, Manage Groups, Group Explorer) with
  different actions each. Merging Manage Groups into the Recipients "Groups" tab would remove
  one.
- The workspace has a recipient filter per section; one filter for the page would be enough.
  "Needs attention" and "Needs details" show the same number for every account tested.

**S8 — Profile.** One long page with three identical "Save Preferences" buttons, each saving
only its own block, and Language and Currency filed under "Reminders". Suggested: tabs or
anchors (Account, Preferences, Display, Notifications, Friends), distinct button labels, and
Friends higher up since sharing and reveal depend on it. The placeholder and the help text of
"Sizes" and "Things to avoid" say the same thing twice.

**S9 — Share page.** It looks like a different app (bright indigo headers, narrower column,
Bootstrap-blue links) and speaks of "objects" and "Persons". It also lists the user's own
person. Suggested: restyle with the standard cards, say "items" and "People", and offer
sharing mainly from each object's own page, where the context is clear.

**S10 — Phone.**
- Gift cards list Link, Price and Tags even when empty ("—"), which makes each card about
  300 px tall; hide empty fields.
- Dashboard: the four counters are stacked one per row; a 2 × 2 grid would bring "Needs
  attention" content above the fold. The four "New …" Library buttons could be one row.
- Person page: five action buttons sit above the person's name; keep Edit and move the rest
  into a "…" menu.
- Many icon-only buttons are under 28 px (17 on the workspace, 15 on recipients).

**S11 — Wording.**
- "Give" on a gift row creates a plan; "Plan" would match the rest of the app.
- "Generate ideas: +1 +2 +3" does not say what the numbers are ("1 idea", "3 ideas").
- "Select" in the filter panel starts bulk selection; "Select several" is clearer.
- "Budget — Planned 0.00 € / Spent 0.00 € / 2 plans without price" reads as a real zero; show
  "—" when no plan has a price.
- A filter by gift name that lists every gift name duplicates the search box.

## Decisions needed

- **Q1 (A3):** hide Edit/Delete in grid rows for viewers, or replace Delete by "Remove my
  access" as on detail pages?
- **Q2 (S3):** should the gift catalogue stay a separate step, or may a plan create its gift?
- **Q3 (A9):** does "Recipients" on the dashboard mean people only, or people and groups? Is
  the user's own person a recipient?
- **Q4 (S7):** keep "Statuses" in the menu? Will statuses become editable?
- **Q5 (A10):** on a Given plan, replace "Due date" by a "Given on" date?

## Decisions (2026-11-13)

| Question | Decision |
|----------|----------|
| Q1 (A3) | Grid rows show "Remove my access" to users who cannot delete, as detail pages do. Edit is not offered to viewers. |
| Q2 (S3) | A gift plan may create its gift: the plan form accepts a new gift as well as an existing one. |
| Q3 (A9) | "Recipients" on the dashboard counts people and groups, the user's own person included. The user's own person appears in the Recipients list like any other person, with the "THIS IS YOU" badge. |
| Q4 (S7) | The Statuses page stays in the More menu: it is the way to find every plan with a given status. Its grid gets a plan count per status, and status badges on cards and detail pages link to it. |
| Q5 (A10) | A Given plan shows a "Given on" date instead of "Due date: No date". |

## Fixes (2026-11-13)

Implemented on `received_log` after the decisions, tests first, one commit per topic. The plan
and the result were reviewed with a second agent (Antigravity, `gemini-4-argon-high`) until
both agreed.

| Commit | Covers |
|--------|--------|
| `b1ca3ff` Make Bootstrap colour utilities and badges readable in both themes | A1, A2, A7, A8, native scrollbars of A6 |
| `edd664b` List the user's own person among the recipients | Q3, A9 |
| `58b401f` Count gift plans per status and link status badges to them | Q4, "Statuses" heading |
| `9c65c95` Show when a given gift plan was given | Q5, claim button and Surprise badge of A10 |
| `047bdfb` Translate the filter panel and tidy small slips | A4, A5, A6, rest of A10 |
| `f12153f` Offer "Remove my access" in grid rows | Q1, A3 |
| `304a65e` Let a new gift plan create the gift it names | Q2 |
| `3823d0c` Polish the fixes after the peer review and the browser suite | wish price badge in the dark theme, new gift field style |

Choices made while fixing:

- **Theme (S1):** the Bootstrap variables are defined under `data-theme="dark"` instead of
  setting `data-bs-theme`, which would restyle every Bootstrap component.
- **Blocked Delete (Q1):** when a row can be neither deleted nor left and the user can edit
  it, the menu shows a disabled Delete with the server's reason (for example "At least one
  owner is required."), as detail pages do. In the seed data this is the case of most of
  alice's objects: she is their only owner, they are shared with bob, and bob is not her
  friend, so she has nobody to hand them to.
- **New gift (Q2):** one optional field "Or a new gift" under the gift list, rather than a
  mode switch; it works without JavaScript. Choosing a gift and naming one is refused.
- **Given on (Q5):** the day the plan became Given, or its due date when that day was never
  recorded. No new field.
- **Search (A5):** the characters typed while the search opens are kept, because the input
  cannot take focus before the backdrop has faded in.
- **Light theme (A7):** only badge texts were darkened. The active menu link (3.63:1), the
  red and purple buttons (3.76 and 4.23) and indigo links (4.27) keep the brand colours.

Checked after the fixes: 3112 unit and view tests and the complete browser suite (500 tests)
pass, and the fixed screens were looked at on the Docker app in both themes.

Not done: the suggestions S2 and S4 to S11, the white scrollbar is fixed only through
`color-scheme` (native controls follow the dark theme), and the two grids of the group page
still show "Give" on gifts with a link to the gift page.

## Verified as working

- Crawl: alice 221 pages (en) and 441 (fr), bob 151 and 301; no 500; the only errors are the
  403 links of A3.
- No horizontal overflow at 390 px on 25 pages (lists, forms, detail pages, profile, share).
- Phone layout: bottom tab bar, card views, stacked forms and detail pages are usable.
- Global search finds gifts and gift plans and shows quick links when empty.
- Dashboard for alice: "Needs details", upcoming birthdays with "Create a gift plan", library
  counters.
- Birthday event is locked in the events grid.
- French: share and profile pages are fully translated.

## Test environment notes

- The Chrome window could not be resized to 390 px (the window manager ignored it), so phone
  checks were done with Playwright.
- The contrast sweep skips text over gradients, images or translucent backgrounds, and reports
  the "skip to main content" link although it is hidden until focused.
- Screenshots and the raw sweep output are in the session scratch directory
  (`shots/`, `sweep_alice.json`); they are not committed.
- `testuser` was already signed in in Chrome and was left signed in. The theme was switched
  with the `data-theme` attribute only; the stored preference was not changed.

## Data changed

None. `collectstatic` was run in the web container (no file changed). One empty gift plan form
was submitted and stopped by browser validation.
