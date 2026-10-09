# Idea: Unify Card Appearance Across Pages

## Status

Proposed

## Summary

Make the card view of the advanced list pages (gifts, events, relations, and the
other Grid.js list pages) look like the cards used on the dashboard and the gift
plan page. Today the advanced pages restyle Grid.js table rows into cards, while
the dashboard and gift plan page use a dedicated gift plan card component, so the
same concept looks different depending on where the user is.

## Motivation

Two unrelated card implementations exist:

- Dashboard and gift plan pages render `includes/gift_plan_card.html` inside a
  `.gift-plan-card-grid`, styled in `css/gift-plan-workspace.css`.
- Advanced list pages switch a Grid.js table to `[data-view="card"]`, where each
  `.gridjs-tr` is restyled as a card in `theme.css` and `modern-ux.css`, with
  `data-label` attributes injected by `filter-panel.js`.

The result is two visual languages for "a card": different spacing, title and
badge treatment, action placement, and hover behavior. Users moving between the
dashboard and a list page have to relearn the layout.

## User Value

Users get a familiar, consistent card on every page: the same hierarchy of title,
metadata, badges, and actions, so information is found in the same place
everywhere. Maintainers get one card look to evolve instead of two.

## Possible Scope

- Define one shared card visual language (container, title, meta row, badges,
  actions, hover and focus states) based on the existing gift plan card.
- Restyle the card view of the gifts, events, relations, and other advanced list
  pages to use it, in light and dark themes and on mobile.
- Decide per entity which fields appear as title, meta, and badges, keeping the
  information the current card view already shows.
- Extract shared card styles (CSS custom properties or a common class) so both
  implementations draw from the same source.

## Out Of Scope

- Changing the list (table) view of the advanced pages.
- Redesigning the gift plan card itself beyond what is needed to share styles.
- Replacing Grid.js, or changing filtering, sorting, pagination, or bulk
  operations behavior.
- New card features such as new quick actions or fields.

## Implementation Notes For AI Agent

Relevant code, to be confirmed before editing:

- `gift_manager/templates/gift_manager/includes/gift_plan_card.html` and
  `gift_manager/static/gift_manager/css/gift-plan-workspace.css` (the reference
  card, used by `home.html` and `relation_list.html`).
- `gift_manager/static/gift_manager/theme.css` (`[data-view="card"]` rules, around
  the `.gridjs-tr`/`.gridjs-td` card styles) and `modern-ux.css`.
- `gift_manager/static/gift_manager/filter-panel.js` (view toggle, `addCardLabels`)
  and `templates/gift_manager/includes/filter_panel.html`.
- `gift_manager/static/gift_manager/grid-utils.js` (shared Grid.js helpers, row
  and column rendering, bulk-selection checkbox column).

Constraints: the card view is a CSS re-skin of Grid.js table rows, so a purely
visual unification may be done in CSS and column formatters. Rendering real
`gift_plan_card.html` markup inside Grid.js would be a larger change; choose the
approach during implementation. Preserve selection checkboxes, inline editing,
the persisted view preference, and the empty-state injection. Keep user-facing
strings translated.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- Relevant files under `gift_manager/`

## Acceptance Criteria

- Card view on the gifts, events, relations, and other advanced list pages shares
  the same container, typography, badge, and action styling as dashboard and gift
  plan cards, in light and dark themes.
- Cards remain usable on mobile widths, with no horizontal overflow.
- Sorting, filtering, pagination, bulk selection, inline editing, and the stored
  list/card preference behave as before.
- Existing tests pass, and an e2e or screenshot check covers card view on at least
  one advanced page next to the dashboard card.

## Dependencies Or Related Ideas

- Related to 0020 (Remove Redundant Toasts) only as general frontend polish; no
  dependency.

## Open Questions

- Should the advanced pages reuse the gift plan card markup, or only its styles?
- Which fields become the card title, meta, and badges for entities without a
  gift plan equivalent (people, groups, tags)?
- Should the list view also gain visual alignment, or stay as is?
