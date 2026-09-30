# Idea: Recipient Gift History And Repeat-Gift Warning

## Status

Proposed

## Summary

Show, on a person or group detail page, a timeline of the gifts given to that
recipient (year, event, status, reaction rating). When creating or editing a
gift plan, warn if the chosen gift was already given or planned for the same
recipient.

## Motivation

The person detail page only shows a count of gift plans. Reaction ratings and
notes are already captured on given or abandoned plans, but they are only
visible plan by plan. Users cannot answer "what did I give Anna last
Christmas, and did she like it?" without scanning the plan list.

## User Value

- Avoid repeating a gift.
- Learn what was well received at a glance.
- Context while choosing a new gift.

## Possible Scope

- "Gift history" section on person and group detail, grouped by year, lazy
  loaded via HTMX.
- Reaction rating and note shown per entry, reusing the existing rating
  partials.
- Non-blocking warning in the gift plan form when the same gift already exists
  for the recipient (given, purchased or planned).

## Out Of Scope

- Recommendations (see `0001`).
- Editing history inline beyond existing quick actions.
- Changing permission rules.

## Implementation Notes For AI Agent

- Data source: `Relation` with `status`, `reaction_rating`, `reaction_note`,
  `event`, `due_date` in `gift_manager/models.py`; use
  `Relation.objects.accessible_by(user)`.
- Display partials: `includes/person_detail_partial.html`,
  `includes/person_group_detail_partial.html`, `includes/rating_stars.html`,
  `includes/reaction_history_partial.html`.
- Reaction visibility rules: check `has_visible_reaction` and related
  helpers before showing notes.
- Duplicate check belongs in form validation or a service, not in the
  template; typed recipient choices (`person:<id>`, `group:<id>`) are
  handled in `gift_manager/forms.py`.
- Avoid N+1 queries; prefetch gift, event and status.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- The history shows only plans the viewer can access, newest year first.
- Ratings and notes respect existing visibility rules.
- The duplicate warning appears for the same recipient and gift, does not
  block saving, and does not appear for other recipients.
- Query count for the history is bounded (covered by a test).

## Dependencies Or Related Ideas

- Supports `0001` (suggestions exclude already-given gifts).

## Open Questions

- Should group-targeted plans appear in the history of each member?
