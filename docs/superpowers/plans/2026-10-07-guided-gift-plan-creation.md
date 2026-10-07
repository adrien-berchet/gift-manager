# Guided Gift Plan Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-step guided flow (recipient, gift, occasion) that creates a gift plan identical to one made with the full form.

**Architecture:** A `RelationGuidedCreateView` (subclass of `RelationCreateView`) renders one server-side step per request (partial for HTMX, full page otherwise). Earlier answers travel as hidden inputs; each step is validated by a small step form. The final submit re-validates all steps, creates any inline gift/event in one `transaction.atomic` with the plan, and validates/saves the plan through the real `RelationForm` and `RelationCreateView.form_valid`.

**Tech Stack:** Django 5.1, HTMX, Bootstrap offcanvas, vanilla JS, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-guided-gift-plan-creation-design.md`

## Global Constraints

- Default status of a guided plan: the status whose `status_en` is `"Idea"`.
- Only gifts, events and recipients accessible to the user are accepted (`accessible_by`, `build_recipient_choices`).
- Inline gift: name only, validated by `GiftForm`. Inline event: name and date, created as `Event.ScheduleType.ONE_TIME`, validated by `EventForm`. Both owned by the user via `PermissionService.create_or_update_permission(..., permission_level=PermissionLevel.OWNER, object_attr="gift" | "event")`, plus `user_link` when the model has it (mirror `BaseCreateView.form_valid`).
- Step 3 has event, new event name/date, due date, and optional notes (`comment`). No sharing section.
- Link label on every step: "Use an empty full form" → `relation_create`; confirmation before leaving if anything was entered.
- Code, comments and docstrings in English; every new user-facing string translated in `locale/fr/LC_MESSAGES/django.po`.
- Do not change the gift-plan model or `RelationCreateView` behavior; do not add UI feature explanations or shortcut docs.
- Verify with `tox run -e py311 -- <path>`, `tox run -e lint`, `tox run -e e2e -- <path>`.

## Review Focus

- Tampered hidden fields (gift/event/recipient the user cannot access) → rejected at final submit, no objects created.
- Plan form invalid after inline gift/event were created → nothing is left behind (rollback), errors shown on the relevant step.
- Recipient with a default surprise (`default_surprise_for`) → guided plan gets the same `is_surprise` default as the full form.
- Whitespace-only new gift name, or both an existing gift and a new name given → validation error on step 2.
- Global Birthday event (no date) chosen in step 3 → no crash, due date stays empty.

---

## File Structure

- Create `gift_manager/guided_plan.py` — step forms, step constants, inline-object creation, plan form-data assembly.
- Create `gift_manager/views/relation_guided.py` — `RelationGuidedCreateView`; export in `gift_manager/views/__init__.py`; route in `gift_manager/urls.py`.
- Create templates `gift_manager/relation_guided.html` (full page) and `gift_manager/includes/relation_guided_partial.html` (step form), plus `includes/forms/guided_step_fields.html`.
- Create `gift_manager/static/gift_manager/guided-plan.js` (empty-form link confirmation), loaded from `base.html`.
- Tests: `gift_manager/tests/test_guided_plan_forms.py`, `test_guided_plan_views.py`, `e2e/test_guided_plan.py`.

---

### Task 1: Step forms and plan assembly

**Files:**
- Create: `gift_manager/guided_plan.py`
- Test: `gift_manager/tests/test_guided_plan_forms.py`

**Interfaces:**
- Produces:
  - `GUIDED_STEPS = ("recipient", "gift", "occasion")`
  - `GuidedRecipientForm(data=None, *, user)` — field `recipient` (typed choice, validated with `resolve_recipient_choice`).
  - `GuidedGiftForm(data=None, *, user)` — fields `gift` (accessible gift, optional), `new_gift_name` (optional). `clean`: stripped name; exactly one of the two required, else errors on `gift`/`new_gift_name`.
  - `GuidedOccasionForm(data=None, *, user)` — fields `event` (accessible, optional), `new_event_name`, `new_event_date`, `due_date`, `comment` (all optional). `clean`: not both `event` and `new_event_name`; a name requires a date and a date requires a name; blank `due_date` defaults to the chosen event's date or `new_event_date`.
  - `STEP_FORMS: dict[str, type]` mapping step name → form class.
  - `create_inline_objects(user, gift_form, occasion_form) -> tuple[Gift, Event | None]` — returns the chosen or newly created gift and event; new objects validated via `GiftForm`/`EventForm`, saved and owned as in Global Constraints. Must be called inside the caller's transaction.
  - `build_relation_data(user, recipient_form, occasion_form, gift, event) -> dict` — POST-like data for `RelationForm`: `recipient`, `gift` pk, `event` pk (or ""), `due_date`, `comment`, `status` (Idea pk), and `is_surprise` taken from `RelationForm(initial={"recipient": value}, user=user).initial.get("is_surprise")`.

- [ ] **Step 1: Write failing tests** in `test_guided_plan_forms.py` (use `user`, `GiftFactory`, `EventFactory`, `PersonFactory` fixtures/factories). Names and key assertions:
  - `test_recipient_form_accepts_accessible_person` / `test_recipient_form_rejects_inaccessible_person` (`"person:<other user's person id>"` invalid, error on `recipient`).
  - `test_gift_form_requires_gift_or_new_name`, `test_gift_form_rejects_both`, `test_gift_form_rejects_whitespace_name`, `test_gift_form_rejects_inaccessible_gift`.
  - `test_occasion_form_event_is_optional`, `test_occasion_form_defaults_due_date_from_event`, `test_occasion_form_defaults_due_date_from_new_event_date`, `test_occasion_form_new_event_needs_name_and_date`, `test_occasion_form_rejects_event_and_new_event`, `test_occasion_form_birthday_event_without_date_leaves_due_date_empty`.
  - `test_create_inline_objects_creates_owned_gift_and_one_time_event` (gift `user_link`/OWNER permission, `event.schedule_type == ONE_TIME`, `event.date`).
  - `test_build_relation_data_defaults_status_to_idea`, `test_build_relation_data_applies_default_surprise`.
- [ ] **Step 2:** Run `tox run -e py311 -- gift_manager/tests/test_guided_plan_forms.py` — expect FAIL (module missing).
- [ ] **Step 3:** Implement `gift_manager/guided_plan.py` per the Interfaces. Reuse `build_recipient_choices`/`resolve_recipient_choice` from `forms.py`; follow the `BaseFormMixin` styling used by `RelationForm` for widgets (`form-select`, `type="date"` ISO format for dates).
- [ ] **Step 4:** Re-run the tests — expect PASS. Run `tox run -e lint`.
- [ ] **Step 5: Commit** — `git add gift_manager/guided_plan.py gift_manager/tests/test_guided_plan_forms.py && git commit -m "Feat: Add guided gift plan step forms"` (append the attribution lines).

---

### Task 2: Guided view, route and templates

**Files:**
- Create: `gift_manager/views/relation_guided.py`, `gift_manager/templates/gift_manager/relation_guided.html`, `gift_manager/templates/gift_manager/includes/relation_guided_partial.html`, `gift_manager/templates/gift_manager/includes/forms/guided_step_fields.html`
- Modify: `gift_manager/views/__init__.py` (import + `__all__`), `gift_manager/urls.py` (next to `relation_create`, around line 188)
- Test: `gift_manager/tests/test_guided_plan_views.py`

**Interfaces:**
- Consumes: Task 1 (`GUIDED_STEPS`, `STEP_FORMS`, `create_inline_objects`, `build_relation_data`), `RelationForm`, `RelationCreateView`.
- Produces: URL name `gift_manager:relation_guided_create` (`relations/guided/`); `RelationGuidedCreateView`. Contract:
  - `GET ?step=N` (default 1, clamped to 1–3) renders step N with empty/prefilled values.
  - POST fields: `step` (current, 1–3), `nav` (`next` | `back`), plus all step fields (current step's visible inputs; other steps' values as hidden inputs, built from POST for known field names only).
  - `back` re-renders step−1 without validating. `next` on steps 1–2 validates the current step with its form: valid → render step+1, invalid → re-render the same step with errors.
  - `next` on step 3 = final submit: re-validate all three step forms; if any invalid, render the earliest invalid step with errors. Otherwise inside `transaction.atomic()`: `create_inline_objects`, `RelationForm(build_relation_data(...), user=request.user)`; valid → `self.form_valid(form)` (set `self.object = None` first); invalid → `transaction.set_rollback(True)` and re-render step 3 with the form's errors shown in the non-field error area.
  - Context: `step`, `steps` (list of `{"number", "name", "label", "state"}` for the progress indicator, with `aria-current="step"` on the current one), `step_form`, `carried` (list of `(name, value)` hidden pairs), `full_form_url`. Template attributes: `data-form-type="relation-guided"`, `hx-post` + `hx-target="this"` + `hx-swap="outerHTML"` + `hx-indicator="#offcanvasLoading"` as in `relation_form_partial.html`; plain `action`/`method="post"` so the non-HTMX page works; Enter submits "Next" (the Next button is the first submit button in DOM order, Back uses `name="nav" value="back"` and `formnovalidate`).
  - On the last step the primary button reads "Create gift plan"; success returns the usual HTMX close/notification response or redirect to `relations`.

- [ ] **Step 1: Write failing tests** with `authenticated_client`. Use `HTTP_HX_REQUEST="true"` for the partial variant. Names and key assertions:
  - `test_get_step_one_renders_recipient_field` (200, template partial for HTMX, full page without).
  - `test_next_with_invalid_step_stays_on_step_with_error` / `test_next_advances_and_carries_values_as_hidden_inputs`.
  - `test_back_preserves_entered_values`.
  - `test_end_to_end_creates_plan_with_existing_gift` (status Idea, owner permission for the user, `user_link`, due date from event).
  - `test_end_to_end_with_new_gift_and_new_event` (gift + one-time event created and owned, plan links both).
  - `test_guided_plan_matches_full_form_plan` — create one plan via `relation_create` POST and one via guided with equal inputs; compare `recipient_key`, `gift`, `event`, `status`, `due_date`, `comment`, `is_surprise`, permission level.
  - `test_group_recipient_works`.
  - `test_tampered_inaccessible_gift_is_rejected_without_side_effects` (no new `Relation`/`Gift`/`Event` rows).
  - `test_invalid_plan_rolls_back_inline_objects` (e.g. patch `RelationForm.is_valid`/force an invalid recipient on the final POST; assert gift and event counts unchanged and the error is rendered).
  - `test_requires_login` (redirects to login).
  - `test_full_form_link_points_to_relation_create`.
- [ ] **Step 2:** Run `tox run -e py311 -- gift_manager/tests/test_guided_plan_views.py` — expect FAIL.
- [ ] **Step 3:** Implement the view, templates and route. Render the visible step fields through the existing `includes/forms/field.html`; the full-page template extends `base.html` like `create_form.html`. Cancel in the offcanvas uses `data-bs-dismiss="offcanvas"`; on the page, a link to `relations`.
- [ ] **Step 4:** Re-run the view tests and `test_guided_plan_forms.py` — expect PASS. Run `tox run -e py311 -- gift_manager/tests/test_locale_coverage.py gift_manager/tests/test_offcanvas_template.py` to catch template regressions; `tox run -e lint`.
- [ ] **Step 5: Commit** — `Feat: Add guided gift plan creation view`.

---

### Task 3: Entry points and empty-form confirmation

**Files:**
- Modify: `gift_manager/templates/gift_manager/relation_list.html` (header actions near line 25, and the empty-state button near line 129), `gift_manager/templates/gift_manager/home.html` (create buttons near lines 910 and 1030), `gift_manager/templates/gift_manager/base.html` (script tag)
- Create: `gift_manager/static/gift_manager/guided-plan.js`
- Test: extend `gift_manager/tests/test_guided_plan_views.py`

**Interfaces:**
- Consumes: URL `gift_manager:relation_guided_create`.
- Produces: a "Guided" secondary button (`btn btn-outline-primary`, `data-action="create"` so `app-shell.js` loads it into `#editPanel`) beside each existing "Create new gift plan" button. The "Use an empty full form" link in the step template carries `data-action="create"`, `data-guided-full-form` and `data-confirm-message="<translated text>"`. `guided-plan.js` adds a delegated click listener on the link: if any non-`csrfmiddlewaretoken`/`step`/`nav` input of the enclosing form has a non-empty value, `window.confirm(message)`; when declined, `preventDefault()` and `stopPropagation()` (so `app-shell.js`'s document-level create handler does not run). Message: "The data you entered will be discarded. Continue?".

