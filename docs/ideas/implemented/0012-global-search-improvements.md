# Idea: Global Search Improvements

## Status

Implemented

## Summary

Make the Ctrl+K search modal a real command palette: include gift plans in
results, show recent items when opened, and offer "Create '<query>'" actions
when nothing matches.

## Motivation

The `global_search` endpoint (`gift_manager/views/common.py`) searches gifts,
persons, groups and events (and tags), but not gift plans, which are the
central object of the app. The modal's empty state shows static quick links
instead of the user's recent work, and a search with no results is a dead end.

## User Value

- Find any gift plan from anywhere.
- Jump back to recent items quickly.
- Create the missing object in one step.

## Possible Scope

- Search gift plans by gift name, recipient name and event name.
- Recent items (client-side storage of the last visited objects).
- "Create gift / person / event named '<query>'" entries on no results,
  prefilling the name.

## Out Of Scope

- Full-text search backends or ranking engines.
- Searching comments or notes beyond existing fields.

## Implementation Notes For AI Agent

- Endpoint and result schema: `global_search` in
  `gift_manager/views/common.py`; modal markup in
  `templates/gift_manager/base.html` and behaviour in
  `static/gift_manager/js/global-search.js`.
- Results must respect `accessible_by(user)`.
- Keep URL and icon sanitisation (`safeSearchUrl`, `safeIconClass`).
- Create shortcuts use the existing `data-action="create"` offcanvas pattern;
  prefilling needs query-string support in the create views.
- Per-type result limits exist (`max_per_category`).

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Searching a gift name or recipient name returns the matching gift plans the
  user can access, and none they cannot.
- Opening the modal with no query shows recent items when any exist.
- A no-result search shows create actions that open the form prefilled.
- Keyboard navigation and ARIA attributes keep working.
- Endpoint and XSS-safety tests cover the new result type.

## Dependencies Or Related Ideas

- None identified.

## Open Questions

- Resolved: recent items are stored per device in `localStorage`. They are recorded when a
  result is opened from the palette (not on every page visit).
