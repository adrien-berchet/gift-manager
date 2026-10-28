# Person And Account Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambiguous `Person.user_link` with `Person.account` ("this record represents
that account"), stop granting access through it, base surprise and recipient rules on it, and let
givers link records to friends (and to themselves) from the person page, the friends list, an
email-match banner and invitations.

**Architecture:** One migration renames and clears the field, then backfills ownership. Task 2
removes every access grant tied to the link and switches the identity rules, which fixes the
current surprise bugs. All linking rules live in a new `gift_manager/account_links.py` service;
views, the invitation flow and unfriending only call it. The UI follows the existing pattern:
plain links and forms, partial templates for HTMX requests.

**Tech Stack:** Django 5.2, PostgreSQL, django-allauth, HTMX, Bootstrap, Grid.js, pytest, tox,
factory_boy, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-28-person-account-link-design.md`

## Global Constraints

- Code, docstrings and comments in English. Every new user-facing string is translatable and
  gets a French translation in `locale/fr/LC_MESSAGES/django.po` in the task that adds it
  (`python manage.py makemessages -l fr`, fill `msgstr`, `python manage.py compilemessages`).
- No new dependencies. No new permission levels. Access is decided only by permission rows
  through `PermissionService`; the link never grants access or ownership.
- Linking happens only through `gift_manager/account_links.py` (the admin is the one documented
  exception).
- Emails never appear in URLs: views fill them in from the friend's account or the person record.
- Every action works without JavaScript (plain links and POST forms); views return a partial for
  HTMX requests (`HX-Request: true`) and a full page or redirect otherwise.
- No explanatory or keyboard-shortcut text in the UI beyond labels, banners and confirmations
  the spec names.
- Run tests on PostgreSQL: `tox run -e py311 -- <path>`; lint with `tox run -e lint`; browser
  tests with `tox run -e e2e -- <path>`.
- Commit subjects follow `commitlint.config.js` (`Feat: ...`, `Fix: ...`, `Test: ...`,
  `Docs: ...`, sentence case, no final period).

## Review Focus

- The linked account opens the record's URLs directly (detail, edit, delete, link form, dismiss,
  "Link to a person" with a forged person id): 404 like any inaccessible object, never 200
  (Tasks 2, 4, 5, 6).
- A record without an email, with an invalid stored email, or a friend with no `EmailAddress`
  rows and an empty `user.email`: no banner and no error (Task 5).
- A stale form: the link form is submitted after the friendship was removed (a refusal message,
  no 500, nothing changed), or after another editor linked the record to someone else (the
  surprise confirmation is computed from the current link, not the one shown when the form was
  opened) (Task 4).
- Unfriending when the record has two owners and only one stays friends with the linked account:
  the link is kept (Task 3).
- The linked account is deleted: the record keeps existing, `account` becomes NULL, badges and
  friends rows disappear without errors (Task 1, asserted again in Task 8).

## File Structure

- Modify `gift_manager/models.py`: `Person.account` (renamed), `Person.link_suggestion_dismissed_account`,
  `Invitation.person`; identity rules on `account`; remove `PersonQuerySet.accessible_by`;
  `excluding_person` on `recipient_groups_for` / `hidden_surprises_for`.
- Create `gift_manager/migrations/0041_person_account_link.py`.
- Modify `gift_manager/services.py`, `gift_manager/mixins/permissions.py`,
  `gift_manager/group_hierarchy_service.py`, `gift_manager/views/search.py`,
  `gift_manager/views/base.py`, `gift_manager/guided_plan.py`, `gift_manager/plan_coordination.py`.
- Create `gift_manager/account_links.py`: every linking rule and the read helpers the UI uses.
- Create `gift_manager/views/account_links.py`: person link form, dismiss, friend "Link to a person".
- Modify `gift_manager/views/person.py`, `views/profile.py`, `views/__init__.py`, `urls.py`,
  `invitations.py`, `forms.py`, `templatetags/custom_filters.py`, `seed_data.py`,
  `management/commands/seed_data.py`.
- Templates: create `includes/person_link_form_partial.html`, `person_link_account.html`,
  `includes/person_link_suggestion_banner.html`, `friend_link_person.html`; modify
  `includes/person_detail_partial.html`, `profile_detail.html`, `send_invitation.html`,
  `includes/forms/person_fields.html`, `includes/person_management_grid_script.html`,
  `person_group_detail.html`.
- Tests: `gift_manager/tests/factories.py` (`owner`), the existing tests that use `user_link`, and
  the new files listed per task.
- Docs: `docs/ai/architecture.md`.

---

### Task 1: Rename the field, migration and test factory

Pure rename plus data migration: behaviour is unchanged except that existing values are cleared.

**Files:**
- Modify: `gift_manager/models.py:584-590` (field), `gift_manager/models.py` `Invitation` (`person`)
- Create: `gift_manager/migrations/0041_person_account_link.py`
- Modify: every non-migration file using `user_link` (37 files, about 170 occurrences; list them
  with `rg -l user_link gift_manager --glob '!migrations'`)
- Modify: `gift_manager/tests/factories.py` (`PersonFactory.owner`)
- Test: `gift_manager/tests/test_migrations.py` (new class `TestPersonAccountLinkMigration`)

**Interfaces:**
- Produces: `Person.account: User | None` (FK `SET_NULL`, `related_name="linked_persons"`);
  `Person.link_suggestion_dismissed_account: User | None` (FK `SET_NULL`, `related_name="+"`);
  `Invitation.person: Person | None` (FK `SET_NULL`, `related_name="invitations"`);
  `PersonFactory(owner=user)` creates an OWNER `PersonPermission` for `user` (repeatable with a
  list: `owner=[u1, u2]`).

- [ ] **Step 1: Write the failing migration tests** with the `MigrationExecutor` pattern of
  `test_migrations.py:69-130`, migrating from `0040_giftsuggestion_dismiss_comment_and_more`:
  - `test_backfills_missing_owner_permission`: a person with `user_link=u` and no permission row
    ends with exactly one OWNER `PersonPermission` for `u`.
  - `test_does_not_duplicate_existing_owner_permission`: a person with `user_link=u` and an OWNER
    row for `u` still has exactly one row.
  - `test_clears_every_account`: after migrating, every `Person.account_id` is NULL.
  - `test_deleting_linked_account_keeps_the_person` (post-migration model): `account=u`,
    `u.delete()`, the person still exists with `account is None`.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_migrations.py`. Expected:
  FAIL (migration missing).
