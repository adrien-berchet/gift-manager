# Secret Santa, Slice 3 (After The Draw) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The organizer fixes problems after the draw without starting over (remove and repair,
add and repair, or the same with a full redraw), closes the exchange with an optional reveal of
all pairings, and starts a new exchange from a previous one without repeating its pairs.

**Architecture:** Builds on slices 1 and 2 (`gift_manager/secret_santa/`). The two repairs are
pure functions in `draw.py`, validated with the same rules as a draw. `service.py` gathers every
active rule in one place (`draw_rules`) used by draws and repairs alike, and adds the repair,
close and copy operations. Emails of repaired participants go out after the commit, like a draw.

**Tech Stack:** Django 5.x, PostgreSQL, Bootstrap, pytest, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-14-secret-santa-design.md` (slice 3 of "Slices",
"After the draw", "Closing"). Earlier plans: `2026-11-14-secret-santa-slice-1-the-draw.md`,
`2026-11-15-secret-santa-slice-2-telling-your-santa.md` (their Global Constraints still apply).

## Global Constraints

- Everything in the slice 1 and 2 Global Constraints still holds (secrecy of `gives_to` on
  organizer pages, personal pages read only their own `gives_to`, emails after commit, privacy
  headers, `strict-origin` on pages with forms, translations, tests and lint commands).
- A repair is checked against every active rule: nobody draws themselves, exclusion sets,
  previous-exchange pairs when "no repeat" is on, no mutual draw when that switch is on. A
  repair that breaks one is refused with a message and nothing is saved; a full redraw stays
  available. Removing someone from a mutual pair (A gives to X, X gives to A) is refused.
- A removal (with repair or redraw) that would leave fewer than 3 participants taking part is
  refused: "At least 3 participants are needed."
- "Remove and redraw everything" and "Add and redraw everything" are one transaction each:
  nothing changes if the redraw fails.
- Only the participants whose recipient changed get a new email: the Santa of the removed
  person; A, C and the latecomer for an insertion; everyone for a redraw.
- Wishes, notes and wishlist selections survive repairs and redraws (they live on the
  participant). A removed participant is deleted with their wishes.
- Closing: only a drawn exchange, from its exchange date (the server's local date) on; final;
  personal pages then show "This exchange is over.", are read-only and show no shared content;
  when the organizer chose to reveal, they list who gave to whom (participants taking part).
  Pairings are kept after closing.
- Copy: participants (name, email, source person, `emails_stopped`, `previous_participant`) and
  exclusion sets. An account link is copied only when it comes from the source person
  (`source_person.account`) or is the organizer taking part; a link the participant attached
  themselves is not copied (designer's call: they attach again). Declines, invitations, wishes,
  notes and selections are not copied; tokens are new.

## Review Focus

1. **A repair that looks valid but is not.** Removal from a mutual pair, removal whose
   repaired pair is in an exclusion set or a previous-exchange pair, insertion when every pair of
   pairings breaks a rule: refused, pairings untouched, no email sent. (Tasks 1, 3)
2. **Secrecy of a repair.** The insertion never makes the latecomer give to A's former recipient
   (A would deduce it); the removal emails only the one Santa; organizer pages still never load
   `gives_to`. (Tasks 1, 3)
3. **Closing too early or twice.** Before the exchange date, on a draft, or already closed:
   refused. After closing every participant write is refused and the Santa no longer sees the
   recipient's wishes, even through an old personal link. (Task 4)
4. **Revealing without consent.** A closed exchange without reveal never reads anyone else's
   `gives_to` on a personal page; with reveal, it lists only participants who took part. (Task 4)
5. **Copying an exchange with history.** A previous exchange deleted later, a participant removed
   from the new one, a previous participant who declined: the "no repeat" rule only forbids pairs
   that actually happened and never crashes on missing rows. (Task 2)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `gift_manager/secret_santa/draw.py` | `repair_removal`, `repair_insertion` (pure). |
| `gift_manager/secret_santa/models.py` | `Exchange.no_repeat_draw`, `previous_exchange`, `pairings_revealed`, `closed_at`; `ExchangeParticipant.previous_participant`. |
| `gift_manager/secret_santa/service.py` | `draw_rules`, repairs, `close_exchange`, `copy_exchange`. |
| `gift_manager/secret_santa/forms.py` | `ExchangeForm.no_repeat_draw`, `LatecomerForm`, `CloseForm`. |
| `gift_manager/views/secret_santa.py`, `urls.py` | Repair, close and copy views; personal page closed state. |
| Templates `secret_santa/exchange_detail.html`, `includes/secret_santa_participants.html`, `secret_santa/exchange_form.html`, `secret_santa/participant_page.html` | UI. |
| Tests: `test_draw.py`, `test_service.py`, `test_organizer_views.py`, `test_participant_views.py`, `test_models.py`, e2e third test. | |

---

### Task 1: Repairs in the draw engine

**Files:** `gift_manager/secret_santa/draw.py`; test `test_draw.py`.

**Interfaces — Produces:**
- `repair_removal(assignment: Mapping[int, int], removed: int, forbidden, *, no_mutual: bool) -> dict[int, int]`:
  the giver of `removed` now gives to `removed`'s recipient; `removed` disappears. Raises
  `NoDrawPossible(IMPOSSIBLE)` when the result breaks a rule (mutual pair, forbidden pair,
  mutual draw) and `NoDrawPossible(TOO_FEW)` below `MIN_PARTICIPANTS`.
- `repair_insertion(assignment, newcomer: int, forbidden, *, no_mutual: bool, rng=None) -> tuple[dict[int, int], set[int]]`:
  chooses, uniformly at random (`rng`, default `SystemRandom`) among every valid choice, two
  givers A and C (A != C, C != assignment[A]) with B = assignment[A], D = assignment[C]; result
  A -> newcomer, newcomer -> D, C -> B. Returns the new assignment and `{A, C, newcomer}` (who
  needs a new email). Only the three new pairs need checking (self, forbidden, mutual against
  the new assignment). No valid choice -> `NoDrawPossible(IMPOSSIBLE)`.

- [ ] **Step 1: Tests** — `test_removal_reconnects_the_chain`,
  `test_removal_from_a_mutual_pair_is_refused`, `test_removal_respecting_forbidden_and_mutual`
  (forbidden repaired pair -> refused; repaired pair making a mutual pair with no_mutual ->
  refused), `test_removal_below_three_is_refused`, `test_insertion_changes_two_pairings_only`
  (every other pair unchanged, the result `is_valid`), `test_insertion_never_gives_the_newcomer_As_former_recipient`
  (newcomer's recipient != B over many seeds), `test_insertion_respects_forbidden_pairs_of_the_newcomer`,
  `test_insertion_impossible`, `test_insertion_choices_vary_with_the_seed`, a Hypothesis test that
  any insertion or removal result `is_valid` or raises `NoDrawPossible`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Repair a Secret Santa draw after a removal or an addition`.

