# Recipient Preference Profiles And Feedback Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Before starting:** set the idea's status to `Ready` in `docs/ideas/0027-recipient-preference-profiles-and-feedback-persistence.md` and `docs/ideas/README.md`, and add a "Plan" line to the idea pointing at this plan file.

**Recommended execution:** subagent-driven (fresh implementer + reviewer per task). The 6 tasks hand typed interfaces to each other, and a shipped privacy mistake (leaking surprise gifts to linked users, or unscrubbed names in AI payloads) is costly.

**Goal:** Bridge the gap between ephemeral event logs and durable recipient preferences by:
1. Synthesizing an all-time deterministic tag preference profile across 100% of a recipient's history and dismissals to power the AI prompt without token bloat or multi-year blind spots.
2. Providing a seamless, opt-in mechanism to persist high-signal feedback from suggestion dismissals and plan reactions/abandonment directly into `Person.notes` (with provenance tags) and `Person.interests`.

**Architecture:**
- A new `PreferenceProfile` dataclass and `build_preference_profile` helper in `gift_manager/suggestions/history.py`, called only during AI payload construction (`_ai_context`).
- Direct tag tracking via `direct_tag_ids` on `HistoryItem` to prevent ancestor category explosion.
- A unified domain module `gift_manager/person_profile.py` encapsulating `promotion_target` (guarding against group recipients, viewer permissions, and surprise gift leaks), atomic provenance note appending (`append_person_provenance_note`), and interest tag promotion (`promote_tags_to_person_interests`).
- Frictionless UI additions: a single opt-in checkbox in `gift_suggestion_item.html` dropdown menu and an opt-in checkbox in `relation_reaction` and `RelationForm` edit flows.

**Tech Stack:** Django 5.1, PostgreSQL, HTMX, Bootstrap, pytest/tox, factory_boy, Playwright.

**Spec:** `docs/ideas/0027-recipient-preference-profiles-and-feedback-persistence.md`

---

## Decisions Taken During Planning & Deliberation

These refine the spec and resolve all open questions:

1. **Surprise Plan Protection:** A recipient who is linked to a user account (`Person.user_link`) has owner permissions on their own profile and sees their own `Person.notes`. To prevent leaking surprise gifts, `promotion_target` strictly returns `None` for any relation where `is_surprise=True`. Furthermore, if `person.user_link_id` is set (and is not the acting user), the UI renders an explicit privacy warning: *"{name} can see their profile notes"*.
2. **Notes Truncation & Scrubbing:** In `_build_recipient_info`, the naive 500-character cut is replaced by a line-aware windowing algorithm. It preserves up to 400 characters of baseline bio plus the newest provenance lines fitting within an 800-character budget. Crucially, notes are scrubbed *before* truncation to prevent boundary leakage.
3. **All-Time Profile Computation:** Unlike the catalogue strategy (which already scores the entire history), the prompt was previously capped to 50 items. The new `build_preference_profile` aggregates all plans and dismissals into three distinct buckets: `liked` (plans rated 4–5★), `owned_or_practiced` (dismissed with that reason), and `disliked` (plans rated 1–2★ or dismissed with `dislikes`). Direct tags are counted and capped at the top 20 per bucket. `PROMPT_VERSION` is bumped to 3.
4. **Single-Checkbox Dismissal UX:** In `gift_suggestion_item.html`, a single checkbox is placed at the top of the dropdown: *"Also save to {name}'s profile"*. The clicked reason dictates the action:
   - `already_owned_or_practiced`: tags added to `Person.interests` (up to 5 direct tags, skipping existing ancestor coverage) **and** a provenance note appended.
   - `dislikes` or `custom`: provenance note appended.
   - `too_expensive` or no reason: no-op with informational feedback toast.
5. **Plan Reaction Trigger:** In `relation_reaction` and `RelationForm`, promotion is offered whenever `reaction_note` is non-empty (for both given and abandoned plans), capturing notes like *"Allergic to wool"* or *"Loved it, wants the sequel"*.
6. **Concurrency & Idempotency:** Note appends use `select_for_update()` inside an atomic transaction with `update_fields=["notes"]`. Appends deduplicate by matching `{source_label}: {item_name}]: {text}` (ignoring the timestamp) to avoid duplicates across repeated edits.

---

## Global Constraints

