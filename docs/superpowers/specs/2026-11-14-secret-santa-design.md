# Secret Santa Exchanges: Design

Date: 2026-11-14. Source idea: `docs/ideas/implemented/0034-secret-santa-draws-for-groups.md`.
This design replaces several decisions of that idea; where they differ, this document wins.

## Intent

Let a Gift Manager user organize a Secret Santa for any circle (a large family, colleagues),
including people who have no Gift Manager account. The organizer needs an account; participants
do not. The feature should replace a draw website, and add what those sites lack: participants
can tell their Santa what they would like, and those who use Gift Manager can share part of
their real wishlist.

## Goals

- Draw directly: pick participants, set exclusions, draw, and everyone learns who they drew.
- Work without accounts and without email: every participant has a personal secret link.
- Let each participant share wishes and a note with their Santa, before or after the draw.
- Let the organizer fix problems after the draw without starting over.
- Give the exchange an end.

## Non-goals

- Anonymous messaging between Santa and recipient.
- Claiming or reserving a wish from an exchange.
- Creating gift plans automatically at the draw.
- White Elephant and other swapping games.
- Automatic closing by a scheduled job.
- Matching typed email addresses against existing accounts.

## Anti-goals

- A participant learning who drew them, or any pairing other than their own, before the
  organizer chooses to reveal them.
- The organizer seeing a pairing without having deliberately asked for it.
- A personal link alone giving access to anything of a Gift Manager account. The link proves
  who the participant is in the exchange, never which account they own.
- A linked user's wishlist being shown to a Santa without that user having confirmed it.
- Participants being added to the organizer's address book as a side effect.
- Telling the organizer which participants have a Gift Manager account.

## Constraints

- Django app `gift_manager`, PostgreSQL, Bootstrap, HTMX, no new production dependency.
- Access rules elsewhere stay as they are: `PermissionService`, friendship rules, wishlist
  privacy (`docs/ai/architecture.md`). An exchange never grants access to a person, a plan or
  a wishlist beyond what is described here.
- Email may be unconfigured on an instance; the feature must stay usable through links.
- User-facing strings are translated (English and French).

## Approaches

1. **Reuse the gift objects**: participants as `Person` rows, the exchange as an `Event` on a
   `PersonGroup`, pairings as surprise `Relation` plans. Rejected: a plan needs a gift and
   account-based permissions, and participants must stay out of the address book.
2. **Own data, one delivery**: everything below in one change. Rejected: a very large diff,
   harder to review and to verify, nothing usable until the end.
3. **Own data, three slices (chosen)**: the same design, built and reviewed in three steps,
   each leaving the application working and tested. The slices are a build order, not three
   releases; they can follow each other immediately.

The user picked the workflow, the delivery rules and the secrecy rules in conversation; the
slicing was chosen because implementation and review are done by AI agents, which review small
diffs more reliably than large ones.

## Decisions made with the user

### Participants

- An exchange has its own participant list. A participant is a name and an optional email
  address.
- The organizer can type participants, import a whole group, or pick people from their address
  book. Importing copies the name and email and remembers which person record it came from.
- The organizer chooses whether they take part.
- A participant is linked to an account in two ways only: they were imported from a person
  record linked to an account, or they attach their participation themselves from their
  personal page after logging in. The organizer is not told who is linked.
- Minimum three participants to draw.

### Exclusions

- Exclusion sets: named sets of participants; nobody draws someone from one of their sets.
  A couple is a set of two. A participant can be in several sets.
- Switch "nobody draws the person who drew them".
- Switch "nobody draws the same person as in the previous exchange", available when the
  exchange was started from an earlier one.
- If no valid draw exists, the organizer gets a clear message and nothing is saved.

### Draw and delivery

- The organizer draws directly. There is no mandatory invitation step.
- Optionally, before drawing, the organizer can send the personal links so that participants
  share wishes or say they cannot take part. A participant who declines before the draw is
  left out of it.
- After the draw, every participant with an email address receives an email with their
  personal link.
- "Send again" re-sends that email and shows nothing to the organizer.
- "Show link" shows one participant's link to the organizer, for any participant, behind a
  warning that opening it reveals who that person drew.
- The organizer's page can show all pairings behind a warning. An organizer who takes part
  gets a stronger warning.

### Personal page

One secret link per participant, working before and after the draw. It shows:

- the exchange name, date, budget and guidelines, and the participant names;
- after the draw, who the participant drew, with what that person shared;
- a place to add exchange-only wishes (title, optional link, optional price) and one note for
  their own Santa, at any time;
- "I have a Gift Manager account" to attach the participation to an account.

It never shows who drew the participant, nor any other pairing, unless pairings were revealed
at closing.

### Sharing a real wishlist

- A linked participant sees their own active wishes with a checkbox each and chooses what to
  share for this exchange.
- Wishes with a price hint within the budget are pre-ticked; others start unticked.
- Nothing is shared until the participant confirms once.
- The choice is per exchange. Wishes added later are not shared automatically.
- The Santa sees shared wishes read-only, with no claim or fulfillment state.

### For Santas with an account