- [ ] **Step 3: Implement the model change**: rename the field to `account`
  (`related_name="linked_persons"`), add `link_suggestion_dismissed_account` and
  `Invitation.person` as specified in the spec's Data model section.
- [ ] **Step 4: Write `0041_person_account_link.py` by hand** in this order: `RunPython`
  backfill (historical models; reverse no-op), `RenameField("person", "user_link", "account")`,
  `AlterField` for the `related_name`, `RunPython` clearing `account` (reverse no-op), the two
  `AddField`s. Then `python manage.py makemigrations --check --dry-run` reports no changes.
- [ ] **Step 5: Rename every caller mechanically**: `user_link` becomes `account` and
  `user_link_id` becomes `account_id` in code and tests, with no other change (Task 2 changes
  behaviour). Add `PersonFactory.owner` (post-generation, OWNER via
  `PersonPermission.objects.update_or_create`). `rg user_link gift_manager --glob '!migrations'`
  returns nothing.
- [ ] **Step 6: Run** the migration tests, then the whole suite `tox run -e py311`. Expected:
  PASS; the suite is as green as on `main` (the rename alone changes no behaviour).
- [ ] **Step 7: Commit** `Refactor: Rename Person.user_link to Person.account and clear it`.

---

### Task 2: The link grants no access; identity rules use `account`

**Files:**
- Modify: `gift_manager/services.py:96-110,216-236,246-270`, `gift_manager/models.py:120-125,267-302`,
  `gift_manager/mixins/permissions.py:169-187`, `gift_manager/group_hierarchy_service.py:63-73`,
  `gift_manager/views/search.py:60-66`, `gift_manager/views/base.py:409-437`,
  `gift_manager/guided_plan.py:385-386`, `gift_manager/views/person.py:62-66`
- Modify: tests from Task 1 whose `account=` meant ownership (switch to `owner=`)
- Modify: `docs/ai/architecture.md` ("Persons and accounts" paragraph)
- Test: create `gift_manager/tests/test_person_account_semantics.py`

