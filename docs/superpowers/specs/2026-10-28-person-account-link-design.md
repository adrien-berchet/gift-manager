# Person And Account Link - Design

Implements project A of `docs/ideas/0028-wishlists-and-collaborative-gift-giving.md`.

## Context

Gift Manager will combine wishlist and gift planner features (idea `0028`): registered users
describe themselves and keep a wishlist (project B), and their friends plan, buy and give gifts
together (project C). Both need the app to know which `Person` record represents which user
account. Today it cannot.

`Person.user_link` carries two meanings:

- Every create path sets it to the **creator** (`BaseCreateView.form_valid`,
  `gift_manager/views/base.py:412-436`; `gift_manager/guided_plan.py:385-386`). Nothing else ever
  sets it.
- The surprise and recipient rules read it as "this record **is** that user"
  (`recipient_groups_for` and `RelationQuerySet.hidden_surprises_for` in
  `gift_manager/models.py:267-297`; `can_be_surprise_for_owners`, `default_surprise_for` and
  `hidden_recipient_ids` in `gift_manager/plan_coordination.py`). Permissions also treat the
  linked user as an owner with access (`gift_manager/services.py:105,222,258`,
  `PersonQuerySet.accessible_by` in `gift_manager/models.py:125`,
  `gift_manager/mixins/permissions.py:169-187`, `gift_manager/group_hierarchy_service.py:63-73`).

Confirmed consequences (throwaway probe on SQLite, not committed):

- Bob creates "Alice" and shares it with Carol. Carol's plan for Alice defaults to a surprise and
  is hidden from Bob, a co-giver, even when Carol shares the plan with him.
- A group plan by Carol is hidden from Bob as soon as the group contains any record Bob created.
- The Surprise checkbox is hidden for every record the user created
  (`surprise_default_hint`, `gift_manager/views/relation.py:1040`), so a surprise can only be set
  on records created by someone else, or on groups.

Ownership never needed `user_link`: every create path also writes an explicit OWNER
`PersonPermission` (`gift_manager/views/base.py:439`).

## Goals

- One unambiguous meaning: `Person.account` says which account a record represents.
- A link never grants access to the record. Access comes only from permission rows.
- Surprise and recipient rules use the link, which fixes the bugs above.
- Givers can link records to their friends, and a user can mark one of their own records as
  themselves, from several natural places in the UI.

## Decisions (agreed with the user)

| Topic | Decision |
|---|---|
| Field | Reuse the column: rename `Person.user_link` to `Person.account` (`RenameField`), so any missed caller fails loudly instead of keeping the old meaning. |
| Meaning | `account` = the account this record represents. It never means "creator" and never grants access or ownership. |
| Existing data | Only test data exists. The migration backfills missing OWNER permissions, then clears every value. Links are recreated by hand. |
| Who may link to a friend | A user with at least EDITOR on the record, only to one of their friends. At least one OWNER of the record must also be friends with that account (always true when the actor is an owner). The linked friend is not asked and is not notified. |
| Self-link ("This is me") | Only an OWNER of the record may link it to their own account. A user has at most one self-linked record. |
| One record per account | A user may own at most one record linked to a given account (friend or self). Checked for every owner of the record being linked. |
| Visibility of a link | Everyone who can see the record sees that it is linked and to whom ("Linked to Ana", "This is you"). The linked account gains no access to the record. |
| Unfriending | A link to a friend stays only while at least one OWNER of the record is still friends with the linked account. Self-links are never removed by unfriending. |
| Effect on plans | The stored `is_surprise` flag is never recomputed. Linking hides existing surprise plans from the newly linked account and releases their claims on them; unlinking can reveal them again, and the UI warns first. |
| Linking entry points | Person page "Link account" form; friends list "Link to a person" and "Create person"; email-match banner on the person page (friend's email or the viewer's own); "Invite to Gift Manager" on the person page, which links when the invitation is accepted. |
| Not added | Linking by name similarity; bulk linking; asking the linked account for consent. |

## Non-goals

- Profile and wishlist fields for users (project B), collaborative purchase and contribution
  tally (project C).
