# Shared Plan Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let collaborators claim a gift plan, discuss it in a comment thread, and hide a plan from a recipient who is also an app user (surprise flag).

**Architecture:** Three new `Relation` fields plus a `RelationComment` model. All rules live in a new `gift_manager/plan_coordination.py` service built on `PermissionService`. Surprise visibility is enforced once, inside `RelationQuerySet.accessible_by`, then every bypass path is audited and covered by a per-surface regression test. UI follows the existing HTMX partial pattern.

**Tech Stack:** Django 5.1, PostgreSQL, HTMX, Bootstrap, pytest/tox, factory_boy, ruff.

**Spec:** `docs/superpowers/specs/2026-10-05-shared-plan-coordination-design.md`

## Global Constraints

- Code, docstrings and comments in English; French translations for every new user-facing string (`makemessages -l fr`, `compilemessages`).
- No new dependencies. No new permission levels. No access logic outside `PermissionService.get_effective_permission`.
- No explanatory or keyboard-shortcut text in the UI beyond labels.
- Comment text: non-blank after stripping, max 2000 characters, rendered with Django autoescaping.
- Views return a partial for HTMX requests (`HX-Request: true`) and a full page / redirect otherwise.
- Surprise default applies at creation only; no backfill of existing plans.
- Run tests with `tox run -e py311 -- <path>`; lint with `tox run -e lint`; PostgreSQL for permission work.

## Review Focus

- A claimer's account is deleted: the plan becomes claimable again, no `IntegrityError` (Task 1).
- Comment text that is blank, whitespace-only, over 2000 chars, or contains HTML (Tasks 3 and 6).
- The recipient opens a plan URL directly (detail, edit, claim, comment POST) after it is flagged a surprise: must be 404, not 403 or 200 (Task 6).
- Counts and totals that reveal a hidden plan exist: person/gift/event detail plan counts, budget totals, dashboard buckets (Task 4).
- A group recipient whose only linked member is the creator: flag defaults off and the creator still sees the plan (Tasks 2 and 5).

## File Structure

- Modify `gift_manager/models.py`: new `Relation` fields, `RelationComment`, `RelationQuerySet.hidden_surprises_for` / `accessible_by`, unshare signal.
- Create `gift_manager/migrations/0037_plan_coordination.py` (generated, reviewed).
- Create `gift_manager/plan_coordination.py`: claim/release/comments/surprise rules.
- Modify `gift_manager/forms.py`: `SurpriseFieldMixin` on the four plan forms; `gift_manager/plan_repeat.py`: carry the flag.
- Create `gift_manager/views/plan_coordination.py`; modify `views/__init__.py`, `urls.py`, `views/relation.py` (detail context), `forms` templates, `includes/relation_detail_partial.html`, `includes/relation_cards_partial.html`, new `includes/relation_coordination_partial.html`.
- Modify `gift_manager/tests/factories.py` only if a helper is needed; tests listed per task.

---

### Task 1: Data model, migration, unshare release

**Files:**
- Modify: `gift_manager/models.py` (`Relation`, new `RelationComment`, signal after `RelationPermission`)
- Create: `gift_manager/migrations/0037_plan_coordination.py`
- Modify: `docs/superpowers/specs/2026-10-05-shared-plan-coordination-design.md` (claim constraint line)
- Test: `gift_manager/tests/test_plan_coordination_models.py`

**Interfaces:**
- Produces: `Relation.is_surprise: bool` (default False); `Relation.claimed_by: User | None` (FK, `SET_NULL`, `related_name="claimed_relations"`); `Relation.claimed_at: datetime | None`; property `Relation.is_claimed -> bool` (true when `claimed_by_id` is not None); `RelationComment(relation FK CASCADE related_name="comments", author FK User SET_NULL null, text TextField, created_at auto_now_add)`, ordered by `("created_at", "pk")`.