**Interfaces:**
- Consumes: Task 1 field and `PersonFactory(owner=...)`.
- Produces: `recipient_groups_for(user, excluding_person: Person | None = None) -> RawSQL`;
  `RelationQuerySet.hidden_surprises_for(user, excluding_person: Person | None = None)`
  (memberships and person recipients of `excluding_person` are ignored); `Person.objects.accessible_by(user)`
  is the base `shared_with=user` query.

- [ ] **Step 1: Write failing tests** in `test_person_account_semantics.py`:
  - `test_creating_a_person_does_not_link_the_creator`: POST to `person_create` as a logged-in
    user; the new person has `account is None` and the user holds OWNER.
  - `test_linked_account_has_no_access`: Bob owns P, `P.account = alice`:
    `PermissionService.get_effective_permission(P, alice) == PermissionLevel.NONE`,
    `P not in Person.objects.accessible_by(alice)`, and Alice gets 404 on `person_detail`,
    `person_edit`, `person_delete` for P.
  - `test_linked_account_is_not_an_access_holder_or_owner`: `has_other_access_holder(P, bob)` is
    False and `_owner_user_ids(P) == {bob.id}`.
  - `test_co_giver_sees_surprise_for_a_linked_record` (probe scenario 1): Bob owns "Alice" linked
    to alice and shares it with Carol; Carol's plan with
    `is_surprise=default_surprise_for(alice_record, carol)` (True), owned by Carol, shared with
    Bob (EDITOR) and Alice (VIEWER): visible to Bob, hidden from Alice.
  - `test_co_giver_sees_group_surprise` (probe scenario 2): same with a group whose member is
    linked to alice: visible to Bob, hidden from Alice.
  - `test_self_link_hides_group_surprise_from_self`: Bob owns record B with `account=bob` in
    group G shared with Carol; Carol's surprise plan for G shared with Bob is hidden from Bob.
  - `test_surprise_checkbox_shown_for_records_the_user_created`: GET `surprise_default_hint` for
    an unlinked record the user created returns the checkbox (`show` True, unchecked); for the
    user's self-record it is hidden; for a record linked to a friend it is checked.
  - `test_hidden_surprises_excluding_person`: Alice is linked through records P1 and P2 (both
    recipients of surprise plans S1 and S2); `hidden_surprises_for(alice, excluding_person=P1)`
    still contains the plan for P2 and not the plan for P1.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_person_account_semantics.py`.
  Expected: FAIL (access still granted, creator still linked).
- [ ] **Step 3: Implement** the removals listed in the spec's "Permission and surprise rules"
  section (drop the OWNER boost and linked-user branches in `services.py`, delete
  `PersonQuerySet.accessible_by`, drop the list-row override, the group-hierarchy branch, the
  search fallback and both create-path writes, stop selecting `account_id` in the person grid
  rows, which only fed the removed override; Task 8 selects it again for the badge) and add
  `excluding_person` to the two model helpers.
- [ ] **Step 4: Update existing tests** that still pass `account=` where they meant ownership:
  switch them to `owner=`. A test whose expected result only held because of the double meaning
  is rewritten to the new rule and named in the commit message body.
- [ ] **Step 5: Add the "Persons and accounts" paragraph** to `docs/ai/architecture.md`
  (ownership from permission rows; `account` = who the record represents; being a recipient only
  removes visibility).
- [ ] **Step 6: Run** the new file, then `tox run -e py311` and `tox run -e lint`. Expected: PASS.
- [ ] **Step 7: Commit** `Fix: Stop granting access through the person account link`.

---

### Task 3: Linking service core and unfriending

**Files:**
- Create: `gift_manager/account_links.py`
- Modify: `gift_manager/views/profile.py:212-235` (`RemoveFriendView.post`)
- Test: create `gift_manager/tests/test_account_links_service.py`

**Interfaces:**
- Consumes: Task 2 `hidden_surprises_for(user, excluding_person=...)`;
  `PermissionService.get_effective_permission`, `PermissionService.users_are_friends`,
  `PermissionService.lock_object`.
- Produces:
  - `class LinkRefused(ValidationError)`.
  - `owned_persons(user: User) -> QuerySet[Person]` (records where `user` has an OWNER row).
  - `duplicate_conflicts(person: Person, account: User) -> list[Person]` (other records linked to
    `account` owned by any owner of `person`).
  - `link(person: Person, account: User, actor: User) -> Person`.
  - `unlink(person: Person, actor: User) -> None`.
  - `revealed_surprise_count(person: Person) -> int`.
  - `remove_links_after_unfriending(user: User, former_friend: User) -> int` (records unlinked).

- [ ] **Step 1: Write failing tests** in `test_account_links_service.py`:
  - `test_owner_links_record_to_friend`, `test_editor_links_when_an_owner_is_a_friend`,
    `test_editor_refused_when_no_owner_is_a_friend`, `test_viewer_refused` (`PermissionDenied`),
    `test_refused_for_a_non_friend` (`LinkRefused`).
  - `test_self_link_needs_owner`: an editor linking to themselves is refused; an owner succeeds.
  - `test_duplicate_guard_friend` and `test_duplicate_guard_self`: an owner of `person` already
    owns another record linked to the account: `LinkRefused`, and `duplicate_conflicts` returns
    that record.
  - `test_sharing_as_owner_can_create_duplicates`: Bob's P1 linked to Alice, Carol's P2 linked to
    Alice, Bob shares P1 with Carol as OWNER through `create_or_update_permission`: succeeds and
    `duplicate_conflicts(P1, alice) == [P2]`.
  - `test_relinking_same_account_is_a_noop`; `test_linking_replaces_another_link`.
  - `test_link_releases_claims_on_now_hidden_plans`: Alice claimed a surprise plan for P (shared
    with her) before P was linked; after `link(P, alice, bob)` the claim is released; her claim on
    a non-surprise plan is kept.
  - `test_link_clears_dismissed_suggestion`.
  - `test_revealed_surprise_count`: two surprise plans for P shared with Alice: 2; a third one
    hidden through another record P2 also linked to Alice is not counted; a plan not shared with
    Alice is not counted.
  - `test_unlink_needs_editor`.
  - `test_unfriending_removes_links_without_friend_owner`,
    `test_unfriending_keeps_link_when_another_owner_is_friend`,
    `test_unfriending_never_removes_self_links`, and the view-level
    `test_remove_friend_view_unlinks` (POST `remove_friend`).
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_account_links_service.py`.
  Expected: FAIL (module missing).
