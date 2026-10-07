# Guided Gift Plan Creation — Design

Implements idea `docs/ideas/0016-guided-gift-plan-creation.md`.

## Goal

Let a new user create a gift plan in three short steps (recipient, gift, occasion) without
learning the full form. The full form stays available and unchanged.

## Decisions

- Server-driven steps (HTMX partials, full pages without JavaScript).
- Default status of a guided plan: `Idea`.
- A separate "Guided" entry point; existing "new plan" buttons keep opening the full form.
  Prefilled flows (birthday, duplicate, per-person/group/gift) stay on the full form.
- Step 3 contains event, due date and an optional notes field. Sharing is not part of the flow.
- Out of scope: changing the gift-plan model, replacing the existing create form, carrying the
  guided selections over to the full form.

## Design

### Route and view

- New route `relations/guided/`, name `relation_guided_create`.
- `RelationGuidedCreateView` subclasses `RelationCreateView`. It renders a partial for HTMX
  requests and a full page otherwise (same pattern as other create views).

### Steps

1. **Recipient** — choices from `build_recipient_choices` (`person:<id>` / `group:<id>`).
2. **Gift** — an accessible gift, or a new gift name (name only).
3. **Occasion** — an accessible event, or a new event (name and date, created as a one-time
   event); due date defaulting to the event date; optional notes (`comment`).

Each step shows a progress indicator and a Back button. Earlier answers travel as hidden
fields; there is no session state. Each Next/Back POST validates only the current step with a
small step form, so errors appear on the relevant step.

### "Use an empty full form"

Every step carries a link to `relation_create`, labelled "Use an empty full form" (the guided
selections are not carried over). When the user has already entered something, following the
link asks for confirmation that the entered data will be discarded. The existing
unsaved-changes prompt is reused if it covers the hidden step state; otherwise a dedicated
confirm is used.

### Final save

- The view assembles the collected values and validates them with the real `RelationForm`
  (status defaults to `Idea`), so the result matches a plan created with the full form.
- It then reuses `RelationCreateView.form_valid` (owner permission, `user_link`, messages).
- Inline gifts and events are validated with `GiftForm` / `EventForm`, owned by the user via
  `PermissionService`, and created in the same `transaction.atomic` as the plan, so a failed
  plan leaves no orphan gift or event.
- Only gifts, events and recipients accessible to the user are accepted.

### Frontend

The step form follows the offcanvas `hx-post` / `outerHTML` pattern with a `data-form-type`, so
`form-initializer.js` and `unsaved-changes.js` apply (verified during implementation). Keyboard
navigation relies on native controls; Enter submits "Next".

### Entry points

A "Guided" button next to the existing "new plan" buttons on the plan list and home page.

## Testing

- Unit: per-step validation, inline gift and event creation, equivalence with a full-form
  plan, rollback on failure, permissions (inaccessible gift/event/recipient rejected, owner
  set), non-HTMX full-page fallback.
- One Playwright e2e test for the end-to-end flow including inline gift and event.
- French translations for all new strings.

## Acceptance (from the idea)

- A plan is created end to end in three steps, including a new gift and a new event.
- The result matches a plan created with the full form.
- Validation errors appear on the relevant step; keyboard navigation and unsaved-change
  prompts behave.
- Unit and e2e tests cover the flow.
