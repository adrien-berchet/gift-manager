# Shared Plan Coordination - Design

Implements `docs/ideas/0007-shared-plan-coordination.md`.

## Goals

- Collaborators on a gift plan (`Relation`) can see who is already buying the gift (claim).
- Collaborators can discuss a plan in a short comment thread attached to it.
- A plan can be marked as a surprise so that the recipient, when the recipient is also a
  user of the app, never sees it.

## Decisions (agreed with the user)

| Topic | Decision |
|---|---|
| Who may claim or comment | Any user with access to the plan, **including viewers**. |
| Claim semantics | One claimer per plan. While claimed, nobody else can claim. Only the claimer or a plan OWNER can release. |
| Comment deletion | The author or a plan OWNER. Comments are not editable (YAGNI). |
| Who may change the surprise flag | Plan OWNER and EDITOR (existing editor semantics via `PermissionService`). |
| Surprise default | On when a plan is **created** for a person recipient that has a `user_link`, or for a group with at least one member (nested groups included) that has a `user_link`. Users who would be exempt (the creator, or any user holding OWNER on the plan) do not count as recipients. No backfill of existing plans. |
| Enforcement | Inside `RelationQuerySet.accessible_by`, so every consumer inherits it. |
| Group recipients | A surprise plan targeting a group is hidden from every user whose linked person is a member of the group, **including members of descendant groups** (`PersonGroup.get_all_members(include_nested=True)` semantics). |
| Owner exception | A user with OWNER permission on the plan is never hidden from it. When a person recipient's `user_link` is a plan OWNER, the flag is forced off and not editable in the UI or by the server, even for editors. |

## Non-goals

Real-time chat, notifications, new permission levels, comment editing, multiple claimers,
backfilling the surprise flag, changes to the sharing UI redesign tracked in
`docs/ux-roadmap.md`.

## Data model (single migration)

- `Relation.is_surprise`: `BooleanField(default=False)`.
- `Relation.claimed_by`: `ForeignKey(User, null=True, blank=True, on_delete=SET_NULL,
  related_name="claimed_relations")`.
- `Relation.claimed_at`: `DateTimeField(null=True, blank=True)`.
- Check constraint: `claimed_by IS NULL` iff `claimed_at IS NULL`.
- `RelationComment`: `relation` (FK, `CASCADE`, `related_name="comments"`), `author`
  (FK User, `SET_NULL`, null), `text` (`TextField`, validated non-blank, max 2000 chars at
  form level), `created_at` (`auto_now_add`), ordered by `created_at, pk`.
- Duplicate and "Plan again" (`gift_manager/plan_repeat.py`) copies reset the claim and never
  copy comments; they keep `is_surprise` because the recipient is unchanged.
- Removing a user's access to a plan (unshare) releases a claim they hold on it, so a
  claimer who lost access does not block the plan.

## Service: `gift_manager/plan_coordination.py`

All rules live here; views stay thin. Every function takes the acting user, resolves the
effective permission with `PermissionService.get_effective_permission(relation, user)`, and
raises `PermissionDenied` otherwise. No parallel access logic.

- `claim(relation, user)`: needs access (level >= VIEWER). Runs inside
  `transaction.atomic()` with `PermissionService.lock_object(relation)`; if
  `claimed_by` is set to another user it raises a domain error; the same user is a no-op.
- `release(relation, user)`: claimer, or level OWNER. No-op when unclaimed.
- `add_comment(relation, user, text)`, `delete_comment(comment, user)`: rules above.
- `set_surprise(relation, user, value)`: level >= EDITOR; refuses (value forced to
  `False`) when `can_be_surprise(relation)` is false.
- `can_be_surprise(relation)`: false when the recipient is a person whose `user_link` holds
  OWNER on the plan.
- `default_surprise_for(person_or_group, creator)`: used by the create form/view to
  prefill the checkbox. True when the person has a `user_link` that is not the creator, or
  when the group (nested members included, via `get_all_members(include_nested=True)`) has a
  member whose `user_link` is set and is not the creator.

## Surprise visibility

`RelationQuerySet.accessible_by(user)` keeps `shared_with=user` and additionally excludes a
plan when all of the following hold:

1. `is_surprise` is true;
2. `user` is a recipient: `person__user_link=user`, or `group` is in the user's group
   closure (the groups of persons linked to `user`, plus all their ancestors, computed once
   per call from the cached hierarchy);
3. `user` does not hold OWNER on the plan (`Exists` on `RelationPermission`).

Superusers are not special-cased in the queryset, consistent with `shared_with` today.

### Audit (every path that reaches a plan)

The queryset covers all `Relation.objects.accessible_by` call sites (dashboard, plan list and
grids, search, detail, reminders, calendar feed, birthdays, gift history, plan repeat,
budgets, exports). The audit must additionally cover paths that **bypass** it:

- reverse accessors and prefetches on `Person`, `PersonGroup`, `Gift` and `Event`
  (`persons`, `groups`, `gifts`, `relations`) and their counts in templates;
- `values()`/raw queries in `gift_manager/views/search.py`, `views/common.py`,
  `mixins/performance.py`, `views/bulk_operations.py`, `views/sharing.py`,
  `views/recipient.py`, `interests.py`;
- direct `get_object_or_404(Relation, ...)` lookups and object-permission mixins.

Each bypass found is routed through `accessible_by`, or filtered with
`RelationQuerySet.hidden_surprises_for(user)`, the same exclusion exposed as a reusable
queryset method.

## UI

- Cards (`relation_cards_partial.html`) and detail (`includes/relation_detail_partial.html`)
  show "Claimed by <name>" with "I'll take this" / "Release" HTMX buttons, following
  the existing HTMX partial pattern (partial for HTMX requests, full page otherwise).
- The detail panel gets the comment thread and a form (author, text, timestamp, delete for
  author/owner).
- The plan form gets a "Surprise" checkbox, prefilled by `default_surprise_for` on create,
  shown only to OWNER/EDITOR and hidden when `can_be_surprise` is false. The server also
  ignores the submitted value in that case.
- No in-UI explanation text beyond labels (per `AGENTS.md`). French translations added and
  compiled.

## Permissions summary

| Action | Viewer | Editor | Owner |
|---|---|---|---|
| See claim and comments | yes | yes | yes |
| Claim (when free) / comment | yes | yes | yes |
| Release | own claim | own claim | any |
| Delete comment | own | own | any |
| Toggle surprise | no | yes | yes |

## Testing

- Service tests per role (owner, editor, viewer, no access, linked recipient) and for the
  claim race (second claim rejected; same-user claim idempotent), `release`, unshare release.
- Surprise regression suite, one test per surface: dashboard, plan list/grid, search,
  detail, reminders digest, calendar feed, gift history, birthdays, budgets, exports,
  reverse accessors; each for person recipient, group recipient, nested-group member,
  non-recipient (still visible), and owner-recipient (still visible).
- Form tests: default prefill for person and group recipients (including a nested-group
  member and a group whose only linked member is the creator), forced-off for
  owner-recipient, editor-only.
- Existing permission tests and `gift_manager/tests/test_permission_locking.py` pass;
  `makemigrations --check` clean; one e2e flow (claim, comment, release) on PostgreSQL.

## Resolved review points

- Group recipients also default to surprise **on** (see the default rule above).
- An existing plan that is later flagged as a surprise keeps comments written by the
  recipient but they become invisible to them (no cleanup).
