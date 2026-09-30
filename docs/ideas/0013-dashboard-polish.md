# Idea: Dashboard Polish

## Status

Proposed

## Summary

Small improvements to the action dashboard: a helpful "all caught up" state,
clickable library counts, and removal of leftover data that is computed but not
used.

## Motivation

The dashboard answers "what should I do next?" but has rough edges:

- When nothing needs attention it shows a bare "No gift plans need attention."
  message with a create button, which wastes the moment to show what comes next.
- The library stat tiles at the bottom are not navigation aids for the filters
  they describe.
- The `home` view computes `recent_gifts` and `recent_persons`
  (`gift_manager/views/common.py`); confirm they are actually rendered and drop
  them otherwise.

## User Value

- Reassuring, informative empty state.
- Faster navigation from counts to lists.
- Slightly cheaper page loads.

## Possible Scope

- Empty state showing the next upcoming due date or event and a link to it.
- Stat tiles linking to the matching list or filter.
- Remove unused context data, or render it as a "Recently added" section.

## Out Of Scope

- Reworking the action-group logic.
- New dashboard widgets (see birthdays in `0002`).

## Implementation Notes For AI Agent

- View: `home` in `gift_manager/views/common.py`; template:
  `gift_manager/templates/gift_manager/home.html`.
- Bucket logic: `_build_gift_plan_action_groups`,
  `_build_dashboard_summary`.
- Keep the page progressive-enhancement friendly and translated.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ux-roadmap.md` (Phase 5)

## Acceptance Criteria

- With no plan needing attention, the dashboard shows the next upcoming item
  when one exists, otherwise guidance to create one.
- Each stat tile links to its list.
- No unused queries remain in the `home` view (verified by a query-count
  test).
- Existing dashboard tests pass.

## Dependencies Or Related Ideas

- `0002` adds an upcoming-birthdays section.

## Open Questions

- Should clicking a tile apply a filter or only open the list?