- [ ] **Step 1: Write failing tests** in `test_plan_coordination_models.py`:
  - `test_defaults`: new `RelationFactory()` has `is_surprise is False`, `claimed_by is None`, `is_claimed is False`.
  - `test_claimed_by_requires_claimed_at`: saving `claimed_by=user, claimed_at=None` raises `IntegrityError` (wrap in `transaction.atomic()`).
  - `test_deleting_claimer_unclaims_without_error`: claim with a user and `claimed_at=now`, `user.delete()`, reload: `claimed_by is None`, `is_claimed is False`.
  - `test_unsharing_releases_claim`: claimer holds a VIEWER permission; `PermissionService.delete_permission(claimer, relation)` leaves `claimed_by is None and claimed_at is None`; a claim held by a different user is untouched.
  - `test_comments_ordered_and_cascade`: two comments come back oldest first; deleting the relation deletes them; deleting the author leaves the comment with `author is None`.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_plan_coordination_models.py`. Expected: FAIL (missing fields).
- [ ] **Step 3: Implement** the fields and `RelationComment` in `gift_manager/models.py`. Constraint `relation_claimed_by_requires_claimed_at`: `Q(claimed_by__isnull=True) | Q(claimed_at__isnull=False)` (one-directional on purpose: `SET_NULL` on user deletion leaves `claimed_at` set). Add a `post_delete` receiver on `RelationPermission` that runs `Relation.objects.filter(pk=instance.relation_id, claimed_by_id=instance.user_id).update(claimed_by=None, claimed_at=None)`, next to the existing signal handlers.
- [ ] **Step 4: Generate and review the migration:** `python manage.py makemigrations gift_manager -n plan_coordination`; confirm it only adds the three fields, the constraint and `RelationComment`.
- [ ] **Step 5: Amend the spec** line "Check constraint: `claimed_by IS NULL` iff `claimed_at IS NULL`" to the one-directional rule above, with the `SET_NULL` reason.
- [ ] **Step 6: Run** the test file plus `tox run -e py311 -- gift_manager/tests/test_migrations.py`. Expected: PASS; `python manage.py makemigrations --check --dry-run` clean.
- [ ] **Step 7: Commit** `Feat: Add claim, surprise flag and comments data model`.

---

### Task 2: Surprise visibility in `accessible_by`

**Files:**
- Modify: `gift_manager/models.py` (`RelationQuerySet`, `RelationManager`)
- Test: `gift_manager/tests/test_surprise_visibility.py`

**Interfaces:**
- Consumes: Task 1 fields; `PersonGroup.get_ancestors()` (cached hierarchy); `RelationPermission`, `PermissionLevel.OWNER`.
- Produces: `RelationQuerySet.hidden_surprises_for(user) -> RelationQuerySet` (relations hidden from `user`, regardless of sharing) and the manager passthrough `Relation.objects.hidden_surprises_for(user)`; `RelationQuerySet.accessible_by(user)` now excludes them. Helper `recipient_group_ids_for(user) -> set[int]`: pks of the groups of every `Person` with `user_link=user`, plus all their ancestors.

- [ ] **Step 1: Write failing tests** (queryset level; each shares the plan with the recipient user as VIEWER via `PermissionService.create_or_update_permission(..., object_attr="relation")`):
  - `test_person_recipient_hidden`: surprise plan for a person with `user_link=recipient`: `recipient` not in access, `other_collaborator` still sees it.
  - `test_not_surprise_visible`: same setup with `is_surprise=False` is visible to the recipient.
  - `test_group_member_hidden`: group plan; recipient's linked person is a direct member: hidden.
  - `test_nested_group_member_hidden`: member of a child group of the target group: hidden. Member of the parent group of the target: still visible.
  - `test_owner_recipient_never_hidden`: recipient holds OWNER on the plan: visible.
  - `test_hidden_surprises_for_lists_hidden_rows`: returns exactly the hidden relations, including ones not shared with the user.
  - `test_group_with_only_creator_linked_is_visible_to_creator`: group whose only linked member is the OWNER: creator sees it.
  - `test_query_count_constant`: `accessible_by` evaluation uses the same number of queries for 1 and 5 hidden plans (`django_assert_num_queries` or `CaptureQueriesContext`).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_surprise_visibility.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `recipient_group_ids_for` (module-level in `models.py` after `PersonGroup`) and the two queryset methods. Hidden = `is_surprise=True` AND (`person__user_link=user` OR `group_id__in=recipient_group_ids_for(user)`) AND NOT `Exists(RelationPermission(relation=OuterRef("pk"), user=user, permission_type=PermissionLevel.OWNER))`. `accessible_by` = `filter(shared_with=user)` minus `pk__in` of the hidden subquery, then `.distinct()` is not needed (keep the base behavior).
- [ ] **Step 4: Run** the new file plus `tox run -e py311 -- gift_manager/tests/test_permissions.py gift_manager/tests/test_permission_locking.py`. Expected: PASS.
- [ ] **Step 5: Commit** `Feat: Hide surprise plans from their recipients in accessible_by`.

---

### Task 3: Coordination service

**Files:**
- Create: `gift_manager/plan_coordination.py`
- Test: `gift_manager/tests/test_plan_coordination_service.py`

**Interfaces:**
- Consumes: Task 1 models; `PermissionService.get_effective_permission(obj, user) -> int`, `PermissionService.lock_object`, `PermissionService.get_permission_map`.
- Produces (all in `gift_manager.plan_coordination`):
  - `class AlreadyClaimed(Exception)` with attribute `claimed_by: User`.
  - `MAX_COMMENT_LENGTH = 2000`
  - `claim(relation: Relation, user: User) -> Relation`
  - `release(relation: Relation, user: User) -> None`
  - `add_comment(relation: Relation, user: User, text: str) -> RelationComment` (strips text; `ValidationError` when blank or longer than `MAX_COMMENT_LENGTH`)
  - `delete_comment(comment: RelationComment, user: User) -> None`
  - `set_surprise(relation: Relation, user: User, value: bool) -> None`
  - `can_be_surprise_for_owners(recipient: Person | PersonGroup | None, owner_ids: Iterable[int]) -> bool` (false only for a person whose `user_link_id` is in `owner_ids`)
  - `can_be_surprise(relation: Relation) -> bool` (uses `PermissionService.get_permission_map` for owner ids)
  - `default_surprise_for(recipient: Person | PersonGroup | None, creator: User) -> bool`

- [ ] **Step 1: Write failing tests** with the role matrix from the spec's permissions table; use owner / editor / viewer / stranger users:
  - claim: viewer, editor and owner can claim a free plan and get `claimed_by`/`claimed_at` set; stranger raises `PermissionDenied`; the same user claiming again is a no-op (`claimed_at` unchanged); another user raises `AlreadyClaimed` and `exc.claimed_by` is the claimer.
  - release: claimer releases; owner releases anyone's; editor releasing someone else's raises `PermissionDenied`; releasing an unclaimed plan is a no-op.
  - comments: viewer can add; stranger raises `PermissionDenied`; blank, whitespace-only and 2001-char text raise `ValidationError`; 2000 chars passes; `"<b>x</b>"` is stored verbatim (escaping happens at render). Delete: author yes, owner yes, other editor raises `PermissionDenied`.
  - `set_surprise`: viewer raises `PermissionDenied`; editor and owner can set and clear it; setting `True` when `can_be_surprise` is false stores `False`.
  - `can_be_surprise`: false for a person recipient whose `user_link` is a plan owner; true for a linked person who is not an owner; true for any group.
  - `default_surprise_for`: person with `user_link` other than creator is `True`; person linked to the creator `False`; unlinked person `False`; group with a linked member (direct) `True`; group whose linked member sits in a nested child group `True`; group whose only linked member is the creator `False`; `None` recipient `False`.
  - concurrency-shaped test: two sequential `claim` calls by different users on the same instance loaded twice (stale copy) still raise `AlreadyClaimed` for the second.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_plan_coordination_service.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the module. `claim` runs in `transaction.atomic()` and uses a conditional `Relation.objects.filter(pk=..., claimed_by__isnull=True).update(...)` so the second of two racing claims updates zero rows, then re-reads the winner to raise `AlreadyClaimed` (treat "claimed_at set but claimed_by null" as unclaimed). Permission checks use only `PermissionService.get_effective_permission` and `PermissionLevel` constants. `default_surprise_for` uses `PersonGroup.get_all_members(include_nested=True)` filtered on `user_link__isnull=False` excluding `creator`.
- [ ] **Step 4: Run** the test file. Expected: PASS. Run `tox run -e lint`.
- [ ] **Step 5: Commit** `Feat: Add plan coordination service`.

---

### Task 4: Audit bypass paths and per-surface surprise regression tests

**Files:**
- Test: `gift_manager/tests/test_surprise_surfaces.py`
- Modify (as the audit finds leaks): `gift_manager/views/search.py`, `views/common.py`, `mixins/performance.py`, `views/bulk_operations.py`, `views/sharing.py`, `views/recipient.py`, `views/person.py`, `views/gift.py`, `views/event.py`, `views/person_group.py`, `interests.py`, `services.py`, templates using reverse accessors.

**Interfaces:**
- Consumes: `Relation.objects.hidden_surprises_for(user)`, `Relation.objects.accessible_by(user)` (Task 2).
- Produces: no new API. Any leak is fixed by routing the path through `accessible_by`, or by `.exclude(pk__in=Relation.objects.hidden_surprises_for(user).values("pk"))` where `accessible_by` cannot be used.

- [ ] **Step 1: Inventory.** List every non-test read of plans that skips `Relation.objects.accessible_by`: run `rg -n "\.persons\b|\.groups\b|\.gifts\b|relations\b|Relation\._base_manager|Relation\.objects\.(filter|all|get|values)" gift_manager --glob '!tests/**' --glob '!migrations/**'` and `rg -n "relation_set|persons\.|\.relations\." gift_manager/templates`; write the findings as a comment block at the top of the test module (one line per path: leaks / safe).
- [ ] **Step 2: Write failing regression tests**, one per surface, all with the same fixture: surprise plan P shared with `recipient` (VIEWER, `user_link` of the target person) and with `collaborator`. Each test asserts `recipient` does not see P's gift name / relation id and `collaborator` still does. Surfaces: dashboard buckets, plan list (`relations`) and its Grid.js JSON, advanced list, relation search (`/api/search/relations/`), plan detail, person detail (list and plan count), group detail, gift detail and history, event detail (plans and counts), budgets (`BudgetService` totals), reminders digest content, calendar feed (`.ics`), birthdays, plan repeat candidates, bulk operations, sharing page, CSV/export endpoints if present (find with `rg -n "export|csv" gift_manager/views`), and group-recipient and nested-group variants for list and detail.
- [ ] **Step 3: Run** `tox run -e py311 -- gift_manager/tests/test_surprise_surfaces.py`. Expected: FAIL only for the leaking paths found in Step 1.
- [ ] **Step 4: Fix each failing path** as described in Interfaces. Do not alter paths that already pass.
- [ ] **Step 5: Run** `tox run -e py311 -- gift_manager/tests/test_surprise_surfaces.py gift_manager/tests/test_budget_service.py gift_manager/tests/test_reminders.py gift_manager/tests/test_calendar_feed.py gift_manager/tests/test_plan_repeat.py gift_manager/tests/test_permissions.py`. Expected: PASS.
- [ ] **Step 6: Commit** `Fix: Close surprise-plan leaks outside accessible_by`.

---

### Task 5: Surprise field in forms, defaults, duplicate and repeat

**Files:**
- Modify: `gift_manager/forms.py` (`PersonRelationForm`, `PersonGroupRelationForm`, `GiftRelationForm`, `RelationForm`); `gift_manager/plan_repeat.py` (`duplicate_initial`, `repeat_plans`); `gift_manager/views/relation.py` (new `surprise_default_hint` view); `gift_manager/urls.py`; `gift_manager/views/__init__.py`; `templates/gift_manager/includes/forms/relation_fields.html`; the small JS next to the existing repeat-gift-hint behavior (find with `rg -n "repeat-gift-hint|repeat_gift_hint" gift_manager/static gift_manager/templates`).
- Test: `gift_manager/tests/forms/test_surprise_field.py`, `gift_manager/tests/test_plan_repeat.py` (extend), `gift_manager/tests/views/test_surprise_default_hint.py`

**Interfaces:**
- Consumes: `default_surprise_for`, `can_be_surprise_for_owners`, `can_be_surprise` (Task 3).
- Produces: `class SurpriseFieldMixin` in `forms.py` adding `is_surprise = BooleanField(required=False, label=gettext_lazy("Surprise"))` and the rules below; URL `relations/surprise-default/` named `surprise_default_hint`, GET `?recipient=<person:uuid|group:uuid>` returning `JsonResponse({"default": bool, "allowed": bool})`, 400 on a malformed or inaccessible recipient.

- [ ] **Step 1: Write failing tests:**
  - create form, person recipient linked to another user: `form["is_surprise"].initial is True`; unlinked person `False`; group with a linked member `True`; group whose only linked member is the creator `False`.
  - create form, recipient linked to the creator: field absent / saved value forced `False` even when `is_surprise=on` is posted.
  - edit form: editor and owner see the field; a viewer-level user does not (and posting it changes nothing); saving with the field unchanged keeps the stored value.
  - `duplicate_initial(relation)` includes `"is_surprise": relation.is_surprise`; `repeat_plans` copies keep `is_surprise` but have `claimed_by is None` and no comments.
  - hint view: returns `{"default": true, "allowed": true}` for a person linked to another user; `{"default": false, "allowed": false}` for the creator's own linked person; 400 for a malformed value and for a recipient the user cannot access (same response, so existence is not revealed).
- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Implement `SurpriseFieldMixin`** and add `"is_surprise"` to the four forms' `Meta.fields`: on create, initial from `default_surprise_for(recipient, user)`; hide the field when `can_be_surprise_for_owners(recipient, [user.id])` is false or, on edit, when the user's effective permission is below EDITOR or `can_be_surprise(instance)` is false; in `clean`, force `False` whenever the field is hidden for the submitted recipient. Render the checkbox in `includes/forms/relation_fields.html` (label only).
- [ ] **Step 4: Implement the hint endpoint and JS:** on recipient change in create forms, call the endpoint and update the checkbox unless the user already toggled it; hide it when `allowed` is false. No new copy beyond the label.
- [ ] **Step 5: Update `plan_repeat.py`:** carry `is_surprise` in `duplicate_initial` and in the `Relation.objects.create` call of `repeat_plans`.
- [ ] **Step 6: Run** the three test files plus `tox run -e py311 -- gift_manager/tests/forms gift_manager/tests/test_create_form_property.py gift_manager/tests/test_edit_form_save_property.py`. Expected: PASS.
- [ ] **Step 7: Commit** `Feat: Add surprise flag to gift plan forms`.

---

### Task 6: Views, URLs and UI

**Files:**
- Create: `gift_manager/views/plan_coordination.py`, `gift_manager/templates/gift_manager/includes/relation_coordination_partial.html`
- Modify: `gift_manager/views/__init__.py`, `gift_manager/urls.py`, `gift_manager/views/relation.py` (`RelationDetailView.get_context_data`), `includes/relation_detail_partial.html`, `includes/relation_cards_partial.html`, `Relation.objects.with_related_objects` (add `claimed_by` to `select_related`)
- Test: `gift_manager/tests/views/test_plan_coordination_views.py`

**Interfaces:**
- Consumes: Task 3 service functions; `Relation.objects.accessible_by(request.user)` for every lookup (404 for hidden plans).
- Produces: function views `relation_claim(request, pk)`, `relation_release(request, pk)`, `relation_comment_add(request, pk)`, `relation_comment_delete(request, pk, comment_id)`; all `@login_required @require_POST`; URLs `relations/<uuid:pk>/claim/` (`relation_claim`), `.../release/` (`relation_release`), `.../comments/` (`relation_comment_add`), `.../comments/<int:comment_id>/delete/` (`relation_comment_delete`). Detail context key `coordination` = `{"claimed_by", "claimed_at", "can_claim", "can_release", "comments": [{"obj", "can_delete"}], "can_comment": True}`. HTMX requests re-render `includes/relation_coordination_partial.html` (target the coordination container); other requests redirect to `relation.get_absolute_url()`. `AlreadyClaimed` yields HTTP 409 (HTMX: re-render the partial with status 409); `PermissionDenied` yields 403; invalid comment yields 422 with the partial re-rendered.

- [ ] **Step 1: Write failing tests:**
  - viewer can claim and comment via POST; stranger gets 404 (not 403) on every endpoint; the linked recipient gets 404 on detail, edit, claim, release, comment add and delete once the plan is a surprise (Review Focus).
  - second claimer gets 409 and the original claim stands; editor releasing another's claim gets 403; owner release works.
  - comment add: blank gets 422 and creates nothing; `"<script>alert(1)</script>"` is rendered escaped in the detail response (`&lt;script&gt;` present, raw tag absent); over-length gets 422.
  - comment delete: author and owner succeed; another editor gets 403; a `comment_id` belonging to a different plan gets 404.
  - HTMX request (`HTTP_HX_REQUEST="true"`) returns the partial (no `<html`); normal request redirects 302 to the plan detail.
  - detail shows "Claimed by <username>" and the comment list; the card list shows the claimed-by badge; no extra queries per card (`django_assert_max_num_queries` comparing 1 vs 5 claimed plans).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_plan_coordination_views.py`. Expected: FAIL.
