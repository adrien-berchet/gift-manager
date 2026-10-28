# Idea: Wishlists And Collaborative Gift Giving

## Status

Considering

## Summary

Combine wishlist and gift planner features. A registered user describes themselves (interests,
preferences) and keeps a wishlist, so their friends find ideas that suit them. Friends then plan,
buy and give a gift together, with a tally of who paid what, without any money moving through the
app.

The work is split into three projects, each with its own spec and plan:

- **A. Person and account link** (prerequisite): know which `Person` record represents which user
  account, and base surprise and recipient rules on it.
- **B. Own profile and wishlist**: a profile the user writes about themselves and a wishlist on
  their account, shown next to every record linked to that account, with claims and giver
  discussion hidden from the wisher.
- **C. Group gifts**: several participants on a plan, each participant's share, paid or unpaid,
  and what each still owes the buyer.

## Motivation

Comparable products split into wishlist apps (Giftster, GiftList, Giftful, Elfster), which know
what the recipient wants but do not help givers plan, and gift planners (GiftTracker, Santa's
Bag), which help one giver but know nothing about the recipient's wishes. Gift Manager already has
most of the planner and coordination side: per-object sharing, claims, plan comments, surprise
plans, recipient notes, interests and history, and AI suggestions. It lacks a reliable link
between records and accounts (`Person.user_link` is set to the creator but read as the
recipient's identity), a profile written by the user, real wishlist behaviour, and buying
together.

## User Value

- Recipients tell their friends what they like and want, once, instead of repeating it in chats.
- Givers see the recipient's own wishes next to their private notes and plans.
- Several givers buy one gift together and know who still owes what.
- Surprise plans stay hidden from the right people, including co-givers who are not recipients.

## Possible Scope

- Project A, specified in
  `docs/superpowers/specs/2026-10-28-person-account-link-design.md`.
- Project B: self-written profile fields on the account, wishlist items with priorities, a
  "hide claims from me" behaviour for the wisher, giver-only discussion on wishes.
- Project C: participants on a plan, shares, paid or unpaid marks, a per-plan balance.

## Out Of Scope

- Processing payments or holding money.
- Public or anonymous guest access by link (possible later idea).
- Secret Santa draws, price tracking, push notifications and the installable PWA.

## Implementation Notes For AI Agent

- Start with project A; B and C depend on `Person.account`.
- Surprise visibility: `RelationQuerySet.hidden_surprises_for` and `recipient_groups_for` in
  `gift_manager/models.py`, and `gift_manager/plan_coordination.py`.
- Permissions: `PermissionService` in `gift_manager/services.py`; never grant access through the
  account link.
- Friends and invitations: `gift_manager/views/profile.py`, `gift_manager/invitations.py`.
- Recipient data used by suggestions: `gift_manager/person_profile.py`,
  `gift_manager/interests.py`, `gift_manager/suggestions/`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/ideas/implemented/0007-shared-plan-coordination.md`
- `docs/ideas/implemented/0027-recipient-preference-profiles-and-feedback-persistence.md`

## Acceptance Criteria

- Project A: the acceptance criteria and tests of its spec pass on PostgreSQL.
- Project B: a user edits their own profile and wishlist; friends with a linked record see them;
  the wisher never sees claims or giver discussion on their wishes.
- Project C: participants and shares are recorded on a plan, the balance is correct, and no
  payment data is collected.
- Existing surprise, sharing and permission tests keep passing.

## Dependencies Or Related Ideas

- Builds on `0007` (shared plan coordination), `0006` (recipient notes and interests) and `0027`
  (recipient preference profiles).
- The installable PWA (follow-up to `0014`) is deferred until these core features exist.

## Open Questions

- Project B: which profile fields beyond interests (sizes, colours, brands)? Recommendation from
  the spec review: include a self-written "please avoid" list (dislikes, allergies, formats such
  as "no physical books"). Feed it into the existing suggestion signals (dismissal reasons from
  `0026`, preference profiles from `0027`) instead of adding a parallel list. Sending a
  self-written profile to the AI needs the profile owner's consent; the existing
  `Profile.ai_share_person_notes` setting only covers a giver's own notes.
- Project B: should wishes reuse `Relation` (a plan addressed to the user's own linked record) or
  get their own model? Recommendation from the spec review: a dedicated model. `Relation`
  carries the givers' visibility rules (surprises hidden from recipients), while a wish needs the
  opposite boundary (visible to the wisher, claims and giver discussion hidden from them);
  mixing both on one model is where leaks would come from. A plan that fulfils a wish points to
  it (for example `Relation.wish`), so budgets, history and suggestions keep working unchanged.
  To be confirmed in project B's design.
- Project C: how are shares split by default (equal parts or free amounts)? Recommendation from
  the spec review: equal parts by default, with optional custom amounts per participant (which
  also covers a couple counting double, so no weights). The cents left over by an uneven split
  go to one participant.
