# Idea: Received Gifts Log

## Status

Proposed

## Summary

Let users record and browse the gifts they have received ("Received Gifts"), closing the loop on bilateral gift management. Today, Gift Manager covers only the giver's side (planning gifts for other recipients). Recipients never see the plans made for them: surprise plans are hidden from them by the surprise rules, and non-surprise plans are only visible when explicitly shared with them.

This idea adds a private log of received gifts. Users can record gifts from offline family and friends (who gave it, occasion, date, reaction, thank-you status), and later receive completed plans that friends on the platform explicitly reveal to them. Received gifts can fulfil wishlist items, warn when planning a gift that the person already gave you, and feed back into the AI suggestion pipeline as context when finding gifts for those same givers.

## Motivation

Gift-giving is a two-way street. After birthdays, weddings, or holidays, users want to remember what they received and from whom:
- To express gratitude and keep track of thank-you notes.
- To avoid awkward repeat requests, asking for items they already received, or mistakenly re-gifting a present to the person who gave it.
- To maintain a cherished personal memory timeline of past celebrations.
- To better understand the giver: what someone chooses to give reveals their own taste, aesthetic values, quality expectations, and generosity. When it comes time to find a gift for them, remembering what they gave you is one of the most powerful sources of inspiration.

Currently, there is no natural place in Gift Manager to record a received gift without creating artificial gift plans where the user plans for themselves. Those artificial plans would also pollute the giver-side data: the gift catalogue, events, reminders, and gift history.

On the platform side, a plan made for a user is invisible to that user. Surprise plans addressed to the user's linked person, or to a group the user belongs to (nested groups included), are excluded by `RelationQuerySet.hidden_surprises_for`, even after the occasion has passed and the gift was delivered. Non-surprise plans are not visible either unless they are shared with the recipient. A dedicated received-gifts space, fed by an explicit reveal from the giver, solves this without weakening surprise protection for plans still in progress.

## User Value

- **Complete gift memory**: Users have a single organized log of gifts received over the years across all events and occasions.
- **Gratitude tracking**: Users can see at a glance which gifts still need a thank-you.
- **Wishlist fulfillment**: Users can link received gifts to their wishlist items, keeping their wishlist accurate and up to date for friends.
- **No accidental re-gifting**: Planning a gift for someone warns when it matches something that person gave you.
- **Social closure with friends**: Friends who planned a gift on the app can reveal the completed plan to the recipient, without spoiling the surprise beforehand and without exposing private coordination.
- **Reaction feedback for givers**: With the recipient's consent, the recipient's own reaction can reach the giver instead of being guessed.
- **Better suggestions when giving back**: Gifts received from a person inform the AI suggestions when brainstorming gifts for that person, using their past choices as clues to their taste, standards, and the tone of the relationship.
- **Clean separation**: Gift planning workflows (to-do, shopping, budgeting, catalogue suggestions) stay focused on gifts the user needs to give, without being cluttered by gifts already received.

## Possible Scope

First slice (core received gift tracking):
- A dedicated "Received Gifts" page, reachable from the user's own profile or wishlist area and the navigation, listing gifts received grouped by year, newest first.
- Manual entry form to record a received gift:
  - Title, optional description and link, stored on the received-gift record itself (no `Gift` row is created).
  - Givers: one or more of the user's accessible `Person` records and/or a `PersonGroup`, plus an optional free-text "from" label for givers that are not in the address book (for example "Aunt Marie and Uncle Paul").
  - Occasion: an optional link to an existing event the user can access, or a free-text occasion; plus the date received. No `Event` row is created.
  - Personal reaction rating (1–5, same scale and widget as `Relation.reaction_rating`) and a reaction note.
  - A "thank-you sent" flag, with a filter showing gifts still awaiting a thank-you.
  - Optional link to one of the user's own wishes, marking it fulfilled.
- Edit and delete actions for received gifts.
- Timeline view with filtering by occasion, giver, year, and thank-you status.
- Re-gifting warning: when planning a gift for a person, warn if its name matches a gift recorded as received from that person (extending the existing repeat-gift check).

