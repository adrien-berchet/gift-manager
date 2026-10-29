# Own Profile And Wishlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Project B of `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md`: enable registered users to author their own profile preferences (sizes, favorite colors, dislikes/allergies) and manage a personal wishlist. Friends viewing a linked `Person` record can see these preferences, claim wishes, and convert wishes into surprise gift plans while maintaining strict privacy boundaries so the wisher never discovers claims or surprise plans.

**Architecture:**
1. A new `Wish` model stores user wishes. `Profile` gains fields for self-declared preferences, "things to avoid", public interests (`GiftTag` with `is_public=True`), and an AI consent toggle (`ai_share_self_profile`).
2. A new `Relation.wish` foreign key connects a gift plan to the wish it fulfills.
3. All business rules live in a dedicated `gift_manager/wishlist.py` service.
4. Privacy boundary: wisher views never expose claims, claimer names, or fulfilling plans. Givers coordinate with claims and surprise plans (`is_surprise = True` forced).
5. Suggestion engines (AI prompt and catalogue) incorporate recipient preferences when consent is granted.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Bootstrap 5, Grid.js, pytest, tox, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-29-own-profile-and-wishlist-design.md`

## Global Constraints

- Code, docstrings, and comments in English. Every user-facing string is translatable with French translations in `locale/fr/LC_MESSAGES/django.po` compiled with `msgfmt`.
- Follow repository conventions: integer `id` primary key + unique UUID `wish_id`; `condition=` parameter in `CheckConstraint`; `gettext_lazy` for models/forms; `validate_http_url` and `max_length=2000` on URLs.
- No new external production dependencies.
- Access is strictly governed by `PermissionService.users_are_friends`: only confirmed friends can access a user's wishlist and profile preferences.
- Actions work progressively with plain HTML/POST and offcanvas/HTMX partials for enhanced interactions.
- Run tests on PostgreSQL (`tox run -e py311 -- <path>`); lint with `tox run -e lint`; browser tests with `tox run -e e2e -- <path>`.
- Commit messages follow `commitlint.config.js` (`Feat: ...`, `Fix: ...`, `Test: ...`, `Docs: ...`, sentence case, no trailing period).

---

## File Structure

- **Models & Migration:**
  - Modify `gift_manager/models.py`: add `WishPriority`, `WishQuerySet`, `Wish`, fields on `Profile` (`preferences_notes`, `avoid_notes`, `public_interests`, `ai_share_self_profile`), field on `Relation` (`wish`), validation in `Relation.clean()`.
  - Create `gift_manager/migrations/0042_own_profile_and_wishlist.py`.
  - Modify `gift_manager/tests/factories.py`: `WishFactory`, update `ProfileFactory`, `RelationFactory`.
- **Service Layer:**
  - Create `gift_manager/wishlist.py`: wish CRUD, claim/unclaim, plan linking, plan sync on delete/cancel, unfriending claim cleanup.
- **Forms & Views:**
  - Modify `gift_manager/forms.py`: `WishForm`, `ProfilePreferencesForm`.
  - Create `gift_manager/views/wishlist.py`: wisher wishlist views (list, create, edit, archive, delete), friend claim toggle view, plan wish redirect view.
  - Modify `gift_manager/views/person.py` (`PersonDetailView`): load friend's wishlist & preferences into context.
  - Modify `gift_manager/views/profile.py`: render preferences and wishlist entry points; hook unfriending cleanup.
  - Modify `gift_manager/urls.py`: register wishlist routes.
- **Templates:**
  - Create `gift_manager/templates/gift_manager/wishlist_list.html`, `includes/wish_form_partial.html`, `includes/wish_item_partial.html`, `includes/person_wishlist_tab_partial.html`.
  - Modify `gift_manager/templates/gift_manager/profile_detail.html`: preferences form and wishlist link.
  - Modify `gift_manager/templates/gift_manager/includes/person_detail_partial.html`: wishlist & preferences tab.
- **Suggestions Integration:**
  - Modify `gift_manager/suggestions/ai/prompt.py`: inject wisher's scrubbed avoid notes, sizes, and unclaimed wish titles into the prompt.
  - Modify `gift_manager/suggestions/catalogue.py`: match wisher's public interests.
- **Tests:**
  - Create `gift_manager/tests/test_wishlist_models.py`.
  - Create `gift_manager/tests/test_wishlist_service.py`.
  - Create `gift_manager/tests/views/test_wishlist_privacy.py`.
  - Create `gift_manager/tests/views/test_wishlist_views.py`.
  - Create `gift_manager/tests/test_suggestions_wishlist.py`.
  - Create `gift_manager/tests/e2e/test_wishlist_e2e.py`.

---

### Task 1: Data Model, Constraints, and Migration `0042`

Create the `Wish` model, add profile preference fields, link `Relation.wish`, and write migration `0042`.

**Files:**
- Modify: `gift_manager/models.py`
- Create: `gift_manager/migrations/0042_own_profile_and_wishlist.py`
- Modify: `gift_manager/tests/factories.py`
- Create: `gift_manager/tests/test_wishlist_models.py`

**Interfaces:**
- `Wish(models.Model)`: `wish_id` (UUID unique), `wisher` (FK User), `title` (CharField 255), `url` (URLField 2000), `price_hint` (DecimalField >= 0), `notes` (TextField), `priority` (`WishPriority`: 1=LOW, 2=MEDIUM, 3=HIGH), `is_archived` (BooleanField), `is_fulfilled` (BooleanField), `claimed_by` (FK User nullable), `claimed_at` (DateTimeField nullable), `wisher_updated_at` (DateTimeField auto_now), `created_at` (DateTimeField auto_now_add).
- `Wish.is_updated_after_claim() -> bool`.
- `Profile`: `preferences_notes` (TextField), `avoid_notes` (TextField), `public_interests` (M2M `GiftTag` with `is_public=True`), `ai_share_self_profile` (BooleanField default False).
- `Relation.wish`: FK `Wish` nullable (`SET_NULL`, `related_name="fulfilling_plans"`).
- `Relation.clean()` validates `person.account == wish.wisher` and `group is None`.

- [x] **Step 1: Write failing model unit tests in `gift_manager/tests/test_wishlist_models.py`:**
  - `test_wish_creation_and_defaults`: verify fields, default priority MEDIUM, `is_archived=False`, `is_fulfilled=False`.
  - `test_wish_check_constraint_claimed_by_requires_claimed_at`: assert DB IntegrityError when `claimed_by` is set without `claimed_at`.
  - `test_wish_check_constraint_non_negative_price`: assert DB IntegrityError when `price_hint < 0`.
  - `test_wish_is_updated_after_claim`: returns True when `wisher_updated_at > claimed_at`.
  - `test_profile_preference_fields`: verify `preferences_notes`, `avoid_notes`, `public_interests`, and `ai_share_self_profile=False` default.
  - `test_relation_wish_validation_rejects_group_recipient`: verify ValidationError when `relation.group` is set.
  - `test_relation_wish_validation_rejects_unlinked_or_mismatched_person`: verify ValidationError when `relation.person.account != wish.wisher`.
  - `test_relation_wish_validation_accepts_matching_linked_person`: valid when `relation.person.account == wish.wisher`.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_wishlist_models.py`. Expected: FAIL (models not found).
