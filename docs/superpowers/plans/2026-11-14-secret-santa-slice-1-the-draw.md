# Secret Santa, Slice 1 (The Draw) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An organizer creates a Secret Santa exchange, adds or imports participants, sets
exclusions, draws (and redraws), and every participant learns who they drew through a
personal secret link, sent by email or handed out by the organizer.

**Architecture:** A new package `gift_manager/secret_santa/` holds its own models, a pure
draw engine, a service layer, email sending and the read rules. Organizer pages are
login-protected and scoped to `organizer=request.user`; participant pages are reached by a
secret token without login, as standalone pages like `wishlist_guest`. Nothing goes through
`PermissionService`: an exchange belongs to its organizer only.

**Tech Stack:** Django 5.x, PostgreSQL, Bootstrap, HTMX (optional), pytest, Playwright. No new
dependency.

**Spec:** `docs/superpowers/specs/2026-11-14-secret-santa-design.md` (read it first; this plan
implements its slice 1 only).

## Global Constraints

- No new production dependency.
- Organizer views return 404, never 403, for an exchange the user does not organize.
- A personal link alone never shows or changes anything of a Gift Manager account. In this
  slice, participant pages read nothing from `linked_account`.
- Organizer pages never load `gives_to` except in the two reveal actions, which are POST,
  answer with `Cache-Control: private, no-store`, and put nothing in the URL.
- A participant page reads only its own `gives_to`; it never queries who drew the participant.
- Participant pages and the stop-emails page send `Referrer-Policy: no-referrer`,
  `Cache-Control: private, no-store`, `X-Robots-Tag: noindex, nofollow`, and do not extend
  `base.html` (copy the head of `templates/gift_manager/wishlist_guest.html`).
- Limits, exact values: at most 100 participants per exchange; at least 3 to draw; at most
  300 exchange emails per organizer per rolling 24 hours; 5 minutes between two "Send again"
  for the same participant, reset when their email is edited.
- Emails contain the exchange name, the organizer's name, the participant's name (subject and
  first line) and the personal link. Never the guidelines text.
- Emails are sent after the database transaction has committed.
- Participant emails are stored with `gift_manager.email_encoding.encode_email` in a
  `TextField`, like `Person.email_address`.
- Every user-facing string is translatable and has a French translation (0 fuzzy, 0 empty).
- Tests run on PostgreSQL: `tox run -e py311 -- <path>`; browser tests:
  `tox run -e e2e -- <path>`. Never run the two at the same time (they share a test database).
- Lint: `git status --short | awk '{print $2}' | xargs pre-commit run --files`.
- Commit messages: sentence case with a type prefix, e.g. `Feat: Add the Secret Santa draw engine`.

## Review Focus

1. **Impossible or huge exclusions.** One exclusion set holding more than half of the
   participants, or 100 participants with dense sets: the organizer gets "no draw is possible"
   quickly, never a hanging request, and nothing is saved. (Task 1, Task 3)
2. **The same person entered twice.** Two imported groups sharing a member, or a name typed
   twice with different case: the second is skipped or refused, so nobody can draw
   themselves. (Task 3)
3. **Mail failures and missing addresses.** One address bounces or the mail server is down:
   the draw stays saved, the other emails go out, and the organizer sees who was not reached.
   A participant without email is simply listed as "link to hand out". (Task 4)
4. **Stale or foreign links.** A regenerated token, a deleted exchange, a token of another
   exchange in the URL of this one, an organizer URL opened by another user: all 404, with no
   hint that the exchange exists. (Task 5, Task 6)
5. **Redraw after people saw their assignment.** A redraw replaces every pairing in one
   transaction; an old email's link then shows the new assignment, never a mix. (Task 3,
   Task 6)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `gift_manager/secret_santa/__init__.py` | Empty package marker. |
| `gift_manager/secret_santa/draw.py` | Pure draw engine. No Django import. |
| `gift_manager/secret_santa/models.py` | `Exchange`, `ExchangeParticipant`, `ExclusionSet`. |
| `gift_manager/secret_santa/service.py` | Create, edit, import, forbidden pairs, draw, redraw, regenerate, delete. |
| `gift_manager/secret_santa/emails.py` | Build and send emails, stop tokens, limits, cooldown. |
| `gift_manager/secret_santa/forms.py` | `ExchangeForm`, `ParticipantForm`, `ExclusionSetForm`, `ImportForm`. |
| `gift_manager/views/secret_santa.py` | Organizer views and participant views. |
| `gift_manager/templates/gift_manager/secret_santa/` | Organizer pages, participant page, stop page. |
| `gift_manager/templates/gift_manager/email/secret_santa_assignment.{txt,html}` | Assignment email. |
| `gift_manager/tests/secret_santa/` | `test_draw.py`, `test_models.py`, `test_service.py`, `test_emails.py`, `test_organizer_views.py`, `test_participant_views.py`. |
| `gift_manager/tests/e2e/test_secret_santa_e2e.py` | Browser test of the main flow. |