- Recomputing or backfilling `is_surprise` on existing plans.
- Notifications about links.
- Releasing claims when a linked person is later added to a group (same pre-existing behaviour as
  today for membership changes; can be handled with project B).

## Data model (migration `0041`)

- `Person.account`: the renamed `user_link`.
  `ForeignKey(User, null=True, blank=True, on_delete=SET_NULL, related_name="linked_persons")`.
  It stays out of `PersonForm` (its `fields` list is explicit, `gift_manager/forms.py:232`) and is
  only written by the linking service. The default admin shows it; superusers may edit it there
  without the service rules.
- `Person.link_suggestion_dismissed_account`:
  `ForeignKey(User, null=True, blank=True, on_delete=SET_NULL, related_name="+")`. Records "this
  record is not that account" when an editor dismisses the email-match banner. Storing the
  dismissed account, instead of a boolean reset on email change, keeps the rule correct whatever
  path edits the email (form, inline editing, admin): a new email that matches another account
  shows a new suggestion.
- `Invitation.person`:
  `ForeignKey(Person, null=True, blank=True, on_delete=SET_NULL, related_name="invitations")`.
  Set when the invitation is sent from a person page.

Migration operations, in order:

1. `RunPython`: for each `Person` with `user_link` set and no OWNER `PersonPermission` for that
   user, create one. Reverse: no-op.
2. `RenameField` `user_link` to `account`, then `AlterField` for the new `related_name`.
3. `RunPython`: set `account = NULL` on every row. Reverse: no-op (old values are not restored).
4. `AddField` `Person.link_suggestion_dismissed_account` and `Invitation.person`.

## Service: `gift_manager/account_links.py`

All linking rules live here; views, the invitation flow and unfriending call it. Each function
resolves permissions through `PermissionService` and raises `PermissionDenied` or a
`LinkRefused(ValidationError)` with a translated, user-facing message.

- `link(person, account, actor) -> Person`
  - Inside `transaction.atomic()` with `PermissionService.lock_object(person)`.
  - `account == actor`: actor must be OWNER of `person` and must not already own another record
    linked to themselves.
  - Otherwise: actor must have EDITOR or more on `person`, be friends with `account`
    (`PermissionService.users_are_friends`), and at least one OWNER of `person` must be friends
    with `account`.
  - For every OWNER of `person`: they must not own another record linked to `account`.
  - Linking to the account already linked is a no-op. Linking a record linked to someone else
    replaces the link (same checks as unlink plus link).
  - After saving: release the claims `account` holds on plans that are now hidden from it:
    `Relation.objects.hidden_surprises_for(account).filter(claimed_by=account)` updated to
    `claimed_by=None, claimed_at=None` (the bulk form of `release_claim_of_hidden_recipient`,
    `gift_manager/models.py:1761-1774`).
  - Clears `link_suggestion_dismissed_account`.
- `unlink(person, actor) -> None`: actor must have EDITOR or more. No-op when not linked.
- `revealed_surprise_count(person) -> int`: number of plans shared with `person.account` that are
  hidden from it now and would no longer be hidden without this link, computed with the same
  `hidden_surprises_for` query with this record left out. A plan that stays hidden through another
  record linked to the same account is not counted. Used for the unlink and change warnings.
- `link_suggestion(person, viewer) -> User | None`: for an editor viewing an unlinked record with
  an email, the suggested account: the viewer's own account when the email is theirs (shown as
  the self-link banner), else the friend whose account owns the email (decoded and compared with the helpers in
  `gift_manager/invitations.py:23-58`, verified `EmailAddress` rows first, then the legacy
  `user.email`). `None` when the matching account is `link_suggestion_dismissed_account`, when
  linking would be refused by `link`, or when no account matches.
- `dismiss_link_suggestion(person, account, actor)`: EDITOR or more; stores the account.
- `remove_links_after_unfriending(user, former_friend)`: for records linked to either user, unlink
  those where no remaining OWNER is friends with the linked account; self-links are skipped.
  Called from `RemoveFriendView.post` (`gift_manager/views/profile.py:212-235`) after the existing
  permission cleanup, inside its transaction.
