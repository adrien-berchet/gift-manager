# Idea: Complete Gift Plan Visibility And Bounded Sections

## Status

Proposed

## Summary

Make sure every gift plan the user can access appears on the gift plans
("relations") workspace page, and keep each urgency section to a bounded height
so the user can scroll past a long section to reach the last one. Each section
should hold several pages of cards at most, using paging or an expand control,
instead of growing without limit.

## Motivation

The workspace page (`RelationListView`) groups plans into urgency sections
(Overdue, Due soon, Needs details, Later, Ideas, Completed). It was reported
that some gift plans may not show up on the page, which breaks trust in it as
the single overview of what is planned. Separately, a section with many cards
can push later sections far down the page, so reaching the last section (often
Completed) takes a lot of scrolling.

## User Value

- Users can rely on the workspace to list every plan they can access, so no gift
  is forgotten.
- Users with many plans can jump to any section without scrolling through
  hundreds of cards.

## Possible Scope

- Audit why a plan could be missing from the workspace: the workspace queryset,
  the grouping logic, permission filtering (`accessible_by`), the `focus` filter,
  and the per-section recipient filter. Fix every cause found.
- Add a regression test comparing the set of plans shown in the workspace with
  the set of plans accessible to the user (own, shared, group recipients,
  person recipients, no event, no due date, each status).
- Cap the visible size of each section, for example a fixed number of cards per
  section with "show more" or in-section paging, or an internal scroll area
  limited to a few pages of cards.
- Keep section counts and the summary strip showing the true totals, not just the
  visible cards.
- Keep the per-section recipient filter working across the cards that are not
  currently visible.

## Out Of Scope

- Changing the urgency grouping rules or section order.
- Changing card appearance (see idea 0021).
- Changes to the advanced Grid.js list.
- Server-side pagination of the whole page, unless the first slice proves it is
  required.

## Implementation Notes For AI Agent

Relevant code:

- `gift_manager/views/relation.py`: `RelationListView`, in particular
  `get_workspace_queryset`, `get_workspace_groups`, `get_workspace_summary` and
  the `focus` handling in `get_context_data`.
- `gift_manager/templates/gift_manager/relation_list.html`: section markup and
  the inline workspace refresh script.
- `gift_manager/templates/gift_manager/includes/gift_plan_card.html`.
- `gift_manager/static/gift_manager/css/gift-plan-workspace.css`.
- `gift_manager/static/gift_manager/js/gift-plan-recipient-filter.js` and
  `gift-plan-quick-actions.js`, which operate on the rendered cards and must keep
  working with hidden or paged cards.
- `gift_manager/tests/views/test_relation_list.py`.

Prefer rendering all cards and hiding the overflow progressively, or loading
more through HTMX, so that quick actions, the recipient filter and the refresh
script keep working. Follow the guidance in `AGENTS.md`: keep business rules in
services or query helpers, keep translations current, and verify layout changes
on mobile with Playwright.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- Relevant files under `gift_manager/`

## Acceptance Criteria

- For a user with plans of every status, recipient type (person and group),
  with and without event and due date, and both owned and shared, every
  accessible plan appears in exactly one workspace section.
- A test fails if the set of workspace plans differs from the set of plans
  accessible to the user.
- With more than the section cap of plans in one section, only a bounded number
  of cards is visible at once, the rest is reachable in that section, and the
  last section can be reached without scrolling through all cards.
- Section counts and the summary strip show the full totals.
- The recipient filter, quick actions with undo, and the post-action refresh
  still work on plans beyond the first visible page of a section.
- The layout holds on phone and desktop widths, verified with Playwright.
- Existing relation list tests keep passing.

## Dependencies Or Related Ideas

- 0021 Unify Card Appearance Across Pages touches the same card styles and should
  not conflict with the section sizing.

## Open Questions

- Which plans were observed missing? A reproduction (recipient type, status,
  sharing) would show whether this is a query bug or only a perception caused by
  long sections.
- Preferred bounding pattern: "show more" button, in-section pagination, or an
  internal scroll area?
- What section cap should be used (cards per page, number of pages)?
- Should the cap be per section, or should only the sections after the first be
  collapsed by default?