`gift_manager/models.py` gets one line at its end so Django registers the new models:
`from gift_manager.secret_santa.models import *  # noqa: E402,F401,F403`. The new models refer
to existing ones by string (`"gift_manager.Person"`) to avoid a circular import.

---

### Task 1: Draw engine

**Files:**
- Create: `gift_manager/secret_santa/__init__.py`, `gift_manager/secret_santa/draw.py`
- Test: `gift_manager/tests/secret_santa/__init__.py`, `gift_manager/tests/secret_santa/test_draw.py`

**Interfaces:**
- Produces:
  - `class NoDrawPossible(Exception)` with attribute `reason: str`, one of
    `"too_few"`, `"impossible"`, `"gave_up"`.
  - `draw(participants: Sequence[int], forbidden: Collection[tuple[int, int]] = (), *, no_mutual: bool = False, rng: random.Random | None = None, max_steps: int = 50_000) -> dict[int, int]`
    returning giver id -> recipient id. `forbidden` holds ordered pairs (giver, recipient).
  - `is_valid(assignment: Mapping[int, int], participants, forbidden, *, no_mutual: bool) -> bool`.
  - `MIN_PARTICIPANTS = 3`.

- [ ] **Step 1: Write the failing tests** in `test_draw.py` (no database):

```python
def test_result_is_a_permutation_without_self_draw():
    result = draw(range(10), rng=random.Random(1))
    assert sorted(result) == sorted(result.values()) == list(range(10))
    assert all(giver != recipient for giver, recipient in result.items())

def test_forbidden_pairs_are_respected():
    forbidden = {(0, 1), (1, 0), (2, 3)}
    for seed in range(50):
        result = draw(range(6), forbidden, rng=random.Random(seed))
        assert not any((g, r) in forbidden for g, r in result.items())

def test_no_mutual_draw():
    for seed in range(50):
        result = draw(range(5), no_mutual=True, rng=random.Random(seed))
        assert all(result[result[g]] != g for g in result)

@pytest.mark.parametrize("count", [0, 1, 2])
def test_too_few_participants(count):
    with pytest.raises(NoDrawPossible) as error:
        draw(range(count))
    assert error.value.reason == "too_few"

def test_set_larger_than_half_is_impossible_and_fast():
    members = range(60)  # 31 people who must not draw each other
    forbidden = {(a, b) for a in range(31) for b in range(31) if a != b}
    start = time.monotonic()
    with pytest.raises(NoDrawPossible) as error:
        draw(members, forbidden)
    assert error.value.reason == "impossible"
    assert time.monotonic() - start < 1

def test_three_people_with_no_mutual_is_a_cycle():
    result = draw([1, 2, 3], no_mutual=True, rng=random.Random(3))
    assert result[result[result[1]]] == 1

def test_three_people_one_couple_no_mutual_is_impossible():
    # 1 and 2 exclude each other: both must give to 3, impossible
    with pytest.raises(NoDrawPossible):
        draw([1, 2, 3], {(1, 2), (2, 1)}, no_mutual=True)

def test_hundred_participants_with_households_is_fast():
    households = [range(i, i + 4) for i in range(0, 100, 4)]
    forbidden = {(a, b) for h in households for a in h for b in h if a != b}
    start = time.monotonic()
    result = draw(range(100), forbidden, no_mutual=True, rng=random.Random(7))
    assert time.monotonic() - start < 2
    assert is_valid(result, range(100), forbidden, no_mutual=True)

def test_step_budget_gives_up_cleanly():
    with pytest.raises(NoDrawPossible) as error:
        draw(range(30), no_mutual=True, max_steps=0)
    assert error.value.reason == "gave_up"

def test_different_seeds_give_different_draws():
    assert len({tuple(sorted(draw(range(8), rng=random.Random(s)).items())) for s in range(20)}) > 1

@given(...)  # hypothesis: 3..25 participants, random forbidden pairs, random no_mutual
def test_any_result_is_valid(...):
    try:
        result = draw(participants, forbidden, no_mutual=no_mutual, rng=random.Random(0))
    except NoDrawPossible:
        return
    assert is_valid(result, participants, forbidden, no_mutual=no_mutual)
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_draw.py` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `draw.py`.** Algorithm, since the signature does not determine it:
  1. Fewer than `MIN_PARTICIPANTS` -> `NoDrawPossible("too_few")`.
  2. Build `allowed[giver]` = participants except the giver and forbidden recipients.
  3. Pre-check with a bipartite matching (augmenting paths) between givers and allowed
     recipients; no perfect matching -> `NoDrawPossible("impossible")`. This ignores
     `no_mutual`, which the search enforces.
  4. Backtracking search: pick the unassigned giver with the fewest remaining candidates
     (ties broken with `rng`), try candidates in `rng`-shuffled order, skip a candidate that
     would create a mutual pair when `no_mutual`, and abandon a branch as soon as an
     unassigned giver has no candidate left or an unassigned recipient has no possible giver.
     Count one step per candidate tried; past `max_steps` -> `NoDrawPossible("gave_up")`.
  5. Search exhausted without a result -> `NoDrawPossible("impossible")`.
  `rng` defaults to `random.SystemRandom()`.