- [x] **Step 3: Implement models in `gift_manager/models.py`:**
  - Define `WishPriority`, `WishQuerySet`, and `Wish`.
  - Add fields to `Profile`.
  - Add `wish` foreign key to `Relation` and validation in `Relation.clean()`.
- [x] **Step 4: Generate migration `0042_own_profile_and_wishlist.py`:**
  - Run `python manage.py makemigrations gift_manager`.
  - Verify generated migration operations and constraints.
- [x] **Step 5: Update `gift_manager/tests/factories.py`:**
  - Add `WishFactory`.
- [x] **Step 6: Run tests:** `tox run -e py311 -- gift_manager/tests/test_wishlist_models.py`. Expected: PASS.

---

### Task 2: Wishlist Service (`gift_manager/wishlist.py`)

Implement all business logic for wish management, claiming, and plan synchronization.

**Files:**
- Create: `gift_manager/wishlist.py`
- Create: `gift_manager/tests/test_wishlist_service.py`

**Interfaces:**
- `get_wisher_wishes(wisher: User, include_archived: bool = False) -> QuerySet[Wish]`
- `get_friend_visible_wishes(wisher: User, friend: User) -> QuerySet[Wish]`
- `claim_wish(wish: Wish, friend: User) -> Wish`
- `release_wish_claim(wish: Wish, actor: User) -> Wish`
- `plan_wish(wish: Wish, friend: User, person: Person, event=None) -> Relation`
- `sync_wish_on_plan_change(relation: Relation) -> None`
- `release_claims_after_unfriending(user: User, former_friend: User) -> None`
- `format_claimer_label(wish: Wish, viewer: User) -> str`

