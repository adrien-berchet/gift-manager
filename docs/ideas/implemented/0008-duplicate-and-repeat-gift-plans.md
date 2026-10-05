# Idea: Duplicate And Repeat Gift Plans

## Status

Implemented

Decisions: copies never inherit sharing (the user who creates a copy is its only owner);
"Plan again" always creates `Idea` plans; "Duplicate" opens the plan form pre-filled
(`?duplicate_of=<plan id>`, from the card, detail page and grid) and also starts in `Idea`.
"Plan again" lives on the detail page of a repeating event and of the Birthday event, whose
copies are due on each recipient's next birthday (no date for a group or a person without a
birthday). Plans of the last occurrence are offered once per gift and recipient, unless a live
plan already covers the next occurrence; abandoned plans are never offered. The same
visibility rules as the plan form apply: a copy needs access to the gift and the recipient,
and no more. Logic: `gift_manager/plan_repeat.py`.

## Summary

Add a "Duplicate plan" action, and a "Plan again next year" flow that, for a
recurring event, offers to recreate last occurrence's plans as new ideas with
the status reset and the due date moved to the next occurrence.

## Motivation

Families and friend groups receive gifts on the same occasions every year, and
users currently re-create each plan from scratch. The `Event` model already
knows how to compute `next_occurrence`, so the data needed to automate repeats
is present.

## User Value

- Much faster setup for recurring occasions.
- Less retyping when giving similar gifts to several people.

## Possible Scope

- "Duplicate" action in card, detail and grid actions; opens the plan form
  pre-filled with the copy.
- For recurring events, a "Plan again" suggestion listing last occurrence's
  plans with checkboxes; selected ones become new plans in `Idea` status with
  the next occurrence date.
- Reactions and rating are never copied.

## Out Of Scope

- Automatic creation without user confirmation.
- Bulk-duplicate across unrelated events.

## Implementation Notes For AI Agent

- Plan creation and forms: `gift_manager/views/relation.py`,
  `gift_manager/templates/gift_manager/includes/relation_form_partial.html`.
- Quick actions and card metadata: `gift_manager/gift_plan_actions.py`,
  `gift_manager/gift_plan_cards.py`.
- Recurrence: `Event.next_occurrence` in `gift_manager/models.py`.
- Shared plans: copies should not inherit sharing implicitly; decide and
  document, and keep permission checks in `PermissionService`.
- Status lookups use slugs in `gift_manager/statuses.py`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Duplicating a plan opens a pre-filled form and creates a new plan without
  altering the original.
- "Plan again" only offers plans the user can view and creates them with status
  `Idea`, no reaction data and the next occurrence date.
- Viewer-only users cannot create copies in objects they cannot edit.
- Tests cover duplication, date computation and permissions.

## Dependencies Or Related Ideas

- Related to history (`0005`).

## Open Questions

- Should copies keep the original sharing permissions?
- Is "Idea" always the right initial status?