- `link_from_invitation(invitation, user)`: called by `accept_invitation_for_user`
  (`gift_manager/invitations.py:141-162`) after the friendship is created, in the same
  transaction. Links `invitation.person` to `user` through `link(..., actor=invitation.sender)`
  only when the record still exists, the sender is still an OWNER, the record is unlinked, and the
  one-record rule holds. Any refusal is swallowed: the invitation is still accepted and the
  email-match banner remains as a fallback.

## Permission and surprise rules

Remove every place where the link grants access or ownership:

- `PermissionService.get_effective_permission`: drop the OWNER boost (`services.py:105`).
- `PermissionService.has_other_access_holder` and `_owner_user_ids`: drop the linked-user branches
  (`services.py:222-224,258-260`).
- `PersonQuerySet.accessible_by` (`models.py:123-125`): removed, so `Person` uses the base
  `UserPermissionQuerySet.accessible_by` (`shared_with=user`) like every other model.
- `mixins/permissions.py:169-187`: drop the OWNER override for list rows.
- `group_hierarchy_service.py:63-73`: drop the "owner via user_link" editable branch.
- `views/search.py:66`: drop the unreachable `user_link` fallback.
- `BaseCreateView.form_valid` and `guided_plan.py:385-386`: stop writing the field.
- `views/person.py:64`: stop selecting `user_link_id` in the list rows.

Switch the identity rules to `account`, keeping their logic: `recipient_groups_for`,
`hidden_surprises_for`, `can_be_surprise_for_owners`, `default_surprise_for`,
`hidden_recipient_ids`. The rule "an OWNER of a plan is never hidden from it" is unchanged.

Resulting behaviour:

- Carol's surprise plan for Bob's "Alice" (linked to Alice) is hidden from Alice and visible to
  Bob when shared with him.
- After Bob marks his own record "This is me", Carol's surprise plan for a group containing it is
  hidden from Bob.
- The Surprise checkbox is hidden only when the recipient is linked to the acting user (their
  self-record). It defaults to checked when the recipient is linked to another account, and is
  shown unchecked for unlinked records.
- Being a recipient only ever hides plans. Plans are never shared with the linked account
  automatically.
- Sharing warnings (`views/sharing.py:542`), claim and comment rules, the digest, the calendar
  feed, suggestions and history already read visible plans only and need no change.

## UI

All new strings are translated (English and French). Every action is a plain link or form that
works without JavaScript; HTMX requests get partial templates under
`gift_manager/templates/gift_manager/includes/`, as for the other side-panel forms.

- **Person page** (`views/person.py:324`, `includes/action_buttons.html`): a custom "Link
  account" button (icon `fas fa-link`) for editors, labelled "Change link" when linked. It opens
  `persons/<uuid:pk>/link/` (`person_link_account`), a form "Who is this person?" with radio
  choices:
  - "No one".
  - "Me": owners only; disabled with a link to the existing self-record when there is one.
  - Each friend: disabled with a link to the other record when one of the record's owners already
    owns a record linked to that friend.
  When the choice removes or replaces a link and `revealed_surprise_count` is positive, the
  confirmation shows "N surprise plans shared with Ana would become visible to her."
- **Link badge**: next to the person's name on the person page, in the persons list and card
  views (tooltip), and on member rows of the group page: "Linked to Ana" or "This is you".
- **Email-match banner** on the person page, for editors, from `link_suggestion`:
  - "This email belongs to your friend Ana. Link this person to her account?" with "Link" and
    "Not her" buttons.
  - "This email is yours. Is this person you?" with "This is me" and "Not me" buttons.
  Dismissal posts to `persons/<uuid:pk>/link-suggestion/dismiss/`
  (`person_dismiss_link_suggestion`). The banner is computed on each page view, so it covers new
  records, edited emails and friendships created after the record.
- **"Invite to Gift Manager"** button on the person page for editors, when the record has an
  email, is unlinked, and the email belongs neither to the viewer nor to a friend. It opens the
  existing `send_invitation` form with the email prefilled and a hidden `person` field.
  `SendInvitationView` stores `Invitation.person` only if the sender is an OWNER of that record.