- [x] **Step 1: Write failing service unit tests in `gift_manager/tests/test_wishlist_service.py`:**
  - `test_get_friend_visible_wishes_requires_friendship`: non-friend raises PermissionDenied.
  - `test_get_friend_visible_wishes_excludes_archived`: wisher's archived wishes not shown to friends.
  - `test_claim_wish_success`: friend claims unclaimed wish; sets `claimed_by` and `claimed_at`.
  - `test_claim_wish_rejects_wisher_self_claim`: wisher cannot claim own wish (PermissionDenied).
  - `test_claim_wish_rejects_already_claimed_by_another`: raises ValidationError.
  - `test_release_wish_claim`: claimer releases claim; clears fields.
  - `test_release_wish_claim_rejects_unauthorized_user`: non-claimer cannot release (PermissionDenied).
  - `test_plan_wish_creates_surprise_relation_and_claims_wish`: creates `Gift`, creates `Relation(is_surprise=True, wish=wish)`, sets wish claim.
  - `test_sync_wish_on_plan_deletion_or_cancellation_releases_claim`: deleting fulfilling plan clears wish claim.
  - `test_sync_wish_on_plan_given_marks_fulfilled`: status `GIVEN` sets `wish.is_fulfilled = True`.
  - `test_release_claims_after_unfriending`: removes claims across former friends.
  - `test_format_claimer_label_masks_non_friend_username`: returns "Claimed by @bob" if viewer is friends with Bob; "Claimed by a friend" if not.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_wishlist_service.py`. Expected: FAIL.
- [x] **Step 3: Implement `gift_manager/wishlist.py`:**
  - Write atomic claim, release, plan linking, and plan lifecycle synchronization functions.
- [x] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/test_wishlist_service.py`. Expected: PASS.

---

### Task 3: Privacy Boundary and Side-Channel Invariant Tests

Verify that no side channel leaks claim, plan, or surprise information to the wisher.

**Files:**
- Create: `gift_manager/tests/views/test_wishlist_privacy.py`

