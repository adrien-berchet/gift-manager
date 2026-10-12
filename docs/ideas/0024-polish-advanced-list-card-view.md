# Idea: Polish The Advanced List Card View

## Status

Proposed

## Summary

Make the card view of the gifts, events, and advanced relations (gift plans)
list pages nicer to read and more consistent with the dashboard. Each field row
in a card gets a dedicated icon next to its label, the action buttons use the
same icons, colors, and weight as the dashboard gift plan cards, and a few
smaller layout improvements make cards easier to scan.

Idea 0021 already aligned the card container, title typography, and spacing with
the dashboard. This idea covers what is still missing: the rows inside a card and
the action bar still look like a restyled table.

## Motivation

The card view is a CSS re-skin of Grid.js table rows. Today:

- Field rows show only an uppercase text label (from `data-label`, injected by
  `filter-panel.js`) and a value. There are no icons, while the dashboard card
  and the relation cards partial use one icon per piece of information
  (`fa-calendar-alt` for events, `fa-user` for recipients, `fa-tag` for tags,
  `fa-layer-group` for groups, `fa-comment` for comments, and so on).
- Action buttons come from `actionButtonsFormatter` in `grid-utils.js` and
  `permissionAwareActionFormatter` in `permission-utils.js`. They use solid,
  multi-colored buttons (`btn-info` details, `btn-warning` edit with `fa-edit`,
  `btn-danger` delete, `btn-success` share with `fa-share-alt`,
  `btn-secondary` duplicate). The dashboard card (`includes/gift_plan_card.html`)
  uses quiet `btn-outline-secondary` utility buttons with `fa-eye` and `fa-copy`,
  a single `btn-primary` edit button with `fa-pen`, and `fa-lock` when editing
  is not allowed. The same action therefore looks different depending on the page.
- Both formatters keep their own copy of the action config, so icons and colors
  can drift apart again.
- Action titles (`"Give"`, `"Details"`, `"Edit"`, ...) are hard-coded English
  strings in JavaScript, so the tooltips and the large-screen button text are not
  translated.

## User Value

Users recognize each field at a glance from its icon instead of reading every
label, find actions in the same place and style as on the dashboard, and see a
calmer card where the main action stands out and destructive actions do not
dominate. French users get translated action labels. Maintainers get one action
definition instead of two.

## Possible Scope

- Add a dedicated icon to each card field row on the gifts, events, and advanced
  relations pages, reusing the dashboard icon vocabulary where one exists, for
  example:
  - Gifts: comment `fa-comment`, link `fa-link`, price `fa-euro-sign` or
    `fa-coins`, tags `fa-tag`.
  - Events: comment `fa-comment`, schedule `fa-calendar-alt` (or `fa-cake-candles`
    for birthdays if the data allows it).
  - Relations: recipient or group `fa-user` / `fa-layer-group`, event
    `fa-calendar-alt`, comment `fa-comment`, status `fa-circle-half-stroke` or
    the existing status badge, due date `fa-clock`.
  - Card title: an entity icon (`fa-gift` for gifts and gift plans,
    `fa-calendar-day` for events) before the name.
  Icons should be declared per column (for example a column option read by the
  card-label code), not inferred from the translated label text.
- Align the action buttons with the dashboard card, in both card view and list
  (table) view: the same icons (`fa-eye` details, `fa-pen` edit, `fa-copy`
  duplicate, `fa-lock` for no edit permission), outline utility buttons with one
  primary action, and the same button size and spacing.
- Keep a short text label on the important buttons (at least the primary edit
  action, and give on gifts) where space allows; secondary utility buttons can
  be icon-only with a tooltip and accessible name.
- Move delete and share into a compact overflow menu (for example a Bootstrap
  dropdown behind an `fa-ellipsis` button), keeping them keyboard accessible and
  preserving the delete confirmation flow and permission-based hiding.
- Use a single shared action configuration for `grid-utils.js` and
  `permission-utils.js`.
- Translate action titles through the existing JavaScript i18n mechanism.
- Other polish suggestions to evaluate during implementation:
  - Hide rows whose value is empty instead of showing an empty labeled row, so
    cards stay compact.
  - Render the relation status as the same badge as on the dashboard card, and
    show the due date with overdue or soon styling.
  - Show tags as compact chips on one wrapping line, like dashboard cards.
  - Pin the action bar to the bottom of the card so actions line up across a row
    of cards with different heights.
  - Make the whole title clickable to open details, matching the dashboard card.
  - Keep the selection checkbox visually integrated in the card header instead of
    as a separate row.

