# Guided Gift Plan — Full Data For New Objects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the guided flow create a new person, gift and event with all of their data, and set the plan's status, link, price and surprise flag in step 3.

**Architecture:** Each step form composes the real model form (`PersonForm`, `GiftForm`, `EventForm`) as a prefixed sub-form that is only validated when its identifying field is filled; the other fields sit in a native `<details>` "More details". The final save re-validates all steps and creates the new person, gift and event inside the transaction that saves the plan through `RelationForm`.

**Tech Stack:** Django 5.2 (venv), HTMX 1.9, Bootstrap, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-guided-gift-plan-creation-design.md` (revision 2). This plan builds on the code of `docs/superpowers/plans/2026-10-07-guided-gift-plan-creation.md` (already implemented).

## Global Constraints

- Recipient creatable inline: a **person** only; groups stay selectable, never created inline.
- Identifying fields: person `first_name`, gift `name`, event `name`. A new-object block counts as filled when its identifying field is non-empty after stripping.
- Sub-form prefixes: `new_person`, `new_gift`, `new_event` (input names `new_person-first_name`, ids `id_new_gift-name`, …).
- Rule per step: choose an existing object **or** fill the new one, not both; never validate or render errors of an unfilled sub-form.
- A new event defaults to `Event.ScheduleType.ONE_TIME`.
- Plan details in step 3: `due_date`, `comment` visible; `status` (default status whose `status_en` is `"Idea"`), `url`, `price`, `is_surprise` under "More details". `is_surprise` is a Yes/No select (always posted, so it survives Back/Next); default from `default_surprise_for` for an existing recipient, `False` for a new person.
- New objects are owned by the user exactly as the regular create views do (`BaseCreateView.form_valid`: `user_link` when the model has it, then `PermissionService.create_or_update_permission(..., OWNER, object_attr=...)`); gift tags and person interests/groups are limited to what the user can access (the sub-forms/views already scope them; the gift tag queryset is `GiftTag.objects.accessible_by(user)`).
- Multi-valued inputs (groups, interests, tags) are carried between steps with every value.
- Code, comments, docstrings in English; every new user-facing string translated in `locale/fr/LC_MESSAGES/django.po` (glossary: gift plan = "projet de cadeau"); no native `confirm` dialogs.
- Run tests with the venv: `. /tmp/gm-env.sh; pytest <paths> -q -p no:cacheprovider`; e2e additionally `export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers DJANGO_ALLOW_ASYNC_UNSAFE=true` and `--browser chromium -m frontend`; lint `ruff check gift_manager` / `ruff format`.
- Never commit `gift_manager/tests/e2e/test_tmp_debug.py` (stray file; stage files by explicit path, never `git add -A`).

## Review Focus

- Tampered `new_person-groups` / `new_gift-tags` / `new_person-interests` values the user cannot access → rejected, nothing created (Task 1 form test + Task 2 view test).
- Both an existing object and a new one filled, or only "More details" values filled without the identifying field → error on the chooser, typed values kept on re-render (Task 1).
- Plan form rejected after a new person (with groups), gift and event were created → none of them nor the group membership persists (Task 2).
- Multi-valued values survive Back → Next and reach the final save (Task 2).
- Surprise "No" chosen in step 3 survives Back → Next (Task 2); default is Yes for a recipient linked to another user (Task 1/2).

---

## File Structure

- Modify `gift_manager/guided_plan.py` — new-object step forms, plan fields, creation helpers.
- Modify `gift_manager/views/relation_guided.py` — carry/prefill with sub-forms, new final save.
- Modify templates: `includes/forms/guided_step_fields.html` (rewrite), create `includes/forms/guided_new_object.html`, adjust `includes/relation_guided_partial.html` error summary.
- Tests: update `tests/test_guided_plan_forms.py`, `tests/test_guided_plan_views.py`, `tests/e2e/test_guided_plan.py`.
- Docs/i18n: `locale/fr/LC_MESSAGES/django.po|mo`, `docs/ai/architecture.md`, idea doc scope note.

---

### Task 1: Step forms with new-object sub-forms, plan fields, creation helpers

**Files:**
- Modify: `gift_manager/guided_plan.py`
- Test: `gift_manager/tests/test_guided_plan_forms.py`

**Interfaces:**
- Produces (all in `guided_plan.py`):
  - `class _NewObjectStepForm(_GuidedStepForm)` with class attributes `chooser_name: str`, `new_form_class: type[forms.ModelForm]`, `new_prefix: str`, `identifying_field: str`, `visible_new_fields: tuple[str, ...]`, `choose_message`, `both_message` (lazy strings); constructor `(data=None, *, user, initial_values=None, **kwargs)` where `initial_values` is a QueryDict/dict of posted values used only to prefill an *unbound* form (own fields **and** sub-form, via `field.widget.value_from_datadict`).
    - `new_form` — the sub-form: bound to `data` only when `new_requested`, otherwise unbound with `initial` taken from `data` (or `initial_values`) so typed values are kept without validating.
    - `new_requested -> bool` (bound and identifying field filled).
    - `input_names() -> list[str]` — every POST name of the step (own fields + `new_form.add_prefix(name)` for each sub-form field).
    - `new_visible_fields()` / `new_detail_fields()` → lists of `BoundField` of `new_form` (visible = `visible_new_fields`, details = the rest, in form order); `details_open -> bool` (sub-form has errors, or any detail field holds a value).
    - `clean()`: existing chosen **and** new requested → error on the chooser (`both_message`); neither → error on the chooser (`choose_message`). `is_valid()` = base validity and (`not new_requested` or `new_form.is_valid()`).
  - `GuidedRecipientForm` (`chooser_name="recipient"`, `PersonForm`, `new_person`, `first_name`, visible `("first_name",)`; chooser required unless new requested; the existing value is checked with `resolve_recipient_choice`).
  - `GuidedGiftForm` (`gift`, `GiftForm`, `new_gift`, `name`, visible `("name",)`; `new_form.fields["tags"].queryset = GiftTag.objects.accessible_by(user).order_by("name")`).
  - `GuidedOccasionForm(data=None, *, user, recipient_value: str = "", initial_values=None)` (`event`, `EventForm`, `new_event`, `name`, visible `("name", "date")`; new-event `schedule_type` initial `ONE_TIME`) plus plan fields `due_date`, `comment`, `status`, `url`, `price` (taken from `RelationForm(user=user).fields`, `status` initial = the Idea status pk and no empty choice) and `is_surprise` (Yes/No select as in Global Constraints, initial from `RelationForm(initial={"recipient": recipient_value}, user=user).initial.get("is_surprise")`). `clean()` keeps the due-date default: blank → existing event's `next_occurrence()`, else the new event's `instance.next_occurrence()` or its cleaned `date`.
  - `STEP_FORMS` unchanged keys.
  - `class InlineObjects(NamedTuple)`: `recipient_value: str`, `gift: Gift`, `event: Event | None`.
  - `create_inline_objects(user, recipient_form, gift_form, occasion_form) -> InlineObjects` — creates the new person / gift / event from each form's `new_form` (in that order, via `_save_owned`) when `new_requested`, otherwise uses the chosen existing objects; `recipient_value` is `person:<person_id>` for a new person. Must run inside the caller's transaction.
  - `build_relation_data(user, inline: InlineObjects, occasion_form) -> dict` — POST-like data for `RelationForm`: `recipient`, `gift`, `event`, `due_date`, `comment`, `status` (pk of the chosen status), `url`, `price`, `is_surprise`.
- The former `new_gift_name`, `new_event_name`, `new_event_date` fields and the old signatures of `create_inline_objects` / `build_relation_data` are removed; update every caller/test.

- [ ] **Step 1: Write failing tests** (replace the old ones in `test_guided_plan_forms.py`; keep their intent). Names and assertions:
  - Recipient: `test_recipient_form_accepts_new_person_with_details` (`new_person-first_name`, `-family_name`, `-email_address`, `-birthday_day/_month`, `-notes`; valid; `new_requested`), `test_recipient_form_ignores_new_person_details_without_first_name` (only `-email_address` → invalid, error on `recipient`, `new_form` unbound, `new_form.initial["email_address"]` kept), `test_recipient_form_rejects_both_existing_and_new`, `test_recipient_form_validates_new_person_when_requested` (invalid birthday day 31/month 2 → `new_form` errors, step invalid), `test_recipient_form_does_not_validate_new_person_when_existing_chosen`, `test_recipient_form_rejects_inaccessible_group_for_new_person` (group the user cannot edit in `new_person-groups` → invalid).
  - Gift: `test_gift_form_accepts_new_gift_with_comment_price_url_tags`, `test_gift_form_rejects_inaccessible_tag`, plus the earlier name/whitespace/both/inaccessible-gift cases ported to `new_gift-name`.
  - Occasion: ported due-date/event cases to `new_event-name`/`new_event-date`; `test_occasion_form_new_event_defaults_to_one_time`, `test_occasion_form_new_recurring_event_needs_recurrence` (schedule `recurring`, date, no recurrence → `new_form` error), `test_occasion_form_new_event_without_date_is_invalid_for_one_time`, `test_occasion_form_plan_fields_defaults` (`status` initial is Idea, `is_surprise` initial `"false"`), `test_occasion_form_surprise_default_for_linked_recipient` (person linked to another user → `"true"`), `test_occasion_form_input_names_include_prefixed_fields`.
  - Creation: `test_create_inline_objects_creates_person_gift_event_with_all_data`, `test_create_inline_objects_reuses_existing_objects`, `test_created_objects_match_regular_create_views` — POST the same data to the person, gift and event create URLs (`gift_manager:person_create`, `gift_create`, `event_create`; look them up in `gift_manager/urls.py`) and compare every model field plus owner permission, `user_link`, groups, interests, tags with the guided result.
  - `test_build_relation_data_carries_plan_fields` (status, url, price, comment, `is_surprise`), `test_build_relation_data_for_new_person_uses_person_recipient_value`.
- [ ] **Step 2:** `. /tmp/gm-env.sh; pytest gift_manager/tests/test_guided_plan_forms.py -q -p no:cacheprovider` — expect FAIL (old API / missing names).
- [ ] **Step 3:** Implement the interfaces above in `gift_manager/guided_plan.py`. Approach notes: build `new_form` with `new_form_class(data if requested else None, prefix=new_prefix, user=user, initial=...)` (`PersonForm` takes `user=`; `GiftForm`/`EventForm` do not, so scope `tags` in `GuidedGiftForm`); prefill initial with `field.widget.value_from_datadict(values, {}, new_form.add_prefix(name))`; keep `_save_owned(form, user, object_attr)` (call `form.is_valid()` first) and use `"person"`, `"gift"`, `"event"` as `object_attr`.
- [ ] **Step 4:** Re-run the file — expect PASS. Run `ruff check gift_manager && ruff format gift_manager/guided_plan.py gift_manager/tests/test_guided_plan_forms.py`.
- [ ] **Step 5: Commit** `git add gift_manager/guided_plan.py gift_manager/tests/test_guided_plan_forms.py && git commit -m "Feat: Let guided steps create full recipients, gifts and events"` (append the attribution lines).

---

### Task 2: View — carry multi-valued inputs, prefill, final save with new objects

**Files:**
- Modify: `gift_manager/views/relation_guided.py`
- Modify: `gift_manager/templates/gift_manager/includes/relation_guided_partial.html` (error summary)
- Test: `gift_manager/tests/test_guided_plan_views.py`

**Interfaces:**
- Consumes: Task 1 (`STEP_FORMS`, `GUIDED_STEPS`, `input_names()`, `initial_values`, `recipient_value`, `InlineObjects`, `create_inline_objects`, `build_relation_data`).
- Produces: contract changes of `RelationGuidedCreateView`:
  - `_step_form(step, data=None, *, initial_values=None)` passes `recipient_value` to the occasion form: the posted `recipient` value, or `""` when a new person is requested/absent.
  - `_initial_form(step, data)` → `self._step_form(step, initial_values=data)` (no manual `initial` dict).
  - `carried` = `[(name, value)]` for every other step, `for name in other.input_names() for value in data.getlist(name)` (empty on GET).
  - `_finish`: re-validate all steps; inside `transaction.atomic()`: `inline = create_inline_objects(user, recipient_form, gift_form, occasion_form)`, `RelationForm(build_relation_data(user, inline, occasion_form), user=user)`, `form_valid` on success; on rejection collect messages **before** `transaction.set_rollback(True)` and show them on the occasion form (non-field errors).
  - The error summary in `relation_guided_partial.html` also lists the errors of `step_form.new_form` when `step_form.new_requested`.

- [ ] **Step 1: Write failing tests** in `test_guided_plan_views.py` (update existing ones to the prefixed names, e.g. `new_gift-name`, `new_event-name`, `new_event-date`, `new_event-schedule_type`):
  - `test_end_to_end_creates_new_person_with_details_gift_and_event` (person: first/family name, email, birthday, notes, one editable group, one interest; gift: comment, url, price, one tag; event: recurring yearly; plan: status Planned, url/price override, due date) — assert every created object and the plan; owners.
  - `test_new_person_matches_person_create_view` is covered in Task 1; here `test_guided_plan_with_new_objects_matches_full_form_plan` compares the plan created through guided vs the full form pointing at the same new objects.
  - `test_tampered_inaccessible_group_for_new_person_is_rejected_without_side_effects` (no `Person`/`Gift`/`Event`/`Relation` created, step 1 re-rendered with the error).
  - `test_invalid_plan_rolls_back_new_person_gift_event_and_group_membership` (patch `RelationForm.is_valid` → False; assert counts unchanged and `group.person_set` unchanged).
  - `test_multi_valued_inputs_survive_back_and_next` (post step 1 with `new_person-groups` ×2 and `new_person-interests` ×2, go to step 2 and back; `carried`/prefill contain both values each time).
  - `test_surprise_no_survives_back_and_next` (step 3 posts `is_surprise=false` for a recipient whose default is true; Back then Next keeps `"false"` in the step 3 form).
  - `test_new_object_error_is_shown_on_its_step` (invalid new person birthday → step 1, `new_form` errors rendered in the content).
  - `test_details_open_when_values_present` (response content for a step with a filled detail field contains `<details` with `open`).
- [ ] **Step 2:** Run the file — expect FAIL.
- [ ] **Step 3:** Implement the view changes above and the template error-summary tweak; keep the existing rollback pattern (messages first, then `set_rollback(True)`).
- [ ] **Step 4:** Run `pytest gift_manager/tests/test_guided_plan_forms.py gift_manager/tests/test_guided_plan_views.py gift_manager/tests/test_phase5_frontend_contracts.py -q -p no:cacheprovider` — expect PASS; `ruff check gift_manager`.
- [ ] **Step 5: Commit** `Feat: Save new recipients, gifts and events from the guided flow`.

---

### Task 3: Templates, e2e, translations and docs

**Files:**
- Modify: `gift_manager/templates/gift_manager/includes/forms/guided_step_fields.html` (rewrite)
- Create: `gift_manager/templates/gift_manager/includes/forms/guided_new_object.html`
- Modify: `gift_manager/tests/e2e/test_guided_plan.py`
- Modify: `locale/fr/LC_MESSAGES/django.po`, `django.mo`; `docs/ai/architecture.md`; `docs/ideas/implemented/0016-guided-gift-plan-creation.md`

**Interfaces:**
- Consumes: Task 2 context (`step`, `step_form`) and `step_form.new_visible_fields()`, `new_detail_fields()`, `details_open`, `new_form`.
- Produces: `guided_new_object.html` (include with `step_form` and a `heading` string): renders "Or create a new …" heading, the visible fields, then `<details class="guided-new-details"{% if step_form.details_open %} open{% endif %}><summary>More details</summary>` with the detail fields. Person birthday fields render as in `person_fields.html` (locale-ordered `new_form.birthday_fields` row, not as three separate fields); groups and interests use the searchable multi-select markup of `field.html` (`searchable=True`); event `schedule_type` as radio list and `date`/`recurrence` fields. Step 3 renders `due_date` and `comment`, then a second `<details>` "More details" with `status`, `url`, `price`, `is_surprise`.

- [ ] **Step 1: Write failing e2e tests** in `test_guided_plan.py` (update the existing ones to the new ids: `#id_new_gift-name`, `#id_new_event-name`, `#id_new_event-date`; the flatpickr date helper now targets `new_event-date`):
  - `test_guided_flow_creates_new_person_gift_and_event_with_details`: step 1 type a new first name, open "More details" (click the `summary`), fill family name, email, notes, pick a group; step 2 new gift name, details: comment, link, price; step 3 new event name + date, details: choose "Repeating" + yearly; plan details: status Planned, surprise No; create; assert DB (person with group/notes, gift with price/url, event recurring yearly, plan status Planned, `is_surprise` False).
  - `test_back_keeps_multi_valued_selection` (select two groups, Next, Back → both still selected).
  - `test_new_object_error_opens_details` (invalid birthday → the details section is open and the error visible).
