# Idea: Secret Santa Draws For Groups

## Status

Considering

## Summary

Add an automated Secret Santa draw engine to Gift Manager groups and holiday events. An event organizer can set up a gift exchange with a spending budget, an exchange date, and pairing exclusion rules (for example, preventing couples or roommates from drawing each other, or preventing participants from drawing the same person as the previous year). The system runs a valid draw assignment and notifies participants privately.

Unlike standalone Secret Santa platforms that require re-entering wishlists and names, Gift Manager participants are linked to their existing platform profiles and wishlists. In this initial phase, the draw focuses on generation and delivery through dashboard cards and notifications, deferring complex anonymous messaging ("Santa Mail") to a later iteration.

## Motivation

Holiday gift exchanges (Secret Santa, Kris Kringle, White Elephant) are one of the most common reasons groups coordinate gifts. Families, friend circles, and coworkers currently turn to third-party tools (GiftList, Elfster, DrawNames) solely for the lottery draw, losing the benefit of Gift Manager's rich recipient profiles and integrated wishlists.

Gift Manager already has `PersonGroup` (collections of people) and `Event` (holidays, birthdays, recurring occasions). However, there is no mechanism to automate assignments or ensure everyone has a secret recipient while honoring exclusion rules. Bringing Secret Santa into Gift Manager allows the assigned Santa to view their giftee's wishlist without leaving the app.

## User Value

- Group organizers avoid manual name-drawing or third-party ad-heavy lottery sites.
- Automated draw respects exclusion rules (no spouses drawing spouses, no repeat pairings from previous exchanges).
- Assigned Santas can immediately see their recipient's wishlist and self-written profile (preferences, things to avoid, public interests).
- Clear path to planning: Santas can easily launch the guided gift planning flow (`relation_guided_create`) for their assigned recipient.

## Possible Scope

- Setup on an organizer's `PersonGroup`, optionally linked to one of the organizer's `Event`s:
  - Budget recommendation / spending limit.
  - Exchange date and guidelines, stored on the exchange itself. Events are shared per user, so participants usually cannot see the organizer's `Event`; they only see the exchange's own date, budget and guidelines. The optional event link only helps the organizer.
  - Participant selection from group members with linked accounts (`Person.account`).
  - Exclusion matrix: select pairs of participants who must not draw each other, with an option to automatically import previous pairings from last year's exchange to prevent repeat draws.
- Draw engine:
  - Backtracking solver generating a valid derangement (permutation with no fixed points, where nobody draws themselves), with configurable prevention of 2-cycles (mutual draws where A draws B and B draws A).
  - Validates that a complete solution exists before saving, reporting a clear error if constraints are impossible to satisfy.
- Wishlist and profile visibility grant:
  - In Gift Manager, `WishQuerySet.visible_to_friend` requires confirmed mutual friendship. Group members are often not direct friends. The exchange must provide an explicit, read-only grant so the assigned Santa can view the recipient's active wishlist (`WishQuerySet.visible_to_secret_santa(giver, exchange)`) and the recipient's self-written profile fields (`Profile.preferences_notes`, `Profile.avoid_notes`, `Profile.public_interests`).
  - The grant ends when the exchange is completed or the assignment is removed.
  - Santa sees only what the recipient chose to share on their own profile and wishlist. Santa never sees other givers' private notes or past gift histories.
- Assignment visibility & notification:
  - Assignments are sealed: participants only see their own assigned recipient.
  - Primary delivery via a dedicated, prominent card on the user's dashboard and group page.
  - Secondary delivery via transactional notification email and the digest email (note that `Profile.digest_frequency` defaults to `DIGEST_OFF`, so email cannot be the sole delivery mechanism).
  - A "Plan a gift for [Recipient]" button on the assignment card pre-fills the guided plan creation flow (`relation_guided_create`). The Santa usually has no `Person` record for the recipient, so the button selects an existing accessible record linked to the recipient's account when there is one, and otherwise pre-fills the recipient step's new-person sub-form (`recipient_mode=new`, `new_person-first_name`, `new_person-family_name`).

## Out Of Scope