- **Friends list** (`profile_detail.html:313-341`), for each friend:
  - When the viewer owns a record linked to them: the record's name (link to the person page) and
    "Unlink" (to the person link form).
  - Otherwise: "Link to a person" (`profile/friends/<int:friend_id>/link/`,
    `friend_link_person`: the viewer's owned, unlinked records, those whose email matches the
    friend first) and "Create person" (the person create form prefilled with the friend's first
    and last name, falling back to the username, and email, plus `link_to=<friend profile pk>`).
  - A hint "1 person has this email" when owned unlinked records match.
- **Person create form**: `prefill_fields` (`views/base.py:284`) also accepts `email`. The
  `link_to` parameter is carried as a hidden field; after save, `link` is called with the creator
  as actor. A refused link keeps the created record and shows the refusal message.
- **Profile page**: "Your own person record: <name>" when a self-link exists.
- **Admin**: unchanged registrations; `account`, `link_suggestion_dismissed_account` and
  `Invitation.person` appear with the default admin.

## Seed data and documentation

- `gift_manager/seed_data.py`: link the seeded "Alice" and "Bob" records to the seeded Alice and
  Bob accounts, and add a self-linked record for the test user inside a family group.
- `docs/ai/architecture.md`: a short "Persons and accounts" paragraph: ownership comes from
  permission rows, `account` says who a record represents, and being a recipient only removes
  visibility.
- Idea `0028` and its index row in `docs/ideas/README.md` record the overall direction.

## Testing

Existing tests (about 170 `user_link` occurrences in 37 files):

- `PersonFactory` gains an `owner` post-generation option creating an OWNER `PersonPermission`.
- Uses that meant ownership (for example `tests/e2e/conftest.py:134-138`) move to
  `owner=`. Uses that meant identity (surprise, coordination, claim and history tests) move to
  `account=` and keep their assertions. Assertions that only held because of the double meaning
  are changed, with the reason in the commit message.

New tests (pytest, PostgreSQL):

- Migration: backfill of missing OWNER permissions, no duplicate permission, rename, cleared
  values.
- `account_links`: every rule of `link` and `unlink`, including the owner-friendship condition for
  editors, owner-only self-link, one self-record, one owned record per account for every owner;
  claim release on link; `revealed_surprise_count`; `remove_links_after_unfriending` (kept when
  another owner is still a friend, removed otherwise, self-links kept); `link_from_invitation`
  success for new and existing users and each skip condition.
- No access through a link: the linked account cannot list, open, edit or delete the record;
  `get_effective_permission` returns `NONE`; list rows show no edit action.
- Surprise rules: the two probe scenarios as regression tests (visible to Bob, hidden from Alice);
  nested group with a linked member; self-link group case; Surprise checkbox shown for records the
  user created and hidden for their self-record.
- Email-match banner: verified `EmailAddress` and legacy email matches, own email, hidden for
  viewers and linked records, dismissal per account, new suggestion after the email changes to
  another friend's.
- Views: link form choices and disabled states, refusal messages, HTMX partial and full page,
  plain POST without JavaScript, friends list rows in both states, "Create person" with
  `link_to`, invitation sent from a person page.

End-to-end (Playwright, existing `e2e` and `mobile` markers):

- Two browser contexts: Bob uses "Create person" from the friends list, sees the link badge;
  Carol's surprise plan is hidden from Alice and visible to Bob.
- Banner flow: create a person with a friend's email, link from the banner.
- Friends list row with its two buttons at mobile width.

Verification before pushing:

```bash
python manage.py makemigrations --check
tox run -e py311 -- <targeted test files>
tox run -e py311
tox run -e lint
tox run -e e2e -- <new and changed e2e files>
python manage.py makemessages -l fr
python manage.py compilemessages
```

## Known limitations

- A record linked by one giver can be linked to a different account by another editor; the last
  link wins, subject to the rules above.
- Superusers editing `account` in the admin bypass the service rules and the claim release.
