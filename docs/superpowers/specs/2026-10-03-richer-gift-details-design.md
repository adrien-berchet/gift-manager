# Richer Gift Details (Link, Price, Budgets) - Design

Implements slice 1 of `docs/ideas/0004-richer-gift-details.md`. Images are deferred.

## Goals

- Users can attach an optional link and price to a gift and to a gift plan
  (`Relation`).
- A plan's link/price override the gift's, the same way a plan has its own comment.
- Per-person and per-event budget totals are visible.

## Decisions (agreed with the user)

| Topic | Decision |
|---|---|
| Plan-specific data | `Gift` holds default `url`/`price`; `Relation` holds optional overrides. Effective value = plan value if set, else gift value. |
| Currency | One per-user currency on `Profile` (default EUR). Prices are plain decimals; no conversion. |
| Images | Deferred to a later slice (S3 storage, validation, thumbnails). |

## Non-goals

Scraping, price tracking, payments/affiliates, multi-currency conversion, images.

## Data model (single migration)

- `Gift.url`: `URLField(max_length=2000, blank=True, default="")`, http/https validator.
- `Gift.price`: `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`,
  check constraint `price IS NULL OR price >= 0`.
- `Relation.url`, `Relation.price`: same definitions and constraint (named distinctly).
- `Profile.currency`: `CharField(max_length=3, choices=CURRENCY_CHOICES, default="EUR")`
  with EUR, USD, GBP, CHF, CAD.
- `Relation.effective_url` / `Relation.effective_price` properties fall back to the gift.
  Nothing is copied, so editing a gift updates every plan that does not override it.

## Validation and security

- Shared validator `validate_http_url` (scheme must be `http` or `https`), used by both
  forms and as a model field validator. `javascript:`, `data:` and similar are rejected.
- Links render with `target="_blank" rel="noopener noreferrer nofollow"` and always
  go through Django autoescaping. Grid.js cells keep escaping (extend
  `gift_manager/tests/test_grid_xss_safety.py`).
- Empty URL/price is stored as `""` / `NULL`; clearing a plan override reverts to the gift value.
- Fix the dead `price` branch of `DeleteConfirmationMixin.get_entity_details`
  (`gift_manager/views/base.py`): show the formatted price with the user's currency,
  translated, instead of the hard-coded `$`.

## Budgets

- New service in `gift_manager/services.py` (`BudgetService`) summing effective prices of
  plans for a person or an event, restricted to `Relation.objects.accessible_by(user)`
  so users never see totals for plans they cannot view.
- Status grouping uses `gift_manager/statuses.py` (add `is_purchased_status`):
  - **Planned total**: every plan except Abandoned.
  - **Spent total**: plans in Purchased or Given.
- Plans without an effective price are ignored in sums and counted as "N without price".
- Computed in the database (`Coalesce(relation.price, gift.price)` + `Sum`), no N+1.
- Group recipients are out of scope for per-person totals (only plans with `person`).
- Displayed on person detail (`PersonDetailView`) and event detail (`EventDetailView`).

## UI

- Gift form (`includes/forms/gift_fields.html`) and plan form: add url and price fields
  inside a collapsed section (Bootstrap collapse, "Link and price"). The section is
  collapsed by default, but opens automatically when a field holds a value or has a
  validation error, and works without JavaScript (e.g. `<details>` fallback).
  The plan form shows the gift's values as placeholders.
- Gift detail, plan card and plan detail show the link and price only when set; nothing
  when empty (`includes/gift_detail_partial.html`, `includes/gift_plan_card.html`,
  `includes/relation_detail_partial.html`).
- Profile settings gets the currency selector.
- Price formatting uses Django `formats`/locale and the profile currency.
- New user-facing strings are added to the FR catalogue (`makemessages`/`compilemessages`).

## Testing

- Model: effective value fallback, negative price rejected, migration applies cleanly.
- Forms: http/https accepted; `javascript:`/`ftp:` rejected; clear URL/price; plan override and revert.
- Budgets: sums match effective prices; unpriced plans ignored and counted; abandoned excluded
  from planned; spent only Purchased/Given; owner, editor, viewer and no-access visibility.
- Templates: nothing rendered when empty; link has `rel="noopener noreferrer nofollow"`.
- XSS: hostile name/URL/price strings stay escaped in cards and Grid.js output.
- One e2e check (Playwright, PostgreSQL) for link and price on the plan card.

## Rollout

Fields are all optional and the migration is additive and reversible, so no data backfill
is needed. Update `docs/ideas/0004-...` status to "Slice 1 implemented" when done.