- [ ] **Step 4: Run** the same command — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Add the Secret Santa draw engine`.

---

### Task 2: Models and migration

**Files:**
- Create: `gift_manager/secret_santa/models.py`, migration `0049_secret_santa.py` (generated)
- Modify: `gift_manager/models.py` (last line import), `gift_manager/tests/factories.py`
- Test: `gift_manager/tests/secret_santa/test_models.py`

**Interfaces:**
- Produces (all with `id` plus a public UUID field, `on_delete` as stated):
  - `Exchange`: `exchange_id` (UUID, unique), `organizer` (FK User, CASCADE,
    `related_name="organized_exchanges"`), `name` (max 120), `exchange_date` (DateField,
    required), `budget` (Decimal 10/2, null, >= 0), `currency` (3 chars), `guidelines`
    (TextField, blank), `status` (`Exchange.Status`: `DRAFT="draft"`, `DRAWN="drawn"`,
    `CLOSED="closed"`; default draft), `no_mutual_draw` (bool, default False), `drawn_at`
    (null), `created_at`. Ordering `-created_at`.
  - `ExchangeParticipant`: `participant_id` (UUID, unique), `exchange` (FK, CASCADE,
    `related_name="participants"`), `name` (max 120), `email_address` (TextField, null,
    blank; encoded) with an `email` property and `set_email(value)` like `Person`,
    `token` (CharField 64, unique), `source_person` (FK `"gift_manager.Person"`, SET_NULL,
    null, `related_name="+"`), `linked_account` (FK User, SET_NULL, null,
    `related_name="exchange_participations"`), `gives_to` (FK self, SET_NULL, null,
    `related_name="drawn_by"`), `emails_stopped` (bool, default False), `last_emailed_at`
    (null), `created_at`. Ordering `name`.
    - `regenerate_token() -> str` (uses `secrets.token_urlsafe(32)`, saves only `token`).
    - `save()` sets a token when empty.
  - `ExclusionSet`: `set_id` (UUID, unique), `exchange` (FK, CASCADE,
    `related_name="exclusion_sets"`), `name` (max 120), `participants` (M2M
    `ExchangeParticipant`, `related_name="exclusion_sets"`).
  - Constraints on `ExchangeParticipant`: unique `(exchange, Lower("name"))` named
    `ss_participant_unique_name`; unique `(exchange, source_person)` where source person is
    not null, `ss_participant_unique_source`; unique `(exchange, linked_account)` where not
    null, `ss_participant_unique_account`.
  - `MAX_PARTICIPANTS = 100` (module constant).
  - Factories: `ExchangeFactory`, `ExchangeParticipantFactory`, `ExclusionSetFactory`.

- [ ] **Step 1: Write the failing tests** in `test_models.py`:

```python
def test_participant_gets_a_token_and_regenerating_changes_it(): ...
    # len(token) >= 43; regenerate_token() returns a different value and persists it
def test_email_is_stored_encoded_and_read_decoded(): ...
    # participant.set_email("a@example.com"); "a@example.com" not in email_address; .email == it
def test_names_are_unique_in_an_exchange_ignoring_case(): ...
    # "Anna" then "anna" in the same exchange -> IntegrityError; allowed in another exchange
def test_a_source_person_or_an_account_appears_once_per_exchange(): ...
def test_two_participants_may_share_an_email(): ...
def test_deleting_the_exchange_deletes_participants_and_sets(): ...
def test_deleting_a_linked_user_or_source_person_keeps_the_participant(): ...
    # linked_account / source_person become None
