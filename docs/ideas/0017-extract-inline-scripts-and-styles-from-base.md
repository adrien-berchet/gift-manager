# Idea: Extract Inline Scripts And Styles From The Base Template

## Status

Proposed

## Summary

Move the large inline CSS and JavaScript blocks out of `base.html` into static
files, remove duplicated helpers, and consolidate the two notification
implementations.

## Motivation

`gift_manager/templates/gift_manager/base.html` is about 1,650 lines, most of it
inline: global-search CSS and logic, theme toggle, offcanvas and modal wiring,
the delete flow, toasts and HTMX hooks. Consequences:

- Inline code is not cached by the browser, is hard to test and cannot be
  linted like other JavaScript.
- `getCookie` is defined twice, and `window.userViewPreferences` is set twice.
- Toasts exist both inline (`window.showNotification`) and in
  `static/gift_manager/notifications.js`.
- Translated strings are injected through template tags in the middle of
  scripts, which is how untranslated literals slip in (see `0009`).

Other large files (`grid-utils.js` at ~2,100 lines, `theme.css` at ~3,200)
could follow later.

## User Value

- Faster repeat page loads and easier maintenance.
- Fewer regressions in shared UI code.

## Possible Scope

- New static files for global search, offcanvas/modal handling and notifications.
- A small translated-strings object emitted once by the template.
- Remove duplicates and dead branches.
- Smoke tests for the extracted behaviour.

## Out Of Scope

- Introducing a bundler or a frontend framework.
- Visual changes.

## Implementation Notes For AI Agent

- Keep the existing vanilla JavaScript style and load order in `base.html`.
- Preserve event names (`offcanvas:show`, `offcanvas:close`, `list:update`,
  `showNotification`, `reaction:prompt`) used across partials and scripts.
- Verify with the e2e suite because this code drives every panel.

Recommended starting context:

- `docs/ai/testing.md`
- `gift_manager/tests/FRONTEND_TESTING.md`
- `gift_manager/tests/e2e/`

## Acceptance Criteria

- `base.html` contains no large inline script or style blocks beyond
  translated-string data and small bootstrap snippets.
- A single notification implementation remains.
- Existing unit and e2e tests pass with no behaviour change.

## Dependencies Or Related Ideas

- Helps `0009` and `0011`; complementary to `0018`.

## Open Questions

- Incremental extraction per feature, or one refactor?
