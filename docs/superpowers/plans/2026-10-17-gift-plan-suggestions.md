# Gift Plan Suggestions For A Recipient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Before starting:** set the idea's status to `Ready` in `docs/ideas/0001-gift-plan-suggestions-for-recipient.md` and `docs/ideas/README.md`, and add a "Plan" line to the idea pointing at the plan file.

**Recommended execution:** subagent-driven (fresh implementer + reviewer per task). The 12 tasks hand typed interfaces to each other, and a shipped privacy mistake (a leaked name in an AI payload or reason) is costly. Native execution is the cheaper alternative.

**Goal:** Show a lazy-loaded, ranked "Suggestions" section on the person and group detail pages: catalogue gifts scored from the recipient's history (Phase A) plus new gift ideas from an LLM (Phase B), each with a reason, an "Add as idea" action and a permanent "Dismiss".

**Architecture:** A new `gift_manager/suggestions/` package holds everything: a history builder that reuses `gift_history.person_history_queryset` / `group_history_queryset`, a deterministic catalogue strategy, an AI strategy behind a thin `AIClient` protocol with Anthropic and OpenAI adapters, and a `GiftSuggestionService` that combines them, persists AI ideas and dismissals, and creates Gifts and Gift Plans. Views are thin HTMX endpoints per recipient type, following `views/gift_history.py`.

**Tech Stack:** Django 5.x, PostgreSQL, HTMX, Bootstrap, pytest/tox, factory_boy, Playwright; new production dependencies `anthropic` and `openai` (Phase B only).

**Spec:** `docs/ideas/0001-gift-plan-suggestions-for-recipient.md`

## Decisions Taken During Planning

These refine the spec; Task 12 writes them back into the idea file.

