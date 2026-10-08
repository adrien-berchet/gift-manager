# Guided Gift Plan Creation — Design

Implements idea `docs/ideas/implemented/0016-guided-gift-plan-creation.md`.

Revision 2 (2026-10-07): inline creation now covers the full data of a new recipient, gift
and event, and step 3 covers the plan's status, link/price overrides and surprise flag.
Revision 1 only created a gift by name and an event by name and date.

## Goal

Let a user create a gift plan in three short steps (recipient, gift, occasion) without learning
the full form, and create any missing recipient, gift or event along the way with all of its
data. The full form stays available and unchanged.

## Decisions

- Server-driven steps (HTMX partials, full pages without JavaScript), three steps.
- Default status of a guided plan: the status whose `status_en` is `"Idea"`; it can be changed in
  step 3.
- A separate "Guided" entry point; existing "new plan" buttons keep opening the full form.
  Prefilled flows (birthday, duplicate, per-person/group/gift) stay on the full form.
- Recipients that can be created inline: a **person** with all its fields. Groups stay selectable
  from the existing list; creating a group inline is out of scope.
- Each new object shows its identifying field first and every other field inside a native
  `<details>` "More details" disclosure.
- Out of scope: changing the gift-plan model, replacing the existing create form, carrying the
  guided selections over to the full form, the sharing section, creating a group inline.

## Design

### Route and view

- Route `relations/guided/`, name `relation_guided_create`.
- `RelationGuidedCreateView` subclasses `RelationCreateView`. It renders a partial for HTMX
  requests and a full page otherwise (same pattern as other create views).

### Steps