---

### Task 2: Previous exchange: model, rules and copy

**Files:** `models.py`, migration `0051_secret_santa_slice_3.py`, `service.py`, `forms.py`,
`views/secret_santa.py` (create view), `exchange_form.html`, `exchange_detail.html`; tests
`test_models.py`, `test_service.py`, `test_organizer_views.py`.

**Interfaces — Produces:**
- `Exchange`: `no_repeat_draw` (bool, False), `previous_exchange` (FK self, SET_NULL, null,
  `related_name="+"`), `pairings_revealed` (bool, False), `closed_at` (null).
  `ExchangeParticipant.previous_participant` (FK self, SET_NULL, null, `related_name="+"`).
- `service.draw_rules(exchange) -> tuple[set[tuple[int, int]], bool]`: forbidden pairs (exclusion
  sets, plus previous-exchange pairs when `no_repeat_draw` and a previous exchange exists) and
  `no_mutual`. Previous pairs: (p, q) for participants p, q of this exchange whose
  `previous_participant`s were paired as p' -> q' in the previous exchange. `run_draw` uses it.
- `service.copy_exchange(previous, organizer, *, name, exchange_date, budget, guidelines, no_mutual_draw, no_repeat_draw=True) -> Exchange`
  (rules in Global Constraints; exclusion sets copied with the copied members, sets left with
  fewer than two members dropped).