- Catalogue suggestions are computed live on every request (cheap, never stale). Only catalogue **dismissals and acceptances** are stored. AI ideas are stored when generated.
- A person's `interests` (gift tags, idea 0006) count as a positive signal, like a 4/5 rating on a direct plan.
- AI re-ranking of catalogue candidates is **deferred** (not in this plan): catalogue ranking stays deterministic.
- Both providers are supported, chosen by `GIFT_SUGGESTIONS_AI_PROVIDER=anthropic|openai`, through the official SDKs. The OpenAI adapter also serves self-hosted OpenAI-compatible servers through `GIFT_SUGGESTIONS_AI_BASE_URL`. Documented default model: `claude-haiku-5-5`.
- Per-user daily cap on AI calls: `GIFT_SUGGESTIONS_AI_DAILY_LIMIT`, default `20`, counted from a `GiftSuggestionGeneration` log row per call (failed calls count too).
- Suggestions are private to the user who sees them (spec's first-slice assumption).
- "Add as idea" creates a plan owned by the user only, like `plan_repeat.repeat_plans`; its surprise flag uses `plan_coordination.default_surprise_for`.

## Global Constraints

- Privacy: "Only use gifts, plans, ratings and notes the requesting user can access through `accessible_by` / `PermissionService`. A suggestion or its reason must never reveal data from plans the user cannot see, and suggestions are stored per user." Tags are filtered through `VisibleMetadata` (`gift_manager/metadata_visibility.py`).
- Anonymise before anything is sent to the AI provider: "no person or group names, emails or user identifiers; scrub known names from free-text fields." No pks or UUIDs in the payload either.
- Keep ranking and prompt building in services, not templates or JavaScript. The AI client stays behind a thin adapter so tests mock it; no test ever reaches a real provider.
- API key only in environment variables, documented in `.env.example`. New dependencies `anthropic` and `openai` are called out in the PR description.
- AI calls happen in the request with a strict timeout (default 15 s), `max_retries=0`; any AI failure falls back to catalogue suggestions with a discreet notice, never an error page.
- Views return partial templates for HTMX requests; non-HTMX POSTs redirect to the recipient detail page.
- No feature explanations or keyboard-shortcut text in the UI. All new user-facing strings translated to French by hand-editing `locale/fr/LC_MESSAGES/django.po` (do **not** run `makemessages --no-location`; reuse existing msgids; check with `msgfmt --check`; compile with `DJANGO_ENV=development python manage.py compilemessages -l fr` on the host).
- Tests on PostgreSQL: `tox run -e py311 -- <path>`; lint `tox run -e lint`; e2e `tox run -e e2e -- <path>`.
- Review the generated migration before committing. Commit messages follow `commitlint.config.js` (use the `commit-message` skill), e.g. `Feat(suggestions): ...`.

## Review Focus

- A candidate gift whose tags are partly inaccessible to the viewer: the reason never names a hidden tag and hidden tags never change the score (Task 3, `test_hidden_tags_neither_score_nor_appear_in_reason`).
- The viewer is the recipient of a surprise plan hidden from them: that plan neither excludes its gift nor feeds the tag profile (Task 2, `test_hidden_surprise_plan_is_not_in_history`).
- "Add as idea" posted twice (double click, two tabs): exactly one Gift Plan, and for an AI idea exactly one new Gift (Task 4 and Task 10, `test_accept_twice_creates_one_plan`).
- The gift is deleted or unshared, or the AI suggestion belongs to another user, between render and accept: 404 and nothing created (Task 4 / Task 10, `test_accept_inaccessible_gift_is_404`, `test_accept_other_users_suggestion_is_404`).
- The provider returns malformed JSON, wrong types, too many items, HTML in names, or a tag name the user cannot access: invalid items dropped, HTML escaped at render, unknown tags ignored, catalogue still shown (Task 9, Task 11).

## File Structure

- Create `gift_manager/suggestions/__init__.py` (empty), and:
  - `names.py` — `normalize_gift_name`.
  - `history.py` — `HistoryItem`, `RecipientHistory`, `build_recipient_history`, `tag_ancestor_map`.
  - `types.py` — `SuggestionContext`, `SuggestionCandidate`, `SuggestionReason`, `SuggestionStrategy` protocol.
  - `catalogue.py` — `CatalogueStrategy`, scoring constants, `describe_reason`.
  - `service.py` — `GiftSuggestionService`, `CataloguePage`, `AIBlock`.
  - `ai/__init__.py`, `ai/client.py` (`AIClient`, `AIError`, `get_ai_client`), `ai/anthropic_client.py`, `ai/openai_client.py`, `ai/prompt.py` (payload, scrubbing, schema, system prompt), `ai/validation.py` (`AIIdea`, `parse_ideas`), `ai/strategy.py` (`AIStrategy`).
- Modify `gift_manager/models.py` (two models), create `gift_manager/migrations/0038_gift_suggestions.py`.
- Create `gift_manager/views/suggestions.py`; modify `views/__init__.py`, `urls.py`, `views/person.py` (`PersonDetailView.get_context_data`), `views/person_group.py` (`PersonGroupDetailView.get_context_data`).
- Create templates in `gift_manager/templates/gift_manager/includes/`: `gift_suggestions_placeholder.html`, `gift_suggestions_section.html`, `gift_suggestions_catalogue_items.html`, `gift_suggestion_item.html`, `gift_suggestions_ai_block.html`. Modify `includes/person_detail_partial.html`, `includes/person_group_detail_partial.html`, `person_group_detail.html`.
- Modify `GiftManager/settings/base.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `locale/fr/LC_MESSAGES/django.po` (+ `.mo`), `docs/ai/architecture.md`, the idea file and `docs/ideas/README.md`.
- Tests: `gift_manager/tests/suggestions/` (new package: `test_models.py`, `test_names.py`, `test_history.py`, `test_catalogue.py`, `test_service.py`, `test_ai_clients.py`, `test_ai_prompt.py`, `test_ai_validation.py`, `test_ai_service.py`), `gift_manager/tests/views/test_suggestions_views.py`, `gift_manager/tests/e2e/test_gift_suggestions.py`. Shared fixtures in `gift_manager/tests/suggestions/conftest.py`: `user`, `client` (force-logged), `share(user, obj, level=EDITOR)` via `gift_manager.permissions.create_or_update_permission`, `status(name)` via `RelationStatus.objects.get_or_create(status_en=name, defaults={"status": name})` (pattern from `tests/e2e/test_group_gift_history_panel.py`). Task 7 adds `FakeAIClient` there (takes a list of canned JSON strings or an `AIError`, returns one per `generate` call, records each `payload`).

---

# Phase A — Catalogue suggestions (shippable alone)

### Task 1: Data model and name normalisation

**Files:**
- Modify: `gift_manager/models.py` (append after `RelationComment`)
- Create: `gift_manager/migrations/0038_gift_suggestions.py` (generated), `gift_manager/suggestions/__init__.py`, `gift_manager/suggestions/names.py`
- Test: `gift_manager/tests/suggestions/__init__.py`, `conftest.py`, `test_models.py`, `test_names.py`

**Interfaces:**
- Produces: `normalize_gift_name(name: str) -> str`.
- Produces: `GiftSuggestionGeneration(user FK User CASCADE related_name="gift_suggestion_generations", person FK Person CASCADE null related_name="+", group FK PersonGroup CASCADE null related_name="+", created_at DateTimeField(auto_now_add, db_index), succeeded BooleanField(default=False), idea_count PositiveSmallIntegerField(default=0))`; check constraint `gift_suggestion_generation_one_recipient` (same condition as `relation_exactly_one_recipient`).
- Produces: `GiftSuggestion` with `Source(TextChoices)`: `CATALOGUE="catalogue"`, `AI="ai"`; `State(TextChoices)`: `PENDING="pending"`, `ACCEPTED="accepted"`, `DISMISSED="dismissed"`; fields `suggestion_id UUIDField(default=uuid4, unique, editable=False)`, `user FK User CASCADE related_name="gift_suggestions"`, `person FK Person CASCADE null related_name="gift_suggestions"`, `group FK PersonGroup CASCADE null related_name="gift_suggestions"`, `source CharField(max_length=10, choices)`, `state CharField(max_length=10, choices, default=PENDING)`, `gift FK Gift CASCADE null related_name="suggestions"`, `generation FK GiftSuggestionGeneration CASCADE null related_name="ideas"`, `name TextField(blank, default="")`, `description TextField(blank, default="")`, `reason TextField(blank, default="")`, `tags M2M GiftTag(blank, related_name="+")`, `normalized_name TextField(db_index)`, `score FloatField(default=0)`, `created_at auto_now_add`, `updated_at auto_now`. Property `recipient -> Person | PersonGroup`. Meta: `ordering = ("-created_at", "pk")`; constraints `gift_suggestion_one_recipient`, `gift_suggestion_catalogue_has_gift` (`Q(source="ai") | Q(gift__isnull=False)`), `gift_suggestion_ai_has_name` (`Q(source="catalogue") | ~Q(name="")`), unique `gift_suggestion_unique_catalogue_person` on `(user, person, gift)` with `condition=Q(source="catalogue", person__isnull=False)` and `..._group` likewise; indexes on `(user, person, state)` and `(user, group, state)`. `verbose_name`s with `gettext_lazy`.

- [x] **Step 1: Write failing tests.** `test_names.py`, parametrised: `"  Lego  Technic! "` → `"lego technic"`; `"Écharpe en laine"` → `"echarpe en laine"`; `"ÉCHARPE"` equals `normalize_gift_name("echarpe")`; `"Café-crème"` → `"cafe creme"`; `""` → `""`. `test_models.py`: `test_requires_exactly_one_recipient` (both / neither → `IntegrityError` inside `transaction.atomic()`); `test_catalogue_requires_gift`; `test_ai_requires_name`; `test_one_catalogue_row_per_user_recipient_gift` (second catalogue row same user/person/gift → `IntegrityError`; same gift for another user is fine); `test_deleting_gift_deletes_its_suggestions`; `test_generation_requires_one_recipient`.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/`. Expected: FAIL (import errors).
- [x] **Step 3: Implement** `normalize_gift_name`: `unicodedata.normalize("NFKD")`, drop combining marks, `casefold()`, replace every run of non-alphanumeric characters with one space, `strip()`. Implement both models as above.
- [x] **Step 4: Generate and review the migration:** `python manage.py makemigrations gift_manager -n gift_suggestions`; it must only create the two models, their constraints and indexes. `python manage.py makemigrations --check --dry-run` is clean.
- [x] **Step 5: Run** the suite folder plus `gift_manager/tests/test_migrations.py`. Expected: PASS.
- [x] **Step 6: Commit** `Feat(suggestions): Add suggestion models and gift name normalisation`.

---

### Task 2: Recipient history builder

**Files:**
- Create: `gift_manager/suggestions/history.py`
- Test: `gift_manager/tests/suggestions/test_history.py`

**Interfaces:**
- Consumes: `person_history_queryset(user, person)`, `group_history_queryset(user, group)` from `gift_manager/gift_history.py` (already scoped through `Relation.objects.accessible_by`, which also drops surprises hidden from the user); `VisibleMetadata(user).tag_ids`; `relation_status_slug`, `is_abandoned_status`, `can_rate_status` from `gift_manager/statuses.py`.
- Produces:
  - `tag_ancestor_map(tag_ids: set[int]) -> dict[int, frozenset[int]]` — each tag mapped to itself plus all its ancestors, restricted to `tag_ids`. One query on `GiftTag.parent_tags.through` (columns `from_gifttag_id` = child, `to_gifttag_id` = parent; verify the direction in a test), then an in-memory walk with a visited set so a stored cycle cannot loop.
  - `@dataclass(frozen=True) HistoryItem`: `relation_id: int`, `gift_id: int`, `gift_name: str`, `tag_ids: frozenset[int]` (visible tags, ancestors included), `status_slug: str`, `rating: int | None` (only when `relation.has_visible_reaction`), `note: str` (reaction note, only when rating is visible), `comment: str`, `is_direct: bool` (plan targets the recipient itself), `person_id: int | None`, `group_id: int | None`, `created: datetime`.
  - `@dataclass(frozen=True) RecipientHistory`: `recipient: Person | PersonGroup`, `items: tuple[HistoryItem, ...]` (newest first), `planned_gift_ids: frozenset[int]` (gifts of direct, non-abandoned visible plans), `interest_tag_ids: frozenset[int]` (person interests the viewer can see, ancestors included; empty for a group), `ancestors: dict[int, frozenset[int]]`.
  - `build_recipient_history(user, recipient: Person | PersonGroup) -> RecipientHistory` — at most 3 queries plus the tag map: history plans with `prefetch_related("gift__tags")`, interests, tag edges.

- [x] **Step 1: Write failing tests:**
  - `test_person_history_includes_own_and_group_plans`: plans for the person, for their group and for that group's parent appear; `is_direct` is true only for the person's own plan.
  - `test_group_history_includes_member_and_nested_member_plans`: a plan for a member of a child group appears with `is_direct=False`.
  - `test_plans_not_shared_with_viewer_are_absent`.
  - `test_hidden_surprise_plan_is_not_in_history`: viewer is `user_link` of the person; a surprise plan owned by another user and shared with the viewer is absent and its gift is not in `planned_gift_ids`.
  - `test_planned_gift_ids_skip_abandoned_and_indirect_plans`.
  - `test_rating_and_note_only_when_visible`: a rating on an `Idea` plan yields `rating is None` and `note == ""`; on a `Given` plan both are kept.
  - `test_tag_ids_include_visible_ancestors_only`: tag `Lego` under `Toys` under private `Secret` (not shared): item has `{Lego, Toys}`.
  - `test_tag_ancestor_map_survives_cycle`: insert a cycle directly in the through table; the call returns.
  - `test_interest_tags_only_visible_ones`.
  - `test_query_count_is_bounded`: with 10 plans and 10 tags, `django_assert_max_num_queries(6)`.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_history.py`. Expected: FAIL.
- [x] **Step 3: Implement** `history.py`. Status from `relation.status` (already `select_related` by `_base_queryset`).
- [x] **Step 4: Run** the test file. Expected: PASS.
- [x] **Step 5: Commit** `Feat(suggestions): Build recipient history for suggestions`.

---

### Task 3: Catalogue scoring strategy

**Files:**
- Create: `gift_manager/suggestions/types.py`, `gift_manager/suggestions/catalogue.py`
- Test: `gift_manager/tests/suggestions/test_catalogue.py`

**Interfaces:**
- Consumes: `RecipientHistory`, `tag_ancestor_map` (Task 2).
- Produces in `types.py`:
  - `@dataclass(frozen=True) SuggestionReason`: `code: str` (`"liked_tags"`, `"related_liked_tags"`, `"interests"`, `"popular"`), `tag_names: tuple[str, ...]` (≤ 2, visible tags only), `rating: int | None`.
  - `@dataclass(frozen=True) SuggestionCandidate`: `source: str` (`GiftSuggestion.Source` value), `score: float`, `gift: Gift | None`, `name: str`, `description: str`, `reason: SuggestionReason | str` (str for AI), `tag_ids: frozenset[int]`, `suggestion: GiftSuggestion | None` (stored AI row).
  - `@dataclass(frozen=True) SuggestionContext`: `user`, `recipient`, `history: RecipientHistory`, `excluded_gift_ids: frozenset[int]`, `blocked_names: frozenset[str]` (normalised).
  - `class SuggestionStrategy(Protocol)`: `def suggest(self, context: SuggestionContext, limit: int) -> list[SuggestionCandidate]`.
- Produces in `catalogue.py`: `class CatalogueStrategy` implementing the protocol (`limit` counts candidates returned after ranking; the service slices pages), and `describe_reason(reason: SuggestionReason, recipient) -> str` (gettext, rendered at display time so it follows the active language).

Scoring (exact values):

```text
DIRECT_WEIGHT = 1.0, INDIRECT_WEIGHT = 0.5, INTEREST_SIGNAL = 1.0
signal(item) = {5: +2, 4: +1, 3: 0, 2: -1, 1: -2}[rating]  if rating is not None
             = -1    elif status is abandoned
             = +0.5  elif status is given
             = 0     otherwise
profile[tag] += weight(item) * signal(item)   for tag in item.tag_ids
profile[tag] += INTEREST_SIGNAL               for tag in history.interest_tag_ids
score(gift)  = sum(profile.get(t, 0) for t in expanded visible tags of gift)
popularity(gift) = mean visible rating over all plans the user can access for that gift
```

- Candidates: `Gift.objects.accessible_by(user)` minus `context.excluded_gift_ids`, tags prefetched with only visible tags (`Prefetch("tags", queryset=GiftTag.objects.filter(pk__in=visible))`). Popularity: one query on `Relation.objects.accessible_by(user).filter(reaction_rating__isnull=False).select_related("status")`, kept in Python when `can_rate_status(status)`.
- Normal mode (profile has at least one positive tag): keep `score > 0`, order by `(-score, -(popularity or 0), name.casefold())`. Fallback mode (no positive tag): keep `score >= 0` and `popularity >= 4`, order by `(-popularity, name.casefold())`. Negative-score gifts never appear.
- Reason: the code of the largest contribution — `interests` when interest tags contribute most, else `liked_tags` when direct items contribute most, else `related_liked_tags`; `popular` in fallback mode. `tag_names`: the two matching tags with the largest positive contribution; `rating`: the highest rating among contributing items (popularity rounded to one decimal for `popular`).
- Copy (`describe_reason`): `"Shares tags with gifts rated %(rating)s/5: %(tags)s"`, `"Shares tags with gifts liked by related recipients: %(tags)s"`, `"Matches their interests: %(tags)s"`, `"Rated %(rating)s/5 on average"`. When `rating` is None for `liked_tags`, use `"Shares tags with past favourites: %(tags)s"`. Tags joined with `", "`.

- [x] **Step 1: Write failing tests** (each builds gifts, tags, plans and ratings with factories, then calls `CatalogueStrategy().suggest(context, limit=10)` with a context built from `build_recipient_history`):
  - `test_liked_tags_rank_above_disliked_tags`: history plan tagged `A` rated 5, another tagged `B` rated 1; gift `GA` tagged `A` and gift `GAB` tagged `A`+`B` → order `[GA, GAB]`; gift `GB` tagged `B` absent.
  - `test_direct_history_outweighs_group_history`: same rating 5 on tag `A` via a direct plan and on tag `C` via a group plan → `A` gift first.
  - `test_abandoned_plan_tags_are_negative`.
  - `test_ancestor_tags_overlap`: history tagged `Lego` (child of `Toys`) rated 5; candidate tagged `Toys` is suggested.
  - `test_interests_count_as_positive`: no history, person interest `Books`; gift tagged `Books` suggested with reason code `interests`.
  - `test_excluded_gift_ids_are_never_returned`.
  - `test_shared_gift_from_other_user_is_a_candidate`: gift owned by another user and shared as VIEWER is suggested.
  - `test_unshared_gift_is_never_a_candidate`.
  - `test_fallback_uses_best_average_rating`: no history; gift rated 5 for another person ranks above a gift rated 4; a gift rated 3 is absent.
  - `test_hidden_tags_neither_score_nor_appear_in_reason`: candidate tagged with visible `A` and hidden `H`; history (visible plan) tagged `H` rated 5 and `A` rated 4 → score from `A` only, `reason.tag_names == ("A",)`.
  - `test_ratings_from_plans_not_shared_are_ignored`: another user's unshared plan rated 5 neither creates a profile nor popularity.
  - `test_describe_reason_formats_tags_and_rating`: `liked_tags` with `("Books", "Maps")`, rating 5 → `"Shares tags with gifts rated 5/5: Books, Maps"` (French is checked in Task 5).
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_catalogue.py`. Expected: FAIL.
- [x] **Step 3: Implement** `types.py` and `catalogue.py` with the constants above.
- [x] **Step 4: Run** the test file. Expected: PASS.
- [x] **Step 5: Commit** `Feat(suggestions): Score catalogue gifts from recipient history`.

---

### Task 4: Suggestion service — catalogue pages, accept, dismiss

**Files:**
- Create: `gift_manager/suggestions/service.py`
- Test: `gift_manager/tests/suggestions/test_service.py`

**Interfaces:**
- Consumes: Tasks 1–3; `PermissionService.create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER, object_attr=...)` (`gift_manager/services.py`); `RelationStatus.get_default_pk()` (the `Idea` status); `default_surprise_for(recipient, user)` (`gift_manager/plan_coordination.py`).
- Produces:
  - Constants `CATALOGUE_PAGE_SIZE = 5`, `CATALOGUE_FIRST_PAGE_WITH_AI = 3`.
  - `@dataclass(frozen=True) CataloguePage`: `candidates: list[SuggestionCandidate]`, `next_offset: int | None`.
  - `class GiftSuggestionService(user, recipient: Person | PersonGroup, *, ai_client=_DEFAULT)` — in Phase A `_DEFAULT` resolves to `None`; Task 10 makes it resolve to `get_ai_client()`. Property `ai_enabled -> bool` (`ai_client is not None`).
  - `catalogue_page(offset: int = 0) -> CataloguePage` — page size `CATALOGUE_FIRST_PAGE_WITH_AI` when `offset == 0 and ai_enabled`, else `CATALOGUE_PAGE_SIZE`. Excluded gift ids = `history.planned_gift_ids` ∪ gifts of this user's catalogue rows for this recipient in state `dismissed` or `accepted`.
  - `accept_gift(gift_uuid: uuid.UUID) -> Relation` — raises `Http404` when the gift is not in `Gift.objects.accessible_by(user)`.
  - `dismiss_gift(gift_uuid: uuid.UUID) -> None` — same 404 rule; `update_or_create` the catalogue row with `state=dismissed`, `normalized_name=normalize_gift_name(gift.name)`.
  - Private `_create_idea_plan(gift: Gift) -> Relation`: inside `transaction.atomic()`, lock the recipient row (`select_for_update` on the Person/PersonGroup) so concurrent accepts serialise; if a visible non-abandoned plan already links this gift to the recipient, return it; otherwise `Relation.objects.create(person|group=recipient, gift=gift, status_id=RelationStatus.get_default_pk(), is_surprise=default_surprise_for(recipient, user))` and grant the user OWNER with `object_attr="relation"`. Upsert the catalogue row with `state=accepted`.

- [x] **Step 1: Write failing tests:**
  - `test_first_page_has_five_without_ai_and_next_offset`: 7 eligible gifts → 5 candidates, `next_offset == 5`; `catalogue_page(5)` → 2 candidates, `next_offset is None`.
  - `test_first_page_has_three_when_ai_enabled`: service built with `ai_client=object()` → 3 candidates, `next_offset == 3`.
  - `test_gift_planned_for_recipient_is_excluded` / `test_gift_with_only_abandoned_plan_is_not_excluded`.
  - `test_accept_gift_creates_idea_plan_owned_by_user`: status is `Idea` (`is_idea_status`), `person == recipient`, user has OWNER, no other user has a permission, catalogue row `accepted`, gift no longer in `catalogue_page()`.
  - `test_accept_gift_for_group_recipient`.
  - `test_accept_sets_default_surprise`: recipient person linked to another user → `is_surprise is True`.
  - `test_accept_twice_creates_one_plan`.
  - `test_accept_inaccessible_gift_is_404` (gift unshared after render) and `test_dismiss_inaccessible_gift_is_404`.
  - `test_dismissed_gift_never_returns`: dismiss, then new history making it the top match → still absent; another user still gets it.
- [x] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_service.py`. Expected: FAIL.
- [x] **Step 3: Implement** `service.py` as above.
- [x] **Step 4: Run** the test file. Expected: PASS.
- [x] **Step 5: Commit** `Feat(suggestions): Add suggestion service with accept and dismiss`.

---

### Task 5: Views, URLs, templates and detail page placement

**Files:**
- Create: `gift_manager/views/suggestions.py`, the five templates listed in File Structure
- Modify: `gift_manager/views/__init__.py` (import + `__all__`), `gift_manager/urls.py` (next to the gift-history routes), `gift_manager/views/person.py:265-346`, `gift_manager/views/person_group.py:444-559`, `includes/person_detail_partial.html`, `includes/person_group_detail_partial.html`, `person_group_detail.html`, `locale/fr/LC_MESSAGES/django.po`
- Test: `gift_manager/tests/views/test_suggestions_views.py`

**Interfaces:**
- Consumes: `GiftSuggestionService` (Task 4), `describe_reason` (Task 3).
- Produces URL names (all `login_required`): `person_suggestions` `GET persons/<uuid:pk>/suggestions/`, `person_suggestion_accept` `POST persons/<uuid:pk>/suggestions/accept/`, `person_suggestion_dismiss` `POST persons/<uuid:pk>/suggestions/dismiss/`, and `person_group_suggestions`, `person_group_suggestion_accept`, `person_group_suggestion_dismiss` under `person_groups/<uuid:pk>/suggestions/...`. Phase B adds `person_suggestion_ideas` / `person_group_suggestion_ideas`.
- Produces context key `suggestions_url` on both detail views; helper `suggestions_url_for(recipient) -> str` in `views/suggestions.py`.
- Request parameters: `offset` (GET, int ≥ 0, invalid → 0); POST `gift` (UUID) for catalogue, `suggestion` (UUID, Phase B) for AI; `surface` (`"page"` or absent) on GET and POST.

Behaviour:
- Recipient resolved with `get_object_or_404(Person.objects.accessible_by(user), person_id=pk)` / `PersonGroup.objects.accessible_by(user), group_id=pk` (as in `views/gift_history.py`).
- `GET` with `offset == 0` renders `gift_suggestions_section.html`; with `offset > 0` renders `gift_suggestions_catalogue_items.html` only.
- Accept/dismiss, HTMX: dismiss returns the section; accept returns the section plus `HX-Trigger` built with `HTMXResponseMixin.build_hx_trigger_header(["list:update"])` (the detail modal refreshes itself on `list:update`, `static/gift_manager/js/detail-views.js:216`); when `surface == "page"` accept answers `HX-Refresh: true` instead so the full page shows the new plan. No toast (idea 0020). Non-HTMX POST → redirect to `person_detail` / `person_group_detail`. Malformed UUID → 404.
- Templates (markup hooks the tests rely on): placeholder `<div class="detail-section mt-4 mb-4" data-gift-suggestions-section>` with title `"Suggestions"` (icon `fa-lightbulb`) and an inner `hx-get="{{ suggestions_url }}{% if full_page %}&surface=page{% endif %}" hx-trigger="load" hx-swap="innerHTML"` showing `"Loading…"` (copy the `gift_history_placeholder.html` pattern; build the URL so `?surface=page` is correct when there is no query string). Section root `data-gift-suggestions`; each item `data-gift-suggestion data-suggestion-source="catalogue|ai"`, gift name, a source badge (`"From your gifts"` / `"New idea"`), the reason in `text-muted small`, then two forms: `"Add as idea"` (`data-suggestion-accept`, `hx-post`, `hx-target="closest [data-gift-suggestions]"`, `hx-swap="outerHTML"`, `hx-disabled-elt="this"`, hidden `gift`/`suggestion` and `surface`, `{% csrf_token %}`, real `method="post" action=...`) and `"Dismiss"` (`data-suggestion-dismiss`, same pattern). "Show more" button `data-suggestion-show-more` with `hx-get="...?offset=N"` and `hx-swap="outerHTML"` on its wrapper. Empty state `"No suggestions yet."`.
- Placement: person partial — right column, right after the "Gift plans in progress" `detail-section`, before the abandoned include, with `full_page=full_page_detail`. Group partial — before the abandoned include at `includes/person_group_detail_partial.html:187`. Group full page — after the closing tag of `#group-detail-members` (outside the section `person-group-detail.js` swaps), with `full_page=True`.
- Translations for every new string (French): Suggestions → Suggestions, From your gifts → Parmi vos cadeaux, New idea → Nouvelle idée, Add as idea → Ajouter comme idée, Dismiss → Ignorer, Show more → Voir plus, No suggestions yet. → Aucune suggestion pour l'instant., plus the Task 3 reason strings. Reuse an existing `Loading…` msgid.

- [ ] **Step 1: Write failing tests** (Django `Client`, PostgreSQL):
  - `test_person_detail_page_renders_placeholder` / `test_group_detail_page_renders_placeholder` (full page and `HX-Request` partial both contain `data-gift-suggestions-section` and the suggestions URL).
  - `test_suggestions_partial_lists_ranked_items_with_reason`.
  - `test_show_more_returns_next_items_only`.
  - Permission matrix, parametrised over recipient access `owner`, `editor`, `viewer`: GET returns 200 and only gifts the user can access; `test_no_access_recipient_is_404` for GET, accept and dismiss.
  - `test_reason_never_mentions_data_from_unshared_plans`: another user's unshared plan rated 5 with tag `Secret` (tag shared with the viewer) — response does not contain `Secret`.
  - `test_accept_htmx_returns_section_and_list_update_trigger`, `test_accept_full_page_surface_refreshes`, `test_accept_without_htmx_redirects_to_detail`, `test_dismiss_removes_item_from_section`, `test_post_with_malformed_uuid_is_404`, `test_get_on_accept_is_405`.
  - `test_section_is_translated_in_french` (`/fr/` prefixed URL, asserts `Ajouter comme idée`).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_suggestions_views.py`. Expected: FAIL.
- [ ] **Step 3: Implement** views, URLs, context keys, templates, placement and translations; `msgfmt --check locale/fr/LC_MESSAGES/django.po -o /tmp/check.mo`, then compile.
- [ ] **Step 4: Run** the test file plus `gift_manager/tests/views/test_gift_history.py`, `gift_manager/tests/views/test_person_group_detail.py`, `gift_manager/tests/test_locale_coverage.py`. Expected: PASS.
- [ ] **Step 5: Commit** `Feat(suggestions): Show catalogue suggestions on recipient detail pages`.

---

### Task 6: E2E — accept and dismiss a catalogue suggestion

**Files:**
- Create: `gift_manager/tests/e2e/test_gift_suggestions.py`

**Interfaces:**
- Consumes: `BaseE2ETest`, `live_server`, `test_user`, `self.login_as_user` (see `tests/e2e/test_group_gift_history_panel.py`); markup hooks from Task 5.

- [ ] **Step 1: Write the tests:**
  - `test_accept_suggestion_on_person_page`: person with a `Given` plan tagged `Books` rated 5 and two unplanned gifts tagged `Books` (`"Novel"`, `"Atlas"`), all shared with `test_user`. Open the person detail page, wait for `[data-gift-suggestion]` containing `"Novel"`, click its `[data-suggestion-accept]`; after the reload the "Gift plans in progress" list contains `"Novel"` and the suggestions section no longer does.
  - `test_dismiss_suggestion_on_person_page`: dismiss `"Atlas"`; it disappears; after `page.reload()` it is still absent.
  - `test_accept_suggestion_in_detail_panel`: open the person from `/recipients/` with the details action (as in the group history e2e), accept → the panel refreshes and shows the new plan.
- [ ] **Step 2: Run** `tox run -e e2e -- gift_manager/tests/e2e/test_gift_suggestions.py`. Expected: PASS (fix implementation, not tests, if a flow is broken; screenshot the section in light and dark theme and at phone width to confirm layout).
- [ ] **Step 3: Commit** `Test(suggestions): Cover accept and dismiss in the browser`.

---

# Phase B — AI ideas

### Task 7: Settings, dependencies and provider adapters

**Files:**
- Modify: `GiftManager/settings/base.py` (after `CRON_SECRET`), `.env.example` (new "OPTIONAL: AI GIFT SUGGESTIONS" block), `pyproject.toml`, `uv.lock`
- Create: `gift_manager/suggestions/ai/__init__.py`, `ai/client.py`, `ai/anthropic_client.py`, `ai/openai_client.py`
- Test: `gift_manager/tests/suggestions/test_ai_clients.py`, `gift_manager/tests/suggestions/conftest.py` (add `FakeAIClient`)

**Interfaces:**
- Produces settings: `GIFT_SUGGESTIONS_AI_PROVIDER` (`""` disables; `"anthropic"` or `"openai"`), `GIFT_SUGGESTIONS_AI_API_KEY`, `GIFT_SUGGESTIONS_AI_MODEL` (default `"claude-haiku-5-5"` when provider is `anthropic`, required for `openai`), `GIFT_SUGGESTIONS_AI_BASE_URL` (openai only, for self-hosted servers), `GIFT_SUGGESTIONS_AI_TIMEOUT` (float seconds, default `15`), `GIFT_SUGGESTIONS_AI_EFFORT` (anthropic `output_config.effort`, default `"low"`, empty → omitted), `GIFT_SUGGESTIONS_AI_DAILY_LIMIT` (int, default `20`).
- Produces in `ai/client.py`: `class AIError(Exception)`; `class AIClient(Protocol)`: `def generate(self, *, system: str, payload: dict, schema: dict) -> str` (returns the raw JSON text); `get_ai_client() -> AIClient | None` — `None` when the provider is empty, unknown, or misconfigured (missing key for anthropic; missing model, or missing key without a base URL, for openai), logging one `logger.warning` naming the missing setting, never the key.
- `AnthropicClient(api_key, model, timeout, effort)`: lazy `import anthropic` in `__init__`; `anthropic.Anthropic(api_key=..., timeout=timeout, max_retries=0)`; `client.messages.create(model=..., max_tokens=4096, system=system, messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}], output_config={"format": {"type": "json_schema", "schema": schema}, "effort": effort})` (omit `effort` when empty); raise `AIError` when `stop_reason` is `"refusal"` or `"max_tokens"`; return the concatenated `text` blocks. Map `anthropic.RateLimitError`, `anthropic.APIStatusError`, `anthropic.APIConnectionError` (includes timeouts) to `AIError` (catch in that order; log status code only).
- `OpenAIClient(api_key, model, base_url, timeout)`: lazy `import openai`; `openai.OpenAI(api_key=api_key or "unused", base_url=base_url or None, timeout=timeout, max_retries=0)`; `client.chat.completions.create(model=..., messages=[{"role": "system", ...}, {"role": "user", ...}], response_format={"type": "json_schema", "json_schema": {"name": "gift_ideas", "schema": schema, "strict": True}})`; raise `AIError` when `finish_reason != "stop"` or `message.refusal`; return `message.content`. Map `openai.RateLimitError`, `openai.APIStatusError`, `openai.APIConnectionError` to `AIError`.

- [ ] **Step 1: Add dependencies:** `uv add anthropic openai`; set lower bounds to the resolved versions in `pyproject.toml`. Measure the added install size (`uv pip install --target <scratch> anthropic openai` then `du -sh`); if the total with the existing dependencies risks Vercel's `maxLambdaSize` of 15 MB (`vercel.json`), stop and report to the user before continuing.
- [ ] **Step 2: Write failing tests** (patch `anthropic.Anthropic` / `openai.OpenAI` with `unittest.mock`; no network):
  - `test_get_ai_client_disabled_without_provider`, `test_unknown_provider_disables`, `test_anthropic_without_key_disables`, `test_openai_without_model_disables`, `test_openai_base_url_allows_missing_key`, `test_anthropic_default_model_is_haiku` (`override_settings`).
  - `test_anthropic_request_shape`: asserts `max_retries=0`, the timeout, `model`, `output_config["format"]["schema"] is schema`, `effort == "low"`, user content is `json.dumps(payload, ensure_ascii=False, sort_keys=True)`.
  - `test_anthropic_refusal_and_max_tokens_raise_ai_error`, `test_anthropic_api_errors_become_ai_error` (parametrised over the three exception classes; build them with the SDK's constructors).
  - `test_openai_request_shape` (`response_format` name/strict, `base_url` passed), `test_openai_refusal_raises`, `test_openai_api_errors_become_ai_error`.
  - `test_api_key_never_logged` (`caplog` on a failing call does not contain the key).
- [ ] **Step 3: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_ai_clients.py`. Expected: FAIL.
- [ ] **Step 4: Implement** the settings, the `.env.example` block (each variable commented, `GIFT_SUGGESTIONS_AI_MODEL=claude-haiku-5-5` as the example, a note that `openai` + `GIFT_SUGGESTIONS_AI_BASE_URL` targets OpenAI-compatible servers), and the three modules.
- [ ] **Step 5: Run** the test file and `tox run -e lint`. Expected: PASS.
- [ ] **Step 6: Commit** `Feat(suggestions): Add Anthropic and OpenAI clients for gift ideas`.