- [ ] **Step 1: Write failing tests:** `test_relation_list_links_to_guided_flow` and `test_home_links_to_guided_flow` (response contains the `relation_guided_create` URL), `test_guided_template_exposes_confirm_message_on_full_form_link`.
- [ ] **Step 2:** Run them — expect FAIL.
- [ ] **Step 3:** Add the buttons, the link attributes and `guided-plan.js` (vanilla, no dependencies; load it in `base.html` next to the other app scripts).
- [ ] **Step 4:** Run the tests — expect PASS; run `tox run -e py311 -- gift_manager/tests/test_quick_action_buttons.py gift_manager/tests/test_phase5_frontend_contracts.py` to check existing frontend contracts; `tox run -e lint`.
- [ ] **Step 5: Commit** — `Feat: Add guided flow entry points`.

---

### Task 4: End-to-end test, translations and docs

**Files:**
- Create: `gift_manager/tests/e2e/test_guided_plan.py`
- Modify: `locale/fr/LC_MESSAGES/django.po` (+ compiled `.mo` if tracked), `docs/ideas/0016-guided-gift-plan-creation.md` (status), `docs/ideas/README.md`, `docs/ai/architecture.md` (one bullet under Patterns)

- [ ] **Step 1: Write the e2e test** (pattern of `tests/e2e/test_relation_reaction.py`: `login`, `seed_data_e2e`, `@pytest.mark.django_db(transaction=True)`, `@pytest.mark.frontend`, `@pytest.mark.e2e`). Tests:
  - `test_guided_flow_creates_plan_with_new_gift_and_event`: open `/relations/`, click "Guided", pick a recipient, Next, type a new gift name, Next, type a new event name + date, add a note, click "Create gift plan"; expect the panel to close and the plan to exist in the DB (status Idea, new gift and event, due date = event date).
  - `test_validation_error_stays_on_step`: Next on step 2 with nothing entered shows the error and the step 2 heading.
  - `test_back_keeps_values_and_keyboard_enter_advances`: Enter in step 1 advances; Back shows the prior selection.
  - `test_empty_full_form_link_confirms_when_data_entered`: register `page.once("dialog", ...)`; dismissing keeps the guided panel, accepting opens the blank full form.