- **Privacy & Permissions:** Only users with `PermissionLevel.EDITOR` or higher on the `Person` may promote notes or interests. If the user only has viewer permissions on the person (even if they can edit the plan), promotion controls are hidden and requests silently ignored.
- **Surprise Preservation:** Never promote notes or tags from relations with `is_surprise=True`.
- **Anonymisation:** All notes and gift names continue to be scrubbed via `scrub_text` before inclusion in AI payloads. Tag names remain controlled vocabulary.
- **Zero-Friction Default:** Standard 1-click dismissal and card quick actions must remain completely non-blocking and instant.
- **Translations:** All user-facing strings must be localized into French via `locale/fr/LC_MESSAGES/django.po` and compiled with `python manage.py compilemessages -l fr`. Do not run `makemessages --no-location`.

---

## Review Focus

- **Surprise leak regression:** A surprise plan marked abandoned with a reaction note must never offer or execute note promotion to the person's profile.
- **Direct tag isolation:** Ancestor tags must not artificially inflate all-time profile counts (e.g. liking a Lego set must increment "Lego", not "Toys" or "Gifts").
- **Deduplication:** Submitting an edit on an already-abandoned plan with the checkbox ticked must not duplicate the note line if the text has not changed.
- **Non-blocking failures:** If note promotion fails or is a no-op (e.g. `too_expensive`), the underlying plan edit or dismissal must still succeed completely.

---

## Task 1: All-Time History Tag Profiling & Query Consolidation

Add `direct_tag_ids` to `HistoryItem`, refactor dismissed suggestions queries into a shared helper, and implement `build_preference_profile` in `gift_manager/suggestions/history.py`.

### Interfaces
- `HistoryItem.direct_tag_ids: frozenset[int]`
- `dismissed_suggestions_for(user, recipient, visible_tag_ids, limit: int = 500) -> QuerySet[GiftSuggestion]`
- `PreferenceProfile(liked_tags: tuple[tuple[str, int], ...], owned_tags: tuple[tuple[str, int], ...], disliked_tags: tuple[tuple[str, int], ...])`
- `build_preference_profile(user, history: RecipientHistory, visible_tag_ids: set[int]) -> PreferenceProfile`

- [x] **Step 1: Write failing tests**
  In `gift_manager/tests/suggestions/test_history.py`:
  - `test_history_item_carries_direct_tag_ids_without_ancestors`: verify `tag_ids` has ancestors while `direct_tag_ids` has only direct visible tags.
  - `test_build_preference_profile_aggregates_three_buckets_with_direct_counts`: verify plans rated >=4 go to `liked_tags`, <=2 go to `disliked_tags`, dismissals with `already_owned_or_practiced` go to `owned_tags`, and dismissals with `dislikes` go to `disliked_tags`.
  - `test_build_preference_profile_respects_50_plus_history_and_visibility`: verify plans beyond the 50-item mark are included in profile counts, but hidden tags are excluded.

- [x] **Step 2: Run tests to verify failure**
  ```bash
  tox run -e py311 -- gift_manager/tests/suggestions/test_history.py
  ```

- [x] **Step 3: Implement data structures and profile builder**
  - In `gift_manager/suggestions/history.py`:
    - Add `direct_tag_ids: frozenset[int]` to `HistoryItem`. Populate it in `build_recipient_history` from `gift_visible_tags`.
    - Define `dismissed_suggestions_for(user, recipient, visible_tag_ids, limit=500)` pulling the common query from `catalogue.py` and `ai/strategy.py`.
    - Define `PreferenceProfile` and `build_preference_profile(user, history, visible_tag_ids)`.
    - Tally direct tag IDs across all `history.items` and dismissed suggestions, sort by frequency descending then name ascending, cap each bucket at 20.
  - Refactor `_compute_dismissed_signals` in `catalogue.py` to use `dismissed_suggestions_for`.

- [x] **Step 4: Verify tests pass and query count remains bounded**
  ```bash
  tox run -e py311 -- gift_manager/tests/suggestions/test_history.py gift_manager/tests/suggestions/test_catalogue.py
  ```

---

## Task 2: AI Prompt Integration, System Prompt Rule 4 & Notes Windowing

Integrate `PreferenceProfile` into `build_ai_payload`, bump `PROMPT_VERSION` to 3, update `SYSTEM_PROMPT` Rule 4, and implement robust line-aware notes windowing with pre-truncation scrubbing.

### Interfaces
- `PROMPT_VERSION = 3` in `gift_manager/suggestions/ai/prompt.py`.
- Payload key `"all_time_preferences": {"liked_tags": [...], "owned_or_practiced_tags": [...], "disliked_tags": [...]}`.
- `window_person_notes(notes: str, terms: list[str], max_length: int = 800) -> str`.