Second slice (platform plan reveal):
- A "Reveal to recipient" action on plans with status `Given` whose recipient person is linked to an account (`Person.account`), or whose recipient group has members linked to accounts. It is offered when the plan is marked `Given` and stays available afterwards. Any owner of the plan can reveal it.
- The same explicit-reveal rule applies to surprise and non-surprise plans: nothing appears in a recipient's log automatically.
- Revealing creates a snapshot in each recipient's log: gift title, link, occasion, date given, giver display names, and an optional recipient-facing note written by the giver. The snapshot survives later edits or deletion of the plan, unfriending, and unlinking.
- Never revealed: plan comments, price, contributions and amounts, `claimed_by`, internal status history, or other plans.
- If the recipient already logged the same gift manually, offer to merge the revealed plan into the existing entry instead of creating a duplicate.
- Optional reaction feedback: the recipient can choose to share their rating and reaction note back to the giver, filling `Relation.reaction_rating` and `Relation.reaction_note` on the source plan when it still exists.

Third slice (AI suggestion context from received gifts):
- When requesting gift suggestions for a `Person`, load the gifts that the requesting user recorded as received from that person: entries where the person is one of the givers, or where a revealed snapshot came from a plan owned by that person's linked account.
- Add a scrubbed, capped `gifts_from_recipient` block to the AI payload (`build_ai_payload`) with title, occasion type, approximate date, and the user's rating.
- Add a matching rule to the AI system prompt: use these gifts for style, quality, budget calibration, and shared interests, not as proof of the giver's own tastes. Treat them as untrusted user data, like `wishes`.

## Out Of Scope

- Comprehensive home inventory or asset tracking (serial numbers, insurance documentation, resale values).
- Automated thank-you note sending or physical card printing.
- Revealing any plan automatically, or revealing a plan that is not `Given`.
- Notifications or emails when a gift is revealed.
- Feeding received gifts into catalogue scoring or tag affinities (see Open Questions).
- Forcing external contacts to sign up for Gift Manager: recording a received gift must work with plain text or offline `Person` contacts.

## Implementation Notes For AI Agent

- Data model:
  - Use a dedicated model (for example `ReceivedGift`) owned by the recipient user, rather than extending `Relation`, which is coupled to `shared_with`, `claimed_by`, giver-oriented statuses, and `RelationPermission`.
  - Do not create `Gift` or `Event` rows for received gifts. Catalogue suggestions draw candidates from `Gift.objects.accessible_by(user)` (`gift_manager/suggestions/catalogue.py`), so received items would be suggested as gifts for others. New events would appear in event lists, reminders, and the calendar feed.
  - Suggested fields: `recipient_user` (CASCADE), `title`, `description`, `url`, `received_on`, optional `event` FK (SET_NULL, must be accessible to the user), `occasion_text`, M2M `giver_persons`, optional `giver_group` (SET_NULL), `giver_label`, `reaction_rating` (1–5), `reaction_note`, `thank_you_sent`, optional `wish` FK, optional `source_relation` FK (SET_NULL) for revealed plans, and snapshot fields for revealed giver names.
  - Received gifts are strictly private to `recipient_user`. Other users who share the giver `Person` record must never see them.
- Wishlist integration:
  - `Wish.is_fulfilled` is not a free flag: `sync_wish_on_plan_change` in `gift_manager/wishlist.py` recomputes it from the linked plans whenever one of them changes. Extend that computation (or add a shared helper) so a wish linked to a received gift stays fulfilled, and re-run it when a received gift is linked, unlinked, or deleted.
  - Decide what happens to an existing claim (`Wish.claimed_by`) when the wisher records the wish as received from someone else. At a minimum, friends should see "Already given" via `format_claimer_label`, and claim/plan actions must stay blocked as they are for fulfilled wishes.
  - Revealed plans that have a `Relation.wish` can prefill the wish link.