---

### Task 8: Anonymised AI payload

**Files:**
- Create: `gift_manager/suggestions/ai/prompt.py`
- Test: `gift_manager/tests/suggestions/test_ai_prompt.py`

**Interfaces:**
- Consumes: `RecipientHistory` (Task 2).
- Produces: `SYSTEM_PROMPT: str` (constant, English: suggest `count` new, concrete gift ideas for the recipient described by the anonymised history; favour what was liked, avoid what was disliked or abandoned; never repeat a name in `avoid`; use only tag names from `available_tags`; write `name`, `description` and `reason` in `language`; `reason` ≤ 150 characters); `IDEAS_SCHEMA: dict` (`{"type": "object", "properties": {"ideas": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}, "required": ["name", "description", "tags", "reason"], "additionalProperties": False}}}, "required": ["ideas"], "additionalProperties": False}`); `scrub_text(text: str, terms: Iterable[str]) -> str`; `build_ai_payload(history: RecipientHistory, *, viewer, available_tag_names: list[str], avoid_names: list[str], count: int, language: str) -> dict`.

Payload shape (no other keys):

```json
{"recipient_type": "person|group", "language": "fr", "count": 2,
 "history": [{"recipient": "Recipient|Recipient's group|Member 1", "gift": "...", "tags": ["..."],
              "status": "given", "rating": 5, "note": "...", "comment": "..."}],
 "interests": ["..."], "available_tags": ["..."], "avoid": ["..."]}
```