- [ ] **Step 3: Implement `gift_manager/account_links.py`** with the rules of the spec's
  "Service" section. `link` runs in `transaction.atomic()` with
  `PermissionService.lock_object(person)`; after saving it runs
  `Relation.objects.hidden_surprises_for(account).filter(claimed_by=account).update(claimed_by=None, claimed_at=None)`
  and clears `link_suggestion_dismissed_account`. `revealed_surprise_count` counts plans shared
  with the account that are in `hidden_surprises_for(account)` and not in
  `hidden_surprises_for(account, excluding_person=person)`. Refusal messages (translated):
  "You can only link a person to one of your friends.", "Only an owner of this person can mark
  it as you.", "One of this person's owners already has a person linked to this account.",
  "Nobody who owns this person is friends with this account."
- [ ] **Step 4: Call `remove_links_after_unfriending(request.user, friend)`** in
  `RemoveFriendView.post` right after `_cleanup_former_friend_permissions`, inside its
  transaction.
- [ ] **Step 5: Run** the new file and `tox run -e py311 -- gift_manager/tests/views/test_profile.py`.
  Expected: PASS. Add the French translations of the four messages.
- [ ] **Step 6: Commit** `Feat: Add the person account linking service`.

---

### Task 4: Person page link form and link badge

**Files:**
- Modify: `gift_manager/account_links.py` (choices and label helpers)
- Create: `gift_manager/views/account_links.py`, `templates/gift_manager/person_link_account.html`,
  `templates/gift_manager/includes/person_link_form_partial.html`
- Modify: `gift_manager/views/__init__.py`, `gift_manager/urls.py` (after `person_delete`),
  `gift_manager/views/person.py:321-348` (action buttons, context),
  `templates/gift_manager/includes/person_detail_partial.html` (badge next to the name),
  `gift_manager/templatetags/custom_filters.py`
