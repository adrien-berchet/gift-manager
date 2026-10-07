# Idea: Remove Redundant Toasts

## Status

Proposed

## Summary

Stop showing success toasts and flash messages that only repeat something the user
can already see. When an action visibly changes the page (a row appears, a status
badge changes, a form closes) or navigates to a new page, a "saved" or "created"
message adds noise. Keep toasts for outcomes that are not otherwise visible: errors,
warnings, background results, and actions that offer Undo.

## Motivation

- Toasts and Django flash messages are emitted by many views regardless of whether
  the result is already obvious (`messages.success` in `gift_manager/views/`,
  `HX-Trigger` `showNotification` headers, `NotificationMixin`).
- A toast after a redirect to the created object's page, or after an inline edit
  that already updated the cell, competes for attention and can cover content.
- Consistent use makes the remaining toasts (errors, Undo, non-visible changes)
  more noticeable.

## User Value

- Less visual noise and fewer messages to dismiss or read.
- Errors and genuinely invisible outcomes stand out.
- Faster-feeling interface on mobile, where toasts cover content.

## Possible Scope

- Audit every `messages.*` call, `showNotification` call and `HX-Trigger`
  notification, and classify each as visible-result, navigation, or invisible.
- Remove success feedback when the action re-renders the affected content or
  redirects to a page that shows the result.
- Keep toasts for errors, warnings, Undo toasts, deletions (the deleted row
  disappears, so a confirmation message stays), and results the user cannot see
  (for example a copied link, a setting saved without any page change, a
  background or batch outcome).
- Record the decision rule and the list of intentionally kept toasts in
  `docs/ai/architecture.md` so new code follows it.

## Out Of Scope

- Redesigning the toast component or its styling.
- Removing error, warning or validation messages.
- Removing the Undo toast of idea `0011`.
- Changing allauth's own messages unless they clearly fit the rule.

## Implementation Notes For AI Agent

- Server side: `gift_manager/mixins/notifications.py` (`NotificationMixin`,
  `settings_form_response`), `gift_manager/message_levels.py`
  (`MESSAGES_DISPLAY_LEVEL`), and `messages.*` calls in `gift_manager/views/`.
- Client side: `showNotification` and the `showNotification` HX-Trigger listener
  in `gift_manager/static/gift_manager/js/app-shell.js`; callers in
  `inline-editing.js`, `bulk-operations.js`, `grid-utils.js`,
  `gift-plan-quick-actions.js` and `form-initializer.js`.
- Flash message rendering lives in `gift_manager/templates/gift_manager/base.html`.
- Preserve non-JavaScript behaviour: a classic post that redirects must still end
  on a page that makes the result evident.
- Existing tests may assert on messages; update them to match the new rule and
  keep tests for the toasts that remain.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/static/gift_manager/js/app-shell.js`

## Acceptance Criteria

- Creating, editing or deleting an item that redirects to a page showing the
  result no longer produces a success toast or flash message.
- Inline edits, quick actions and HTMX swaps that visibly update the page no
  longer show a redundant success toast.
- Error, warning and Undo toasts are unchanged, and deletions still show a
  confirmation message.
- `docs/ai/architecture.md` documents the rule and the kept toasts.
- Results with no visible change still give feedback.
- Tests are updated, and e2e checks cover one removed and one kept toast.

## Dependencies Or Related Ideas

- Related to `0011` (Undo toasts) and `0017` (single `showNotification`
  implementation).

## Open Questions

- Should a short list of intentionally kept success toasts be documented in
  `docs/ai/architecture.md`? Answered: yes.
- Should deletions keep a confirmation message when the deleted row disappears?
  Answered: yes.
