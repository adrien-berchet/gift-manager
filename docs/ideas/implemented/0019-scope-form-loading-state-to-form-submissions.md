# Idea: Scope Form Loading State To Form Submissions

## Status

Implemented

`setupFormLoadingStates` in `loading-states.js` now locks a form only when the
request comes from the form itself or its submit button. `disableFormControls`
returns an idempotent restore function that runs on `htmx:afterRequest`,
`htmx:responseError` and `htmx:sendError`, keeping the `beforeunload` and 30 s
fallbacks. Controls disabled before a submission stay disabled. Findings:

- No existing form relied on a descendant request locking the whole form; every
  form partial posts through the `<form>` itself.
- `data-loading-ignore` was removed from `relation_fields.html` as redundant.
- `unsaved-changes.js` needed no change.
- Coverage: `gift_manager/tests/e2e/test_form_loading_state.py`.

## Summary

`gift_manager/static/gift_manager/loading-states.js` disables every control of a
form whenever any HTMX request starts from an element inside that form, and only
re-enables them on page unload or after a fixed 30-second timeout. Restrict this
lock to the form's own submission and re-enable the controls when the request
completes.

## Motivation

The lock was written for the case where the `<form>` itself is posted through
HTMX, to prevent double submits. Because it checks `closest('form')` on the
requesting element, any other HTMX request from inside a form triggers it too:
inline hints, lazy-loaded sections, validation or preview requests. For a short
background request the form then stays locked for the full 30 seconds.

This already broke the e2e suite once: the repeat-gift hint box in the gift plan
form fires a request on load, which left the recipient, gift and status selects
disabled. It was worked around with an opt-out attribute, `data-loading-ignore`
(see `setupFormLoadingStates`), but every new in-form HTMX feature has to
remember that attribute.

## User Value

- Forms never lock up because of an unrelated background request.
- Developers can add in-form HTMX features without knowing about a hidden side
  effect.
- Controls are re-enabled as soon as a real submission finishes (for example
  after a validation error) instead of after a timeout.

## Possible Scope

- Only apply the loading state when the request element is the form itself (or
  its submit button), not for any descendant.
- Re-enable controls on `htmx:afterRequest` and `htmx:responseError` for the
  request that disabled them, keeping the `beforeunload` and timeout fallbacks.
- Keep `data-loading-ignore` working, or remove it and its markup if it becomes
  redundant.
- Review every form that contains inner HTMX buttons or triggers to confirm none
  relies on the current lock.

## Out Of Scope

- Redesigning the loading indicators, overlays or button spinners.
- Changing unsaved-changes handling (`unsaved-changes.js`), even though it reads
  the same `data-original-disabled` attribute.
- Adding new in-form HTMX features.

## Implementation Notes For AI Agent

- `gift_manager/static/gift_manager/loading-states.js`: `setupFormLoadingStates`
  (the `htmx:beforeRequest` listener) and `disableFormControls` (stores
  `dataset.originalDisabled`, restores it on `beforeunload` or after 30 s).
- `gift_manager/static/gift_manager/unsaved-changes.js` reads
  `data-original-disabled` (search for `originalDisabled`); keep it consistent.
- The in-form hint box that needed the opt-out is in
  `gift_manager/templates/gift_manager/includes/forms/relation_fields.html`.
- Existing coverage: `gift_manager/tests/test_loading_state_feedback_property.py`
  and the e2e tests under `gift_manager/tests/e2e/` (gift planning workflow,
  `test_phone_layout.py`, `test_relation_reaction.py`).
- Verify with the e2e suite, since the behaviour is only observable in a browser.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/ideas/implemented/0005-recipient-gift-history.md` (origin of the workaround)

## Acceptance Criteria

- A background HTMX request from an element inside a form does not disable the
  form's controls, with no opt-out attribute needed.
- Submitting a form through HTMX still disables its controls, and they are
  re-enabled when the request fails or returns validation errors.
- Controls that were already disabled before a submission stay disabled
  afterwards.
- The repeat-gift hint in the gift plan form keeps working, and the e2e suite
  passes.
- Tests cover both the submission lock and the non-locking background request.

## Dependencies Or Related Ideas

- Related to `0005`, whose repeat-gift hint exposed the problem.
- Related to `0017` (inline scripts moved to static files), which put this logic
  in `loading-states.js`.

## Open Questions

None.