- The exchange appears on their dashboard.
- "Plan a gift" opens the guided plan with the recipient pre-filled: the existing person when
  the recipient came from the Santa's own address book, otherwise a new person with the
  recipient's name. A new person is not linked to the recipient's account.

### After the draw

- "Remove and repair": the participant is removed and whoever had drawn them now gives to the
  person they had drawn. Only that Santa gets a new assignment and a new email.
- "Add and repair": a latecomer is inserted by changing two pairings, so that nobody can
  deduce who the latecomer drew. If A gave to B and C gave to D, then A now gives to the
  latecomer, the latecomer gives to D, and C gives to B. A, C and the latecomer get an email.
- A repair is checked against every active rule: nobody draws themselves, exclusions,
  previous-exchange pairs, and no mutual draw when that switch is on. If it breaks one, the
  repair is refused and the organizer can redraw everything. This includes removing someone
  from a mutual pair (A gives to X and X gives to A), which would leave A alone.
- "Redraw everything" is always available; everyone gets a new email. "Remove and redraw
  everything" is one operation: the participant is not removed if the redraw fails.
- Wishes, notes and wishlist selections survive repairs and redraws. The new Santa sees them;
  the previous one no longer does.

### Closing

- The exchange date is required. "Close exchange" is offered from that date.
- Closing is final. Personal pages then show that the exchange is over, are read-only, and
  what was shared for the exchange is no longer visible.
- At closing, the organizer can choose to reveal all pairings to every participant.
- Pairings are kept so that a later exchange can avoid repeats.
- "Start from a previous exchange" copies participants and exclusion sets. A participant keeps
  the account they attached themselves (decided after the QA pass of 2026-11-15), so they need
  not attach it again; like an imported account, it shows the copy only once invited or drawn,
  and their wishlist selection starts empty.

### Budget and language

- The budget is an amount in the organizer's currency, shown as a guideline and used for the
  pre-ticking only. The exchange remembers that currency. A linked participant's wishes are
  pre-ticked only when their own currency is the same.
- Emails use the organizer's language for participants without an account, and the
  participant's own language once linked. Personal pages use the organizer's language unless
  the visitor is logged in as the linked account.

## Design

### Data (new models, in a `gift_manager/secret_santa/` package)