- [ ] **Step 2:** Run `tox run -e e2e -- gift_manager/tests/e2e/test_guided_plan.py` — fix any failures in the earlier tasks' code (including checking that `unsaved-changes.js` does not block the legitimate final submit or double-prompt on step navigation).
- [ ] **Step 3:** Run `python manage.py makemessages -l fr`, translate every new string in the `.po` (progress labels, step headings, buttons, error messages, confirm message, "Guided", "Use an empty full form"), then `python manage.py compilemessages`. Run `tox run -e py311 -- gift_manager/tests/test_locale_coverage.py`.
- [ ] **Step 4:** Docs: follow `docs/ideas/README.md` conventions to mark idea 0016 implemented (status line, move to `docs/ideas/implemented/` as done for earlier ideas, update the README index); add an `architecture.md` bullet: guided creation lives in `gift_manager/guided_plan.py` and `views/relation_guided.py`, final save goes through `RelationForm`.
- [ ] **Step 5:** Run the full relevant suites: `tox run -e py311 -- gift_manager/tests/test_guided_plan_forms.py gift_manager/tests/test_guided_plan_views.py gift_manager/tests/test_locale_coverage.py`, `tox run -e lint`, and the e2e file. Then commit — `Feat: Add e2e tests, translations and docs for guided plan creation` — and push the branch.

---

## Self-Review

- **Spec coverage:** route/view/steps → Tasks 1–2; hidden-field state, per-step validation, progress/back → Task 2; empty-form link + confirmation → Tasks 2–3; final save via `RelationForm`/`form_valid`, atomic inline creation, access checks → Tasks 1–2; entry points → Task 3; unit/e2e tests, French, docs → Tasks 1–4.
- **Type consistency:** names (`GUIDED_STEPS`, `STEP_FORMS`, `create_inline_objects`, `build_relation_data`, `relation_guided_create`, `data-guided-full-form`) are used identically across tasks.
- **Open verification (to settle while implementing):** whether `unsaved-changes.js` interferes with step navigation; Task 4 Step 2 covers it with the e2e run.