- [x] **Step 1: Write failing tests**
  In `gift_manager/tests/suggestions/test_ai_prompt.py`:
  - `test_build_ai_payload_includes_all_time_preferences`: verify payload contains three tag lists with counts.
  - `test_window_person_notes_preserves_baseline_and_recent_provenance`: test notes >800 chars keep first 400 chars of bio and most recent `[YYYY-MM-DD - ...]` lines, joined by `…`.
  - `test_window_person_notes_scrubs_before_truncation`: verify names straddling the character cut are scrubbed and never leak fragments.

- [x] **Step 2: Run tests to verify failure**
  ```bash
  tox run -e py311 -- gift_manager/tests/suggestions/test_ai_prompt.py
  ```

- [x] **Step 3: Implement prompt updates and notes windowing**
  - In `gift_manager/suggestions/ai/prompt.py`:
    - Bump `PROMPT_VERSION = 3`.
    - Update `SYSTEM_PROMPT` Rule 4 to explicitly reference `all_time_preferences` as long-term verified affinities and avoidances.
    - Implement `window_person_notes(notes, terms, max_length=800)` using regex `r"^\[\d{4}-\d{2}-\d{2} - "` to separate provenance lines from baseline text. Scrub with `scrub_text` before applying character limits.
    - Update `_build_recipient_info` to use `window_person_notes`.
    - Update `build_ai_payload` to accept `preference_profile: PreferenceProfile | None` and serialize it into payload.
  - In `gift_manager/suggestions/service.py`:
    - In `_ai_context`: call `build_preference_profile(self.user, history, visible_tag_ids)` and attach to context.
  - In `gift_manager/suggestions/ai/strategy.py`:
    - Pass `context.preference_profile` to `build_ai_payload`.

- [x] **Step 4: Verify prompt tests and AI service tests**
  ```bash
  tox run -e py311 -- gift_manager/tests/suggestions/test_ai_prompt.py gift_manager/tests/suggestions/test_ai_service.py
  ```

---

## Task 3: Domain Helpers (`person_profile.py`)

Create `gift_manager/person_profile.py` implementing `promotion_target`, atomic provenance note appending, and cycle-aware interest tag promotion.

### Interfaces
- `promotion_target(user, recipient_or_relation) -> Person | None`
- `append_person_provenance_note(person, *, source_label: str, item_name: str, text: str, today: date | None = None) -> bool`
- `promote_tags_to_person_interests(person, tags: Iterable[GiftTag], user) -> list[str]`

- [x] **Step 1: Write failing tests**
  Create `gift_manager/tests/test_person_profile.py`:
  - `test_promotion_target_guards_surprise_plans`: verify returns `None` if `relation.is_surprise` is True.
  - `test_promotion_target_guards_groups_and_viewer_permissions`: verify returns `None` for `PersonGroup` or when user has `< PermissionLevel.EDITOR`.
  - `test_append_person_provenance_note_formats_and_deduplicates`: verify format `[YYYY-MM-DD - {source_label}: {item_name}]: {text}`, collapses newlines, and avoids appending identical line on re-save.
  - `test_append_person_provenance_note_uses_select_for_update`: verify atomic update only modifies `notes`.
  - `test_promote_tags_to_person_interests_skips_ancestors_and_limits`: verify direct accessible tags added, tags covered by existing interest ancestors skipped, capped at 5 tags.

- [x] **Step 2: Run tests to verify failure**
  ```bash
  tox run -e py311 -- gift_manager/tests/test_person_profile.py
  ```

- [x] **Step 3: Implement `gift_manager/person_profile.py`**
  - Implement `promotion_target(user, target) -> Person | None`:
    - Check if target is a `Person` or a `Relation` with a person.
    - If `Relation`: return `None` if `is_surprise` or `group_id` is set.
    - Check `PermissionService.get_effective_permission(person, user) >= PermissionLevel.EDITOR`.
  - Implement `append_person_provenance_note`:
    - Clean and collapse whitespace in `item_name` (max 120 chars) and `text` (max 200 chars).
    - Match existing lines on `rf"\]: {re.escape(cleaned_text)}$"` or `{source_label}: {cleaned_name}]: {cleaned_text}`. Return `False` if duplicate.
    - Use `transaction.atomic()`, `Person.objects.select_for_update().get(pk=person.pk)`, append `f"[{today.isoformat()} - {source_label}: {cleaned_name}]: {cleaned_text}"`, `person.save(update_fields=["notes"])`.
  - Implement `promote_tags_to_person_interests`:
    - Filter tags to accessible tags. Use `tag_ancestor_map` to skip tags that are ancestors of existing interests.
    - Add up to 5 tags using `person.interests.add(*tags_to_add)`. Return list of added tag names.