def test_deleting_the_organizer_deletes_the_exchange(): ...
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_models.py` — expected: FAIL.
- [ ] **Step 3: Implement** the models, the import line, the factories; run
  `python manage.py makemigrations gift_manager -n secret_santa` and read the migration
  (three models, three constraints, nothing touching existing tables).
- [ ] **Step 4: Run** the tests and `tox run -e py311 -- gift_manager/tests/test_migrations.py` — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Add the Secret Santa exchange models`.

---

### Task 3: Service layer

**Files:**
- Create: `gift_manager/secret_santa/service.py`
- Test: `gift_manager/tests/secret_santa/test_service.py`

**Interfaces:**
- Consumes: Task 1 `draw`, `NoDrawPossible`, `MIN_PARTICIPANTS`; Task 2 models.
- Produces:
  - `class ExchangeError(Exception)`: carries a translated, user-facing `message`.
  - `organized_by(user) -> QuerySet[Exchange]`.
  - `create_exchange(organizer, *, name, exchange_date, budget=None, guidelines="", no_mutual_draw=False, organizer_takes_part=False) -> Exchange`
    (copies `organizer.profile.currency`; when taking part, adds a participant named
    `organizer.get_full_name().strip() or organizer.username`, with the organizer's decoded
    email and `linked_account=organizer`).
  - `add_participant(exchange, *, name, email="") -> ExchangeParticipant`.
  - `import_persons(exchange, organizer, persons: Iterable[Person]) -> tuple[int, int]`
    returning (added, skipped). Only persons in `Person.objects.accessible_by(organizer)` are
    used. Name: `str(person)`. Carries `person.email` and `person.account`. Skips a person
    already present (same source person, same linked account, or same name ignoring case).
  - `import_group(exchange, organizer, group: PersonGroup) -> tuple[int, int]`: the group
    must be in `PersonGroup.objects.accessible_by(organizer)`; imports its direct and nested
    members through `hierarchy_subquery`.
  - `update_participant(participant, *, name, email) -> ExchangeParticipant` (allowed in draft
    and drawn; clears `last_emailed_at` when the email changes).
  - `remove_participant(participant) -> None` (draft only).
  - `save_exclusion_set(exchange, *, name, participants, instance=None) -> ExclusionSet` and
    `delete_exclusion_set(exclusion_set) -> None` (draft only; participants must belong to
    the exchange; at least two).
  - `forbidden_pairs(exchange) -> set[tuple[int, int]]`: every ordered pair of two distinct
    members of one exclusion set, by participant primary key.
  - `run_draw(exchange, *, rng=None) -> list[ExchangeParticipant]`: draft or drawn (a redraw);
    in one transaction with the exchange row locked, replaces every `gives_to`, sets
    `status=DRAWN` and `drawn_at`; returns the participants. Raises `ExchangeError` with the
    messages below.
  - `delete_exchange(exchange) -> None`.
- Rules raising `ExchangeError`:
  - 101st participant: "An exchange can have at most 100 participants."
  - duplicate name: "Two participants cannot have the same name."
  - editing participants or sets while drawn (except name/email): "The draw is done. Redraw
    to change the participants or the exclusions."
  - any change on a closed exchange: "This exchange is closed."
  - `NoDrawPossible("too_few")`: "At least 3 participants are needed."
  - `"impossible"`: "No draw is possible with these exclusions."
  - `"gave_up"`: "No draw was found. Try again or relax the exclusions."

- [ ] **Step 1: Write the failing tests** in `test_service.py`:

```python
def test_create_exchange_copies_the_organizer_currency(): ...
def test_organizer_taking_part_becomes_a_linked_participant(): ...
def test_add_participant_refuses_a_duplicate_name_ignoring_case(): ...
def test_add_participant_refuses_the_101st(): ...
def test_import_persons_copies_name_email_and_account_link(): ...
def test_import_skips_people_already_present():
    # same person twice; a second person record linked to the same account; same name
    assert service.import_persons(exchange, user, [person, person, same_account, same_name]) == (1, 3)
def test_import_ignores_persons_the_organizer_cannot_access(): ...
def test_import_group_includes_nested_members_once(): ...
def test_import_group_the_organizer_cannot_access_is_refused(): ...
def test_forbidden_pairs_cover_every_pair_of_a_set_in_both_directions(): ...
def test_exclusion_set_needs_two_participants_of_the_same_exchange(): ...
def test_run_draw_assigns_everyone_and_marks_the_exchange_drawn(): ...
    # every gives_to set, a permutation, no self draw, respects sets and no_mutual_draw
def test_run_draw_with_impossible_exclusions_saves_nothing():
    with pytest.raises(ExchangeError, match="No draw is possible"):
        service.run_draw(exchange)
    exchange.refresh_from_db()
    assert exchange.status == Exchange.Status.DRAFT
    assert not exchange.participants.filter(gives_to__isnull=False).exists()
def test_run_draw_needs_three_participants(): ...
def test_redraw_replaces_every_pairing_in_one_go(): ...
    # after a redraw with another seed: still a valid permutation, drawn_at updated
def test_failed_redraw_keeps_the_previous_pairings(monkeypatch): ...
    # draw raising NoDrawPossible("gave_up") leaves gives_to unchanged
def test_participants_and_sets_are_frozen_after_the_draw_except_name_and_email(): ...
def test_update_participant_email_clears_the_send_again_cooldown(): ...
def test_renaming_to_an_existing_name_is_refused_after_the_draw_too(): ...
def test_delete_exchange_removes_everything(): ...
def test_organized_by_returns_only_my_exchanges(): ...
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_service.py` — expected: FAIL.
- [ ] **Step 3: Implement `service.py`.** Convert `IntegrityError` on the constraints into
  `ExchangeError`; check for duplicates before saving so the common case needs no exception.
- [ ] **Step 4: Run** — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Add the Secret Santa exchange service`.

---

### Task 4: Emails, stop link and limits

**Files:**
- Create: `gift_manager/secret_santa/emails.py`,
  `gift_manager/templates/gift_manager/email/secret_santa_assignment.txt`, `.html`
- Modify: `GiftManager/settings/base.py` (`SECRET_SANTA_EMAIL_LIMIT = 300`,
  `SECRET_SANTA_EMAIL_WINDOW_SECONDS = 86400`, `SECRET_SANTA_RESEND_COOLDOWN_SECONDS = 300`)
- Test: `gift_manager/tests/secret_santa/test_emails.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces:
  - `participant_path(participant) -> str`: the path of the personal page, reversed with the
    organizer's language active (`translation.override(exchange.organizer.profile.language)`).
  - `make_stop_token(participant) -> str` / `read_stop_token(token: str) -> int | None`
    (Django `signing`, salt `"gift_manager.secret_santa.stop"`, payload: participant pk).
  - `@dataclass SendReport`: `sent: list[ExchangeParticipant]`, `no_email: list[...]`,
    `stopped: list[...]`, `failed: list[...]`, `over_limit: list[...]`.
  - `send_assignments(exchange, participants, build_absolute_uri: Callable[[str], str]) -> SendReport`:
    one mail connection for all messages; a participant without email goes to `no_email`,
    with `emails_stopped` to `stopped`; an exception for one recipient is logged and goes to
    `failed`; once the organizer's quota is used up the rest go to `over_limit`. Sets
    `last_emailed_at` for each sent email. The email language is the linked account's
    `profile.language` when linked, otherwise the organizer's.
  - `can_send_again(participant, now=None) -> bool` (cooldown from `last_emailed_at`).
  - `send_again(participant, build_absolute_uri) -> SendReport` (raises
    `service.ExchangeError("Wait a few minutes before sending this email again.")` during
    the cooldown; refuses a draft exchange).
  - The quota uses the cache like `invitations.invitation_send_limit_exceeded`, key
    `gift_manager:secret-santa-emails:{organizer.pk}`, counting one per email.
- Email content: subject `Secret Santa "{exchange}": your link, {participant}`; first line
  `Hello {participant},`; then one sentence naming the organizer, the personal link, and the
  stop link. Headers `List-Unsubscribe` and `List-Unsubscribe-Post` like the digest
  (`gift_manager/digest_sending.py::_build_message`). The recipient's name is NOT in the
  email: the assignment is only on the page.

- [ ] **Step 1: Write the failing tests** in `test_emails.py` (locmem backend, `mail.outbox`):

