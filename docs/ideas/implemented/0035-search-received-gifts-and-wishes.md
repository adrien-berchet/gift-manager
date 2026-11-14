# Idea: Search Received Gifts And Wishes

## Status

Implemented

## Summary

Extend the global search (Ctrl+K) so it also returns the signed-in user's own
received gifts and wishlist items. Today, searching "QA Party" or the title of a
received gift returns nothing, although the gift is in the user's log.

## Motivation

The received gifts log and the wishlist are now first-class parts of the
profile, but they are the only user content the global search ignores. Users
who want to check "did someone already give me this?" or "is this on my
wishlist?" must open the right page and scroll or filter by hand.

## User Value

- Recipients find a past received gift by title, giver or occasion in one step.
- Users check quickly whether an item is already on their wishlist before
  adding a duplicate.

## Possible Scope

- Add a "received gift" result type matching title, description, occasion and
  free-text giver label, scoped with `ReceivedGift.objects.for_user(user)`.
- Add a "wish" result type matching title and notes, scoped to the user's own
  non-deleted wishes (`Wish.objects.for_wisher(user)`).
- Link each result to its existing detail or edit view.
- Keep the per-category limit used by the other result types.

## Out Of Scope

- Searching other users' wishes from the global search (friends' wishlists stay
  on the person detail page).
- Full-text ranking or fuzzy matching beyond what the existing search uses.

## Implementation Notes For AI Agent

Recommended starting context:

- `gift_manager/views/common.py` — `global_search`, which builds one result
  list per model with `accessible_by(user)` and `max_per_category`.
- `gift_manager/static/gift_manager/js/global-search.js` — result rendering,
  icons and type labels.
- `gift_manager/models.py` — `ReceivedGiftQuerySet.for_user` and the `Wish`
  queryset helpers.
- `gift_manager/urls.py` — `received_gift_detail` and `wish_edit` routes.
- `docs/ai/testing.md`

## Acceptance Criteria

- Searching the title of one of the user's received gifts returns it, with a
  link to its detail view.
- Searching the title of one of the user's wishes returns it.
- Another user's received gifts and wishes never appear in results (tested
  with two accounts).
- Existing result types and their order are unchanged.
- Unit tests cover matching, scoping and the result payload.

## Dependencies Or Related Ideas

- 0012 Global Search Improvements.
- 0030 Received Gifts Log and 0028 Wishlists And Collaborative Gift Giving.

## Open Questions

- Resolved: two separate result types, "Received Gifts" and "Wishlist", listed after the
  existing ones. Received gifts also match their event and address-book givers; givers kept
  from a revealed plan are not searched, because some of them are only shown as a count.
