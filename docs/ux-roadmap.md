# Gift Manager UX Roadmap

This document tracks UX and product-model ideas for the `ux_improvements`
branch. The branch is intentionally unstable, so items here may involve breaking
changes once the target workflow is clearer.

## Guiding Principles

- Make the basic gift-planning workflow obvious: who, what, when, and status.
- Keep advanced capabilities available without making them the first thing users
  must understand.
- Prefer user-facing language over implementation vocabulary.
- Stabilize the current UX infrastructure before layering on more interaction
  patterns.

## Decisions So Far

- Use `Gift Plan` as the user-facing name for the central planning object.
- Keep groups visible in the product because a gift plan can directly target a
  group.
- Explore a unified `Recipients` experience for people and groups, while keeping
  the existing `Person` and `PersonGroup` models until the migration path is
  justified.
- Defer guided creation, advanced list workflows, and sharing redesign until the
  primary model and workflow are stable.
- Stabilization is the first implementation priority.

## Execution Plan

### Phase 0 - Stabilize The Current Branch

Goal: make the current `ux_improvements` branch reliable enough to build on.

Tasks:

- [x] Fix malformed branch-only frontend code.
      - `gift_manager/templates/gift_manager/includes/gift_form_partial.html`
      - `gift_manager/templates/gift_manager/person_group_list.html`
      - `gift_manager/static/gift_manager/css/mobile-responsive.css`
- [x] Remove broad debug logging from production-facing templates and scripts.
- [x] Confirm key pages render without template, JavaScript, or CSS syntax
      errors.
- [x] Keep a short stabilization note for any intentionally breaking changes.

Acceptance checks:

- [x] `rtk python manage.py check` passes.
- [x] Targeted template/list/form tests pass where available.
- [ ] A smoke pass of dashboard, gift list, gift-plan list, people/groups, and
      form open/save flows has no obvious console or rendering errors.

Phase 0 stabilization notes:

- Removed the hidden `DEBUG_FORCE_OFFLINE` localStorage override from offline
  helpers. Offline behavior now relies on browser and network connectivity
  checks.
- Gift sharing controls now use the existing HTMX permission-update form pattern.
- Person-group bulk checkboxes now submit `group_id` values, and inline editing
  targets the visible group-name cell.

### Phase 1 - Product Language: Gift Plans

Goal: remove implementation vocabulary from the main user journey.

Tasks:

- [x] Replace user-facing `Relation`, `Relations`, and ambiguous `Gifting`
      labels with `Gift Plan` or `Gift Plans`.
- [x] Keep internal model names unchanged unless a later migration is explicitly
      planned.
- [x] Update navigation, page titles, buttons, empty states, grid labels,
      validation text, translations, and tests.
- [x] Document any remaining developer-only uses of `Relation` so they are not
      mistaken for missed UX work.
- [ ] Later migration-aware cleanup: decide whether Django model/admin metadata
      should also move from `Relation` / `Relation Status` to `Gift Plan` /
      `Gift Plan Status`.

Acceptance checks:

- [x] A user can create, view, edit, and delete a gift plan without seeing the
      `Relation` model name.
- [x] URLs and internals can remain stable, but visible copy uses the new
      language consistently.

### Phase 2 - Recipient UX Foundation

Goal: make people and groups feel like one recipient hierarchy without forcing a
database redesign yet.

Tasks:

- [x] Introduce a `Recipients` navigation item or landing page that can show
      people and groups together.
- [x] Keep group management accessible because users can create gift plans for
      groups directly.
- [x] Add a typed recipient display/picker concept, such as `person:<id>` and
      `group:<id>`, mapped back to the current fields.
- [x] Add display helpers for gift plans, for example recipient name, recipient
      type, and recipient URL.
- [x] Make group-targeted plans explicit in copy, distinguishing "for this
      group" from "for every member of this group."

Acceptance checks:

- [x] The gift-plan form can target either a person or a group from one
      recipient-oriented control.
- [x] Existing group hierarchy, membership, and permission behavior still works.
- [x] The UI no longer makes users learn the model split before they can plan a
      gift.

Phase 2 implementation notes:

- Added a `Recipients` page and navigation entry while keeping the existing
  groups page for hierarchy management.
- Added typed recipient choices (`person:<id>` and `group:<id>`) to the gift-plan
  forms, mapped back to the existing `Relation.person` and `Relation.group`
  fields.
- Added gift-plan recipient helpers for display name, type, key, URL, and direct
  group targeting.
- Kept the database model unchanged. A future model-level recipient migration is
  still a separate product and data-migration decision.

### Phase 3 - Unified Form System

Goal: make basic creation and editing easy, consistent, and progressively
enhanced.

Tasks:

- [x] Replace `form.as_p` full-page forms with shared field/section/action
      patterns used by offcanvas forms.
- [x] Standardize validation, help text, required markers, sharing sections, and
      save/cancel/delete action placement.
- [x] Preserve non-JavaScript fallbacks for core create/edit workflows where
      practical.