```python
def test_one_email_per_participant_with_an_address(): ...
    # 3 participants, one without email: len(outbox) == 2; report.no_email == [that one]
def test_email_names_the_participant_and_holds_the_personal_and_stop_links(): ...
    # participant.name in subject and body; participant.token in body; "List-Unsubscribe" header
def test_email_never_contains_the_guidelines_nor_the_recipient_name(): ...
def test_stopped_participants_get_nothing(): ...
def test_one_failing_recipient_does_not_stop_the_others(monkeypatch): ...
    # a connection whose send_messages raises for one address: others sent, report.failed has it
def test_quota_stops_sending_and_reports_the_rest(settings):
    settings.SECRET_SANTA_EMAIL_LIMIT = 2
    report = send_assignments(exchange, five_participants, build)
    assert len(report.sent) == 2 and len(report.over_limit) == 3
def test_quota_is_per_organizer(): ...
def test_send_again_respects_the_cooldown(): ...
def test_send_again_is_allowed_after_an_email_change(): ...
def test_linked_participant_gets_their_own_language(): ...
    # linked account with profile.preferred_language="fr": French subject
def test_stop_token_round_trip_and_tampering(): ...
    # read_stop_token(make_stop_token(p)) == p.pk; read_stop_token("x") is None
def test_personal_path_uses_the_organizer_language_prefix(): ...
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_emails.py` — expected: FAIL.
- [ ] **Step 3: Implement** `emails.py` and the two templates.
- [ ] **Step 4: Run** — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Send Secret Santa assignment emails`.

---

### Task 5: Organizer pages

**Files:**
- Create: `gift_manager/secret_santa/forms.py`, `gift_manager/views/secret_santa.py`,
  templates `secret_santa/exchange_list.html`, `exchange_form.html`, `exchange_detail.html`,
  `includes/secret_santa_participants.html`, `includes/secret_santa_revealed_link.html`,
  `includes/secret_santa_pairings.html`
- Modify: `gift_manager/urls.py`, `gift_manager/views/__init__.py`,
  `gift_manager/templates/gift_manager/base.html` ("More" menu entry "Secret Santa", icon
  `fa-hat-wizard`), `gift_manager/templatetags/navigation_tags.py` (add the fragment
  `"secret_santa"` to the `more` section)
- Test: `gift_manager/tests/secret_santa/test_organizer_views.py`

**Interfaces:**
- Consumes: Task 3 service, Task 4 emails.
- Produces URL names (all under `secret-santa/`, login required):

| Name | Path | Method | Does |
| --- | --- | --- | --- |
| `secret_santa_list` | `` | GET | My exchanges. |
| `secret_santa_create` | `new/` | GET, POST | Create, then go to detail. |
| `secret_santa_detail` | `<uuid:exchange_id>/` | GET | Participants, sets, actions. |
| `secret_santa_edit` | `<uuid>/edit/` | GET, POST | Name, date, budget, guidelines, switch (switch only in draft). |
| `secret_santa_delete` | `<uuid>/delete/` | POST | Delete, back to list. |
| `secret_santa_participant_add` | `<uuid>/participants/add/` | POST | Typed participant. |
| `secret_santa_participant_import` | `<uuid>/participants/import/` | POST | Fields `group` (uuid) and/or `persons` (uuids). |
| `secret_santa_participant_edit` | `<uuid>/participants/<uuid:participant_id>/edit/` | POST | Name and email. |
| `secret_santa_participant_remove` | `<uuid>/participants/<uuid>/remove/` | POST | Draft only. |
| `secret_santa_set_save` | `<uuid>/sets/save/` | POST | Create or update (hidden `set_id`). |
| `secret_santa_set_delete` | `<uuid>/sets/<uuid:set_id>/delete/` | POST | Draft only. |
| `secret_santa_draw` | `<uuid>/draw/` | POST | Draw or redraw, then send emails. |
| `secret_santa_send_again` | `<uuid>/participants/<uuid>/send-again/` | POST | Re-send one email. |
| `secret_santa_show_link` | `<uuid>/participants/<uuid>/show-link/` | POST | Reveal one link. |
| `secret_santa_regenerate_link` | `<uuid>/participants/<uuid>/regenerate-link/` | POST | New token. |
| `secret_santa_pairings` | `<uuid>/pairings/` | POST | Reveal all pairings. |

- Behavior to pin:
  - Every view looks the exchange up with `service.organized_by(request.user)` and 404s
    otherwise; participant and set ids are looked up inside that exchange.
  - `ExchangeError` messages are shown with `messages.error` and the user returns to the
    detail page; nothing is saved.
  - Detail page: the participant queryset is `.defer("gives_to")` and the template never
    names a recipient. Per participant it shows: name, email or "no email", and, once drawn,
    "email sent" / "link to hand out" / "emails stopped", with "Send again" (only with an
    email and outside the cooldown), "Show link", "New link".
  - `secret_santa_draw`: calls `service.run_draw`, then
    `transaction.on_commit(lambda: emails.send_assignments(...))` and reports counts with
    `messages` (sent, without email, failed, over the limit). A redraw (status drawn) is
    offered behind a confirmation modal reusing `includes/delete_confirmation_modal.html`
    style: "Everyone will get a new assignment."
  - `secret_santa_show_link` and `secret_santa_pairings` require a posted `confirm=1`
    (the page's confirmation dialog posts it); without it they answer 400. They answer with
    the partial only, `Cache-Control: private, no-store`. Pairings text:
    "X gives to Y" per line. The dialog text for pairings says it shows who everyone drew;
    when the organizer takes part it adds "including who drew you".
  - Import form: a select of the organizer's groups (`PersonGroup.objects.accessible_by`) and
    a multi-select of their persons; reports "N added, M already there".

- [ ] **Step 1: Write the failing tests** in `test_organizer_views.py`:

```python
def test_every_organizer_url_requires_login(client, exchange): ...            # 302 to login
def test_another_user_gets_404_on_every_organizer_url(other_client, exchange): ...
def test_create_exchange_and_take_part(authenticated_client): ...
def test_add_edit_remove_participant(authenticated_client, exchange): ...
def test_duplicate_name_shows_an_error_and_saves_nothing(...): ...
def test_import_group_and_persons_reports_added_and_skipped(...): ...
def test_import_refuses_a_group_of_another_user(...): ...
def test_exclusion_set_with_participants_of_another_exchange_is_refused(...): ...
def test_draw_sends_emails_after_commit_and_reports(authenticated_client, exchange, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client.post(url("secret_santa_draw"), follow=True)
    assert exchange refreshed is DRAWN and len(mail.outbox) == participants with email
def test_impossible_draw_shows_the_message_and_stays_draft(...): ...
def test_detail_page_never_contains_a_pairing(authenticated_client, drawn_exchange):
    content = authenticated_client.get(detail_url).content.decode()
    for participant in drawn_exchange.participants.select_related("gives_to"):
        assert f"{participant.name} gives to" not in content
    # and the detail query does not select gives_to_id (CaptureQueriesContext)
def test_show_link_needs_confirmation_and_post(...): ...     # GET 405, POST without confirm 400
def test_show_link_returns_the_link_uncached(...): ...        # token in body, no-store header
def test_pairings_need_confirmation_and_list_everyone(...): ...
def test_regenerate_link_kills_the_old_one(...): ...          # old token page 404, new 200
def test_send_again_during_cooldown_shows_an_error(...): ...
def test_redraw_changes_assignments_and_resends(...): ...
def test_participants_cannot_be_added_after_the_draw_but_can_be_renamed(...): ...
def test_delete_exchange(...): ...
def test_more_menu_links_to_secret_santa(authenticated_client): ...
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_organizer_views.py` — expected: FAIL.
- [ ] **Step 3: Implement** forms, views, templates, URLs, navigation. Plain pages and POST
  forms with redirects; the two reveal actions use `hx-post` with a plain-form fallback that
  renders the same partial inside the detail page layout.
- [ ] **Step 4: Run** — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Add the Secret Santa organizer pages`.

---

### Task 6: Participant page and stop-emails page

**Files:**
- Create: templates `secret_santa/participant_page.html`, `secret_santa/stop_emails.html`
  (standalone, head copied from `wishlist_guest.html`)
- Modify: `gift_manager/views/secret_santa.py`, `gift_manager/urls.py`,
  `gift_manager/views/__init__.py`
- Test: `gift_manager/tests/secret_santa/test_participant_views.py`

**Interfaces:**
- Consumes: Task 2 models, Task 4 `read_stop_token`.
- Produces:
  - `secret_santa_participant` at `secret-santa/p/<str:token>/` — GET only (`require_safe`),
    no login.
  - `secret_santa_stop_emails` at `secret-santa/stop/<str:token>/` — GET asks for
    confirmation, POST sets `emails_stopped=True` (CSRF-exempt like `DigestUnsubscribeView`,
    the signed token being the only credential).
- Behavior to pin:
  - Lookup: `ExchangeParticipant` by `token`, with `exchange__organizer__is_active=True`;
    unknown token 404.
  - The page is rendered in the organizer's language (`translation.override`), whatever the
    URL prefix or the visitor's session.
  - Shows: exchange name, date, budget formatted with `format_price` in the exchange
    currency (omitted when empty), guidelines (`linebreaksbr`), the participant names in
    alphabetical order, and:
    - draft: "The draw has not been done yet."
    - drawn: "You give a gift to: {name}".
    - closed: "This exchange is over." and nothing else (slice 3 completes this).
  - The view loads the participant with `select_related("exchange", "gives_to")` and the
    names with `.only("name")`; it never touches `drawn_by`.
  - Three response headers from Global Constraints; `meta referrer` before any `<link>`.

- [ ] **Step 1: Write the failing tests** in `test_participant_views.py`:

```python
def test_page_before_the_draw(client, exchange): ...           # 200, names listed, no assignment
def test_page_after_the_draw_shows_only_my_recipient(client, drawn_exchange):
    me = drawn_exchange.participants.first()
    content = client.get(page(me.token)).content.decode()
    assert f"You give a gift to: {me.gives_to.name}" in content
    assert "gives to" not in content
def test_page_never_reads_who_drew_me(client, drawn_exchange): ...
    # CaptureQueriesContext: no query filters on gives_to_id = me.pk
def test_page_after_a_redraw_shows_the_new_recipient(...): ...
def test_guidelines_are_escaped(client, exchange): ...          # "<script>" in guidelines not raw
def test_headers_and_meta(client, exchange): ...
def test_unknown_token_and_inactive_organizer_are_404(...): ...
def test_token_of_a_deleted_exchange_is_404(...): ...
def test_page_is_read_only(client, exchange): ...               # POST 405
def test_page_uses_the_organizer_language(client, exchange): ...
    # organizer preferred_language="fr": French text even at /en/ URL
def test_linked_participant_page_shows_nothing_of_the_account(client, exchange): ...
    # participant linked to a user with wishes: page identical to an unlinked one, no wish title
def test_closed_exchange_page_hides_the_assignment(...): ...
def test_stop_emails_get_asks_and_post_stops(client, participant): ...
def test_stop_emails_with_a_bad_token_is_400(client): ...
```

- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_participant_views.py` — expected: FAIL.
- [ ] **Step 3: Implement** the two views and templates.
- [ ] **Step 4: Run** — expected: PASS.
- [ ] **Step 5: Lint and commit** — `Feat: Add the Secret Santa personal page`.

---

### Task 7: Browser test, translations, documentation, full verification

**Files:**
- Create: `gift_manager/tests/e2e/test_secret_santa_e2e.py`
- Modify: `locale/fr/LC_MESSAGES/django.po` and `.mo`, `docs/ai/architecture.md` (one bullet
  under Patterns: the package, the secrecy rules, that it bypasses `PermissionService` on
  purpose), `docs/ideas/0034-secret-santa-draws-for-groups.md` (status `Ready`, a note that
  the design document supersedes it and that slice 1 is implemented),
  `docs/ideas/README.md` (row 0034 updated)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the browser test** (markers `django_db(transaction=True)`, `frontend`,
  `e2e`; fixtures `browser`, `browser_context_args`, `live_server`, `seed_data_e2e`; log in
  as `alice` like `test_wishlist_e2e.py`):
  1. Open "More" > "Secret Santa", create an exchange dated in the future, taking part.
  2. Add three typed participants, one without email; add an exclusion set of two.
  3. Draw. Assert the status shows the draw is done and the page text contains no
     "gives to".
  4. "Show link" for the participant without email: confirm the dialog, read the link.
  5. Open the link in a fresh anonymous context at 390x844: the recipient's name is one of
     the other participants and not a member of the same exclusion set; no `nav`, no
     horizontal scroll.
  6. Reveal the pairings: four lines, the one for that participant matches step 5.
  7. Redraw, confirm; the anonymous page still answers 200.
- [ ] **Step 2: Run** `tox run -e e2e -- gift_manager/tests/e2e/test_secret_santa_e2e.py` — expected: PASS (fix the feature, not the test, on a real failure).
- [ ] **Step 3: Translations.** `python manage.py makemessages -l fr` (never with
  `--no-location`), translate every new entry, `python manage.py compilemessages -l fr`,
  then `msgfmt --check --statistics -o /dev/null locale/fr/LC_MESSAGES/django.po` — expected:
  0 fuzzy, 0 untranslated. Use "échange", "tirage au sort", "participant".
- [ ] **Step 4: Documentation** edits listed above.
- [ ] **Step 5: Full verification**, one after the other:
  `tox run -e py311 -- -q -p no:warnings` then
  `tox run -e e2e -- gift_manager/tests/e2e/test_secret_santa_e2e.py gift_manager/tests/e2e/test_wishlist_e2e.py`
  and the lint command — expected: all pass. Take a screenshot of the organizer detail page
  and of the participant page and look at them.
- [ ] **Step 6: Commit** — `Feat: Translate and document the Secret Santa draw`.

---

## Not in this slice

Exchange wishes and notes, invitations and declining, attaching an account, sharing real
wishes, the dashboard card, "Plan a gift" (slice 2); remove and repair, add and repair,
closing and reveal, starting from a previous exchange and its switch (slice 3). The `closed`
status exists in the model but no page sets it yet.
