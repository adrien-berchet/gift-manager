# Idea: Recipient Notes And Interests

## Status

Proposed

## Summary

Let users attach free-text notes and interest tags (hobbies, sizes, allergies,
things to avoid) to a person. Interest tags are matched against gift tags to
highlight relevant gifts when planning.

## Motivation

The best gift ideas are noticed in passing ("she mentioned wanting a
kayak"), but `Person` has nowhere to store that. Users fall back to gift
comments or external notes, and the information never reaches the planning
flow.

## User Value

- One place to remember what a person likes or must avoid.
- Faster gift selection through tag matching.
- Safer choices when allergies or preferences are recorded.

## Possible Scope

- `notes` text field on `Person`, shown on the detail page and edited in the
  person form.
- Interest tags reusing the existing `GiftTag` hierarchy (or a dedicated link)
  so matching with gifts is direct.
- In the gift picker of the plan form, a hint or sort that prefers gifts
  sharing tags with the recipient's interests.

## Out Of Scope

- AI-generated suggestions (see `0001`).
- Notes on groups.
- Rich text or attachments.

## Implementation Notes For AI Agent

- Models: `Person`, `GiftTag` in `gift_manager/models.py`; tag hierarchy rules
  and cycle checks live on `GiftTag`.
- Forms and partials: `includes/forms/person_fields.html`,
  `includes/person_form_partial.html`, `includes/person_detail_partial.html`.
- Notes are sensitive personal data: share them only with users who can see
  the person, and never log them. Review whether `email_encoding.py`-style
  protection is appropriate.
- Tag visibility: `GiftTag` has `is_public` and sharing permissions; decide how
  interests interact with tags the viewer cannot see.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Notes and interest tags can be set on a person in both form variants and
  appear on the detail page.
- Users without access to the person cannot read the notes.
- The plan form surfaces gifts sharing tags with the recipient's interests.
- Migration, permission and form tests pass.

## Dependencies Or Related Ideas

- Feeds `0001` suggestions; related to `0002` and `0005`.

## Open Questions

- Reuse `GiftTag` for interests or add a separate interest model?
- Should notes be visible to users the person is shared with at view level?
