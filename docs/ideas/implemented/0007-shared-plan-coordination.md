# Idea: Coordination On Shared Gift Plans

## Status

Implemented

Decisions: any user with access to a plan (viewers included) can claim it and comment; one
claimer at a time, released by the claimer or a plan owner; owners and editors set the surprise
flag. A surprise plan is hidden from the linked recipient, or from every member of the targeted
group (nested groups included), inside `RelationQuerySet.accessible_by`; a user who owns the plan
is never hidden. The flag defaults on for new plans addressed to another app user. The rules live
in `gift_manager/plan_coordination.py`. See
`docs/superpowers/specs/2026-10-05-shared-plan-coordination-design.md`.

## Summary

Help several users planning a gift together avoid conflicts. Add a "claimed
by" marker on a gift plan, a short comment thread per plan, and a way to hide a
plan from the recipient when the recipient is also a user of the app.

## Motivation

Sharing exists (per-object permissions and a bulk share page) but nothing tells
two collaborators that one of them is already buying the gift, or lets them
discuss it. Shared family gifting is a core use case of the sharing model.

## User Value

- No double purchases.
- Discussion stays attached to the plan instead of going through other apps.
- Surprises are protected.

## Possible Scope

- "I'll take this" action storing the claiming user and timestamp, visible on
  cards and details.
- Plan comments (author, text, timestamp) in the detail panel.
- Surprise flag that excludes a plan from everything visible to the linked
  user (`Person.user_link`).

## Out Of Scope

- Real-time chat or push notifications.
- New permission levels.
- Changes to the sharing UI redesign tracked in the UX roadmap.

## Implementation Notes For AI Agent

- Permission model: `PermissionLevel`, `RelationPermission` and
  `PermissionService` in `gift_manager/models.py` and
  `gift_manager/permissions.py`; sharing logic in
  `gift_manager/sharing_service.py`. Do not duplicate access checks.
- Who may claim or comment must follow existing editor/viewer semantics; decide
  explicitly for viewers.
- The surprise flag touches every query that lists plans, including dashboard,
  search, grids and exports: audit `RelationQuerySet.accessible_by` and the
  search views in `gift_manager/views/search.py`.
- Detail partial: `includes/relation_detail_partial.html`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/tests/test_permission_locking.py`

## Acceptance Criteria

- A collaborator can claim and release a plan; others see who claimed it.
- Comments are visible only to users with access to the plan.
- A plan marked as a surprise is never visible to the linked recipient user in
  any list, search result or detail view (regression tests per surface).
- Existing permission tests still pass.

## Dependencies Or Related Ideas

- Requires care with the sharing redesign noted in `docs/ux-roadmap.md`.

## Open Questions

Resolved: viewers can comment and claim; the surprise flag defaults on when the recipient is
another user (person or group member).
