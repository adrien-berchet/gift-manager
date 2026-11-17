# New User Guidance: Design

Date: 2026-11-17.

## Intent

Gift Manager is about to have its first public release. No outside user has tried it yet, and
the app now covers much more than its core loop (wishlists, sharing, Secret Santa, received
gifts, bookmarklet, calendar feed). The worry is that a new user finds it too complex to start.
This work explains the main concepts and features to new users, without getting in the way of
people who already know the app.

The first public users are expected to **arrive on their own** (sign up cold, empty account),
not through an invitation from an existing user.

## Goals

- Within their first session, a new user creates one real gift plan and understands what it is:
  a link between a recipient (person or group), a gift, usually an occasion (event or
  birthday), and a status that moves until the gift is given.
- Later, the user discovers the secondary features (wishlist, sharing with friends, Secret Santa,
  received gifts, bookmarklet, reminders and calendar feed) without having to hunt for them.
- Anything shown on first use can be dismissed, stays dismissed, and **remains reachable
  afterwards from a Help entry**.

## Non-goals

- An interactive product tour (popovers pointing at buttons).
- An explanation box at the top of each page.
- Videos, screenshots, search inside Help.
- Onboarding tailored to invited users (friend invitation, guest wishlist link, Secret Santa
  participant). Revisit once real users arrive that way.
- Usage analytics on the guidance.

## Anti-goals

- Getting in the way of returning users: no modal, no forced step, nothing that reappears after
  being hidden.
- Walls of text. Help pages are short, scannable, and task-oriented.
- English-only content: everything is translated into French like the rest of the UI.
- Requiring custom JavaScript for the core of it.

## Constraints

- No new production dependency.
- Progressive enhancement: the checklist hide/restore and Help pages work as plain links and
  form posts; HTMX may enhance them.
- Translations through the normal `makemessages` / `compilemessages` flow (`fr`).
- Matches the existing Bootstrap style, light and dark themes, and the mobile layout.
- `AGENTS.md` currently says "Do not put feature explanations or keyboard shortcut documentation
  into the UI unless the user asks." This work is that request. The rule is updated to: "Full
  feature explanations live in the Help section and the getting-started checklist; a page may
  keep one short intro line linking to its Help topic."
- Existing short explanations stay where they are (decided with the user): the intro lines on
  the wishlist and received-gifts pages, the feature blurbs on the Profile page (including the
  bookmarklet instructions), and the how-to line on the Share page. Each gets a "Learn more"
  link to its Help topic.

## Approaches

Three were considered:

- **A. Help section + "Getting started" checklist (chosen).** Server-rendered Help pages, plus a
  dismissible dashboard card whose steps tick themselves from real data and link to the action
  and to the matching Help page. No dependency, works without JS, easy to translate and test.
  Cost: written content to keep current.
- **B. Interactive guided tour** (e.g. driver.js), replayable from Help. Eye-catching, but a new
  JS dependency, fragile across layout changes and mobile/desktop, often skipped, and it shows
  where buttons are rather than explaining concepts.
- **C. Per-page dismissible explanations** ("What is this?") on each list page and empty state.
  Explanations sit where needed, but they clutter pages, multiply dismissal state, and give no
  single place for the big picture.

The user picked **A**. The one idea kept from C is that empty states link to the relevant Help
page.

## Design

### 1. Help section

- New pages under `/help/`: an index and one page per topic (`/help/<topic>/`).
- Topics:
  - **How Gift Manager works**, the core page: gift plans and how recipients (people and
    groups), gifts, occasions (events and birthdays), and statuses fit together, followed by a
    typical workflow from first plan to "given".
  - One short page per feature: **Wishlist and guest links**, **Friends and sharing**
    (including invitations), **Secret Santa**, **Received gifts**, **Quick capture (bookmarklet)**,
    **Reminders and calendar feed**. Gift suggestions get a section in the core page or a page
    of their own, at the builder's discretion.
- Each feature page says what the feature is for, when to use it, and how to start, with a link
  to the page where you do it.
- Content is written in Django templates with `{% trans %}` / `{% blocktrans %}` so it goes
  through the existing translation workflow. *(My call: matches how every other string is
  translated; no Markdown dependency.)*
- No screenshots. Use the same Font Awesome icons as the navigation so users can match a concept
  to the menu entry.
- Help pages are **public**: they contain no user data and are useful before signing up. The
  logged-out welcome page links to the core Help page. *(My call.)* The links on them that lead
  into the app go through the normal login redirect.