- Labels: direct plan → `"Recipient"`; a person's group plan → `"Recipient's group"`; for a group recipient, plans of members → `"Member N"` numbered by first appearance.
- Scrub terms: first name, family name and full name of the recipient and of every person or group referenced by a history item (load them in one query each), every decoded email of those persons (`Person.email`), and the viewer's `username`, `first_name`, `last_name`; terms shorter than 2 characters skipped. `scrub_text` replaces each term case-insensitively on word boundaries with `"[name]"` and any e-mail-looking token (`\S+@\S+\.\S+`) with `"[email]"`. Apply to **every** string in the payload (gift names, tags, notes, comments, avoid list).
- Caps: history ≤ 50 newest items; note and comment truncated to 300 characters; `available_tags` ≤ 200 names sorted case-insensitively; `avoid` ≤ 100 names.

- [ ] **Step 1: Write failing tests:**
  - `test_payload_contains_no_names_emails_or_ids`: person "Marguerite Dupont" with email `marguerite@example.com`, a group "Famille Dupont", viewer username `adrien`; a reaction note `"Marguerite loved it, ask adrien"` and a gift named `"Album photo Marguerite"`. `json.dumps(payload)` contains none of `Marguerite`, `Dupont`, `marguerite@example.com`, `adrien`, `Famille`, any `pk`, `person_id`, `group_id`, `gift_id` or UUID string, and contains `[name]`.
  - `test_group_payload_labels_members`: two members → `"Member 1"`, `"Member 2"`; group name absent.
  - `test_ratings_and_notes_only_when_visible` (from `HistoryItem`).
  - `test_caps_are_applied`, `test_scrub_is_case_insensitive_and_word_bounded` (`"Ann"` scrubbed in `"ann's gift"`, not in `"annual"`), `test_short_terms_are_ignored`.
  - `test_schema_is_strict_compatible`: every object in `IDEAS_SCHEMA` has `additionalProperties: False` and `required` listing all its properties.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_ai_prompt.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `prompt.py`.
