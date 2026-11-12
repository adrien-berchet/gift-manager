# Idea: Consistent Price Formatting

## Status

Proposed

## Summary

Format prices the same way everywhere, following the active language. Today
the gifts list shows "€24.50" while budgets, wishes and plan details show
"24.50 €" for the same English user.

## Motivation

Two formats for the same amount look like a bug and make prices harder to scan
and compare between pages.

## User Value

Users see one predictable price format in every list, card and detail view, in
both English and French.

## Possible Scope

- Pick one source of truth for the format: the server-side `format_price`
  filter, or a locale-aware formatter shared by server and client.
- Make the Grid.js gifts list use the same format as server-rendered pages.
- Check every place that displays a price: gifts list, gift and plan details,
  budgets, wishes, group-gift contributions.

## Out Of Scope

- Multi-currency support or currency conversion.
- Changing how prices are stored.

## Implementation Notes For AI Agent

Recommended starting context:

- `gift_manager/templatetags/custom_filters.py` — `format_price`, which
  renders `"<amount> <symbol>"`.
- `gift_manager/templates/gift_manager/gift_list.html` — the Grid.js price
  column formats with `Intl.NumberFormat(..., { style: 'currency' })`.
- Templates using `format_price`: `includes/link_price_display.html`,
  `includes/budget_summary.html`, `includes/wish_item_partial.html`,
  `includes/person_wish_item_partial.html`.
- `docs/ai/testing.md`

## Acceptance Criteria

- The same amount renders identically on the gifts list, gift detail, plan
  detail, budget summary and wish cards, in English and in French.
- Template filter tests and an e2e or contract test cover both languages.
- No price disappears or loses its currency symbol.

## Dependencies Or Related Ideas

- 0004 Richer Gift Details (Link, Price, Image).
- 0009 Close Translation And Locale Gaps.

## Open Questions

- Should English use the symbol before the amount ("€24.50") and French after
  it ("24,50 €"), following each locale's convention?