- [x] **Step 4: Verify domain helper tests pass**
  ```bash
  tox run -e py311 -- gift_manager/tests/test_person_profile.py
  ```

---

## Task 4: Suggestion Dismissal UI & Feedback Promotion

Add the profile promotion checkbox to `gift_suggestion_item.html`, wire `person_suggestion_dismiss`, deliver feedback toasts, and verify with a Playwright e2e test.

### Interfaces
- Form parameters: `save_profile_note: str` (`"1"` or `"on"`).
- Context in `_render_suggestions` and `_render_ai_block`: `profile_target: Person | None`, `linked_user_warning: bool`.
- Response: HTMX response triggers informational or success toast detailing note/interest updates.

- [x] **Step 1: Write failing unit and view tests**
  In `gift_manager/tests/views/test_suggestions_views.py`:
  - `test_dismiss_with_already_owned_promotes_interests_and_note`: verify note appended and tags added to interests.
  - `test_dismiss_with_dislikes_promotes_note_only`: verify note appended but interests untouched.
  - `test_dismiss_with_too_expensive_does_not_promote_note`: verify no note written.
  - `test_dismiss_promotion_refused_for_viewer_only`: verify viewer cannot modify notes.
  - `test_dismiss_toast_indicates_promoted_actions`: verify `HX-Trigger` contains detailed feedback message.

- [x] **Step 2: Run view tests to verify failure**
  ```bash
  tox run -e py311 -- gift_manager/tests/views/test_suggestions_views.py -k "dismiss"
  ```

- [x] **Step 3: Update suggestion item template & dismiss view**
  - In `gift_manager/views/suggestions.py`:
    - In `_render_suggestions` and `_render_ai_block`: compute `profile_target = promotion_target(request.user, recipient)` and `linked_user_warning = bool(profile_target and profile_target.user_link_id and profile_target.user_link_id != request.user.id)`. Pass into context.
    - In `_handle_dismiss`:
      - Check `save_profile = request.POST.get("save_profile_note") in {"1", "on", "true"}`.
      - If `save_profile` and `profile_target`:
        - If `reason == "already_owned_or_practiced"`: call `promote_tags_to_person_interests` and `append_person_provenance_note`.
        - If `reason in {"dislikes", "custom"}`: call `append_person_provenance_note`.
        - Construct localized notification toast (`"Note added to profile"`, `"Interests added: {tags}"`).
  - In `gift_manager/templates/gift_manager/includes/gift_suggestion_item.html`:
    - If `profile_target`: render a checkbox at the top of the dropdown menu:
      ```html
      <li class="px-2 pb-1">
          <div class="form-check form-check-sm">
              <input class="form-check-input" type="checkbox" name="save_profile_note" id="save_profile_{{ candidate.name|slugify }}_{{ forloop.counter }}" onclick="event.stopPropagation();">
              <label class="form-check-label small text-muted" for="save_profile_{{ candidate.name|slugify }}_{{ forloop.counter }}">
                  {% blocktrans with name=recipient.first_name %}Save to {{ name }}'s profile{% endblocktrans %}
              </label>
          </div>
          {% if linked_user_warning %}
              <div class="text-warning small fst-italic mt-1">{% blocktrans with name=recipient.first_name %}{{ name }} can see their profile notes{% endblocktrans %}</div>
          {% endif %}
      </li>
      ```

- [x] **Step 4: Write Playwright E2E test**
  In `gift_manager/tests/e2e/test_gift_suggestions.py`:
  - `test_e2e_dismiss_with_save_to_profile_persists_note_and_shows_toast`: open dropdown, check "Save to profile", click "Already owned", verify dropdown closes cleanly, toast appears, and Person detail shows appended note.

- [x] **Step 5: Verify tests pass**
  ```bash
  tox run -e py311 -- gift_manager/tests/views/test_suggestions_views.py
  tox run -e e2e -- gift_manager/tests/e2e/test_gift_suggestions.py
  ```

---

## Task 5: Plan Reaction & Edit Form Promotion

Add the profile promotion checkbox to `relation_reaction` and `RelationForm` edit flows, ensuring surprise exclusion and atomic note persistence.