- [ ] **Step 4: Run** the test file. Expected: PASS.
- [ ] **Step 5: Commit** `Feat(suggestions): Build an anonymised payload for AI gift ideas`.

---

### Task 9: AI output validation and de-duplication

**Files:**
- Create: `gift_manager/suggestions/ai/validation.py`
- Test: `gift_manager/tests/suggestions/test_ai_validation.py`

**Interfaces:**
- Consumes: `normalize_gift_name` (Task 1).
- Produces: `@dataclass(frozen=True) AIIdea`: `name: str`, `normalized_name: str`, `description: str`, `reason: str`, `tag_ids: frozenset[int]`; `parse_ideas(raw: str, *, tags_by_name: dict[str, int], blocked_names: frozenset[str], limit: int) -> list[AIIdea]`.

Rules: invalid JSON or a missing/non-list `ideas` → `[]` (no exception). Per item, drop it unless it is a dict whose `name`, `description`, `reason` are strings and `tags` a list. Strip control characters and surrounding whitespace; drop when `name` is empty or longer than 120 characters or `reason` is empty; truncate `description` to 500 and `reason` to 200 characters. `tag_ids` = items of `tags` whose `casefold()` matches a key of `tags_by_name` (keys are casefolded visible tag names; first pk wins on duplicates), unknown names ignored. Drop when `normalized_name` is in `blocked_names` or repeats an earlier kept idea. Return at most `limit` ideas in input order.