- [ ] **Step 3: Implement the views and URLs** as specified; resolve permissions only through the Task 3 service. Build `coordination` in `RelationDetailView.get_context_data` from the service rules (`can_claim` = no current claimer; `can_release` = claimer or OWNER; `can_delete` per comment likewise).
- [ ] **Step 4: Implement templates:** coordination partial (claim/release HTMX buttons, comment list with author, text, timestamp and delete, comment form) included from `relation_detail_partial.html` (labels only, `{% trans %}`), a "Claimed by" badge in `relation_cards_partial.html`, and a surprise badge in the detail for OWNER/EDITOR viewers.
- [ ] **Step 5: Run** the view test file plus `tox run -e py311 -- gift_manager/tests/test_quick_action_buttons.py gift_manager/tests/test_detail_view_display_property.py gift_manager/tests/test_htmx_mixin.py`. Expected: PASS.
- [ ] **Step 6: Commit** `Feat: Add claim and comment actions to gift plans`.

---

### Task 7: Translations, docs, e2e, final verification

**Files:**
- Modify: `gift_manager/locale/fr/LC_MESSAGES/django.po` (+ compiled `.mo` if tracked), `docs/ai/architecture.md`, `docs/ideas/README.md`, `docs/ideas/0007-shared-plan-coordination.md`
- Test: `gift_manager/tests/e2e/test_plan_coordination.py`