- [x] Keep advanced fields accessible but visually secondary.

Acceptance checks:

- [x] Full-page and offcanvas forms expose the same fields and validation
      behavior.
- [x] Forms are usable on mobile and keyboard-only navigation.
- [x] Error states are visible, localizable, and do not shift the layout
      unexpectedly.

Phase 3 implementation notes:

- Added shared form includes for field rendering, error summaries, actions,
  entity-specific field groups, and sharing controls.
- Full-page create/edit templates and HTMX offcanvas partials now render the
  same field groups instead of diverging through `form.as_p` and duplicated
  markup.
- Edit-time sharing now has a non-JavaScript fallback: permission selectors are
  submitted with the main form through `permission_<user_id>` fields.
- Removed nested sharing forms from offcanvas form partials.
- Moved searchable multi-select controls and event date-type toggling into the
  shared form initializer.
- Fixed stale query optimization relation names that prevented some edit forms
  from loading reliably.

### Phase 4 - Gift Plan Workspace

Goal: make the mockup direction real: a clear workspace centered on planning,
status, urgency, and quick details.

Tasks:

- [x] Build a primary gift-plan card/detail experience.
- [x] Keep Grid.js list mode for scanning, sorting, filtering, and power-user
      workflows.
- [x] Standardize status badges, urgency groups, due dates, recipients, gifts,
      occasions, tags, and notes across cards, details, and grids.
- [x] Add a quick detail/edit panel where it improves the workflow without
      hiding the full edit page.

Acceptance checks:

- [x] From the gift-plan workspace, a user can identify what needs attention and
      update the plan with minimal navigation.
- [x] Advanced list tools remain available without dominating the default view.

Phase 4 implementation notes:

- Added a primary gift-plan workspace on the Gift Plans page with cards grouped
  by overdue, due soon, later, no due date, and completed.
- Kept the existing Grid.js list, filters, selection, inline editing, sorting,
  and pagination available in an advanced list section.
- Added shared visual classes for gift-plan status, due-date urgency, and gift
  tags, then reused them in cards, the full detail page, the quick detail panel,
  and the grid status control.
- Card detail and edit actions are normal links enhanced by the existing
  `data-action` offcanvas/modal behavior, preserving full-page fallbacks.
- Tightened the existing grid status update endpoint so viewers cannot change a
  gift plan status.

### Phase 5 - Action-Oriented Dashboard

Goal: make the dashboard useful every time a user opens the app.

Tasks:

- [x] Prioritize upcoming, overdue, stale, and incomplete gift plans over raw
      entity counts.
- [x] Surface gifts without recipients and recipients with upcoming occasions.
- [x] Add clear empty states that lead to the next useful action.
- [x] Keep summary counts as secondary navigation aids.

Acceptance checks:

- [x] The dashboard answers "what should I do next?" within the first viewport.
- [x] New users and returning users both get useful guidance without reading
      instructions.

Phase 5 implementation notes:

- Reworked the authenticated dashboard so the first viewport starts with next
  actions and compact attention counts instead of the large welcome hero and raw
  entity totals.
- Added server-rendered action buckets for overdue, due soon, incomplete, and
  stale gift plans. Completed gift plans are excluded from the attention flow.
- Added support sections for accessible gift ideas without a gift plan and
  recipients attached to gift plans with upcoming occasions.
- Kept library counts and quick-create links as secondary navigation below the
  action dashboard.
- Used normal links enhanced by existing create/detail offcanvas behavior, so
  the dashboard remains progressively enhanced.

### Phase 6 - Deferred Advanced Workflows

Goal: preserve good ideas without blocking the core UX.

Tasks:

- [x] Design guided gift-plan creation after the core form and recipient model
      language are stable.
- [x] Move advanced filters, bulk actions, inline editing, and saved views behind
      explicit advanced controls.
- [x] Redesign sharing around clear per-object permissions and later bulk
      workflows.

Acceptance checks:

- [x] Advanced workflows improve speed for experienced users without making the
      basic workflow harder.
- [x] No sharing workflow changes ship until they are validated against existing
      permission behavior.

Phase 6 implementation notes:

- Added a shared advanced list disclosure for filters, selection, bulk actions,
  inline editing, and view controls.
- Updated Gift, Person, Event, Group, Gift Plan, and Status list pages so create,
  detail, and edit actions stay visible while advanced list tools are opt-in.
- Added a shared Grid.js advanced-control gate so bulk operations, inline
  editing, dynamic filters, and real-time search initialize only after users open
  the advanced tools.
- Kept guided gift-plan creation and sharing redesign documented as deferred
  workflows. Sharing needs a dedicated permission validation pass before any bulk
  workflow expands.
- No new sharing behavior ships in this phase; permission validation is an
  explicit pre-rollout gate for the deferred sharing workflow.

## Do Not Forget Checklist

- [ ] Translation coverage for all user-facing copy, including JavaScript-created
      labels.
- [ ] Mobile layouts for dashboard, gift-plan workspace, recipient pages, and
      forms.
