# Idea: Unify Delete Confirmation

## Status

Proposed

## Summary

Use one confirmation pattern and one code path for destructive actions across
the app, instead of the current mix of modal and native `confirm()` dialogs.

## Motivation

Deletion is implemented several ways:

- The HTMX-loaded confirmation modal in `static/gift_manager/js/app-shell.js`
  (`[data-action="delete"]`).
- Native `confirm()` in
  `templates/gift_manager/fallback/includes/fallback_actions.html`,
  `fallback/base_fallback.html` and
  `includes/person_group_management_grid_script.html`.
- A separate delete-confirmation loader in
  `static/gift_manager/js/touch-gestures.js`.

Wording, styling, loading state and accessibility differ between them, and the
modal path has untranslated text ("Deleting...").

## User Value

- Predictable, consistent behaviour for a risky action.
- Better accessibility and translated feedback everywhere.

## Possible Scope

- One JavaScript module handling `[data-action="delete"]`.
- Reuse the modal for grids and touch gestures; keep a no-JavaScript
  confirmation page as fallback for the fallback mode.
- Standard wording and related-objects summary from
  `DeleteConfirmationMixin`.

## Out Of Scope

- Changing what deletion does or cascade rules.
- Undo behaviour (see `0011`).

## Implementation Notes For AI Agent

- Modal content: `includes/delete_confirmation_modal.html`,
  `includes/bulk_delete_confirmation_modal.html`,
  `views/base.py` (`DeleteConfirmationMixin`).
- Bulk deletes: `gift_manager/views/bulk_operations.py` and
  `static/gift_manager/bulk-operations.js`.
- Tests: `gift_manager/tests/test_delete_confirmation_modal.py`.
- Permission checks stay server side.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Single deletes from lists, cards, grids, detail panels and touch gestures use
  the same modal.
- No `window.confirm` call remains outside the no-JavaScript fallback.
- The confirmation is focus-managed, keyboard accessible and translated.
- Existing delete and bulk-operation tests pass.

## Dependencies Or Related Ideas

- Related to `0010` and `0017`.

## Open Questions

- Keep the native confirmation inside fallback mode, or replace it with a
  confirmation page?
