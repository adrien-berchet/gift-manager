# Group Gifts And Contribution Tally Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Project C of `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md`: enable collaborators on a shared gift plan (`Relation`) to organize collaborative group gifts, divide costs (equal or custom split), track who has paid their share to the buyer, and maintain a per-plan balance tally, while enforcing strict universal privacy boundaries so the recipient never sees financial tallies or contributors for their own gift.

**Architecture:**
1. A new `RelationContribution` model stores financial contributions toward a gift plan (`Relation`), supporting both registered plan collaborators (`user`) and external individuals (`name`).
2. `Relation` gains `is_group_gift` and `split_mode` (`EQUAL` vs `CUSTOM`).
3. Core business logic lives in `gift_manager/group_gifts.py`:
   - Pure penny rounding algorithm with `divmod` integer cents, proven by Hypothesis tests.
   - Dynamic equal split derivation at read time; freezing share amounts upon payment (`paid_at`).
   - Buyer role dynamically derived from `relation.claimed_by`.
   - Centralized access guard `_require_group_gift_access` rejecting recipients with HTTP 403 `PermissionDenied` and leveraging `plan_coordination.require_level`.
4. Dedicated HTMX partial `relation_group_gift_partial.html` on `relation_detail` with progressive fallback.
5. Strict privacy: recipients never see group gift sections or tallies on any plan (surprise or non-surprise), and no contribution data appears in calendar feeds, email digests, or AI prompts.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Bootstrap 5, Hypothesis, pytest, tox, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-group-gifts-design.md`

## Global Constraints

- Code, docstrings, and comments in English. Every user-facing string is translatable with French translations in `locale/fr/LC_MESSAGES/django.po` compiled with `compilemessages`.
- Repository conventions: integer `id` primary key; `condition=` parameter in `CheckConstraint`; `gettext_lazy` for models/forms; `MinValueValidator(Decimal("0.00"))`.
- No new external production dependencies.
- Access governed by `_require_group_gift_access` (reusing `plan_coordination.require_level`): plan editors manage group gifts; editors and the buyer toggle payments; recipients are strictly barred.
- Actions work progressively with plain HTML/POST and HTMX partial swaps.
- Run tests on PostgreSQL (`tox run -e py311 -- <path>`); lint with `tox run -e lint`; browser tests with `tox run -e e2e -- <path>`.
- Commit messages follow Conventional Commits (`Feat: ...`, `Test: ...`, `Docs: ...`, sentence case, no trailing period).

---

## File Structure

- **Models & Migration:**
  - Modify `gift_manager/models.py`: add `SplitMode` choices, `Relation.is_group_gift`, `Relation.split_mode`, and `RelationContribution` model.
  - Create `gift_manager/migrations/0043_group_gifts.py`.
  - Modify `gift_manager/tests/factories.py`: `RelationContributionFactory`.
  - Create `gift_manager/tests/test_group_gift_models.py`.
- **Service Layer & Mathematics:**
  - Create `gift_manager/group_gifts.py`: calculation functions, access guard, summary dataclasses, and mutation operations with row locks.
  - Modify `gift_manager/plan_coordination.py`: expose public `require_level(relation, user, minimum)`.
  - Create `gift_manager/tests/test_group_gift_service.py`.
- **Privacy & Side Channels:**
  - Create `gift_manager/tests/views/test_group_gift_privacy.py`.
- **Forms & Views:**
  - Modify `gift_manager/forms.py`: `GroupGiftContributorForm`, `GroupGiftCustomAmountForm`.
  - Create `gift_manager/views/group_gifts.py`: HTMX endpoints for toggle, mode, add, remove, toggle-paid, amount.
  - Modify `gift_manager/views/relation.py` (`RelationDetailView`): load group gift context summary.
  - Modify `gift_manager/urls.py`: register group gift endpoints.
  - Create `gift_manager/templates/gift_manager/includes/relation_group_gift_partial.html`.
  - Modify `gift_manager/templates/gift_manager/includes/relation_detail_partial.html`: include group gift partial.
  - Create `gift_manager/tests/views/test_group_gift_views.py`.
- **E2E & Final Integration:**
  - Modify `gift_manager/seed_data.py`: seed demo group gift and contributions.
  - Create `gift_manager/tests/e2e/test_group_gift_e2e.py`.
  - Update `docs/ideas/README.md` and move `0028` to `docs/ideas/implemented/`.

---

### Task 1: Data Model, Constraints, and Migration `0043`

Implement the `RelationContribution` model, fields on `Relation`, constraints, and factory.

**Files:**
- Modify: `gift_manager/models.py`
- Create: `gift_manager/migrations/0043_group_gifts.py`
- Modify: `gift_manager/tests/factories.py`
- Create: `gift_manager/tests/test_group_gift_models.py`

- [x] **Step 1: Write failing model tests in `gift_manager/tests/test_group_gift_models.py`:**
  - `test_contribution_requires_name`: name cannot be empty.
  - `test_contribution_amount_non_negative`: amount < 0 violates check constraint.
  - `test_contribution_is_paid_requires_paid_at`: `is_paid=True` requires `paid_at IS NOT NULL`; `is_paid=False` requires `paid_at IS NULL`.
  - `test_unique_user_contribution_per_plan`: same user cannot have two contribution rows on the same relation.
  - `test_multiple_external_contributors_allowed`: multiple rows with `user=None` and different or same names are allowed.
  - `test_save_snapshots_user_username_into_name`: when `user` is set and `name=""`, `save()` automatically snapshots `user.username` into `name`.
  - `test_user_account_deletion_preserves_contribution_row`: deleting contributor's `User` sets `user=None` via `SET_NULL`, preserving row and snapshot `name` without `IntegrityError`.
  - `test_relation_split_mode_and_is_group_gift_defaults`: default `is_group_gift=False` and `split_mode="equal"`.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_group_gift_models.py`. Expected: FAIL.