## Out Of Scope

- List (table) view changes beyond the action buttons; columns and row layout
  stay as they are.
- People, groups, tags, and other advanced list pages; they can follow once the
  pattern exists.
- Replacing the Grid.js re-skin with server-rendered card markup.
- New actions, new fields, or changes to filtering, sorting, pagination, bulk
  operations, inline editing, or permissions.
- Redesigning the dashboard gift plan card itself.

## Implementation Notes For AI Agent

Relevant code, confirmed when this idea was written:

- `gift_manager/templates/gift_manager/includes/gift_plan_card.html`: reference
  icons and action buttons (`gift-plan-card-utility-action`), styled in
  `gift_manager/static/gift_manager/css/gift-plan-workspace.css`.
- `gift_manager/templates/gift_manager/includes/relation_cards_partial.html`:
  another card with per-field icons worth reusing.
- `gift_manager/static/gift_manager/grid-utils.js`: `actionButtonsFormatter`
  and its `actionConfig` (no `duplicate` entry).
- `gift_manager/static/gift_manager/permission-utils.js`:
  `permissionAwareActionFormatter` with a second `actionConfig`, used by the
  relation list for `details`, `edit`, `duplicate`, `delete`, `share`.
- `gift_manager/static/gift_manager/filter-panel.js`: `addCardLabels` and
  `addCardLabelsImmediate`, which copy header text into `data-label`; a natural
  place to also set a per-cell icon attribute or class.
- `gift_manager/static/gift_manager/theme.css`: `[data-view="card"]` rules
  (label `::before`, title first cell, comment clamping) and
  `modern-ux.css` for quick-action buttons.
- Page column definitions: `templates/gift_manager/gift_list.html`,
  `event_list.html`, and `relation_list.html`. Note that some relation columns
  (`Status Label`, `Row State`) are internal and must not get a visible row.

Constraints: card styles currently match some fields by label substring
(`[data-label*="omment"]`), which breaks across languages; prefer stable column
keys. Preserve tooltips, `data-action` attributes used by the offcanvas and
delete flows, permission-based hiding, the persisted list/card preference, and
the empty-state injection. Check light and dark themes and mobile widths.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/ideas/implemented/0021-unify-card-appearance.md`

## Acceptance Criteria

- In card view on the gifts, events, and advanced relations pages, every visible
  field row and the card title show a dedicated icon, and the same concept uses
  the same icon as on the dashboard card.
- In both card view and list view, details, edit, and duplicate buttons use the
  same icons, button variants, and size as the dashboard gift plan card; edit is
  the only primary action and keeps a visible text label where space allows, and
  users without edit permission see the locked state.
- Delete and share are reachable from an overflow menu in both views, operable
  by keyboard, hidden when the user lacks the permission, and delete still goes
  through the shared confirmation flow.
- Action icons and colors come from one shared configuration used by both
  `grid-utils.js` and `permission-utils.js`.
- Action tooltips and labels are translated in French.
- Icons are decorative (`aria-hidden="true"`) and buttons keep accessible names.
- Cards remain usable in light and dark themes and on mobile widths without
  horizontal overflow.
- Sorting, filtering, pagination, bulk selection, inline editing, offcanvas
  details/edit, delete confirmation, and the stored view preference behave as
  before.
- Existing tests pass, and an e2e or screenshot check covers the card view of at
  least one of the three pages, including the action bar.

## Dependencies Or Related Ideas

- Builds on 0021 (Unify Card Appearance Across Pages), which shared the card
  container and typography; this idea is self-contained otherwise.
- Related to 0009 (Close Translation And Locale Gaps) for the untranslated
  action titles.

## Open Questions

- Which buttons count as important enough to keep a text label (edit and give
  for sure; details?), and at which breakpoint does the text collapse to
  icon-only?
- Does the overflow dropdown render correctly inside Grid.js cells (clipping by
  `overflow` on the wrapper, z-index over neighboring cards and rows), or does
  it need `data-bs-boundary`/popper configuration or a body-attached menu?
- Should the dashboard gift plan card adopt the same overflow menu later, for
  symmetry?
