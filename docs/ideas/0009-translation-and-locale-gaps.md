# Idea: Close Translation And Locale Gaps

## Status

Proposed

## Summary

Fix user-facing text and formatting that bypasses the existing French
translation: hardcoded English strings in JavaScript and templates, fixed
English date formats, and a hardcoded `lang="en"`.

## Motivation

The app ships French translations, but a review found text that never gets
translated:

- `date:"M d, Y"` is hardcoded in 14 templates (for example
  `includes/gift_plan_card.html`, `includes/event_detail_partial.html`).
- JavaScript strings such as `'Deleting...'`, `'Loading...'`,
  `'You do not have permission to perform this action'` and
  `'Error loading form. Please try again.'` in `templates/gift_manager/base.html`,
  `static/gift_manager/loading-states.js`, `ui-enhancements.js`,
  `notifications.js` and `form-initializer.js`.
- `<html lang="en">` is hardcoded in `base.html`, which hurts screen readers and
  browser translation.
- Untranslated attributes: `alt="Gift"`, `aria-label="Toggle dark mode"`, the
  "Login" button in `registration/login.html`, and `Created:` / `Schedule:` in
  `DeleteConfirmationMixin` (`views/base.py`).

## User Value

- French users see a consistent interface and locale-correct dates.
- Better accessibility through a correct document language.

## Possible Scope

- Replace fixed date formats with `DATE_FORMAT` / `SHORT_DATE_FORMAT`.
- Route JavaScript strings through the existing translation mechanism (see
  `includes/grid-translations.html` and
  `includes/unsaved_changes_translations.html`).
- Use `{{ LANGUAGE_CODE }}` for the `lang` attribute.
- Wrap remaining literals with `gettext`/`{% trans %}` and update
  `locale/fr`.
- Add a test that fails on new hardcoded date formats.

## Out Of Scope

- Adding new languages.
- Redesigning the affected components.

## Implementation Notes For AI Agent

- Workflow: `python manage.py makemessages -l fr` then
  `python manage.py compilemessages`.
- Existing terminology test: `gift_manager/tests/test_gift_plan_terminology.py`.
- Do not translate values used as slugs or identifiers (see
  `gift_manager/statuses.py`).

Recommended starting context:

- `docs/ai/testing.md`
- `locale/`

## Acceptance Criteria

- No template uses a hardcoded English date format.
- Switching to French shows translated loading, error and permission messages.
- The `lang` attribute follows the active language.
- Translation files are up to date and compile; lint and related tests pass.

## Dependencies Or Related Ideas

- Overlaps the "Translation coverage" item of the UX roadmap checklist.

## Open Questions

- None identified.