- [x] **Step 3: Implement models and create migration:**
  - Add `SplitMode` choices to `Relation`.
  - Add `is_group_gift` and `split_mode` to `Relation`.
  - Add `RelationContribution` model with constraints and snapshot `save()`.
  - Run `python manage.py makemigrations gift_manager` (creating `0043_group_gifts.py`).
  - Add `RelationContributionFactory` in `gift_manager/tests/factories.py`.
- [x] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/test_group_gift_models.py`. Expected: PASS.

---

### Task 2: Service Layer, Penny Rounding, and Concurrency (`gift_manager/group_gifts.py`)

Implement mathematics, permissions, access guards, financial summary builder, and state mutations.

**Files:**
- Create: `gift_manager/group_gifts.py`
- Modify: `gift_manager/plan_coordination.py` (expose `require_level`)
- Create: `gift_manager/tests/test_group_gift_service.py`

- [x] **Step 1: Write failing service tests in `gift_manager/tests/test_group_gift_service.py`:**
  - `test_calculate_equal_shares_divmod_penny_distribution`: tests exact cents distribution (e.g. 100/3 -> [33.34, 33.33, 33.33]; 0.07/4 -> [0.02, 0.02, 0.02, 0.01]).
  - `test_calculate_equal_shares_hypothesis_property`: Hypothesis property test asserting `sum(calculate_equal_shares(p, n)) == p` across arbitrary 2-decimal positive Decimals and counts.
  - `test_calculate_equal_shares_edge_cases`: zero count returns empty list; zero or None price returns list of 0.00.
  - `test_enable_group_gift_adds_buyer_get_or_create`: buyer is added as contributor; re-enabling after disable doesn't duplicate.
  - `test_disable_group_gift_preserves_rows_and_refuses_when_paid`: refuse if any share is paid; otherwise preserve rows.
  - `test_set_split_mode_freezes_and_resets`: switching to custom freezes equal amounts; switching to equal resets unpaid amounts.
  - `test_add_contributor_validations`: rejects recipient, rejects user without plan viewer access, rejects whitespace name, requires group gift enabled.
  - `test_remove_contributor_refuses_buyer_or_paid`: rejects removing claimed buyer; rejects removing paid contributor.
  - `test_toggle_contribution_paid_freezes_amount_in_equal_mode`: freezes amount at current share; rejects buyer toggle; rejects zero amount share.
  - `test_rebalancing_with_paid_freeze`: paid shares stay frozen; remaining unpaid contributors rebalance over `price - sum_frozen`.
  - `test_overfunded_state_when_price_drops`: flags `is_overfunded=True` when frozen payments exceed reduced price.
  - `test_recipient_guard_owner_exemption_matrix`: owner member on group recipient allowed; non-owner member blocked; person recipient blocked even if plan owner.
  - `test_concurrency_locking_prevents_duplicate_user`: transactional test with PostgreSQL row locks.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_group_gift_service.py`. Expected: FAIL.
- [x] **Step 3: Implement `gift_manager/group_gifts.py`:**
  - `calculate_equal_shares`.
  - `is_recipient_of_plan` and `_require_group_gift_access` (reusing `require_level` from `plan_coordination`).
  - `ContributorRow` and `GroupGiftSummary` dataclasses.
  - Service functions with `PermissionService.lock_object(relation)` inside `transaction.atomic()`.
- [x] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/test_group_gift_service.py`. Expected: PASS.

---

### Task 3: Privacy Boundary & Side-Channel Invariant Tests

Verify that no side channel leaks group gift tallies, contributor names, or amounts to recipients or external feeds.

**Files:**
- Create: `gift_manager/tests/views/test_group_gift_privacy.py`

- [ ] **Step 1: Write privacy boundary tests in `gift_manager/tests/views/test_group_gift_privacy.py`:**
  - `test_recipient_gets_403_on_all_group_gift_endpoints`: recipient user calling any group gift endpoint gets generic HTTP 403 `PermissionDenied`.
  - `test_recipient_never_sees_group_gift_markup_on_surprise_or_non_surprise_plan`: wisher / recipient rendering `relation_detail` receives zero group gift markup, table, or balance bar.
  - `test_calendar_feed_excludes_group_gift_data`: `.ics` feed for recipient and collaborators contains no group gift text or contributor names.
  - `test_email_digest_excludes_group_gift_data`: reminder digest contains no group gift text or contributor names.
  - `test_ai_prompt_excludes_group_gift_data`: AI suggestion payload contains no group gift text or contributor names.
  - `test_dynamic_recipient_protection_converts_recipient_contributor_rows`: linking a person to an account or adding to a group converts any existing contributor row for that user to an external snapshot (`user=None`), preventing exposure.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_group_gift_privacy.py`. Expected: PASS.