### 2. Help entry points

- A **Help** link in the navbar utilities (next to Profile). It falls into the collapsed menu on
  mobile like the other utilities.
- Each checklist step has a "What's this?" link to its Help page.
- The empty states of the main list pages (gift plans, recipients, Secret Santa) get a "Learn
  more" link to the matching Help page. The wishlist and received-gifts pages carry it on their
  intro line instead, so the link doesn't appear twice. *(My calls, from the reviews:)*
  - **Gifts:** Grid.js draws the list and only shows a generic "No matching records found".
    Add a server-rendered empty state for when the user can access no gifts, and put the link
    there.
  - **Events:** gets no link. Its list is never empty, because the shared Birthday event
    (migration `0032`) is always there.
- The logged-out welcome page links to the core Help page.

### 3. Getting-started checklist

A card at the top of the authenticated dashboard's content: just below the "Next actions"
heading and its buttons, and above "Needs attention". It sits inside the live-refreshed block,
so ticks update after creating something in the side panel. *(My call.)*

```
Getting started                                   2/4   [Hide]
✓ Add a recipient                                  What's this?
✓ Add a gift idea                                  What's this?
○ Create your first gift plan   [Create] [Guided]  What's this?
○ Move a plan to Purchased or Given                What's this?
  Explore more
○ Add something to your wishlist                   What's this?
○ Connect with a friend                            What's this?
```

- **Core steps**, ticked from data the user **owns** (`PermissionLevel.OWNER`), not merely
  data shared with them. Otherwise a friend's shares or a co-owner's change could tick a step
  the user never did. *(My call: the checklist teaches by doing.)*
  1. Add a recipient: at least one owned person or group.
  2. Add a gift idea: at least one owned gift.
  3. Create a gift plan: at least one owned gift plan.
  4. Move a plan forward: at least one owned gift plan with a Purchased or Given status
     (use the slug helpers in `gift_manager/statuses.py`).
- **Explore more (optional) steps:**
  5. Add something to your wishlist: at least one `Wish` by the user.
  6. Connect with a friend: at least one friend, or one invitation sent.
- Each step is one small `exists()` query, filtered on ownership where it applies, plus one
  query to load the short status list. The accessible counts the dashboard
  already computes in `views/common.py` (`home`) can't be reused, since they include shared
  data.
- An unfinished step shows its action link: the create page, plus the guided flow for the
  gift-plan step. A finished step shows a tick and no action.
- **When the card shows:** whenever `getting_started_hidden_at` is null. Only an explicit hide
  removes it. Nothing hides the card automatically, so it can never reappear on its own when data
  changes, for example after deleting the only wish. Once every step is done, the card shows a
  short "You're all set" state with the Hide button. *(My call: a single saved value, and "Show
  again" always has a visible effect.)*
- **Hide:** a POST to a small view that sets a new `Profile.getting_started_hidden_at`
  (nullable `DateTimeField`) and redirects back to the dashboard. HTMX may swap the card out in
  place.
- **Show again:** for logged-in users with the card hidden, the Help index shows a "Show the
  getting-started checklist on my dashboard" button. It POSTs, clears the field, and redirects
  to the dashboard.
- **Existing accounts:** the migration leaves the field null, so current accounts see the card
  too, mostly ticked, and can hide it. *(My call: there are no public users yet.)*
- Step computation lives in a small module (e.g. `gift_manager/getting_started.py`) that
  returns a list of step objects (key, label, done, action URL, help URL, optional flag). The
  view and the template stay thin.

### 4. Testing

- Unit tests for step computation: an empty account, each step done in turn, the
  Purchased/Given detection, the optional steps, and that **shared** objects do not tick a step.
- The card stays visible with all steps done, and stays hidden after a hide even when data
  changes.
- View tests: the dashboard shows or hides the card. Hide and show-again work through plain
  POST (and HTMX if added). Help pages render logged in and logged out, and an unknown topic
  returns 404.
- One Playwright e2e test: a new user sees the card, follows a Help link, hides the card, and
  restores it from Help. Check mobile width.
- French translations are filled in for all new strings.

## Left to the builder

- Exact wording of the Help pages and checklist labels. Keep them short and use the product
  vocabulary: gift plan, recipient, gift, event, status.
- Whether Help topics are a static list in code or a small registry; template layout of the Help
  index (cards or list).
- Exact placement and styling of the Help link and the "Learn more" links within the existing
  style.
- Whether gift suggestions get their own Help page.
- Whether to enhance hide and show-again with HTMX.