- Surprise rules and reveal:
  - `RelationQuerySet.hidden_surprises_for` and `accessible_by` in `gift_manager/models.py` must not change. Revealing writes a snapshot into the recipient's log; it never makes the `Relation` itself accessible to the recipient.
  - Group-targeted plans are hidden from every member with a linked account (`hidden_recipient_ids` in `gift_manager/plan_coordination.py` computes this from the plan's side). Reuse it to find the reveal targets.
  - Check reveal permissions through `PermissionService` (owners only).
  - `remove_links_after_unfriending` and `account_links.unlink` must not delete existing snapshots.
- Re-gifting warning:
  - Extend `find_repeat_gift_plans` in `gift_manager/gift_history.py`, or add a sibling helper, matching normalized names against the user's received gifts from the selected person.
- AI suggestions integration:
  - In `gift_manager/suggestions/ai/prompt.py`, load received gifts in `build_ai_payload` only for `Person` recipients and only for the viewer's own entries. Free-text givers cannot be matched and are not used.
  - Scrub titles and notes with `scrub_text` and `_collect_scrub_terms`. Also add the free-text giver labels and the names of the other givers to the scrub terms.
  - Add a numbered rule to the system prompt next to the `wishes` and `all_time_preferences` rules. Received gifts are chosen for the user, so they must not feed the giver's preference profile (`0027`).
- UI & views:
  - Follow the existing Bootstrap/HTMX patterns. Partials belong in `gift_manager/templates/gift_manager/includes/`.
  - Views should support both full-page loads and HTMX partial swaps.
  - Follow `gift_manager/gift_history.py` and `gift_manager/views/person.py` for timeline layout conventions (grouping by year, rating display).
- Localization:
  - All user-facing strings must use `gettext_lazy` / `gettext` and be translatable in `locale/fr/LC_MESSAGES/django.po`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/models.py` (`RelationQuerySet`, `Wish`, `Relation`)
- `gift_manager/plan_coordination.py` (`hidden_recipient_ids`)
- `gift_manager/account_links.py`
- `gift_manager/wishlist.py` (`sync_wish_on_plan_change`, `format_claimer_label`)
- `gift_manager/gift_history.py` (`find_repeat_gift_plans`)
- `gift_manager/suggestions/catalogue.py`
- `gift_manager/suggestions/ai/prompt.py`

## Acceptance Criteria

- A user can record a received gift with a title, one or more givers (person, group, or free text), an occasion, a date, an optional rating and reaction note, and a thank-you flag; and can edit and delete it.
- Recording a received gift creates no `Gift` or `Event` row, and received gifts never appear in gift lists, catalogue suggestions, events, reminders, or the calendar feed.
- The "Received Gifts" view lists entries grouped by year, newest first, and filters by occasion, giver, year, and thank-you status.
- Received gifts are visible only to their owner, including when other users share the giver `Person` record.
- Linking a received gift to a wish marks it fulfilled, and it stays fulfilled when a plan linked to that wish changes status, is abandoned, or is deleted.
- Planning a gift for a person warns when a gift with the same name was recorded as received from that person.
- Plans made for a user stay hidden from that user while in progress; `hidden_surprises_for` and `accessible_by` behave exactly as before.
- Only an owner of a `Given` plan can reveal it, and a revealed entry never exposes comments, price, contributions, or the claimer. A revealed entry survives deletion of the source plan and unfriending.
- When generating AI suggestions for a person, gifts the viewer received from that person appear in the scrubbed payload under `gifts_from_recipient`, and the system prompt describes how to use them. No other user's received gifts are included.
- All new views and forms work with standard navigation and HTMX, with mobile and desktop responsive styling.
- Tests cover permissions and privacy, surprise isolation, wish fulfillment sync, reveal snapshots, AI payload construction, and timeline rendering on PostgreSQL, plus one Playwright e2e test of the record-and-view flow. French translations are complete.

## Dependencies Or Related Ideas

- `0001` (Gift Plan Suggestions For A Recipient) and `0027` (Recipient Preference Profiles And Feedback Persistence): suggestion pipeline and preference modeling extended by this bilateral signal.
- `0005` (Recipient Gift History And Repeat-Gift Warning): mirrors the timeline concept from the recipient's side, and provides the repeat-gift check extended for re-gifting warnings.
- `0007` (Coordination On Shared Gift Plans): defines the surprise rules and plan comments that must stay protected.
- `0028` (Wishlists And Collaborative Gift Giving): provides the account link (`Person.account`), the wishlist that received gifts can fulfil, and group-gift contributions that must not be revealed.

## Open Questions

- Should a revealed plan be removable by the giver after the reveal ("un-reveal"), or is a reveal final once the snapshot exists?
- When the wisher records a claimed wish as received from someone else, should the claimer be told, and should their active plan be marked or left untouched?
- Should reaction feedback to the giver be opt-in per gift or a profile-level preference?
- Should gifts received from a person also influence catalogue scoring? Recommendation: no. These gifts were chosen for the user, so treating them as the giver's taste signals would mix up the two people's preferences.