- [x] **Step 1: Write privacy boundary tests in `gift_manager/tests/views/test_wishlist_privacy.py`:**
  - `test_wisher_views_render_identically_whether_claimed_or_not`: Alice's wishlist page HTML, form context, and responses are character-for-character identical when wish is unclaimed vs claimed by Bob vs planned by Bob.
  - `test_wisher_cannot_see_claim_status_via_api_or_html`: no claimer username or badge appears in wisher's payload.
  - `test_plan_wish_forces_surprise_flag_on_relation`: assert `relation.is_surprise is True`.
  - `test_created_gift_from_wish_is_not_shared_with_wisher`: assert `Gift` created by `plan_wish` has no `GiftPermission` for wisher.
  - `test_archiving_claimed_wish_preserves_claim_for_giver`: when Alice archives a claimed wish, Bob still sees the wish with an archived notice, without breaking his plan.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_wishlist_privacy.py`. Expected: PASS (after matching service implementation).

---

### Task 4: Wisher Profile Preferences and Wishlist Management UI

Build the user-facing UI for managing personal preferences and wishlist items on `/profile/`.

**Files:**
- Modify: `gift_manager/forms.py` (`WishForm`, `ProfilePreferencesForm`)
- Create: `gift_manager/views/wishlist.py` (`WishListView`, `WishCreateView`, `WishUpdateView`, `WishArchiveView`, `WishDeleteView`)
- Create: `gift_manager/templates/gift_manager/wishlist_list.html`
- Create: `gift_manager/templates/gift_manager/includes/wish_form_partial.html`
- Create: `gift_manager/templates/gift_manager/includes/wish_item_partial.html`
- Modify: `gift_manager/views/profile.py` (`ProfileDetailView`, `ProfileUpdateView`)
- Modify: `gift_manager/templates/gift_manager/profile_detail.html`
- Modify: `gift_manager/urls.py`
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Create: `gift_manager/tests/views/test_wishlist_wisher_views.py`

- [x] **Step 1: Write failing wisher view tests in `gift_manager/tests/views/test_wishlist_wisher_views.py`:**
  - `test_profile_preferences_form_saves_preferences_and_tags`: updates `preferences_notes`, `avoid_notes`, `public_interests`, and `ai_share_self_profile`.
  - `test_wishlist_list_view_renders_wisher_wishes`: wisher sees active and archived wishes.
  - `test_wish_create_view`: creates wish and redirects / returns partial on HTMX.
  - `test_wish_update_view`: updates title, notes, price hint, priority; sets `wisher_updated_at`.
  - `test_wish_archive_toggle`: toggles `is_archived`.
  - `test_wish_delete_view`: deletes wish or marks deleted.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_wishlist_wisher_views.py`. Expected: FAIL.
- [x] **Step 3: Implement forms, views, templates, and routes:**
  - In `forms.py`: `WishForm` with validation for non-negative price and URL. `ProfilePreferencesForm` with `public_interests` choices limited to `is_public=True`.
  - In `views/wishlist.py`: CRUD views supporting HTMX offcanvas editing. `WishListView` mapped to `gift_manager:wishlist_list` at `profile/wishlist/`.
  - In `profile_detail.html`: embed "My Preferences" section and "My Wishlist" card/link.
  - Add French translations in `locale/fr/LC_MESSAGES/django.po` and compile.
  - Remove `@pytest.mark.xfail` markers from `gift_manager/tests/views/test_wishlist_privacy.py` so contract tests run against the newly landed view.
- [x] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/views/test_wishlist_wisher_views.py gift_manager/tests/views/test_wishlist_privacy.py`. Expected: PASS.

---

### Task 5: Giver UI on Linked Person Page

Display the friend's wishlist and preferences to givers when viewing a linked `Person` record, with claim and plan actions.

**Files:**
- Create: `gift_manager/templates/gift_manager/includes/person_wishlist_tab_partial.html`
- Modify: `gift_manager/templates/gift_manager/includes/person_detail_partial.html`
- Modify: `gift_manager/views/person.py` (`PersonDetailView`)
- Modify: `gift_manager/views/wishlist.py` (`WishClaimToggleView`, `WishPlanView`)
- Modify: `gift_manager/views/profile.py` (`RemoveFriendView`: call `release_claims_after_unfriending`)
- Modify: `gift_manager/urls.py`
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Create: `gift_manager/tests/views/test_wishlist_giver_views.py`

- [x] **Step 1: Write failing giver view tests in `gift_manager/tests/views/test_wishlist_giver_views.py`:**
  - `test_person_detail_displays_friend_preferences_and_wishlist`: giver viewing Bob's person record linked to Alice sees Alice's sizes, avoid notes, public tags, and wishes.
  - `test_person_detail_own_record_shows_profile_redirect_notice`: viewing own person record displays link to profile instead of giver wishlist view.
  - `test_wish_claim_toggle_htmx`: friend clicks claim -> returns updated wish item partial with "Claimed by you".
  - `test_wish_plan_redirects_to_guided_plan`: friend clicks "Plan this gift" -> initializes plan and attaches wish.
  - `test_unfriending_cleans_up_claims`: former friend's claims are released.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_wishlist_giver_views.py`. Expected: FAIL.