---

### Task 4: UI Endpoints, Templates, and Localization

Build the HTMX endpoints, dedicated partial template, and French translations.

**Files:**
- Modify: `gift_manager/forms.py` (`GroupGiftContributorForm`, `GroupGiftCustomAmountForm`)
- Create: `gift_manager/views/group_gifts.py`
- Modify: `gift_manager/views/relation.py` (`RelationDetailView.get_context_data`)
- Create: `gift_manager/templates/gift_manager/includes/relation_group_gift_partial.html`
- Modify: `gift_manager/templates/gift_manager/includes/relation_detail_partial.html`
- Modify: `gift_manager/urls.py`
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Create: `gift_manager/tests/views/test_group_gift_views.py`

- [ ] **Step 1: Write failing view tests in `gift_manager/tests/views/test_group_gift_views.py`:**
  - `test_enable_disable_group_gift_htmx_and_redirect`: enables and disables group gift via HTMX and standard POST.
  - `test_switch_split_mode_htmx`: switches between equal and custom split modes.
  - `test_add_contributor_user_and_external`: adds collaborator and external name.
  - `test_remove_contributor_htmx`: removes contributor and re-renders partial.
  - `test_toggle_paid_htmx`: toggles paid status with visual badge update.
  - `test_update_custom_amount_htmx`: updates custom share amount.
  - `test_plan_detail_renders_group_gift_card_for_collaborators`: editors see group gift card, progress bar, and contributor rows.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_group_gift_views.py`. Expected: FAIL.
- [ ] **Step 3: Implement forms, views, templates, routes, and translations:**
  - In `forms.py`: `GroupGiftContributorForm` and `GroupGiftCustomAmountForm`.
  - In `views/group_gifts.py`: 6 endpoints with HTMX partial swap and standard POST redirect.
  - In `views/relation.py`: pass `group_gift` summary in `RelationDetailView.get_context_data`.
  - In `urls.py`: register routes under `relations/<uuid:pk>/group-gift/...`.
  - In templates: create `relation_group_gift_partial.html` (with accessible `role="progressbar"`, mobile card layout, and buyer badges) and include in `relation_detail_partial.html`.
  - Add French translations in `locale/fr/LC_MESSAGES/django.po` and run `django-admin compilemessages`.
- [ ] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/views/test_group_gift_views.py`. Expected: PASS.

---

### Task 5: End-to-End Tests, Documentation, and Final Verification

Write Playwright E2E tests, seed demo data, update idea 0028 status to Implemented, and run all verification suites.

**Files:**
- Create: `gift_manager/tests/e2e/test_group_gift_e2e.py`
- Modify: `gift_manager/seed_data.py`
- Modify: `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md`
- Modify: `docs/ideas/README.md`

- [ ] **Step 1: Write Playwright E2E tests in `gift_manager/tests/e2e/test_group_gift_e2e.py`:**
  - `test_group_gift_surprise_plan_collaborative_workflow`:
    - Alice creates surprise plan for Bob, sets price $90, claims plan (buyer).
    - Alice organizes as group gift, adds Carol (collaborator) and Dave (external name).
    - Equal split computes $30 each.
    - Alice marks Carol as paid.
    - Progress bar shows $60 / $90 collected, Dave owes $30.
    - Bob logs in and verifies zero trace of group gift or finances.
  - `test_group_gift_non_surprise_shared_plan_privacy`:
    - Alice creates non-surprise plan shared with Bob and Carol.
    - Alice organizes group gift with Carol.
    - Bob views plan: sees gift details, but group gift section is strictly absent.
- [ ] **Step 2: Seed demo group gift data in `gift_manager/seed_data.py`:**
  - Add a group gift on one of the seed plans (e.g. Alice and Bob chipping in for Mom's birthday gift).
- [ ] **Step 3: Run full verification suite:**
  - `tox run -e py311 -- gift_manager/tests/test_group_gift_models.py gift_manager/tests/test_group_gift_service.py gift_manager/tests/views/test_group_gift_privacy.py gift_manager/tests/views/test_group_gift_views.py gift_manager/tests/test_locale_coverage.py`
  - `tox run -e lint`
  - `tox run -e e2e -- gift_manager/tests/e2e/test_group_gift_e2e.py`
- [ ] **Step 4: Refresh repo context graph:**
  - Run `graft build`.
- [ ] **Step 5: Move Idea 0028 to Implemented:**
  - Update `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md` status to `Implemented`.
  - Move to `docs/ideas/implemented/0028-wishlists-and-collaborative-gift-giving.md`.
  - Update row in `docs/ideas/README.md`.
- [ ] **Step 6: Commit and push:**
  - `Feat: Implement collaborative group gifts and contribution tally (Project C)`
