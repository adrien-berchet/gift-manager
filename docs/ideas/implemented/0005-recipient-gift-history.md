# Idea: Recipient Gift History And Repeat-Gift Warning

## Status

Implemented

## Summary

Show, on a person or group detail page, a timeline of the gifts given to that
recipient (year, event, status, reaction rating). When creating or editing a
gift plan, warn if the chosen gift was already given or planned for the same
recipient.

## Motivation

The person detail page only shows a count of gift plans. Reaction ratings and
notes are already captured on given or abandoned plans, but they are only
visible plan by plan. Users cannot answer "what did I give Anna last
Christmas, and did she like it?" without scanning the plan list.

## User Value

- Avoid repeating a gift.
- Learn what was well received at a glance.
- Context while choosing a new gift.

## Possible Scope

- "Gift history" section on person and group detail, grouped by year, lazy
  loaded via HTMX.
- Reaction rating and note shown per entry, reusing the existing rating
  partials.
- Non-blocking warning in the gift plan form when the same gift already exists
  for the recipient (given, purchased or planned).

## Out Of Scope

- Recommendations (see `0001`).
- Editing history inline beyond existing quick actions.
- Changing permission rules.

## Implementation Notes

Implemented: the history lists only given plans, grouped by year, newest first. It includes plans reaching a person through their groups (labelled with the group when visible) and, on a group page, plans targeting the group directly. To show each plan once, the detail panels list only plans in progress, put abandoned plans in a collapsed "Abandoned ideas" section and load the history lazily. The duplicate warning is a live HTMX hint (`/relations/repeat-gift-hint/`) that ignores abandoned plans.