- `Exchange`: organizer (user), name, exchange date (required), budget, currency (copied from
  the organizer's profile at creation), guidelines, status (draft, drawn, closed), the two
  switches, `previous_exchange` (set to null if that exchange is deleted),
  `pairings_revealed`.
- `ExchangeParticipant`: exchange, name, email (encoded like `Person.email_address`), secret
  token, optional source person, optional linked account, `previous_participant` (the same
  person in the exchange this one was copied from), declined flag, `invited_at`,
  `account_attached_by_participant`, `emails_stopped`, `gives_to` (another participant, empty
  before the draw), note for their Santa, `wishlist_confirmed`.
- `ExclusionSet`: exchange, name, participants.
- `ExchangeWish`: participant, title, optional link, optional price.
- Shared real wishes: a many-to-many between `ExchangeParticipant` and `Wish`.

Every model has a UUID used in URLs, like the other models of the app. Optional links to
other rows are set to null when the target is deleted.

Constraints on `ExchangeParticipant`, per exchange: names are unique ignoring case; a source
person appears once; an account is linked to one participant at most. Importing skips people
already present (same person record or same linked account). Several participants may share
an email address. An exchange holds at most 100 participants.

An organizer who takes part is an ordinary participant linked to the organizer's account.

An exchange belongs to its organizer only. It is not shared through the permission system.

### Modules

- `secret_santa/draw.py`: pure functions, no database. Input: participant ids, forbidden pairs,
  the mutual-draw switch. Output: a mapping giver to recipient, or a failure. It first checks
  that a draw can exist (a matching between givers and allowed recipients), then backtracks:
  always the giver with the fewest remaining choices, candidates shuffled, stopping a branch
  as soon as someone has no choice left, with a step budget so that a request never hangs.
  Also the repair functions (remove, insert), which validate every new pair. Fully
  unit-tested, including impossible cases, sizes up to 100, and a property test that every
  result respects every rule.
- `secret_santa/service.py`: creates and edits exchanges, turns exclusion sets and switches
  into forbidden pairs, saves a draw in one transaction, repairs, closes, copies.
- `secret_santa/access.py`: what a participant token may read. The single place that decides
  which wishes of a recipient a Santa sees.
- `secret_santa/emails.py`: assignment, invitation and re-send emails, built like the digest
  email (`gift_manager/templates/gift_manager/email/`). Emails are sent after the database
  transaction has committed, over one connection; a failure for one recipient does not stop
  the others and is reported to the organizer, who can use "Send again" or "Show link".
- Views: organizer views behind login, scoped to `organizer=request.user` (404 otherwise);
  participant views by token, without login, standalone pages with the same protections as
  `views.wishlist.wishlist_guest` (no-referrer, no-store, noindex).

### Secrecy rules in code

- Organizer pages never load `gives_to` unless the organizer confirmed the warning. Revealing
  pairings or a link is a POST whose response is not cached and leaves nothing in the URL.
- A personal link alone never shows or changes anything of an account: real wishes, the
  linked state and the account's language appear only when the visitor is logged in as the
  linked account. Without login, a linked and an unlinked participant's pages look the same.
- Attaching an account: the participant is remembered in the session, the login URL never
  carries the token, and the attachment needs an explicit confirmation once logged in
  ("Link your account to participant X?"). It is refused when the account is already linked
  to another participant of the exchange, and it can be undone.
- A participant page reads only its own `gives_to`. The reverse relation (who drew me) is
  never read on a participant page before pairings are revealed.
- Recipient wishes shown to a Santa come only from `access.py`: exchange wishes, plus the
  shared real wishes when the exchange is drawn and `wishlist_confirmed`. Real wishes are read
  as `wishlist.guest_wishes(linked account)` restricted to the selection, so a wish that was
  archived, deleted or received since then disappears, and claim or fulfillment columns are
  never loaded.
- The dashboard shows an exchange to a participant who did not decline, once it is drawn, or
  earlier if they were invited or attached their account themselves. A person silently
  imported into a draft sees nothing.
- "Plan a gift" preselects only what the Santa can already see: the participant's source
  person when the Santa can edit it; otherwise a person the Santa owns that is linked to the
  recipient's account; otherwise a new person with the recipient's name. The guided plan's
  query-string prefill is extended to the recipient (checked through `accessible_by`) and the
  new person's names.
- Tokens are created with `secrets.token_urlsafe(32)`. Changing a participant's email does
  not change their token. The organizer can regenerate a participant's token.

### Emails and abuse

Emails go to addresses typed by the organizer, so:

- an email holds the exchange name, the organizer's name, the participant's name (in the
  subject and the first line) and the personal link; the free-text guidelines are shown on the
  personal page only;
- every email has a signed "stop emails for this exchange" link (also as `List-Unsubscribe`),
  which sets `emails_stopped`; the flag is kept when the exchange is copied;
- an organizer can send at most 300 exchange emails per rolling 24 hours;
- "Send again" has a 5-minute cooldown per participant, reset when their email is edited.

### Slices

1. **The draw**: models, organizer pages (create, delete, participants and import, exclusion
   sets, the mutual-draw switch), draw, "Redraw everything", assignment email with its stop
   link and limits, "Send again", "Show link", regenerating a link, editing a participant's
   name and email after the draw, pairings behind a warning, personal page showing the
   exchange and who the participant drew. Navigation entry.
2. **Telling your Santa**: exchange wishes and note, optional invitation before the draw and
   declining, attaching an account, choosing shared wishes, dashboard card, "Plan a gift".
3. **After the draw**: remove and repair, add and repair, close with optional reveal, start
   from a previous exchange and its "no repeat" switch.

Each slice ends with unit tests, a browser test of its main flow, French translations, lint,
and a review. The data model of slice 1 already holds the fields later slices need only when
that costs nothing; otherwise each slice adds its own migration.

## Calls made by the designer (not decided by the user)

- Package name `gift_manager/secret_santa/` and the model names above.
- Participant emails are stored with the application's existing email encoding.
- A declined participant stays in the list, greyed out. The organizer can put them back with
  one click before the draw; after it, through "Add and repair" or a redraw.
- After the draw, a participant's name and email can still be edited. Adding or removing
  participants and changing exclusions is only possible through the repair and redraw actions.
- The limits: 100 participants per exchange, 300 emails per organizer per 24 hours, 5 minutes
  between two "Send again" for the same participant.
- Deleting an exchange deletes its participants, wishes and pairings. Deleting a user deletes
  the exchanges they organize; a linked participant whose account is deleted becomes an
  unlinked participant.
- Declining from the personal page is only offered before the draw. After the draw, a
  participant who cannot take part tells the organizer, who removes them.
- A removal that would leave fewer than three participants is refused; the organizer deletes
  or redraws instead.
- "Add and repair" picks the two pairings at random among the choices that keep every rule
  valid (the two pairings are distinct, C is not B, and the three new pairs respect the
  exclusions, the previous-exchange pairs and the mutual-draw switch). The latecomer's
  exclusion sets are chosen in the same form. If no choice is valid, the organizer is
  offered a full redraw.
- A regenerated token makes the old link return 404.
- The exchange entry sits under the "More" menu and on the dashboard when the user organizes
  or takes part in an open exchange.

## Peer review

Reviewed on 2026-11-14 by an independent agent (`agy`, `gemini-4-argon-high`), two rounds,
ending in agreement with nothing blocking for slice 1. The two-pairing insertion of a
latecomer came from this review and was chosen by the user. The review changed: the rule that a
personal link never acts for an account, the dashboard rule, the account attachment flow,
the validation of repairs, the draw's pre-check and step budget, the uniqueness constraints,
`previous_participant`, the email rules and limits, and the content of slice 1.

## Left to the builder

- Page layouts, within the existing Bootstrap and card styles.
- Exact wording of emails and warnings.
- Whether organizer pages use HTMX partials or plain pages, following the nearest existing
  pattern.
- How the email limits are counted and stored.