- Test: create `gift_manager/tests/views/test_person_link_account.py`

**Interfaces:**
- Consumes: Task 3 `link`, `unlink`, `duplicate_conflicts`, `revealed_surprise_count`,
  `LinkRefused`.
- Produces:
  - `@dataclass(frozen=True) class LinkChoice: value: str; label: str; account: User | None;
    disabled: bool; conflicts: tuple[Person, ...]` (`value` is `""` for "No one", else the
    account's `pk` as a string; the actor's own account is labelled "Me").
  - `link_choices(person: Person, actor: User) -> list[LinkChoice]` ("No one", then "Me" for
    owners, then friends ordered by username).
  - `link_label(person: Person, viewer: User) -> str`: `""`, "This is you", or
    "Linked to %(username)s".
  - Template filter `person_link_label` (`{{ person|person_link_label:request.user }}`).
  - URL `persons/<uuid:pk>/link/`, name `person_link_account`, view
    `PersonLinkAccountView` (GET form, POST `account=<value>` with optional `confirm=1`).

- [ ] **Step 1: Write failing tests** in `test_person_link_account.py`:
  - `test_non_editor_gets_403_and_stranger_gets_404` (also the linked account itself: 404).
  - `test_choices_and_disabled_states`: a friend with a conflicting owned record is disabled and
    its conflict is listed; "Me" appears for owners only and is disabled when a self-record
    exists.
  - `test_post_links_and_redirects` (plain POST: 302 to `person_detail`, success message) and
    `test_post_htmx_returns_hx_redirect` (`HX-Redirect` header to `person_detail`).
  - `test_unlink_with_revealed_surprises_asks_confirmation`: POST `account=""` without `confirm`
    re-renders with "2 surprise plans shared with ana would become visible to them." and changes
    nothing; with `confirm=1` it unlinks.
  - `test_stale_post_after_unfriending_shows_refusal`: POST for a friend removed meanwhile:
    status 400, refusal message, `account` unchanged.
  - `test_stale_post_after_another_link_asks_confirmation`: the form was opened while unlinked,
    another editor then linked the record to Ben, who has a hidden surprise plan through it; the
    POST for Ana re-renders with the confirmation for Ben and changes nothing.
  - `test_htmx_get_returns_partial`: GET with `HX-Request: true` renders
    `includes/person_link_form_partial.html` without the base layout.
  - `test_detail_page_shows_badge_and_button`: the person page shows "Linked to ana" and the
    "Change link" button for editors; "Link account" when unlinked; no button for viewers; the
    badge reads "This is you" on a self-record.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_person_link_account.py`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `link_choices`, `link_label`, the filter, the view and templates.
  The view resolves the person through `Person.objects.accessible_by(request.user)` (404) and
  requires EDITOR (`PermissionDenied`). The full page extends `base.html` and includes the partial;
  HTMX GET gets the partial alone. The confirmation is a second render of the same form carrying
  `confirm=1`. Add the custom action button (`type: "custom"`, icon `fas fa-link`,
  `btn_class: "btn-outline-secondary"`, label "Link account" or "Change link", editors only) to
  `PersonDetailView`'s `action_buttons`.
- [ ] **Step 4: Run** the new file and `tox run -e py311 -- gift_manager/tests/views/`. Expected:
  PASS. Add the French translations.
- [ ] **Step 5: Commit** `Feat: Link a person to an account from the person page`.

---

### Task 5: Email-match banner and dismissal

**Files:**
- Modify: `gift_manager/account_links.py`, `gift_manager/views/account_links.py`,
  `gift_manager/urls.py`, `gift_manager/views/person.py` (context)
- Create: `templates/gift_manager/includes/person_link_suggestion_banner.html`
- Modify: `templates/gift_manager/includes/person_detail_partial.html` (include the banner first)
- Test: create `gift_manager/tests/views/test_person_link_suggestion.py`

**Interfaces:**
- Consumes: Task 3 `link`; Task 4 `PersonLinkAccountView` (the banner's "Link" / "This is me"
  buttons POST to `person_link_account` with `account=<pk>`); `gift_manager.invitations.user_has_email`.
- Produces: `link_suggestion(person: Person, viewer: User) -> User | None`;
  `dismiss_link_suggestion(person: Person, account: User, actor: User) -> None`; URL
  `persons/<uuid:pk>/link-suggestion/dismiss/`, name `person_dismiss_link_suggestion` (POST
  `account=<pk>`, redirect or `HX-Redirect` to `person_detail`).

- [ ] **Step 1: Write failing tests** in `test_person_link_suggestion.py`:
  - `test_suggests_friend_by_verified_email` and `test_suggests_friend_by_legacy_user_email`
    (friend without `EmailAddress` rows, matching `user.email`).
  - `test_suggests_self_for_own_email` (banner text "This email is yours. Is this person you?").
  - `test_no_banner_for_viewers_linked_records_or_refused_links` (a friend for whom `link` would
    raise the duplicate guard gets no banner).
  - `test_no_banner_without_or_with_invalid_email` (empty email; stored value that decodes to an
    invalid address; friend with empty `user.email` and no rows).
  - `test_dismissal_is_per_account`: dismissing Ana hides her banner; changing the email to Ben's
    shows Ben's banner; the dismiss URL returns 404 for the linked account and 403 for viewers.
  - `test_banner_link_button_links`: POST from the banner links and the badge appears.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_person_link_suggestion.py`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `link_suggestion` (decode `person.email`, normalise with
  `casefold()`, check the viewer then each friend with `user_has_email`; skip the dismissed account
  and any account for which `duplicate_conflicts` is non-empty or the friendship rules of `link`
  would refuse), `dismiss_link_suggestion` (EDITOR or more), the dismiss view, the banner
  template (friend text "This email belongs to your friend %(username)s. Link this person to
  their account?" with "Link" / "Not them"; self text with "This is me" / "Not me").
- [ ] **Step 4: Run** the new file. Expected: PASS. Add the French translations.
- [ ] **Step 5: Commit** `Feat: Suggest linking a person whose email matches an account`.

---

### Task 6: Friends list links, "Create person" and own record line

**Files:**
- Modify: `gift_manager/account_links.py`, `gift_manager/views/account_links.py`,
  `gift_manager/urls.py`, `gift_manager/views/profile.py:41-57` (`ProfileDetailView` context),
  `gift_manager/views/person.py:201-238` (`PersonCreateView`)
- Create: `templates/gift_manager/friend_link_person.html`
- Modify: `templates/gift_manager/profile_detail.html:313-341`,
  `templates/gift_manager/includes/forms/person_fields.html` (hidden `link_to`)
- Test: create `gift_manager/tests/views/test_friend_links.py`

**Interfaces:**
- Consumes: Task 3 `link`, `owned_persons`; Task 4 `person_link_label`.
- Produces:
  - `@dataclass(frozen=True) class FriendLinkRow: profile: Profile; linked: tuple[Person, ...];
    matching_count: int`.
  - `friend_link_rows(viewer: User) -> list[FriendLinkRow]` (one row per friend, ordered like
    today's list).
  - `linkable_persons(viewer: User, friend: User) -> list[Person]` (owned, unlinked records,
    email matches first, then by family and first name).
  - `own_records(viewer: User) -> list[Person]` (owned records with `account=viewer`).
  - URL `profile/friends/<int:friend_id>/link/`, name `friend_link_person` (GET list, POST
    `person=<person_id uuid>`; `friend_id` is the friend's `Profile` pk like `remove_friend`).

- [ ] **Step 1: Write failing tests** in `test_friend_links.py`:
  - `test_friend_row_unlinked_shows_actions_and_hint` ("Link to a person", "Create person",
    "1 person has this email").
  - `test_friend_row_linked_shows_records_and_unlink` (two rows when sharing produced two owned
    linked records).
  - `test_link_to_a_person_page_orders_email_matches_first` and
    `test_link_to_a_person_post_links`; `test_forged_person_id_is_404` (a record the viewer does
    not own).
  - `test_create_person_prefills_from_friend_and_links_on_save`: GET
    `person_create?link_to=<pk>` pre-fills first name, family name (or username) and email from
    the friend's account; POST with the hidden `link_to` creates the record, the viewer owns it
    and it is linked; a `link_to` for a non-friend is ignored (record created, not linked).
  - `test_profile_lists_own_records`: "Your own person record: <name>" for each self-linked owned
    record.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/views/test_friend_links.py`.
  Expected: FAIL.
- [ ] **Step 3: Implement** the helpers, the view and template, the friends list markup (keeps
  the existing remove-friend button and modal), the profile context (`friend_link_rows`,
  `own_records`), and in `PersonCreateView`: `get_initial` fills the friend's values when
  `link_to` resolves to one of the viewer's friends' profiles, the template renders
  `<input type="hidden" name="link_to">`, and `form_valid` calls `link(self.object, friend.user,
  self.request.user)` after `super().form_valid`, turning `LinkRefused` into a warning message.
- [ ] **Step 4: Run** the new file and `tox run -e py311 -- gift_manager/tests/views/test_profile.py gift_manager/tests/test_offcanvas_person_form.py`.
  Expected: PASS. Add the French translations.
- [ ] **Step 5: Commit** `Feat: Link friends to persons from the friends list`.

---

### Task 7: Invite from a person page and link on acceptance

**Files:**
- Modify: `gift_manager/account_links.py`, `gift_manager/invitations.py:141-162`,
  `gift_manager/views/profile.py:60-128` (`SendInvitationView`), `gift_manager/forms.py:1296-1313`
  (`InvitationForm`), `templates/gift_manager/send_invitation.html`,
  `gift_manager/views/person.py` (button)
- Test: create `gift_manager/tests/test_invitation_person_link.py`

**Interfaces:**
- Consumes: Task 3 `link`, `LinkRefused`; Task 5 `link_suggestion` (the button shows only when it
  returns `None` and the email is not the viewer's or a friend's).
- Produces: `link_from_invitation(invitation: Invitation, user: User) -> bool`;
  `InvitationForm.person` (hidden `UUIDField`, optional).

- [ ] **Step 1: Write failing tests** in `test_invitation_person_link.py`:
  - `test_invite_button_conditions`: shown to editors for an unlinked record whose email belongs
    to nobody the viewer knows; hidden without email, when linked, or when the email is a friend's
    or the viewer's.
  - `test_send_invitation_prefills_from_person`: GET `send_invitation?person=<uuid>` pre-fills the
    record's email; POST stores `Invitation.person` when the sender is OWNER and leaves it NULL
    for an editor; a forged uuid is ignored.
  - `test_accepting_links_the_record` for a new user (signup and email confirmation path) and an
    existing user (`accept_invitation_for_user`).
  - `test_accepting_skips_linking_when` (parametrized): record deleted, sender no longer OWNER,
    record already linked, duplicate guard fails. In each case the invitation is accepted, the
    friendship exists, nothing is linked, no error.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_invitation_person_link.py`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `link_from_invitation` (calls `link(..., actor=invitation.sender)`
  and returns False on `LinkRefused`, `PermissionDenied` or a missing record), call it in
  `accept_invitation_for_user` after the two `friends.add` calls inside the same atomic block,
  the form field, the view changes and the "Invite to Gift Manager" custom action button (icon
  `fas fa-envelope`).
- [ ] **Step 4: Run** the new file and `tox run -e py311 -- gift_manager/tests/views/test_profile.py`.
  Expected: PASS. Add the French translations.
- [ ] **Step 5: Commit** `Feat: Link a person when the invitation sent from it is accepted`.

---

### Task 8: Link badges in lists, cards and group pages

**Files:**
- Modify: `gift_manager/views/person.py:50-67,113-139` (`get_person_grid_queryset`,
  `get_person_grid_data`), `gift_manager/views/person.py:161` and `gift_manager/views/recipient.py:59`
  (pass the viewer), `templates/gift_manager/includes/person_management_grid_script.html:14-68`,
  `templates/gift_manager/person_group_detail.html:378-430`, `gift_manager/views/person_group.py:474`
  (`select_related("account")`)
- Test: `gift_manager/tests/views/test_grid_data_serialization.py`,
  `gift_manager/tests/views/test_person_group_detail.py`

**Interfaces:**
- Consumes: Task 4 `link_label`.
- Produces: `get_person_grid_data(items, viewer: User | None = None) -> list` appends the link
  label as row index 10; existing indexes 0-9 are unchanged.

- [ ] **Step 1: Write failing tests**:
  - `test_person_rows_end_with_link_label`: rows keep indexes 0-9 and add `"Linked to ana"`,
    `"This is you"` or `""` at index 10.
  - `test_deleted_linked_account_leaves_empty_label`: after deleting the linked account the row
    label is `""`.
  - `test_group_members_show_link_label`: the group page's member rows carry the label.
- [ ] **Step 2: Run** both test files. Expected: FAIL.
- [ ] **Step 3: Implement**: select `account_id` and `account__username` in
  `get_person_grid_queryset`, compute the label in `get_person_grid_data`, add a hidden
  `{ name: 'link_label', hidden: true }` column right before `actions` in both grid scripts, and
  make the first-name formatter append
  `<i class="fas fa-link ms-1" title="<label>" aria-hidden="true"></i><span class="visually-hidden"><label></span>`
  when the label is set (escaped with `GridUtils.escapeHtml`). Actions are found by
  `id: 'actions'`, not by index (`dynamic-filters.js:440`, `real-time-search.js:36`).
- [ ] **Step 4: Run** the two files, `tox run -e py311 -- gift_manager/tests/views/` and
  `tox run -e e2e -- gift_manager/tests/e2e/test_card_view_polish.py gift_manager/tests/e2e/test_list_templates.py`.
  Expected: PASS (list, card view, inline editing and bulk selection unchanged).
- [ ] **Step 5: Commit** `Feat: Show account links in person lists and group members`.

---

### Task 9: Seed helper and end-to-end tests

**Files:**
- Modify: `gift_manager/seed_data.py` (new helper), `gift_manager/management/commands/seed_data.py`
- Create: `gift_manager/tests/e2e/test_person_account_link.py`
- Test: `gift_manager/tests/test_seed_data.py`, `gift_manager/tests/test_seed_data_command.py`

**Interfaces:**
- Consumes: Task 3 `link`; all UI from Tasks 4-8.
- Produces: `create_account_link_seed(data: SeedData) -> AccountLinkSeed` with
  `@dataclass(frozen=True) class AccountLinkSeed: household: PersonGroup; alice_record: Person;
  self_record: Person` (both records owned by `testuser`, in the new "Household" group,
  `alice_record` linked to `data.alice`, `self_record` linked to `testuser`).

- [ ] **Step 1: Write failing tests**:
  - `test_account_link_seed` in `test_seed_data.py`: the helper creates the group and two records
    with the links above, and `create_seed_data()` alone is unchanged (`len(data.persons) == 5`).
  - `test_seed_command_creates_account_links` in `test_seed_data_command.py`.
  - In `test_person_account_link.py` (`@pytest.mark.e2e`, `@pytest.mark.frontend`, reusing
    `login_as` and `open_page` from `test_plan_coordination.py`):
    - `test_create_person_from_friends_list_and_surprise_visibility`: testuser uses "Create
      person" on Bob's friends row, sees "Linked to bob" on the new record; a surprise plan by
      Alice for that record, shared with Bob and testuser, returns 404 for Bob and is visible to
      testuser.
    - `test_link_from_email_banner`: testuser creates a person with `alice@example.com`, clicks
      "Link" on the banner, sees the badge.
    - `test_friends_row_buttons_fit_on_phone` (`@pytest.mark.mobile`, 390x844): both buttons are
      visible and the page has no horizontal scroll.
- [ ] **Step 2: Run** `tox run -e py311 -- gift_manager/tests/test_seed_data.py gift_manager/tests/test_seed_data_command.py`
  and `tox run -e e2e -- gift_manager/tests/e2e/test_person_account_link.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the helper (links through `account_links.link` with `testuser` as
  actor) and call it from the command after `create_seed_data()`.
- [ ] **Step 4: Run** the step 2 commands, then the final verification:
  `python manage.py makemigrations --check --dry-run`, `tox run -e py311`, `tox run -e lint`,
  `tox run -e e2e -- gift_manager/tests/e2e/test_person_account_link.py gift_manager/tests/e2e/test_plan_coordination.py`,
  `python manage.py makemessages -l fr` (no new untranslated or fuzzy entries) and
  `python manage.py compilemessages`. Expected: all PASS.
- [ ] **Step 5: Commit** `Test: Add account link seed and end-to-end tests`.
