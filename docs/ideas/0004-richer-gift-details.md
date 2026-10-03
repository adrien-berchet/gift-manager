# Idea: Richer Gift Details (Link, Price, Image)

## Status

Slice 1 implemented (link, price, budgets); images deferred

Slice 1 decisions: a gift's link and price are defaults that a gift plan can override
(`Relation.url` / `Relation.price`); currency is a per-user preference
(`Profile.currency`); budgets are computed by `BudgetService` in `gift_manager/services.py`.
See `docs/superpowers/specs/2026-10-03-richer-gift-details-design.md`.

## Summary

Extend `Gift` with optional product details: a URL, an estimated price, and
optionally an image. Show them on gift and gift-plan cards, and allow a budget
per person or per event with a running total.

## Motivation

A `Gift` only has a name, a comment and tags, so users put links and prices
into free-text comments where they cannot be sorted, totalled or clicked. The
delete-confirmation helper already contains a `Price: $` branch
(`DeleteConfirmationMixin.get_entity_details` in `gift_manager/views/base.py`)
that never renders because no model has a `price` field.

## User Value

- One-click access to the place where the gift can be bought.
- Budgets become visible before overspending.
- Cards are easier to scan with a thumbnail.

## Possible Scope

- Optional `url` and `price` (decimal with currency) fields on `Gift`; image
  as a possible second slice.
- Display on gift detail, gift plan card and detail.
- Per-person and per-event totals of planned or purchased gifts.
- Remove or fix the dead `price` branch in the delete confirmation helper.

## Out Of Scope

- Scraping product pages or price tracking.
- Payment or affiliate integrations.
- Multi-currency conversion.

## Implementation Notes For AI Agent

- Model: `gift_manager/models.py` (`Gift`); forms: `gift_manager/forms.py`,
  `gift_manager/templates/gift_manager/includes/forms/gift_fields.html`.
- Display: `includes/gift_detail_partial.html`, `includes/gift_plan_card.html`,
  `includes/relation_detail_partial.html`.
- URL fields must be validated (http/https only) and rendered with
  `rel="noopener noreferrer"` to avoid unsafe links.
- Image uploads need a storage decision and size/type validation; consider
  deferring them.
- Grids render through Grid.js; keep output escaped (see
  `gift_manager/tests/test_grid_xss_safety.py`).

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`

## Acceptance Criteria

- Users can add, edit and clear a URL and a price on a gift.
- Non-http(s) URLs are rejected.
- Price and link appear on the gift detail and plan card when set, and nothing
  is shown when empty.
- Budget totals for a person or event match the sum of prices of the relevant
  plans and ignore gifts without price.
- Migration, form validation and XSS-safety tests pass.

## Dependencies Or Related Ideas

- Gift history (`0005`) can show prices of past gifts.

## Open Questions

- Single currency in settings, or per-gift currency?
- Is image upload worth the storage and privacy cost in the first slice?