- [ ] **Step 1: Write failing tests:** `test_valid_ideas_are_parsed`, `test_invalid_json_returns_empty`, `test_wrong_types_are_dropped` (parametrised: name int, tags string, missing reason, item not a dict), `test_overlong_name_dropped_and_long_fields_truncated`, `test_unknown_tags_are_ignored`, `test_blocked_and_duplicate_names_dropped` (`"Lego Technic!"` blocked by `"lego technic"`; two ideas `"Puzzle"` / `"puzzle "` keep one), `test_limit_is_applied`, `test_html_is_kept_as_text` (`"<b>x</b>"` survives parsing; escaping happens at render, covered in Task 11).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_ai_validation.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `validation.py`.
- [ ] **Step 4: Run** the test file. Expected: PASS.
- [ ] **Step 5: Commit** `Feat(suggestions): Validate and de-duplicate AI gift ideas`.

---

### Task 10: AI strategy, generation, daily cap and AI accept/dismiss

**Files:**
- Create: `gift_manager/suggestions/ai/strategy.py`
- Modify: `gift_manager/suggestions/service.py`
- Test: `gift_manager/tests/suggestions/test_ai_service.py`

**Interfaces:**
- Consumes: Tasks 4, 7, 8, 9.
- Produces in `ai/strategy.py`: `class AIStrategy(client: AIClient)` implementing `SuggestionStrategy`: builds the payload (available tags = visible tags; avoid = names of `history.planned_gift_ids` gifts, every AI suggestion of this user+recipient in any state, dismissed catalogue gifts, and the current first catalogue page), calls `client.generate(system=SYSTEM_PROMPT, payload=..., schema=IDEAS_SCHEMA)`, parses with `parse_ideas`, returns `SuggestionCandidate(source="ai", score=float(limit - index), ...)`. `blocked_names` = `context.blocked_names` = normalised names of every gift in `Gift.objects.accessible_by(user)` ∪ every AI suggestion name of this user+recipient ∪ dismissed catalogue names. Lets `AIError` propagate.
- Produces in `service.py`: constants `AI_BATCH_SIZE = 2`, `AI_MAX_VISIBLE = 6`; `@dataclass(frozen=True) AIBlock`: `ideas: list[GiftSuggestion]` (pending AI rows of this user+recipient, newest first, ≤ `AI_MAX_VISIBLE`), `notice: str | None` (`"unavailable"` or `"limit"`), `can_request_more: bool`; `ai_block() -> AIBlock` (generates one batch only when no `GiftSuggestionGeneration` exists for this user+recipient); `request_more_ideas() -> AIBlock` (always generates, subject to the cap); `accept_suggestion(suggestion_uuid) -> Relation`; `dismiss_suggestion(suggestion_uuid) -> None`. `ai_client` default now `get_ai_client()`.
- Generation: count today's rows (`created_at >= start of today in the current timezone`) for the user; at or above `GIFT_SUGGESTIONS_AI_DAILY_LIMIT` → notice `"limit"`, no call. Otherwise create the generation row first (`succeeded=False`), call the strategy, then in one transaction create one `GiftSuggestion` per idea (`source=ai`, `state=pending`, name/description/reason/normalized_name/score, `tags.set(idea.tag_ids)`, `generation=row`) and update the row (`succeeded=True`, `idea_count`). On `AIError` keep the failed row, log at warning level without payload or key, and return notice `"unavailable"`.
- `accept_suggestion`: `GiftSuggestion.objects.select_for_update().get(suggestion_id=..., user=user, source=ai, person|group=recipient)` else `Http404`; when already `accepted`, return the plan linking `suggestion.gift`; when `dismissed`, 404. Otherwise, in one transaction: create `Gift(name=suggestion.name, comment=suggestion.description)`, `gift.tags.set(tags still in VisibleMetadata(user).tag_ids)`, OWNER permission with `object_attr="gift"`, then `_create_idea_plan(gift)` (Task 4), then `state=accepted`, `gift=gift`.
- `dismiss_suggestion`: same lookup, sets `state=dismissed` (idempotent).