1. **Recipient** — an existing person or group (`build_recipient_choices`), or a new person.
2. **Gift** — an existing gift, or a new gift.
3. **Occasion** — an existing event (optional) or a new event; due date (defaulting from the
   event's next occurrence); notes; plus the plan's own details.

Each step shows a progress indicator and a Back button. Earlier answers travel as hidden
fields (all submitted values of a field, so multi-valued fields such as groups, interests and
tags are carried completely); there is no session state. Each Next/Back POST validates only the
current step with its step form, so errors appear on the relevant step.

### New objects reuse the real forms

Each "create new" block embeds the real model form as a prefixed sub-form of the step form:

| Step | Sub-form (prefix) | Identifying field | In "More details" |
| --- | --- | --- | --- |
| 1 | `PersonForm` (`new_person`) | first name | family name, email, birthday, notes, groups, interests |
| 2 | `GiftForm` (`new_gift`) | name | comment, link, price, tags |
| 3 | `EventForm` (`new_event`) | name | date, comment, schedule type, recurrence |

- Fields added to those forms later appear in the guided flow without extra work, and their
  `clean()` rules apply (birthday combinations, email, event schedule/recurrence rules).
- Rule per step: an explicit **mode** decides the path (see "Choosing a path"). Only the chosen
  path is validated; the other path's inputs are still posted (so typed values survive switching)
  but ignored. In "new" mode the sub-form is fully validated and its errors are shown on that step.
- A new event defaults to the one-time schedule; its date is visible next to the name because it
  is needed in the common case. The "More details" disclosure opens automatically when it holds
  values or errors.
- Person sub-form scopes (groups the user may edit, accessible interest tags) come from
  `PersonForm.set_user`; the gift's tags are limited to the tags the user can access, as in the
  gift create view.

### Step 3 layout and wording

Step 3 (progress label "Event and gift plan") is two titled sections, in the words of the complete
workflow: **Event** (the existing-event chooser, the new event with its date, and "More event
details") and **Gift Plan** (due date, "Gift plan comment" and "More gift plan details"). Fields
that exist on both objects are labelled by owner: "Event name", "Event date", "Event comment" vs
"Due date", "Gift plan comment".

### Choosing a path (existing or new)

Each step shows a segmented radio choice, then only the chosen path's panel:

- Step 1 `recipient_mode`: "Existing recipient" | "New person".
- Step 2 `gift_mode`: "Existing gift" | "New gift".
- Step 3 `event_mode`: "Existing event" | "New event" | "No event".

The radios are plain `<input type="radio">` posted with the form (carried like any other input);
CSS (`:has(...:checked)`) hides the inactive panel, and where `:has` is unsupported both panels
stay visible. The mode decides the path, so there is no "not both" error. "Existing" with nothing
chosen is an error for recipient and gift, and means "no event" for the event step. When a post
carries no valid mode (non-browser clients), the mode is inferred from what is filled (the chooser
first, then the identifying field).

Default mode: "existing" when the user has something to choose from, otherwise "new" (event:
"none"). When a user has no existing recipient or gift, the choice is skipped and only the
"new" panel is shown. The recipient used for the surprise default ignores a stale chooser value
when the mode is "new".

### Plan details (step 3)

Due date (blank → the chosen event's next occurrence, or the new event's date), status (default
`Idea`) and the comment are visible. "More gift plan details" holds the link and price overrides and
the surprise **checkbox**, rendered with the same partial as the full form. Its default comes from
`default_surprise_for`, as in the full form. Because an unchecked checkbox posts nothing, a hidden
`surprise_for` marker (the recipient the value was chosen for) travels with it: with the same
recipient an absent checkbox means "unchecked" when the step is shown again; with another recipient
the carried value is dropped and the default applies.

### "Use an empty full form"

Every step carries a link to `relation_create`, labelled "Use an empty full form" (the guided
selections are not carried over). Native `confirm` dialogs are not allowed by the frontend
contracts, so the existing unsaved-changes prompt is reused: `unsaved-changes.js` honours
`data-unsaved-always-dirty` (answers carried as hidden inputs), `data-unsaved-no-save` (no
"Save" action) and `data-unsaved-body` (message). `clearForm` removes the always-dirty flag so a
form left in a closed panel no longer guards navigation. The same prompt protects closing the
panel on a later step.

### Final save

- Re-validate all three step forms; then, inside one `transaction.atomic()`:
  1. create the new person (if any) with the same semantics as `PersonCreateView` (owner
     permission, `user_link` handling, group memberships through `GroupHierarchyService`,
     interests);
  2. create the new gift and event (if any) as their create views do;
  3. build the data for `RelationForm` (recipient `person:<id>` of the new person, gift, event,
     status, due date, notes, link, price, surprise) and validate it with the real form;
  4. save through `RelationCreateView.form_valid` (owner permission, messages, HTMX response).
- If anything is rejected the transaction is rolled back, so nothing new (person, gift, event,
  group membership) is left behind, and the errors are shown.
- Only gifts, events, recipients and groups accessible to the user are accepted.
- An equivalence test pins each created object type to what its regular create view produces.

### Frontend

The step form follows the offcanvas `hx-post` / `outerHTML` pattern with a `data-form-type`.
`form-initializer.js` and `unsaved-changes.js` fall back to the event's own target after an
`outerHTML` swap, so every step form is initialized and tracked. Keyboard navigation relies on
native controls; Enter submits "Next" (the first submit button is a hidden default "Next").

An invalid step answers HTMX requests with 422 (and an error notification), like the other forms of
the app, so the shell focuses the first error and the typed input stays protected by the unsaved
changes prompt. Non-HTMX requests keep answering 200. A step shows a single error summary covering
the step's own errors and those of its new object.

### Entry points

A "Guided" button next to the existing "new plan" buttons on the plan list and home page.

## Testing

- Unit: step forms with new-object sub-forms (valid, invalid, existing chosen so sub-form ignored,
  both given), multi-valued carry-over, inline creation, equivalence with the regular create views
  (person incl. groups/interests/birthday, gift incl. tags/price/link, event incl. recurrence),
  rollback on failure, permissions (inaccessible gift/event/recipient/group rejected, owner set),
  equivalence of the final plan with a full-form plan, non-HTMX full-page fallback.
- E2E (Playwright): end-to-end flow creating a new person with details, a new gift with price and
  link, and a repeating event; validation errors on the right step; keyboard; empty-full-form
  prompt; no stale prompts after creating or discarding.
- French translations for all new strings.

## Acceptance

- A plan is created end to end in three steps, including a new recipient, a new gift and a new
  event, each with its full data.
- The result matches a plan created with the full form; each created object matches the one its
  regular create view would create.
- Validation errors appear on the relevant step; keyboard navigation and unsaved-change
  prompts behave.
- Unit and e2e tests cover the flow.