- [ ] **Step 1: Translations:** `python manage.py makemessages -l fr`, translate every new msgid (labels, errors, "Claimed by", buttons), `python manage.py compilemessages`; run `tox run -e py311 -- gift_manager/tests/test_locale_coverage.py`. Expected: PASS.
- [ ] **Step 2: E2E test** (follow `tests/e2e/test_crud_workflows.py` markers and fixtures): owner shares a plan with a collaborator; collaborator claims it; owner sees "claimed by"; comment posted and visible to the owner; collaborator releases; owner flags a surprise for a linked recipient and the recipient's plan list no longer shows it. Run `tox run -e e2e -- gift_manager/tests/e2e/test_plan_coordination.py`. Expected: PASS.
- [ ] **Step 3: Docs:** add a "Plan coordination" bullet to `docs/ai/architecture.md` Patterns (service, `hidden_surprises_for`, unshare signal, owner exception); mark idea 0007 implemented the way idea 0004 was (move to `docs/ideas/implemented/` and update `docs/ideas/README.md`).
- [ ] **Step 4: Full verification:** `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `tox run -e lint`, `tox run -e py311`. Expected: all clean/pass; if anything fails, report it instead of claiming success.
- [ ] **Step 5: Commit** `Docs: Document plan coordination and add translations`, then push to `claude/youthful-shannon-m1du8t`.