- [ ] **Step 1: Write failing tests** (service built with `FakeAIClient` returning canned ideas):
  - `test_first_ai_block_generates_once`: two `ai_block()` calls → one client call, two pending rows, one generation row with `succeeded=True`.
  - `test_more_ideas_adds_a_batch_and_keeps_previous`.
  - `test_ai_ideas_matching_existing_gift_planned_or_dismissed_are_dropped`: canned ideas `"Atlas"` (an accessible gift), `"Novel"` (planned), `"Kite"` (previously dismissed AI idea), `"Telescope"` → only `"Telescope"` stored.
  - `test_ai_payload_has_no_identifiers`: inspect `FakeAIClient.payload` as in Task 8 (end-to-end through the service).
  - `test_ai_error_falls_back_with_notice`: client raises `AIError` → `notice == "unavailable"`, no idea rows, failed generation row; `catalogue_page()` unaffected.
  - `test_daily_limit_blocks_calls`: `override_settings(GIFT_SUGGESTIONS_AI_DAILY_LIMIT=1)`, second `request_more_ideas()` → `notice == "limit"`, client called once; a generation row from yesterday does not count.
  - `test_ai_disabled_returns_no_block`: `ai_client=None` → `ai_enabled is False`, first catalogue page has 5.
  - `test_accept_ai_idea_creates_gift_and_idea_plan`: gift owned by user (OWNER), comment = description, tags limited to visible ones (a tag unshared after generation is dropped), plan in `Idea`, row `accepted` and gone from `ai_block().ideas`.
  - `test_accept_twice_creates_one_plan` (AI variant: one Gift, one Relation).
  - `test_accept_other_users_suggestion_is_404`, `test_accept_dismissed_suggestion_is_404`, `test_dismissed_ai_idea_never_comes_back`: dismiss `"Kite"`, next batch from the fake client proposes `"kite"` → dropped.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/suggestions/test_ai_service.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `ai/strategy.py` and the service additions.