- [ ] **Step 2:** Run `pytest gift_manager/tests/e2e/test_guided_plan.py … --browser chromium -m frontend` — expect FAIL.
- [ ] **Step 3:** Implement the templates. Keep `field.html` for every field; wrap each `<details>` content so submitted values are present even when collapsed (native `<details>` already submits collapsed fields).
- [ ] **Step 4:** Re-run the guided e2e file plus `test_unsaved_changes_snapshots.py` and `test_form_loading_state.py` — expect PASS.
- [ ] **Step 5:** Translations: `python manage.py makemessages -l fr`, translate every new string (heading "Or create a new recipient/gift/event" variants, "More details", step/field labels not already translated, error messages), clear `#, fuzzy` entries you touched, `python manage.py compilemessages`; run `pytest gift_manager/tests/test_locale_coverage.py -q -p no:cacheprovider` — expect PASS.
- [ ] **Step 6:** Docs: add to the `architecture.md` guided-creation bullet that new objects reuse `PersonForm`/`GiftForm`/`EventForm` as prefixed sub-forms; update the idea doc's Possible Scope (inline creation now covers full data of person, gift, event; group creation excluded). Run the full non-browser suite (`pytest gift_manager -q -p no:cacheprovider -m "not frontend and not playwright" --ignore=gift_manager/tests/e2e`) and the e2e files named above — expect all PASS.
- [ ] **Step 7: Commit** `Feat: Show full details for new objects in the guided flow` and push (`git push -u origin claude/guided-gift-plan-creation-cxp3aa`, retrying on server errors).

---

## Self-Review

- **Spec coverage:** new person/gift/event with full data (Tasks 1–3); reuse of real forms and their validation (Task 1); choose-or-new rule and unfilled-sub-form handling (Task 1); plan status/link/price/surprise (Tasks 1–2); multi-valued carry (Task 2); one-transaction rollback incl. group membership (Task 2); equivalence with create views (Task 1) and full-form plan (Task 2); "More details" disclosure, auto-open (Task 3); French and docs (Task 3). Out of scope items (inline group, sharing) have no task by design.
- **Type consistency:** `InlineObjects`, `create_inline_objects(user, recipient_form, gift_form, occasion_form)`, `build_relation_data(user, inline, occasion_form)`, `input_names()`, `initial_values`, `recipient_value`, `new_form`, `new_requested`, `new_visible_fields()`, `new_detail_fields()`, `details_open` are used with the same names across tasks.
- **Review Focus:** each line has its test in Tasks 1–2 (tamper tests, both/details-only, rollback incl. groups, multi-valued carry, surprise).
