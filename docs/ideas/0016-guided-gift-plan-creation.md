# Idea: Guided Gift Plan Creation

## Status

Proposed

## Summary

Offer a short guided flow for creating a gift plan: choose the recipient,
choose or create the gift inline, then choose the occasion and date. The full
form stays available for advanced users.

## Motivation

The UX roadmap deferred guided creation until the recipient and gift-plan
language were stable; both now are. Today a new user must understand the full
form (recipient, gift, event, status, due date, notes, sharing) before
planning their first gift, and creating a missing gift or event means leaving
the form.

## User Value

- New users succeed at the core task without learning the model.
- Missing gifts and events are created without losing context.
- Returning users keep the complete form.

## Possible Scope

- Three-step offcanvas flow with progress indication and back navigation.
- Inline creation of a gift (name only) and an event (name and date).
- Sensible defaults for status (`Idea` or `Planned`) and due date from the
  event.
- A link to "Use the full form".

## Out Of Scope

- Changing the gift-plan model.
- Replacing the existing create form.

## Implementation Notes For AI Agent

- Existing forms and recipient choices (`person:<id>`, `group:<id>`):
  `gift_manager/forms.py`,
  `templates/gift_manager/includes/relation_form_partial.html`,
  `includes/forms/relation_fields.html`.
- Create views: `gift_manager/views/relation.py`.
- Offcanvas loading and form initialisation: `base.html` and
  `static/gift_manager/form-initializer.js`; unsaved-changes handling in
  `unsaved-changes.js`.
- Must work without JavaScript as a multi-page fallback where practical.
- Sharing and permissions are applied by existing create logic; reuse it.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ux-roadmap.md` (Deferred Workflow Ideas)

## Acceptance Criteria

- A user can create a plan end to end in three steps, including a new gift and
  a new event created inline.
- The resulting plan matches one created with the full form.
- Validation errors are shown on the relevant step, keyboard navigation works,
  and unsaved-change prompts behave.
- Unit and e2e tests cover the flow.

## Dependencies Or Related Ideas

- Natural target of the "+" action in `0015`; can prefill from `0002`.

## Open Questions

- Default status for a guided plan?