- [ ] Keyboard navigation and visible focus states for cards, dialogs, filters,
      and action bars.
- [ ] Empty, loading, error, and permission-denied states.
- [ ] Progressive enhancement for HTMX/offcanvas flows.
- [ ] Permission and sharing regression checks, especially for group recipients.
- [ ] Tests close to the changed surface before broad test runs.
- [ ] Documentation updates when user-facing names or workflows change.

## Reference Notes

### Product Language

The current user-facing model mixes implementation terms such as `Relation` with
newer labels such as `Gifting`. The chosen user-facing name is `Gift Plan`.

Names considered:

- Gift Plan
- Gift Idea
- Gift Assignment
- Gift Match
- Gift Intention
- Gift Task
- Gifting
- Present Plan

`Gift Plan` is the clearest choice because it naturally supports a gift,
recipient, occasion, due date, status, notes, and sharing.

### Recipient Model Exploration

The current UI splits people and groups, but the product concept is closer to a
recipient hierarchy:

- A person is a leaf recipient.
- A group is a parent recipient.
- A gift plan can target either level.

Explore whether to introduce a user-facing `Recipient` concept while preserving
the existing database model until the migration path is clear.

Questions to answer:

- Should people and groups remain separate database models with a unified
  recipient UI, or become one polymorphic/self-referential model?
- How should direct group gift plans and inherited/member gift plans be shown?
- What labels distinguish a person from a group without exposing model names?
- How should sharing, permissions, and hierarchy inheritance work under the
  unified recipient concept?

### Dashboard

Redesign the dashboard around useful next actions instead of entity counts.

Candidate sections:

- Upcoming gift plans
- Overdue or stale gift plans
- Gift plans without ideas
- Gifts not assigned to anyone
- People or groups with upcoming occasions
- Recently changed items

Counts can remain, but should be secondary navigation aids rather than the
primary content.

### List And Detail Experience

1. Make detail/card views the primary user experience for gift planning.
2. Keep Grid.js list mode for scanning and power-user workflows.
3. Prefer cards that show: gift, recipient, occasion, due date, status, tags,
   and notes.
4. Standardize status colors and badges across dashboard, cards, details, and
   grids.

### Deferred Workflow Ideas

These are intentionally deferred until the model and primary user workflow are
more stable.

#### Guided Gift Plan Creation

Create a guided flow for basic users:

1. Choose recipient.
2. Choose or create gift.
3. Choose occasion.
4. Set due date and status.
5. Add notes or sharing only when needed.

Advanced users should still be able to access the complete form directly.

#### Progressive Disclosure For Power Tools

Move advanced list controls behind explicit actions:

- Multi-select and bulk actions behind `Select`.
- Complex filters and multi-sort behind `Advanced filters`.
- Inline editing behind a clear edit mode or discoverable affordance.
- Saved view preferences in profile/settings.

#### Sharing Redesign

Replace scattered sharing controls with:

- A simple per-object sharing panel.
- Plain permission labels: can view, can edit, can manage sharing.
- A separate advanced bulk-sharing workflow for power users.

Before implementation, validate the permission boundary:

- Posted friend IDs must resolve to confirmed friends of the current user.
- Every selected object must pass a centralized can-share check through
  `PermissionService` or a dedicated sharing service.
- Viewer-only users and inaccessible object IDs must not be shareable even if
  posted manually.
- Bulk sharing should follow the same object narrowing pattern as bulk delete.

### Interface Concept

Draft a gift-plan-centered interface with:

- Calm left navigation: Dashboard, Gift Plans, Recipients, Gifts.
- A dashboard focused on next actions.
- Main gift-plan cards grouped by urgency or occasion.
- A right-side details panel for quick edits.
- Advanced filtering hidden behind a compact control.


====================================================================================


I think we need to improve the workflow, especially when we want to create a new gift and a new plan in one workflow. How could we make it easier for the user?


Yes. The current model already has the pieces, but the UX forces users through two separate mental steps: create gift, then create plan for gift.
I’d improve it in this order:
Best quick win: add “Save and create plan” to New Gift
When creating a gift, the form should offer:
Save
Save and create gift plan
After saving, the offcanvas can immediately transition into the existing GiftRelationCreateView, with the new gift already selected. This fits the current architecture well.

Better long-term flow: create gift inline from New Gift Plan
In the New Gift Plan form, the Gift field should support:
choose an existing gift
or click/type Create new gift
Then it expands a small inline “New gift” block:
gift name
optional note
optional tags
Submitting creates both the Gift and the Relation in one transaction. This is the smoothest flow because the user’s intent is usually “I want to plan a gift,” not “I want to manage database objects.”

Keep the form lightweight
The combined flow should not become a giant form. I’d show:
Gift: existing/new
Recipient
Occasion/event
Due date
Status
Notes
Tags and detailed gift comments can stay optional/collapsed.

My recommendation: start with “Save and create gift plan” on the gift form because it is low-risk and uses the existing GiftRelationCreateView. Then, if it feels good, evolve New Gift Plan to support inline gift creation.
