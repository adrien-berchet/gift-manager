# Idea: Undo Toasts For Low-Risk Actions

## Status

Implemented

Gift-plan card quick actions (Given, Purchased, Abandon, Set date) now show a toast
with an Undo button for 5 seconds. `showNotification` in `app-shell.js` accepts
`options.action` ({label, onClick}); the toast is then `role="status"` /
`aria-live="polite"`. `relation_quick_action` returns a signed token (5 minutes max
age, bound to the user and plan) holding the previous and resulting values, and
`relation_quick_action_undo` restores them (including `status_changed_at`) only if
the plan still matches the resulting state (409 otherwise) and the user can still
edit it. Undoing also closes the reaction prompt opened by Given/Abandon. The "Plan"
action is not undoable because of its sharing cascade, and tag removal was left out.

## Summary

For reversible, low-risk actions (abandoning a gift plan, changing a status,
removing a tag from a gift), replace or complement confirmation modals with an
immediate action followed by a toast offering "Undo" for a few seconds.

## Motivation

Every destructive action currently goes through a confirmation modal, which
adds friction to frequent actions such as quick status changes on cards. Modals
are right for permanent deletion, but undo is faster and more forgiving for
reversible changes.

## User Value

- Fewer clicks for common actions.
- Mistakes are recoverable without extra dialogs.

## Possible Scope

- Extend `window.showNotification` (in `static/gift_manager/js/app-shell.js`)
  with an optional action button and longer timeout.
- Undo for quick status changes on cards and for "Abandon".
- A server endpoint or HTMX pattern that restores the previous value,
  including `status_changed_at`.

## Out Of Scope

- Undo for permanent deletion.
- A global undo history.

## Implementation Notes For AI Agent

- Quick actions: `gift_manager/gift_plan_actions.py`,
  `static/gift_manager/js/gift-plan-quick-actions.js`, view
  `relation_quick_action` in `gift_manager/views/relation.py`.
- `showNotification` in `app-shell.js` is the only toast implementation (the
  unused `notifications.js` was removed with idea 0017); toast styling lives in
  `static/gift_manager/css/notifications.css`.
- The reaction prompt that opens after marking a plan given must still work.
- Undo must re-check permissions server side.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Changing a plan status from a card shows a toast with Undo for at least 5
  seconds; Undo restores status and dates.
- Undo fails safely if the plan changed meanwhile or permissions were lost.
- Toast and Undo are reachable by keyboard and announced to screen readers.
- Unit and e2e tests cover success and failure paths.

## Dependencies Or Related Ideas

- Related to the notification consolidation in `0017`.

## Open Questions

- Undo window length? Answered: 5 seconds.