- [ ] **Step 4: Run** `tox run -e py311 -- gift_manager/tests/suggestions/`. Expected: PASS.
- [ ] **Step 5: Commit** `Feat(suggestions): Generate, store and accept AI gift ideas`.

---

### Task 11: AI block UI, "More ideas" and browser coverage

**Files:**
- Modify: `gift_manager/views/suggestions.py`, `gift_manager/urls.py`, `views/__init__.py`, `includes/gift_suggestions_section.html`, `includes/gift_suggestions_ai_block.html`, `includes/gift_suggestion_item.html`, `locale/fr/LC_MESSAGES/django.po`
- Test: `gift_manager/tests/views/test_suggestions_views.py`, `gift_manager/tests/e2e/test_gift_suggestions.py`

**Interfaces:**
- Consumes: `AIBlock`, `request_more_ideas`, `accept_suggestion`, `dismiss_suggestion` (Task 10).
- Produces URL names `person_suggestion_ideas` / `person_group_suggestion_ideas` at `.../suggestions/ideas/`: `GET` → `ai_block()`, `POST` → `request_more_ideas()`; both render `gift_suggestions_ai_block.html`. Accept/dismiss views route a POST carrying `suggestion` to the AI methods and one carrying `gift` to the catalogue ones (both present or neither → 400).
- Section: when `ai_enabled`, render below the catalogue items a nested `<div data-gift-suggestions-ai hx-get="{{ ideas_url }}" hx-trigger="load" hx-swap="outerHTML">` with `"Loading…"`, so catalogue items never wait for the provider. AI block root `data-gift-suggestions-ai`; items use `gift_suggestion_item.html` with `data-suggestion-source="ai"`, the stored `reason` and `description` (autoescaped); `"More ideas"` button `data-suggestion-more-ideas` (`hx-post`, `hx-disabled-elt="this"`, `hx-swap="outerHTML"` on the block) shown when `can_request_more`; notice `<p class="text-muted small" data-suggestion-notice>` with `"New ideas are unavailable right now."` or `"Daily limit for new ideas reached."`.
- Translations: More ideas → Plus d'idées; New ideas are unavailable right now. → Les nouvelles idées sont indisponibles pour le moment.; Daily limit for new ideas reached. → Limite quotidienne de nouvelles idées atteinte.

- [ ] **Step 1: Write failing view tests** (patch `gift_manager.suggestions.service.get_ai_client` to return a `FakeAIClient`): `test_section_includes_ai_placeholder_only_when_enabled`, `test_ideas_get_generates_once_and_renders`, `test_more_ideas_post_adds_batch`, `test_ai_failure_shows_notice_and_status_200`, `test_ai_idea_html_is_escaped` (idea name `"<script>x</script>"` renders as `&lt;script&gt;`), `test_accept_ai_suggestion_creates_plan`, `test_dismiss_ai_suggestion`, `test_post_with_gift_and_suggestion_is_400`, `test_other_users_suggestion_is_404`, `test_ideas_endpoint_for_inaccessible_recipient_is_404`, `test_ai_block_translated_in_french`.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_suggestions_views.py`. Expected: FAIL on the new tests.
- [ ] **Step 3: Implement** the views, URLs, templates and translations; `msgfmt --check`, compile.
- [ ] **Step 4: Add e2e** `test_accept_ai_idea_on_group_page` in `test_gift_suggestions.py`: `monkeypatch.setattr("gift_manager.suggestions.service.get_ai_client", lambda: FakeAIClient(...))` (live_server runs in-process), open the group detail page, wait for `[data-suggestion-source="ai"]` with `"Telescope"`, accept → after reload a plan for `"Telescope"` is listed in the group's gift plans; click `"More ideas"` and see the second canned batch.
- [ ] **Step 5: Run** the view tests and `tox run -e e2e -- gift_manager/tests/e2e/test_gift_suggestions.py`. Expected: PASS.
- [ ] **Step 6: Commit** `Feat(suggestions): Show AI gift ideas with more-ideas action`.

---

### Task 12: Documentation and idea bookkeeping

**Files:**
- Modify: `docs/ai/architecture.md`, `docs/ideas/0001-gift-plan-suggestions-for-recipient.md`, `docs/ideas/README.md`

- [ ] **Step 1:** In `docs/ai/architecture.md`, add a short "Gift suggestions" entry: package layout, the privacy rule (history only through `accessible_by`, payload anonymised in `ai/prompt.py`), and where to switch providers.
- [ ] **Step 2:** In the idea file, record the "Decisions Taken During Planning" (above), answer the three Open Questions with them, set status `Implemented`, and move it to `docs/ideas/implemented/`; update its row in `docs/ideas/README.md` (status, note "Moved to `implemented/`").
- [ ] **Step 3:** Run `graft build` to refresh the context graph.
- [ ] **Step 4: Commit** `Docs(suggestions): Document gift suggestions and close idea 0001`.

---

## Final Verification

- `tox run -e py311 -- gift_manager/tests/suggestions/ gift_manager/tests/views/test_suggestions_views.py gift_manager/tests/views/test_gift_history.py gift_manager/tests/views/test_person_notes_interests.py gift_manager/tests/test_surprise_surfaces.py gift_manager/tests/test_locale_coverage.py` — all pass.
- `tox run -e lint` clean; `python manage.py check`; `python manage.py makemigrations --check --dry-run` clean.
- `tox run -e e2e -- gift_manager/tests/e2e/test_gift_suggestions.py gift_manager/tests/e2e/test_group_gift_history_panel.py` — pass.
- Coverage of `gift_manager/suggestions/` ≥ 80 % (`reports/coverage-py311/`).
- Manual, with `docker compose up`: person and group detail pages (full page and details panel), with AI disabled, then with a real key in `.env` for each provider (`anthropic` with `claude-haiku-5-5`; `openai` with a configured model): ideas appear, "More ideas" works, a bad key shows the notice and catalogue items. Screenshot the section in light/dark theme and at phone width.
- PR description lists the new dependencies `anthropic` and `openai`, the new environment variables, and the measured install size.
