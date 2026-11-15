# Secret Santa, Slice 2 (Telling Your Santa) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Participants tell their Santa what they would like (exchange-only wishes, a note, and,
for Gift Manager users, part of their real wishlist), can decline before the draw, can attach
their participation to their account, and Santas with an account get a dashboard card and a
"Plan a gift" shortcut.

**Architecture:** Builds on slice 1 (`gift_manager/secret_santa/`). Participant-side writes go
in a new `participation.py`; `access.py` is the single place that decides what a Santa sees of
their recipient; `planning.py` computes the "Plan a gift" prefill; `dashboard.py` lists the
cards. Personal-page actions are POST views reached by the participant token, standalone like
the page itself. Attaching an account goes through the session and a login-protected
confirmation page, never through a URL that carries the token.

**Tech Stack:** Django 5.x, PostgreSQL, Bootstrap, HTMX (optional), pytest, Playwright. No new
dependency.

**Spec:** `docs/superpowers/specs/2026-11-14-secret-santa-design.md` (slice 2 of "Slices").
Slice 1 plan: `docs/superpowers/plans/2026-11-14-secret-santa-slice-1-the-draw.md` (its Global
Constraints still apply).

## Global Constraints

- Everything in the slice 1 plan's Global Constraints still holds (404 not 403, no-store /
  no-referrer / noindex on token pages, no `gives_to` on organizer pages outside the reveals,
  emails after commit, translations with 0 fuzzy and 0 empty, test and lint commands).
- A personal link alone never shows or changes anything of an account: real wishes, the linked
  state and the account's language appear only when the visitor is logged in as the linked
  account. Without that login, a linked and an unlinked participant's pages are identical.
- A participant page reads only its own `gives_to`; who drew the participant is never read.
- Recipient wishes shown to a Santa come only from `access.py`: exchange wishes and the note,
  plus the shared real wishes when the exchange is drawn and `wishlist_confirmed`, read as
  `wishlist.guest_wishes(linked account)` restricted to the selection (claim and fulfillment
  columns never loaded).
- The login URL and the confirmation URL never carry the token. Attaching needs an explicit
  confirmation once logged in, is refused when the account is already linked to another
  participant of the exchange, and can be undone.
- The organizer is never told who is linked.
- The dashboard shows an exchange to a participant who did not decline, once it is drawn, or
  earlier if they were invited or attached their account themselves; to the organizer while the
  exchange is not closed.