- [x] **Step 3: Implement giver UI and claim endpoints:**
  - In `PersonDetailView.get_context_data`: query friend's preferences and visible wishes via `gift_manager/wishlist.py`.
  - In `person_detail_partial.html`: render "Wishlist & Preferences" tab with claim buttons and claimer badges.
  - Hook unfriending cleanup in `RemoveFriendView`.
  - Add French translations and compile messages.
- [x] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/views/test_wishlist_giver_views.py`. Expected: PASS.

---

### Task 6: AI and Catalogue Suggestions Integration

Incorporate recipient self-profile preferences and unclaimed wishes into AI prompt generation and catalogue interest matching.

**Files:**
- Modify: `gift_manager/suggestions/ai/prompt.py`
- Modify: `gift_manager/suggestions/catalogue.py`
- Create: `gift_manager/tests/test_suggestions_wishlist.py`

- [ ] **Step 1: Write failing suggestion tests in `gift_manager/tests/test_suggestions_wishlist.py`:**
  - `test_ai_prompt_includes_self_profile_when_enabled`: when `ai_share_self_profile=True`, prompt includes public interests, scrubbed avoid notes, and scrubbed unclaimed wish titles.
  - `test_ai_prompt_excludes_self_profile_when_disabled`: when `ai_share_self_profile=False` (default), prompt does not include self-profile data.
  - `test_ai_prompt_excludes_claimed_and_fulfilled_wishes`: wishes claimed by any friend are not passed to prompt.
  - `test_catalogue_matches_public_interests`: catalogue recommendations match against `public_interests`.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_suggestions_wishlist.py`. Expected: FAIL.
- [ ] **Step 3: Implement suggestions integration:**
  - In `prompt.py`: update `_build_recipient_info` and `build_ai_payload` to inspect `recipient.account.profile.ai_share_self_profile`.
  - In `catalogue.py`: incorporate `public_interests` into candidate tags.
- [ ] **Step 4: Run tests:** `tox run -e py311 -- gift_manager/tests/test_suggestions_wishlist.py`. Expected: PASS.

---

### Task 7: End-to-End Tests & Final Verification

Create Playwright E2E tests validating the full collaborative workflow and verify all suites.

**Files:**
- Create: `gift_manager/tests/e2e/test_wishlist_e2e.py`
- Modify: `gift_manager/seed_data.py` (seed wishes and preferences for demo)

- [ ] **Step 1: Write E2E test in `gift_manager/tests/e2e/test_wishlist_e2e.py`:**
  - Alice logs in, writes sizes and avoid notes, and adds a wish with title and link.
  - Bob logs in, navigates to his linked record for Alice, views her "Wishlist & Preferences" tab.
  - Bob claims the wish and creates a surprise gift plan from it.
  - Alice logs in, verifies her wish is intact, verifies she cannot see Bob's claim or plan.
  - Test light and dark mode accessibility and contrast.
- [ ] **Step 2: Run E2E test:** `tox run -e e2e -- gift_manager/tests/e2e/test_wishlist_e2e.py`.
- [ ] **Step 3: Run full verification:**
  - `tox run -e lint`
  - `tox run -e py311 -- gift_manager/tests/test_wishlist_models.py gift_manager/tests/test_wishlist_service.py gift_manager/tests/views/test_wishlist_privacy.py gift_manager/tests/views/test_wishlist_wisher_views.py gift_manager/tests/views/test_wishlist_giver_views.py gift_manager/tests/test_suggestions_wishlist.py gift_manager/tests/test_locale_coverage.py`
- [ ] **Step 4: Run `graft build`** to refresh the repo context graph.
- [ ] **Step 5: Commit and push:** `Feat: Implement own profile and wishlist (Project B)`.