- Automatically creating `Relation` rows upon draw (a `Relation` requires an accessible `Person` record and a `Gift` foreign key, which does not exist until the Santa chooses an item).
- Anonymous bi-directional chat ("Santa Mail" / "Mystery Q&A"): requires a messaging subsystem that does not exist in the app; deferred to a future phase.
- Offline participants without user accounts: draws require an authenticated user to receive the secret assignment.
- Physical gift swapping games (White Elephant / Yankee Swap stealing rules).

## Implementation Notes For AI Agent

- Data model:
  - `SecretSantaExchange`: linked to a `PersonGroup` and an optional `Event`, with fields `exchange_date`, `guidelines`, `budget`, `status` [Draft, Drawn, Completed], `organizer` FK, and optional `previous_exchange` FK (for repeat exclusions).
  - `SecretSantaAssignment`: linked to `exchange`, `giver` (User), `recipient` (User/Person), and optional `relation` FK (`Relation`, linked later once the user plans a gift).
  - `ExclusionRule`: linked to `exchange`, `user_a`, `user_b`.
- Wishlist access:
  - Extend `WishQuerySet` with `visible_to_secret_santa(giver, exchange)`: returns active, unarchived, non-deleted wishes of the recipient assigned to `giver` in `exchange`, even if `giver` and `recipient` are not direct friends.
  - Expose the recipient's self-written profile fields through the same assignment check, not through friendship.
  - The grant is read-only in the first slice: claiming still goes through `WishClaimToggleView`, which requires friendship (see Open Questions).
- Draw Algorithm:
  - Implement a backtracking solver in a service module (`gift_manager/secret_santa.py`).
  - Generate a derangement matching exclusion rules.
  - Check for impossible constraints and return a user-friendly error before attempting the draw.
- Privacy & Permissions:
  - Decision: the organizer cannot view the assignments, whether or not they participate (standard Secret Santa etiquette). A participant who lost track of their recipient sees it again on their own dashboard card, so the organizer never needs to reveal pairings.
  - Ensure assignment queries are strictly scoped: `SecretSantaAssignment.objects.filter(giver=request.user)`.
- UI & Integration:
  - Add an "Exchange" card to the dashboard and group detail page.
  - The assignment card displays recipient details, a link to view their wishlist, and a "Plan Gift" button that routes to `relation_guided_create`.

Recommended starting context:

- `docs/ai/architecture.md`
- `gift_manager/models.py`
- `gift_manager/views/relation_guided.py`
- `gift_manager/views/person_group.py`
- `gift_manager/guided_plan.py`

## Acceptance Criteria

- An organizer can create a Secret Santa exchange for a group, specify a budget, and configure pairing exclusions (manual or imported from a past exchange).
- The draw algorithm successfully pairs all participants without violating exclusion rules, self-pairing, or unwanted 2-cycles.
- If exclusions make a valid draw impossible, a clear validation message is shown without corrupting data.
- Once drawn, each participant can view only their own assigned recipient, along with that recipient's active wishlist and self-written profile via the exchange grant, even when they are not friends.
- The organizer cannot view other participants' assignments.
- Assignments are immediately surfaced via dashboard cards.
- The assignment card includes an action to start planning a gift via `relation_guided_create`.
- Comprehensive unit tests verify the pairing algorithm, exclusion rules, impossible-constraint handling, and privacy isolation.

## Dependencies Or Related Ideas

- Builds on `0028` (Wishlists And Collaborative Gift Giving).
- Uses `0016` (Guided Gift Plan Creation).
- Scoped out of `0028` originally as a potential future idea.

## Open Questions

- What should happen if a participant leaves the group or exchange after the draw has taken place: should the organizer trigger a complete redraw, or should an unassigned swap mechanism be provided?
- Should the exchange grant also allow the Santa to claim the recipient's wishes? Claiming currently requires friendship (`WishClaimToggleView`); a claim by a non-friend would also need a release rule when the exchange ends.
- When the Santa creates a new `Person` for their recipient from the assignment card, should that record be linked to the recipient's account (`Person.account`), given that account links are normally made between friends?