- Limits on the public page (designer's calls): 30 exchange wishes per participant, title 200
  characters, link 2000 characters (`validate_http_url`), price >= 0 with 2 decimals, note 2000
  characters. Over a limit the action is refused with a message and nothing is saved.
- A closed exchange refuses every participant write (`ExchangeError("This exchange is closed.")`).

## Review Focus

1. **The recipient's real wishes change after sharing.** A shared wish archived, received or
   deleted, the recipient unlinking, or their account deleted: the Santa's page stops showing it
   at the next load, and shows nothing of the unshared wishes. (Task 2)
2. **An anonymous visitor of a linked participant's link.** The page is byte-identical to the
   unlinked case (no real wishes, no linked state, organizer's language); a visitor logged in as
   another account sees the same. (Task 5)
3. **Attaching with a stale or contested link.** The token regenerated after the session was
   started, the account already linked to another participant, the participant already linked to
   another account, or the session lost at login: refused with a message, nothing linked. (Task 5)
4. **Declines around the draw.** A declined participant in an exclusion set, fewer than 3
   participants left after declines, a decline after the draw (not offered, POST refused): the
   draw ignores declined people, says when too few remain, and never assigns them. (Task 3)
5. **Abuse through the public page.** A 31st wish, a 2001-character note, a `javascript:` link,
   a negative price, a POST without CSRF token: refused, nothing saved. (Task 4)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `gift_manager/secret_santa/models.py` | New participant fields, `ExchangeWish`, shared wishes M2M. |
| `gift_manager/secret_santa/participation.py` | Participant writes: wishes, note, decline, attach, detach, shared wishes. |
| `gift_manager/secret_santa/access.py` | What a Santa sees of their recipient; what the page may show a viewer. |
| `gift_manager/secret_santa/planning.py` | "Plan a gift" prefill for the guided plan. |
| `gift_manager/secret_santa/dashboard.py` | Dashboard cards of a user. |
| `gift_manager/secret_santa/forms.py` | `ExchangeWishForm`, `NoteForm`, `SharedWishesForm` added. |
| `gift_manager/secret_santa/service.py`, `emails.py` | Declines in the draw, invitations, put back. |
| `gift_manager/views/secret_santa.py` | Personal-page actions, attach confirmation, plan redirect, invitations. |
| `gift_manager/views/relation_guided.py` | Query-string prefill of the recipient. |
| `gift_manager/views/common.py`, `templates/gift_manager/home.html` | Dashboard card. |
| templates `secret_santa/participant_page.html`, `attach_confirm.html`, `includes/secret_santa_dashboard.html`, `email/secret_santa_invitation.{txt,html}` | UI. |
| tests `gift_manager/tests/secret_santa/test_participation.py`, `test_access.py`, `test_planning.py`, `test_dashboard.py`, plus additions to the slice 1 test files; `gift_manager/tests/e2e/test_secret_santa_e2e.py` (second test) | Tests. |

---

### Task 1: Data model

**Files:** Modify `gift_manager/secret_santa/models.py`, `gift_manager/models.py` (import the new
model like the others), `gift_manager/tests/factories.py`; create migration
`0050_secret_santa_slice_2.py`; test `gift_manager/tests/secret_santa/test_models.py`.

**Interfaces — Produces:**
- `ExchangeParticipant` new fields: `declined` (bool, False), `invited_at` (datetime, null),
  `account_attached_by_participant` (bool, False), `note_for_santa` (TextField, blank,
  max_length 2000), `wishlist_confirmed` (bool, False), `shared_wishes` (M2M
  `"gift_manager.Wish"`, blank, `related_name="+"`).
- `ExchangeWish`: `wish_id` (UUID unique), `participant` (FK CASCADE,
  `related_name="exchange_wishes"`), `title` (max 200), `url` (URLField max 2000, blank,
  `validate_http_url`), `price` (Decimal 10/2, null, >= 0), `created_at`. Ordering
  `created_at, pk`.
- Constants `MAX_EXCHANGE_WISHES = 30`, `MAX_NOTE_LENGTH = 2000`.
- `ExchangeWishFactory`.

- [ ] **Step 1: Tests** — `test_exchange_wishes_are_deleted_with_the_participant`,
  `test_deleting_a_shared_wish_removes_it_from_the_selection`,
  `test_new_participant_defaults` (not declined, not invited, not confirmed, empty note).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/secret_santa/test_models.py` — FAIL.
- [ ] **Step 3: Implement**, `makemigrations gift_manager -n secret_santa_slice_2`, read it
  (only new columns, one table, one M2M table).
- [ ] **Step 4: Run** the tests and `gift_manager/tests/test_migrations.py` — PASS.
- [ ] **Step 5: Commit** `Feat: Add the Secret Santa wishes and participation fields`.

---

### Task 2: What a Santa sees (`access.py`)

**Files:** Create `gift_manager/secret_santa/access.py`; test `test_access.py`.

**Interfaces — Produces:**
- `@dataclass RecipientView`: `name: str`, `note: str`, `exchange_wishes: list[ExchangeWish]`,
  `shared_wishes: list[Wish]`, `shared_currency: str | None` (the recipient account's
  currency, for the shared wishes' prices).
- `recipient_view(santa: ExchangeParticipant) -> RecipientView | None`: None unless the exchange
  is drawn, the Santa did not decline and has a `gives_to`. Loads the recipient with
  `.only("name", "note_for_santa", "linked_account_id", "wishlist_confirmed", "exchange_id")`
  filtered on the Santa's exchange; never touches the recipient's `gives_to` nor anyone's
  `drawn_by`. Shared wishes: `guest_wishes(account).filter(pk__in=recipient.shared_wishes)` only
  when `wishlist_confirmed` and the recipient is linked.
- `viewer_is_linked(participant, user) -> bool`: user authenticated, active, and
  `participant.linked_account_id == user.pk`.

- [ ] **Step 1: Tests** — `test_nothing_before_the_draw`, `test_nothing_for_a_declined_santa`,
  `test_nothing_once_closed`, `test_exchange_wishes_and_note_of_my_recipient_only`,
  `test_shared_wishes_need_confirmation`, `test_only_selected_active_wishes_are_shared`
  (an unselected wish, an archived selected wish and a received selected wish are absent),
  `test_unlinked_recipient_shares_nothing` (selection kept, account unlinked -> empty),
  `test_shared_wishes_load_no_claim_columns` (`get_deferred_fields` covers `is_fulfilled`),
  `test_never_reads_who_drew_the_santa` (CaptureQueriesContext: no query filters
  `gives_to_id = santa.pk`), `test_viewer_is_linked`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Decide what a Secret Santa sees of their recipient`.

---

### Task 3: Declines, invitations and the draw

**Files:** Modify `service.py`, `emails.py`, `views/secret_santa.py`, organizer templates
(`includes/secret_santa_participants.html`, `secret_santa/exchange_detail.html`); create
`email/secret_santa_invitation.{txt,html}`; tests in `test_service.py`, `test_emails.py`,
`test_organizer_views.py`.

**Interfaces — Produces:**
- `service.run_draw` draws only `declined=False` participants (declined ones keep
  `gives_to=None`); "too few" counts them out.
- `service.put_back(participant) -> None`: draft only, `declined=False`.
- `service.taking_part(exchange) -> QuerySet` (`declined=False`, no `gives_to`).
- `emails.send_invitations(exchange, build_absolute_uri) -> SendReport`: draft only; every
  non-declined participant not yet invited; sets `invited_at` on each sent; same quota, stop
  link, connection and failure rules as `send_assignments` (share the sending loop).
- `emails.send_again`: in draft, re-sends the invitation to a participant with `invited_at`;
  otherwise refuses with "Send the invitations first."; drawn as before; declined participants
  are refused ("This participant does not take part.").
- Invitation email: subject `Secret Santa "{exchange}": your page, {participant}`; first line
  `Hello {participant},`; one sentence: `{organizer} invites you to the Secret Santa
  "{exchange}". On your personal page, tell your Santa what you would like, or say that you
  cannot take part. The draw comes later.`; personal link; stop link. No guidelines.
- Organizer URL `secret_santa_invite` (`<uuid>/invite/`, POST) and `secret_santa_put_back`
  (`<uuid>/participants/<uuid>/put-back/`, POST).
- Organizer page: a declined participant is greyed (`.secret-santa-declined`) with a
  "Declined" badge and, in draft, "Put back"; in draft an invited participant has an "Invited"
  badge; the draw card in draft has "Send the personal links now" (shown while someone with an
  email is not invited yet); `can_draw` counts non-declined participants; the pairings reveal
  lists non-declined participants only.

- [ ] **Step 1: Tests** — service: `test_declined_participants_are_left_out_of_the_draw`,
  `test_too_few_after_declines`, `test_declined_member_of_an_exclusion_set_is_ignored`,
  `test_put_back_only_before_the_draw`; emails: `test_invitations_go_to_non_declined_not_yet_invited`
  (second call sends nothing), `test_invitation_content` (subject, first line, no guidelines,
  stop header), `test_send_again_in_draft_resends_the_invitation_only_when_invited`,
  `test_redraw_never_emails_declined`; views: `test_invite_and_put_back_urls_are_scoped`
  (404 for another user), `test_declined_participant_is_shown_and_can_be_put_back`,
  `test_draw_button_counts_non_declined`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Invite Secret Santa participants and leave out those who decline`.

---

### Task 4: Personal page: wishes, note, decline, what my Santa sees

**Files:** Create `participation.py`; modify `forms.py`, `views/secret_santa.py`, `urls.py`,
`views/__init__.py`, `secret_santa/participant_page.html`, `secret-santa.css`; test
`test_participation.py`, additions to `test_participant_views.py`.

**Interfaces — Consumes:** Task 2 `recipient_view`, `viewer_is_linked`.
**Produces:**
- `participation.add_exchange_wish(participant, *, title, url="", price=None) -> ExchangeWish`
  (refuses the 31st: "You can add at most 30 wishes."),
  `delete_exchange_wish(participant, wish_id) -> None` (only the participant's own wish; 404
  otherwise), `save_note(participant, note) -> None`, `decline(participant) -> None` and
  `rejoin(participant) -> None` (draft only: "The draw is done: tell the organizer if you
  cannot take part."), all refusing a closed exchange; all lock the exchange row like
  `service`.
- Forms: `ExchangeWishForm` (title required max 200, url `URLField` max 2000 +
  `validate_http_url`, price `DecimalField` min 0 max_digits 10 decimal_places 2),
  `NoteForm` (note max 2000).
- URLs (no login, POST, CSRF protected, answer 303 to the personal page; invalid input
  re-renders the page with the errors, status 400; same three privacy headers):
  `secret_santa_wish_add` `secret-santa/p/<str:token>/wishes/add/`,
  `secret_santa_wish_delete` `secret-santa/p/<str:token>/wishes/<uuid:wish_id>/delete/`,
  `secret_santa_note` `secret-santa/p/<str:token>/note/`,
  `secret_santa_decline` `secret-santa/p/<str:token>/decline/`,
  `secret_santa_rejoin` `secret-santa/p/<str:token>/rejoin/`.
- Page content: own exchange wishes (with delete) and add form; the note form; in draft
  "I cannot take part" (inside `<details>` with a confirm button) or, once declined,
  "You said you cannot take part" with "I can take part after all"; after the draw a declined
  participant sees "You do not take part in this exchange."; drawn and not declined: the
  assignment plus "What {name} would like" from `recipient_view` (exchange wishes with link and
  price in the exchange currency, the note with `linebreaksbr`, then shared wishes with their
  price in `shared_currency`), or "{name} has not shared anything yet."; the participant list
  shows non-declined participants only; closed: unchanged ("This exchange is over." only).

- [ ] **Step 1: Tests** — participation: `test_add_and_delete_own_wish`,
  `test_cannot_delete_a_wish_of_someone_else`, `test_31st_wish_is_refused`,
  `test_note_is_limited_to_2000`, `test_decline_and_rejoin_only_before_the_draw`,
  `test_closed_exchange_refuses_writes`; views: `test_wish_add_redirects_and_shows_the_wish`,
  `test_javascript_link_and_negative_price_are_refused` (400, nothing saved),
  `test_post_without_csrf_is_refused` (`Client(enforce_csrf_checks=True)` -> 403),
  `test_my_santa_sees_my_wishes_and_note_after_the_draw` (Santa found through `drawn_by` in the
  test only), `test_someone_else_does_not_see_my_wishes`, `test_declined_page_states`,
  `test_wish_and_note_survive_a_redraw`, `test_action_pages_have_privacy_headers`,
  `test_page_still_never_reads_who_drew_me` (slice 1 test still passes with the new sections).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Let Secret Santa participants tell their Santa what they would like`.

---

### Task 5: Attaching an account and sharing real wishes

**Files:** Modify `participation.py`, `forms.py`, `views/secret_santa.py`, `urls.py`,
`participant_page.html`; create `secret_santa/attach_confirm.html` (extends `base.html`); tests
in `test_participation.py`, `test_participant_views.py`.

**Interfaces — Produces:**
- Session key `"secret_santa_attach"`: `{"participant": <pk>, "token_hash": sha256(token)}` —
  the token itself is never stored nor put in a URL.
- `participation.attach_account(participant, user) -> None`: refuses a closed exchange, a
  participant linked to another account ("This participation is already linked to an
  account."), and an account linked to another participant of the exchange ("Your account is
  already linked to another participant of this exchange."); sets `linked_account` and
  `account_attached_by_participant=True`. Same account again: no change.
- `participation.detach_account(participant, user) -> None`: only the linked account; clears
  `linked_account`, `account_attached_by_participant`, `wishlist_confirmed`, `shared_wishes`.
- `participation.shareable_wishes(participant) -> list[tuple[Wish, bool]]`: the linked
  account's `wishlist.active_wishes`, each with its checkbox state: the current selection once
  `wishlist_confirmed`; before that, pre-ticked when the exchange has a budget, the account's
  `profile.currency == exchange.currency`, and `price_hint <= budget`.
- `participation.save_shared_wishes(participant, user, wish_ids) -> None`: only the linked
  account; keeps only ids among its active wishes; sets `wishlist_confirmed=True`.
- URLs: `secret_santa_attach_start` `secret-santa/p/<str:token>/attach/` (POST, no login:
  stores the session key, then redirects to the confirmation, through
  `redirect_to_login(next=confirmation path)` when anonymous);
  `secret_santa_attach_confirm` `secret-santa/attach/` (login; GET shows "Link your account to
  participant {name} of "{exchange}"?", POST attaches, clears the session key, redirects to the
  personal page; missing/stale session -> page saying the link expired, status 400);
  `secret_santa_detach` `secret-santa/p/<str:token>/detach/` (POST, linked viewer only, else
  404); `secret_santa_share` `secret-santa/p/<str:token>/share/` (POST, linked viewer only).
- Page for the linked viewer only (`viewer_is_linked`): rendered in the account's
  `profile.language`; "Linked to your account" with "Unlink"; the shareable wishes with
  checkboxes and "Share these wishes with my Santa" (before confirmation a sentence says nothing
  is shared yet). Everyone else sees "I have a Gift Manager account" (also for an already
  linked participant, so linked and unlinked pages stay identical).

- [ ] **Step 1: Tests** — participation: `test_attach_and_detach`,
  `test_attach_refused_when_the_account_is_linked_elsewhere_in_the_exchange`,
  `test_attach_refused_when_linked_to_another_account`, `test_detach_clears_the_selection`,
  `test_prefill_rules` (budget/currency/price combinations), `test_save_shared_wishes_ignores_foreign_and_inactive_ids`;
  views: `test_attach_flow_anonymous_goes_through_login_without_the_token`
  (Location of each redirect never contains the token), `test_attach_needs_confirmation`,
  `test_attach_with_a_regenerated_token_is_refused`, `test_linked_page_is_identical_for_anonymous_and_other_accounts`
  (unlinked vs linked participant, anonymous and logged in as a third user: same bytes after
  replacing the name and the token), `test_linked_viewer_sees_selection_and_own_language`,
  `test_share_and_detach_need_the_linked_account` (404 otherwise),
  `test_santa_sees_shared_wishes_after_confirmation_only`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Attach a Secret Santa participation to an account and share real wishes`.

---

### Task 6: Dashboard card and "Plan a gift"

**Files:** Create `dashboard.py`, `planning.py`, `includes/secret_santa_dashboard.html`;
modify `views/common.py` (`home`), `home.html`, `views/relation_guided.py`,
`views/secret_santa.py`, `urls.py`; tests `test_dashboard.py`, `test_planning.py`, an addition
to the guided plan tests (`rg -l relation_guided gift_manager/tests`).

**Interfaces — Produces:**
- `dashboard.cards(user) -> list[DashboardCard]`; `@dataclass DashboardCard`: `exchange`,
  `is_organizer: bool`, `participant: ExchangeParticipant | None`, `recipient_name: str | None`.
  One card per exchange (organizer and participant merged), not closed, organizer active,
  ordered by `exchange_date`. Participation rule: linked to the user, not declined, and drawn,
  or `invited_at` set, or `account_attached_by_participant`. `recipient_name` only when drawn.
- `planning.plan_prefill(santa: ExchangeParticipant, user) -> dict[str, str]`: the recipient's
  `source_person` when `PermissionService.get_effective_permission(person, user) >=
  PermissionLevel.EDITOR` -> `{"recipient": "person:<person_id>"}`; else the first person the
  user owns (`PersonPermission` OWNER) with `account_id == recipient.linked_account_id` ->
  same shape; else `{"new_person-first_name": first word, "new_person-family_name": the rest}`.
- `RelationGuidedCreateView._query_prefill` also accepts `recipient` (kept only when
  `resolve_recipient_choice` accepts it for this user and it is a `person:` value; sets
  `recipient_mode=existing`) and `new_person-first_name` / `new_person-family_name` (sets
  `recipient_mode=new` when no valid recipient).
- URL `secret_santa_plan_gift` `secret-santa/participations/<uuid:participant_id>/plan/`
  (login, GET): participant linked to `request.user`, not declined, exchange drawn, organizer
  active, else 404; redirects to `relation_guided_create?<urlencoded prefill>`.
- Dashboard section `.dashboard-secret-santa` above the birthdays: per card the exchange name,
  date, "You give a gift to {name}" when drawn, "My page" (personal link), "Plan a gift" when
  drawn, "Manage" for the organizer. Personal page of the linked viewer gets "Plan a gift" too.

- [ ] **Step 1: Tests** — dashboard: `test_imported_into_a_draft_sees_nothing`,
  `test_invited_or_self_attached_sees_the_draft`, `test_drawn_shows_my_recipient_only`,
  `test_declined_or_closed_sees_nothing`, `test_organizer_and_participant_cards_are_merged`,
  `test_home_page_shows_the_card` (view test); planning: `test_editable_source_person_is_used`,
  `test_viewer_only_source_person_is_not_used`, `test_owned_person_linked_to_the_account`,
  `test_new_person_names`, `test_plan_gift_view_scoping` (404 for another user, declined,
  draft); guided plan: `test_query_prefill_selects_an_accessible_recipient`,
  `test_query_prefill_ignores_an_inaccessible_recipient`, `test_query_prefill_new_person_names`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `Feat: Show Secret Santa exchanges on the dashboard and plan a gift`.

---

### Task 7: Browser test, translations, documentation, verification

**Files:** `gift_manager/tests/e2e/test_secret_santa_e2e.py` (second test),
`locale/fr/LC_MESSAGES/django.po/.mo`, `docs/ai/architecture.md` (extend the Secret Santa
bullet: `access.py`, the attach flow), `docs/ideas/0034-...md` and `docs/ideas/README.md`
(slice 2 implemented).

- [ ] **Step 1: Browser test** (seed users `alice` organizer, `bob` participant with an account):
  alice creates an exchange with Bob (typed, bob's email), Chris, Dana, Eve; "Send the personal
  links now"; an anonymous phone context opens Chris's link (from "Show link"), adds a wish and a
  note; Eve's link declines; Bob logs in through his page's "I have a Gift Manager account",
  confirms, shares one real wish; alice draws (Eve greyed, left out); Chris's Santa page shows
  what their recipient shared (found via the database in the test); Bob's dashboard shows the
  card and "Plan a gift" opens the guided plan with the recipient prefilled; no horizontal
  scroll at 390 px on the personal page.
- [ ] **Step 2: Run** `tox run -e e2e -- gift_manager/tests/e2e/test_secret_santa_e2e.py` — PASS.
- [ ] **Step 3: Translations** (makemessages, translate, compile, `msgfmt --check --statistics`:
  0 fuzzy, 0 untranslated).
- [ ] **Step 4: Documentation** edits above.
- [ ] **Step 5: Full verification** (unit suite, then e2e Secret Santa + wishlist, lint),
  screenshots of the personal page (anonymous, linked) and the dashboard card, looked at.
- [ ] **Step 6: Commit** `Feat: Translate and document Secret Santa wishes and accounts`.

---

## Not in this slice

Remove and repair, add and repair, closing with reveal, starting from a previous exchange and
its "no repeat" switch (slice 3). Closing is still not reachable from the UI.

## Calls made by the planner (not decided by the user)

- The limits above (30 wishes, 200/2000 characters, note 2000).
- Exchange wishes can be added and deleted, not edited.
- A declined participant can undo their decline themselves before the draw, besides the
  organizer's "Put back".
- The participant list on personal pages shows only participants who take part.
- "Send again" before the draw re-sends the invitation (only to invited participants).
- The attach session stores a hash of the token, not the token.
- A new person for "Plan a gift" splits the name at the first space.
