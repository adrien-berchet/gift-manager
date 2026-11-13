# Idea: Delete For Everyone With Copies For Dependent Plans

## Status

Proposed

## Summary

Let the only owner of a shared object delete it for everyone without destroying other
people's gift plans. Before deleting the original, give the users who own plans pointing to it
their own copy of the object, move their plans to that copy, then delete the original.

Today the only owner of a shared object can hand it over to someone and remove their own
access ("Hand over and remove my access"), but cannot delete it for everyone.

## Motivation

Deleting a person, group or gift cascades to every gift plan made for it, including plans owned
by other users and plans the owner is not allowed to see (surprises, plans not shared with
them). A warning cannot list those plans without revealing them, so a plain "delete for
everyone" would silently destroy other people's work. Copying the object for the users who
depend on it removes the data loss and reveals nothing to the owner.

## User Value

- Owners can really get rid of something they no longer want, even after sharing it.
- Collaborators never lose the gift plans they built, and no surprise is exposed.

## Possible Scope

- A "Delete for everyone" choice next to "Hand over and remove my access" in the delete
  confirmation of a shared object's only owner, with a warning naming the people who lose
  access and saying that people who planned gifts with it keep their own copy.
- For people, groups and gifts (plans cascade on them today) and events (plans lose their
  occasion today): one shared copy for the owners of the dependent plans, who become its
  owners; their plans are moved to the copy in the same transaction; then the original is
  deleted.
- The copy only contains what those users could already see: a plan owner without access to
  the original gets only what the plan already showed (e.g. the name).
- A short note on the copy, e.g. "Copy kept when the original was deleted".

## Out Of Scope

- Copies for users who only had access without any dependent plan: they simply lose access.
- Tags (no plan points to them).
- Bulk "delete for everyone" from list grids.

## Implementation Notes For AI Agent

Recommended starting context:

- `gift_manager/services.py` — `PermissionService.delete_mode_for`, `delete_or_leave`,
  `handover_candidates`, `_hand_over` (the current hand-over flow).
- `gift_manager/views/base.py` — `DeleteSharedMixin`, `BaseDeleteView`,
  `delete_action_button`.
- `gift_manager/templates/gift_manager/confirm_delete.html`,
  `includes/delete_confirmation_modal.html`, `includes/handover_owner_field.html`.
- `gift_manager/models.py` — `Relation` foreign keys (`person`, `group`, `gift` cascade;
  `event` is set to null), `Person.account` links, `PersonGroup` hierarchy and members,
  `ReceivedGift.giver_persons` / `giver_groups`.
- `docs/ai/architecture.md`, `docs/ai/testing.md`.

Points to settle:

- A copied person linked to an account must respect the person-account link rules.
- A copied group must keep its members and its place in the hierarchy.
- Received gifts whose givers point to the deleted person or group.
- Surprise plans: the deleting owner must learn nothing about plans hidden from them.

## Acceptance Criteria

- The only owner of a shared object can delete it for everyone after an explicit warning.
- Every gift plan owned by another user that pointed to it still exists afterwards, pointing to
  a copy those users own; plans the deleting owner could not see are kept too.
- The deleting owner's confirmation reveals no plan they could not see (no names, no counts).
- Unit tests cover people, groups, gifts and events, co-owned plans, surprise plans, and copies
  restricted to what the plan owners could see; an e2e test covers the confirmation flow.

## Dependencies Or Related Ideas

- The 2026-11-12 QA report (`docs/qa/2026-11-12-pre-release-qa-report.md`), which introduced
  "Remove my access" and "Hand over and remove my access".

## Open Questions

- Should the users who receive a copy be notified (e.g. at their next visit)?
- When several users own the dependent plans, one shared copy or one copy each?