- `update_exchange` accepts `no_repeat_draw` (draft only to change, like `no_mutual_draw`).
- Create view: `?from=<exchange uuid>` (an exchange the user organizes, else 404) prefills name,
  budget, guidelines and the switches, shows the "Nobody draws the same person as in the
  previous exchange" switch (checked), and calls `copy_exchange`. Detail page: "Start a new
  exchange from this one" link. Edit form shows the switch only when `previous_exchange` is set.

- [ ] **Step 1: Tests** — models: `test_deleting_the_previous_exchange_keeps_the_copy`;
  service: `test_copy_copies_participants_and_sets`, `test_copy_keeps_emails_stopped_and_source_links_only`,
  `test_copy_drops_a_set_left_with_one_member`, `test_no_repeat_forbids_last_years_pairs`,
  `test_no_repeat_off_or_without_history_forbids_nothing`, `test_no_repeat_survives_a_deleted_previous_exchange`;
  views: `test_create_from_a_previous_exchange`, `test_create_from_an_exchange_of_another_user_is_404`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**, migration read. **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Start a Secret Santa from a previous exchange without repeats`.

---

### Task 3: Repairs in the service and the organizer page

**Files:** `service.py`, `forms.py`, `views/secret_santa.py`, `urls.py`, `views/__init__.py`,
`includes/secret_santa_participants.html`, `exchange_detail.html`; tests `test_service.py`,
`test_organizer_views.py`.

**Interfaces — Consumes:** Task 1 repairs, Task 2 `draw_rules`.
**Produces:**
- `service.remove_and_repair(participant) -> list[ExchangeParticipant]` (drawn only; a declined
  participant without pairing is simply deleted and returns []), `service.remove_and_redraw(participant) -> list[...]`,
  `service.add_and_repair(exchange, *, participant=None, name="", email="", exclusion_sets=(), rng=None) -> list[...]`
  (a new latecomer from name/email, or an existing declined participant put back; joins the
  chosen exclusion sets of the exchange), `service.add_and_redraw(...)` same arguments. Each
  returns the participants to email; each runs in one transaction with the exchange locked;
  repairs clear `last_emailed_at` of the participants whose recipient changed. Messages:
  "No repair keeps every rule. Redraw everything instead." for an impossible repair.
- Organizer URLs (POST): `secret_santa_remove_repair`, `secret_santa_remove_redraw`
  (`<uuid>/participants/<uuid>/remove-repair/`, `.../remove-redraw/`), `secret_santa_add_latecomer`
  (`<uuid>/latecomer/`, fields name, email, sets, optional `participant` uuid for a declined
  participant, and `mode` = `repair` | `redraw`). Emails sent on commit like `secret_santa_draw`.
- Page (drawn): per participant a "Remove" `<details>` with both buttons and their warning
  ("Only the person who drew {name} gets a new assignment." / "Everyone gets a new assignment.");
  per declined participant "Put back" with both modes; an "Add a latecomer" `<details>` form
  (name, email, exclusion sets) with "Add and repair" and "Add and redraw everything".

- [ ] **Step 1: Tests** — service: `test_remove_and_repair_changes_one_pairing_and_returns_the_santa`,
  `test_remove_from_a_mutual_pair_is_refused_and_nothing_changes`, `test_remove_below_three_is_refused`,
  `test_remove_and_redraw_rolls_back_on_failure`, `test_add_and_repair_changes_two_pairings`,
  `test_add_and_repair_puts_back_a_declined_participant`, `test_add_and_repair_joins_the_chosen_sets`,
  `test_impossible_insertion_saves_nothing` (no new participant), `test_repairs_respect_no_repeat`,
  `test_repairs_keep_wishes_and_notes`; views: `test_repair_urls_are_scoped`,
  `test_remove_and_repair_emails_only_the_santa`, `test_add_and_repair_emails_three_people`,
  `test_detail_page_still_never_loads_gives_to` (drawn, with the new forms).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Remove or add Secret Santa participants after the draw`.

