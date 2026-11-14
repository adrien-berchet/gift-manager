# Idea: Filter Received Gifts By Free-Text Giver

## Status

Implemented

## Summary

Let the giver filter on the received gifts list match givers recorded as free
text ("Someone else", e.g. "Aunt Marie") and giver names kept from revealed
plans, not only people and groups from the address book.

## Motivation

The giver dropdown on `/profile/received-gifts/` lists only address-book
people and groups. Gifts whose giver was typed as free text, or whose revealed
givers did not match a contact, cannot be filtered by giver at all, so the
filter silently hides part of the log.

## User Value

Recipients can answer "what did Aunt Marie give me over the years?" even when
Aunt Marie is not in their address book, which helps with thank-you notes and
with avoiding repeat gifts.

## Possible Scope

- Add the distinct free-text giver labels of the user's received gifts to the
  giver dropdown, in their own option group.
- Or add a text search on giver names next to the dropdown, matching
  `giver_label` and `source_givers_text`.
- Keep the current `person:<uuid>` and `group:<uuid>` filter values working.

## Out Of Scope

- Merging free-text givers into address-book people automatically.
- Editing giver labels from the filter.

## Implementation Notes For AI Agent

Recommended starting context:

- `gift_manager/views/received_gift.py` — `_parse_giver_filter` and
  `ReceivedGiftListView.get`, which build the filter and the available givers.
- `gift_manager/templates/gift_manager/includes/received_gift_list_partial.html`
  — filter form markup.
- `gift_manager/models.py` — `ReceivedGift.giver_label` and
  `ReceivedGift.source_givers_text`.
- `gift_manager/tests/views/test_received_gift_views.py` — existing filter
  tests.

## Acceptance Criteria

- A gift recorded with a free-text giver can be found through the giver filter.
- Filtering by a person or group still returns the same results as before.
- Invalid filter values are ignored without an error.
- View tests cover free-text, person and group filtering.

## Dependencies Or Related Ideas

- 0030 Received Gifts Log.

## Open Questions

- Resolved: dropdown entries. Free-text givers get an "Other givers" section (whole label,
  case-insensitive) and friends named on revealed gifts a "Friends" section.
  `source_givers_text` is never matched: it names owners the recipient only sees as a count.