### Interfaces
- `RelationForm.save_to_profile: forms.BooleanField(required=False)`
- `ReactionForm.save_to_profile: forms.BooleanField(required=False)`

- [x] **Step 1: Write failing tests**
  In `gift_manager/tests/views/test_relation_views.py` and `gift_manager/tests/test_relation_reaction.py`:
  - `test_relation_edit_abandoned_with_note_promotes_to_person`: verify abandoning plan with reaction note appends `[YYYY-MM-DD - Plan abandoned: {gift}]: {note}`.
  - `test_relation_reaction_rated_promotes_to_person`: verify rating given plan with note appends `[YYYY-MM-DD - Gift rated {N}★: {gift}]: {note}`.
  - `test_surprise_plan_never_offers_or_promotes_note`: verify checkbox omitted on surprise plans and note write blocked.
  - `test_plan_save_succeeds_even_if_note_promotion_fails`: verify decoupling of plan update and profile note append.

- [x] **Step 2: Run tests to verify failure**
  ```bash
  tox run -e py311 -- gift_manager/tests/views/test_relation_views.py gift_manager/tests/test_relation_reaction.py
  ```

- [x] **Step 3: Update `RelationForm`, `relation_reaction`, and views**
  - In `gift_manager/forms.py`:
    - In `RelationForm.__init__`: if `self.instance.pk` and `promotion_target(user, self.instance)`: add `save_to_profile = forms.BooleanField(required=False, label=_("Save note to recipient's profile"))`.
    - In `RelationReactionForm`: add `save_to_profile` field when `promotion_target` is present.
  - In `gift_manager/views/relation.py`:
    - In `RelationUpdateView.form_valid`: after saving relation, if `form.cleaned_data.get("save_to_profile")`:
      - Check `target = promotion_target(request.user, self.object)`.
      - If target and `self.object.reaction_note` in form.changed_data:
        - Format label: `"Plan abandoned"` if abandoned, else `f"Gift rated {rating}★"`.
        - Call `append_person_provenance_note` inside a safe try/except block. Add success/warning toast message.
    - In `relation_reaction` view: similarly trigger note append if checkbox ticked and note non-empty.
  - In `gift_manager/templates/gift_manager/includes/relation_form_partial.html` and `relation_reaction_partial.html`:
    - Render `save_to_profile` field inside the reaction note container.

- [x] **Step 4: Verify relation tests pass**
  ```bash
  tox run -e py311 -- gift_manager/tests/views/test_relation_views.py gift_manager/tests/test_relation_reaction.py
  ```

---

## Task 6: Localization, Status Update & Verification

Hand-edit French translations in `locale/fr/LC_MESSAGES/django.po`, compile messages, update idea status in `docs/ideas/`, and run verification test suite.

- [x] **Step 1: Add French translations**
  In `locale/fr/LC_MESSAGES/django.po`:
  - Add translations for:
    - `"Save to %(name)s's profile"` -> `"Enregistrer sur le profil de %(name)s"`
    - `"Save note to recipient's profile"` -> `"Enregistrer la note sur le profil du destinataire"`
    - `"%(name)s can see their profile notes"` -> `"%(name)s peut voir les notes de son profil"`
    - `"Note added to profile"` -> `"Note ajoutée au profil"`
    - `"Interests added: %(tags)s"` -> `"Centres d'intérêt ajoutés : %(tags)s"`
    - `"Plan abandoned"` -> `"Projet de cadeau abandonné"`
    - `"Gift rated %(rating)s★"` -> `"Cadeau noté %(rating)s★"`
    - `"Suggestion dismissed: %(gift)s"` -> `"Suggestion écartée : %(gift)s"`
  - Verify syntax with `msgfmt -c -v -o /dev/null locale/fr/LC_MESSAGES/django.po`.
  - Compile with `python manage.py compilemessages -l fr`.

- [x] **Step 2: Update Idea documentation status**
  - In `docs/ideas/0027-recipient-preference-profiles-and-feedback-persistence.md`:
    - Set `Status: Ready`.
    - Add `Plan: docs/superpowers/plans/2026-10-22-recipient-preference-profiles.md`.
  - In `docs/ideas/README.md`:
    - Update row `0027` status to `Ready`.

- [x] **Step 3: Run comprehensive verification**
  ```bash
  tox run -e lint
  tox run -e py311 -- gift_manager/tests/suggestions/ gift_manager/tests/test_person_profile.py gift_manager/tests/views/test_suggestions_views.py gift_manager/tests/views/test_relation_views.py
  ```