---

### Task 4: Closing and the reveal

**Files:** `service.py`, `forms.py`, `views/secret_santa.py`, `urls.py`, `exchange_detail.html`,
`participant_page.html`; tests `test_service.py`, `test_organizer_views.py`,
`test_participant_views.py`.

**Interfaces — Produces:**
- `service.close_exchange(exchange, *, reveal: bool, today: date | None = None) -> None`: drawn
  only ("Only a drawn exchange can be closed."), not before `exchange_date` ("The exchange can
  be closed from {date}."); sets `status=CLOSED`, `closed_at`, `pairings_revealed=reveal`.
- URL `secret_santa_close` (`<uuid>/close/`, POST, field `reveal`). Detail page (drawn, from the
  date): "Close the exchange" modal with the "Show every participant who gave to whom" checkbox
  and the warning that closing is final. Closed page: no repair, invite, draw or edit actions;
  "Start a new exchange from this one" stays.
- Personal page when closed: "This exchange is over."; when `pairings_revealed`, the list
  "{giver} gave to {recipient}" of participants who took part (read only then). Nothing else.

- [ ] **Step 1: Tests** — service: `test_close_only_drawn_and_from_the_date`,
  `test_close_twice_is_refused`, `test_close_keeps_pairings`; views: `test_close_url_is_scoped`,
  `test_closed_detail_page_offers_no_change`; personal page:
  `test_closed_without_reveal_reads_no_other_pairing` (CaptureQueriesContext),
  `test_closed_with_reveal_lists_everyone_who_took_part`, `test_closed_page_hides_shared_content_and_refuses_writes`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Close a Secret Santa exchange with an optional reveal`.

---

### Task 5: Browser test, translations, documentation, verification

- [ ] **Step 1: Browser test** (third test in `test_secret_santa_e2e.py`): an exchange drawn in
  the past date with five participants built through the service; the organizer removes one
  with "Remove and repair" (one email sent, the page shows no pairing), adds a latecomer with
  "Add and repair" (three emails), closes with reveal; an anonymous personal page lists who gave
  to whom; "Start a new exchange from this one" creates a copy with the switch on, and its draw
  never repeats a previous pair (checked in the database).
- [ ] **Step 2: Run** — PASS. **Step 3: Translations** (0 fuzzy, 0 untranslated).
- [ ] **Step 4: Documentation**: architecture bullet (repairs, closing, copy), idea 0034 and the
  ideas README (all three slices implemented; status `Implemented` and moved to
  `docs/ideas/implemented/` following `docs/ideas/README.md`).
- [ ] **Step 5: Full verification** (unit suite, e2e Secret Santa + wishlist + dashboard, lint),
  screenshots of the drawn organizer page with the repair forms and of a revealed closed page.
- [ ] **Step 6: Commit** `Feat: Translate and document the Secret Santa repairs and closing`.

## Calls made by the planner (not decided by the user)

- A self-attached account link is not copied to the next exchange; a link from the source
  person, or the organizer's own, is.
- Exclusion sets left with fewer than two members after a copy are dropped.
- After the draw, exclusion sets stay frozen except for the latecomer joining existing sets.
- "Close the exchange" uses the server's local date.
- The insertion picks uniformly among valid (A, C) choices.
