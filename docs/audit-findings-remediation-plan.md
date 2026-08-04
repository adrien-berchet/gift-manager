# Project Audit Findings And Remediation Plan

Date: 2026-07-30

Scope: read-only audit of the Gift Manager Django application, including security,
authorization, backend logic, frontend UX/UI, accessibility, dependencies, CI/CD,
deployment, backups, and operational readiness.

The audit used four focused sub-agent reviews:

- Security review: authentication, authorization, sharing, secrets, CSRF, XSS, settings.
- Django/backend review: views, forms, models, permissions, data integrity, tests.
- Frontend/UX review: Grid.js, HTMX, forms, accessibility, mobile workflows.
- DevOps review: Docker, Compose, Vercel, CI, dependency scanning, backups, health.

Local verification performed:

- `pytest -q gift_manager/tests/test_permissions.py gift_manager/tests/views/test_sharing.py gift_manager/tests/test_inline_editing.py`
  passed with 67 tests.
- `manage.py check --deploy` with dummy production environment values reported only
  the expected dummy-secret warning.
- `pip-audit` found 54 known vulnerabilities across 7 resolved packages.
- `bandit` reported 12 medium findings, all around `mark_safe()` usage in Grid.js
  template-tag helpers.
- Direct `pytest` was used for the targeted test run because `tox run -e py311`,
  `tox run -e py312`, and `tox run -e lint` all skipped under the local `uv`/tox
  interpreter specs (`cpython3.11`, `/usr/bin/python3.12`, and `cpython3.10`).

No source files were changed during the audit. Secret files such as `.env` were not
read.

## Remediation Status

Updated: 2026-07-30

Issues 1-28 and Phases 1-5 are implementation-complete in the current working tree.

Verification after remediation:

- `pytest gift_manager/tests/test_permissions.py gift_manager/tests/views/test_sharing.py
  gift_manager/tests/views/test_base.py gift_manager/tests/test_inline_editing.py
  gift_manager/tests/test_grid_xss_safety.py gift_manager/tests/test_operational_hardening.py
  gift_manager/tests/test_production_settings.py` passed with 162 tests.
- Phase 5 targeted regression slice passed with 24 tests:
  `gift_manager/tests/test_models.py` selected cache/inheritance/relation tests,
  `gift_manager/tests/forms/test_event_form.py`,
  `gift_manager/tests/views/test_search.py`,
  `gift_manager/tests/views/test_person_group_views.py::TestPersonGroupListView::test_list_view_tree_data_excludes_inaccessible_children`,
  `gift_manager/tests/test_phase5_frontend_contracts.py`, and
  `gift_manager/tests/test_permission_ui_adaptation_property.py`.
- Broader Phase 5-adjacent surface checks passed:
  `gift_manager/tests/views/test_base.py`,
  `gift_manager/tests/views/test_person_group_views.py`,
  `gift_manager/tests/views/test_gift_tag_authorization.py`,
  `gift_manager/tests/views/test_relation.py`,
  `gift_manager/tests/test_offcanvas_person_form.py`,
  `gift_manager/tests/test_phase5_frontend_contracts.py`, and
  `gift_manager/tests/test_permission_ui_adaptation_property.py` passed with 133
  tests; `gift_manager/tests/test_grid_xss_safety.py` passed with 4 tests and 1
  skip.
- `ruff check` passed for the changed Python files.
- `bash -n build.sh scripts/postgres_backup.sh scripts/postgres_restore.sh
  scripts/media_backup.sh scripts/pre_migration_snapshot.sh` passed.
- `python manage.py check --deploy --fail-level WARNING` passed with a dummy
  production environment.
- `DJANGO_ENV=testing python manage.py makemigrations --check --dry-run`
  reported no changes.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet`
  passed with required production environment values.
- `bandit -r gift_manager -x gift_manager/tests --severity-level medium
  --confidence-level medium` passed.
- `pip-audit` against the frozen production export reported no known vulnerabilities.

Operational evidence still needs to be collected in the deployment environment:

- Run a clean-volume production Compose startup with real certificates and secrets.
- Restore the latest off-host backup into a clean database and record the drill.
- Scan the built production image for accidental env, key, cert, report, or backup
  artifacts.

## Executive Summary

The highest-risk issues are authorization failures in sharing and edit flows. Several
POST endpoints trust client-submitted object IDs, user IDs, or the fact that an object
is merely viewable. This creates practical paths for users with low privileges to edit
objects, grant permissions, or share objects they should not control.

The next major risk is stored XSS in Grid.js renderers that use `gridjs.html()` with
unescaped user-controlled names. After that, the most important work is deployment
hardening: production compose has likely startup blockers, dependency security checks
are non-blocking, and there is no backup/restore runbook.

Recommended sequencing:

1. Fix authorization and sharing mutations.
2. Fix XSS surfaces and add hostile-input browser tests.
3. Harden production configuration, dependencies, CI, and backups.
4. Fix backend logic/data-integrity bugs.
5. Improve HTMX UX, accessibility, and mobile workflows.

## P0: Critical Security Findings

### 1. Bulk Sharing Trusts Posted Users And Object IDs

Severity: critical

Evidence:

- `ShareObjectsView._get_selected_friends()` accepts any posted user IDs via
  `User.objects.filter(id__in=friend_ids)` in `gift_manager/views/sharing.py`.
- Share handlers query objects globally instead of filtering by caller access:
  `Person.objects.filter(person_id__in=...)`,
  `PersonGroup.objects.filter(group_id__in=...)`,
  `Gift.objects.filter(gift_id__in=...)`,
  `Event.objects.filter(event_id__in=...)`,
  and `Relation.objects.filter(relation_id__in=...)`.
- Relation sharing also cascades permissions to related gift, person, group, and
  event objects.

Risk scenario:

A logged-in user who learns or obtains an object UUID can POST it to `/share/` and
grant themselves or another account access, potentially at `OWNER` level. UUIDs lower
guessability, but they do not remove IDOR risk because UUIDs can leak through pages,
logs, screenshots, emails, browser history, or shared links.

Plan:

- Restrict selected recipients to `request.user.profile.friends`.
- Restrict selected objects to effective objects the caller can share.
- Require a clear share permission, probably `OWNER` or at least `EDITOR`, for every
  object being shared.
- Reject unauthorized submitted IDs rather than silently ignoring them.
- Prevent granting a permission level higher than the caller's own effective level.
- Re-check authorization for cascaded relation/group/member sharing.

Tests:

- Forged non-friend user ID is rejected.
- Forged private person/gift/event/relation UUID is rejected.
- Viewer cannot share a viewed object onward.
- Editor/owner behavior is explicit and covered.
- Relation cascade cannot grant access to related objects unless the caller can share
  each related object.

### 2. Viewers Can Edit Objects And Self-Elevate

Severity: critical

Evidence:

- `BaseUpdateView` uses `FilterByUserMixin`, whose queryset is
  `self.model.objects.accessible_by(self.request.user)`.
- `BaseUpdateView.form_valid()` saves accessible objects, then calls
  `PermissionService.create_or_update_permission(... permission_level=EDITOR ...)`
  for the current user.
- For models with `user_link`, update also assigns `form.instance.user_link =
  self.request.user`.

Risk scenario:

If Alice shares a gift with Bob as `VIEWER`, Bob can manually POST to the edit URL,
change the gift, and become `EDITOR`. For some object types, ownership-like fields may
also be reassigned as a side effect.

Plan:

- Add a single server-side edit guard before normal update POST processing.
- Require `PermissionService.get_permission(obj, request.user) >= EDITOR` for object
  edits.
- Do not grant `EDITOR` as a side effect of normal updates.
- Do not modify `user_link` on update unless there is a specific ownership-transfer
  workflow.
- Audit all subclasses of `BaseUpdateView` for custom `get_queryset()` overrides.

Tests:

- Viewer GET behavior is intentional: either no edit form or read-only/403.
- Viewer POST to each update URL returns 403/404 and does not change data.
- Owner remains owner after edit.
- Editor can edit but does not unexpectedly gain owner-level access.

### 3. Permission Update Endpoints Lack Actor Authorization

Severity: critical

Evidence:

- `PermissionUpdateMixin.handle_permission_update()` updates/deletes permissions for
  a posted `user_id` without checking the requesting user's permission on the object.
- `EditPermissionMixin._handle_update_permission()`,
  `_handle_remove_share()`, and `_handle_share_with()` do the same.
- These paths are reached before normal form handling in edit views.

Risk scenario:

A viewer of a shared object can POST permission fields to grant themselves or another
user `EDITOR` or `OWNER`, remove another user's access, or otherwise modify sharing.

Plan:

- Centralize share-management authorization in one helper or service method.
- Require `OWNER` for permission management unless product requirements explicitly
  allow `EDITOR` to share.
- Validate target permission values against `PermissionLevel`.
- Restrict target users to valid friends or approved collaborators.
- Prevent self-removing the last owner and prevent demoting all owners.
- Use the same logic for HTMX, AJAX, and non-HTMX paths.

Tests:

- Viewer cannot add, remove, or change permissions.
- Editor behavior matches the product decision.
- Owner can add, update, and remove shares.
- Invalid user ID, invalid permission value, and non-friend target are rejected.
- Last-owner protection works.

### 4. Private Gift Tags Are Editable By UUID

Severity: high

Evidence:

- `GiftTagUpdateView.get_queryset()` returns
  `GiftTag.objects.prefetch_related("parent_tags", "child_tags")` instead of
  filtering through `accessible_by(request.user)`.

Risk scenario:

Any authenticated user who knows another user's private tag UUID can submit the edit
form and change the tag or its parent relationships.

Plan:

- Change the update queryset to `GiftTag.objects.accessible_by(request.user)`.
- Apply the same edit-level guard as other update views.
- Confirm delete/detail querysets use the same effective access model.

Tests:

- Inaccessible private tag UUID returns 404/403.
- Viewer of a shared tag cannot edit unless granted editor access.
- Editor can edit only allowed parent tags.

### 5. Stored XSS Through Grid.js HTML Formatters

Severity: high

Evidence:

- `grid-utils.js` returns `gridjs.html()` with interpolated `text`, `item.name`, and
  `tag.name` in `linkFormatter`, `multiLinkFormatter`, and `badgeFormatter`.
- Several templates use inline `gridjs.html()` with names from gifts, people, tags,
  groups, events, and relation comments.
- `escapejs` in templates protects JavaScript literals, but after parsing the runtime
  string is still inserted as HTML.
- Bandit also flagged `mark_safe()` in `gift_manager/templatetags/grid_tags.py`.

Risk scenario:

An attacker creates a name such as `<img src=x onerror=...>`, shares it with another
user, and code executes in the victim's browser when Grid.js renders the list/detail
cell.

Plan:

- Add a central `escapeHtml()` helper for Grid.js formatters.
- Escape dynamic URL attributes and text separately.
- Prefer Grid.js native escaping for text-only cells.
- Replace inline `gridjs.html()` snippets with safe shared formatters where possible.
- Use `json_script` for data bootstrapping instead of manual JavaScript literals where
  practical.
- Review `mark_safe()` usages and replace with `format_html`, `json_script`, or
  clearly safe JSON emission.

Tests:

- Add browser tests with hostile gift/person/tag/group/event names.
- Assert hostile strings render literally and no script executes.
- Include formatter-level unit tests for escaping.

## P1: High Priority Security And Operations

### 6. Inline Editing Is CSRF-Exempt

Severity: medium/high

Evidence:

- `InlineUpdateView.dispatch()` is decorated with `csrf_exempt`.
- The frontend already sends CSRF tokens in `inline-editing.js`.
- `get_queryset()` returns `self.model.objects.all()` before permission checking.

Plan:

- Remove `csrf_exempt`.
- Require normal Django CSRF validation and JSON content type.
- Consider returning 404 for objects outside the editable queryset to reduce UUID
  enumeration.

Tests:

- Missing/invalid CSRF token is rejected.
- Viewer receives no update and no data changes.
- Editor update still succeeds with valid CSRF token.

### 7. Removing A Friend Can Revoke The Friend's Own Object Permissions

Severity: high

Evidence:

- `RemoveFriendView` queries objects shared with `request.user`, then removes
  `friend` from those same objects if present.

Risk scenario:

If Bob shared Bob's object with Alice, Alice removing Bob as a friend can remove Bob
from his own object while Alice may retain access.

Plan:

- Separate the two cleanup directions:
  - remove `request.user` from objects owned/shared by the friend;
  - remove `friend` only from objects owned/shared by `request.user`.
- Use through-model permission deletion rather than only many-to-many removal, so
  permission rows stay consistent.
- Preserve owner permissions.

Tests:

- Two-user ownership scenario.
- Mutual sharing scenario.
- Removing friendship revokes cross-access but never removes an owner from their own
  object.

### 8. Production Environment Handling Is Fragile

Severity: high

Evidence:

- Missing or unknown `DJANGO_ENV` falls back to development settings.
- `get_env_variable(required=True)` rejects only `None`, not blank strings.
- Production compose interpolates unset secrets as blank values.
- `EMAIL_ENCRYPTION_KEY` is optional in base settings but required by migration/runtime
  encryption code.

Plan:

- Fail closed for unknown `DJANGO_ENV`.
- Treat blank required environment variables as missing.
- Require `EMAIL_ENCRYPTION_KEY` in production settings and deployment manifests.
- Add startup checks for key format and required production values.
- Remove import-time `print()` calls or replace them with sanitized logging.

Tests:

- Missing `DJANGO_ENV` in production entrypoints fails explicitly.
- Blank `DJANGO_SECRET_KEY`, DB vars, and `EMAIL_ENCRYPTION_KEY` fail startup.
- Valid production env passes `manage.py check --deploy`.

### 9. Production Compose Has Startup And Exposure Problems

Severity: high

Evidence:

- Production DB config defaults `sslmode=require`, but bundled Compose Postgres is a
  plain internal `postgres:15-alpine` service and `DB_SSLMODE` is not passed.
- `web` mounts `/app/staticfiles` read-only but runs `collectstatic`.
- nginx config requires certificate files, but prod compose does not mount an SSL
  directory.
- `web` still publishes port 8000 on the host, bypassing nginx.
- Redis uses `--requirepass ${REDIS_PASSWORD:-}` and Django sessions use cache-backed
  Redis in production.

Plan:

- Set `DB_SSLMODE=disable` or `prefer` for the bundled internal DB, or require an
  external TLS-enabled database.
- Run `collectstatic` either at image build or in a one-shot writable job, then serve
  the result read-only.
- Mount certs explicitly or terminate TLS upstream and simplify nginx accordingly.
- Replace host `ports` for `web` with internal `expose`, or bind only to loopback.
- Require `REDIS_PASSWORD` or define a clear unauthenticated internal Redis mode.
- Add DB/cache-aware readiness checks separate from liveness.

Tests:

- Clean-volume `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`
  succeeds.
- `nginx -t` passes in the production container.
- External scan cannot reach app port 8000.
- Login/session behavior is tested during Redis outage and recovery.

### 10. Dependency And CI Security Gates Are Too Weak

Severity: high

Evidence:

- A fresh `pip-audit` run against a frozen `uv export` written to `/tmp` found 54
  known vulnerabilities across 7 resolved packages. The older checked-in
  `pip-audit-report.json`, if present, was not used as audit evidence.
- Affected resolved packages:
  - `click 8.3.1`: 1 vulnerability; fixed by `8.3.3`.
  - `cryptography 46.0.3`: 6 vulnerabilities; fixed versions include `46.0.5`,
    `46.0.6`, `46.0.7`, and `48.0.1`.
  - `django 5.2.9`: 38 vulnerabilities; fixed versions include newer `5.2.x`
    releases.
  - `django-allauth 65.13.1`: 2 vulnerabilities; fixed by `65.14.1`.
  - `python-dotenv 1.2.1`: 1 vulnerability; fixed by `1.2.2`.
  - `urllib3 2.6.2`: 4 vulnerabilities; fixed versions include `2.6.3` and
    `2.7.0`.
  - `werkzeug 3.1.4`: 2 vulnerabilities; fixed versions include `3.1.5` and
    `3.1.6`.
- CI installs broad dependency ranges with `pip install -e ".[test]"`.
- Bandit and pip-audit are run with `|| true`, so findings do not fail CI.

Plan:

- Update `uv.lock` to patched dependency versions.
- Prefer `uv sync --frozen` or equivalent lockfile-based installs in CI.
- Make dependency and security checks blocking at least for high/critical findings.
- Decide whether dev-only dependencies such as `django-debug-toolbar`, `werkzeug`, and
  `uvicorn` belong in production dependencies.
- Pin GitHub Actions and container base images according to the project's supply-chain
  policy.

Tests:

- `uv lock` and `uv export --frozen` succeed.
- `pip-audit` passes or only allows documented exceptions.
- CI test environment and Docker production install resolve the same versions.

### 11. Build And Release Workflow Can Mutate Production

Severity: high

Evidence:

- `build.sh` runs `makemigrations` and `migrate`.
- Vercel invokes the build script.
- `Dockerfile` suppresses `collectstatic` errors with `|| true`.

Plan:

- Remove `makemigrations` from deployment builds.
- Use `makemigrations --check --dry-run` in CI.
- Move `migrate` to a controlled release step with pre-migration backup and rollback
  instructions.
- Stop suppressing `collectstatic` failures, or skip collectstatic at image build when
  env is intentionally unavailable.

Tests:

- Build from a clean checkout is reproducible and does not require database access.
- Missing migrations fail CI.
- Migration job can be run and observed separately from app build.

### 12. No Backup Or Restore Mechanism Found

Severity: high

Evidence:

- Database and media data are stored in Docker volumes.
- Repository search found no `pg_dump`, `pg_restore`, backup schedule, restore script,
  or recovery runbook.

Plan:

- Add encrypted off-host PostgreSQL backups.
- Add media backups if uploads become active.
- Take pre-migration snapshots.
- Document restore steps to a fresh environment.
- Schedule recurring restore drills.

Tests:

- Restore latest backup into a clean database.
- Verify app starts and core workflows work against restored data.
- Confirm backup monitoring alerts on failures.

### 13. Docker Build Context May Include Local Secrets

Severity: high

Evidence:

- Production image copies the entire build context.
- `.gitignore` excludes more secret/local artifacts than `.dockerignore`.
- `.dockerignore` excludes `.env` but not all likely variants such as `.env_prod`,
  certs, PEM keys, reports, or local assistant/tooling files.

Plan:

- Align `.dockerignore` with secret/local patterns from `.gitignore`.
- Explicitly ignore `.env*`, `*.pem`, `*.key`, cert directories, local tool config,
  reports, coverage, and generated docs not needed in the image.
- Audit built images for accidental env/cert files.

Tests:

- Build image and run `find /app` checks for env, key, cert, and report artifacts.
- CI fails if secret-like files are found in image layers.

### 14. Host, Origin, CDN, And CSP Hardening

Severity: medium/high

Evidence:

- Production defaults allow broad Vercel host/origin patterns.
- nginx uses catch-all host handling.
- External CDN assets are loaded without Subresource Integrity.
- No Content Security Policy was found.

Plan:

- Use exact production hostnames by default.
- Reject unknown hosts at nginx.
- Self-host frontend dependencies or add SRI attributes.
- Add a Content Security Policy suitable for HTMX/Grid.js/bootstrap usage.

Tests:

- Unknown Host header returns a controlled rejection.
- CSP report-only phase shows no unexpected violations, then enforce.
- CDN integrity failures are observable.

## P2: Backend Logic And Data Integrity

### 15. Hierarchy Cache Invalidation Misses Removed Parents

Severity: medium

Evidence:

- `clear_hierarchy_cache()` recomputes ancestors after relationship changes.
- `m2m_changed` invalidation runs on `post_add`, `post_remove`, and `post_clear`.
- On remove/clear, old ancestors may no longer be discoverable from the changed
  instance, leaving stale descendant cache entries.

Plan:

- Capture affected parent/child IDs on `pre_remove` and `pre_clear`.
- Clear stale ancestor/descendant keys after the relationship changes.
- If exact invalidation is complex, temporarily clear broader hierarchy cache keys.

Tests:

- Cache descendants, remove a parent, then confirm old parent descendants update.
- Repeat for gift tag hierarchy.

### 16. Group Permission Inheritance Is Not Consistently Honored

Severity: medium

Evidence:

- Permission service contains inheritance-oriented logic.
- Querysets and views generally use direct `.accessible_by()` checks against
  `shared_with`.

Plan:

- Decide whether inherited group/tag permission is product contract.
- If yes, implement effective-access query helpers and use them consistently in
  list/detail/form/edit/share/delete paths.
- If no, remove or rename inheritance logic to avoid misleading behavior.

Tests:

- Parent group shared to a user causes intended child visibility and edit behavior.
- Revoking parent permissions removes inherited access.

### 17. Relation Recipient Integrity Is Only Form-Level

Severity: medium

Evidence:

- `Relation.person` and `Relation.group` are both nullable.
- `Relation.clean()` checks that exactly one is set, but the database does not enforce
  the invariant.

Plan:

- Add a `CheckConstraint` requiring exactly one of `person` or `group`.
- Clean or migrate any invalid existing rows before adding the constraint.

Tests:

- ORM/database rejects both-null and both-set rows.
- Valid person-recipient and group-recipient rows still save.

### 18. Recurrent Event Forms Cannot Persist The Anchor Date

Severity: medium

Evidence:

- `EventForm` exposes `date_type`, `absolute_date`, and `recurrence`, but not
  `usual_date`.
- Dashboard recurrence logic returns no upcoming occurrence when `usual_date` is
  missing.

Plan:

- Add a recurrence anchor date field or map the existing date input cleanly to
  `usual_date` when `date_type == recurrence`.
- Clear incompatible date fields based on selected date type.
- Validate recurrence plus anchor date together.

Tests:

- Yearly/monthly/weekly event created through the form appears in upcoming occasions.
- Switching between absolute and recurrent date types clears stale fields.

### 19. HTMX Search Uses Stale Field Names

Severity: medium

Evidence:

- Person search serializes `group.person_group_id`.
- Gift search serializes `tag.gift_tag_id`.
- Current models expose `group_id` and `tag_id`.

Plan:

- Replace stale field names.
- Prefetch `groups` and `tags` for the search queryset.

Tests:

- Searching a person with groups does not 500.
- Searching a gift with tags does not 500.

### 20. Gift Tag Usage Stats Can Leak Inaccessible Counts

Severity: low/medium

Evidence:

- `GiftTag.get_all_gifts()` returns all gifts for a tag and descendants.
- Gift tag detail counts `self.object.get_all_gifts()` without filtering by
  `request.user`.

Plan:

- Add a user-aware count/query method.
- Filter by `Gift.objects.accessible_by(request.user)` before counting.

Tests:

- Shared/public tag stats do not include private inaccessible gifts.

### 21. Delete Semantics Are Inconsistent

Severity: medium

Evidence:

- Bulk delete checks editor-level permissions.
- Generic delete behavior allows any accessible user to enter delete handling, then
  either removes their share or deletes when no other users exist.

Plan:

- Split "delete object" from "remove my access" as separate operations.
- Require owner/editor according to product rules for destructive deletes.
- Make list/detail button availability match backend enforcement.

Tests:

- Viewer can leave a shared object only through the intended endpoint.
- Viewer cannot delete the underlying object.
- Owner/editor delete behavior remains intact.

## P3: Frontend, UX, And Accessibility

### 22. HTMX Validation Errors Can Look Like Successful Saves

Severity: high UX

Evidence:

- `form_invalid()` returns the default 200 response.
- Client handlers treat 200/201 as success, close the offcanvas, trigger list refresh,
  and show success feedback.

Plan:

- Return 400 or 422 for invalid HTMX form responses.
- Keep the offcanvas open.
- Focus the first error or error summary.
- Ensure success toasts only come from explicit success events.

Tests:

- Server-side invalid submit keeps panel open.
- Error is visible and focused.
- No success toast or list refresh occurs.

### 23. Duplicate HTMX Success Handling

Severity: medium

Evidence:

- Inline `hx-on`, global `htmx:afterRequest`, `htmx:afterSwap`, and server
  `HX-Trigger` all overlap.

Plan:

- Define one HTMX response contract.
- Prefer server `HX-Trigger` events plus one global listener.
- Remove duplicate inline success behaviors.

Tests:

- One successful save produces exactly one toast and one grid/list refresh.

### 24. Status Update Error Handling Can Render Raw JSON

Severity: medium

Evidence:

- Detail-page fetch handlers call `response.text()` and inject the result without
  checking `response.ok`.
- The server returns JSON for error statuses.
- The advanced relation list expects `data-current-value`, but the replacement HTML
  omits it.

Plan:

- Add a shared status-update helper.
- Disable the control while saving.
- Check `response.ok`, parse JSON errors, revert the selection, and show a toast.
- Include required data attributes in success replacement HTML.

Tests:

- 403/404/400 responses do not replace cells with JSON.
- Failed update reverts UI state.

### 25. Share Page Uses Bootstrap 4 Markup In A Bootstrap 5 App

Severity: medium/low

Evidence:

- `share_objects.html` uses `custom-control`, `custom-checkbox`,
  `custom-control-input`, `custom-control-label`, and `badge badge-info`.
- Accordion headers are clickable `div` elements rather than accessible buttons.

Plan:

- Replace with Bootstrap 5 `form-check`, `form-check-input`, `form-check-label`, and
  `badge text-bg-*` classes.
- Convert collapsible headers to buttons with keyboard support.
- Make selected counts and cascade options visually clear.

Tests:

- Keyboard can expand/collapse every section.
- Mobile layout remains usable.
- Labels activate the intended checkbox.

### 26. Advanced Filter Controls Need Stronger ARIA State

Severity: medium

Evidence:

- Expanded/collapsed, multi-sort, and active view states are mostly visual.
- Search label association is weak.

Plan:

- Add `aria-expanded`, `aria-controls`, `aria-pressed`, and associated labels.
- Keep ARIA state synchronized in `filter-panel.js`.

Tests:

- Playwright/axe checks for filter panel states.
- Keyboard-only operation covers expand/collapse and sort toggles.

### 27. Group Tree Reparenting Is Drag-Only

Severity: medium/low

Evidence:

- Person group tree reparenting depends on mouse drag-and-drop.

Plan:

- Add an explicit Move/Reparent action usable by keyboard and touch users.
- Alternatively implement an accessible tree keyboard interaction model.

Tests:

- Keyboard-only move workflow.
- Mobile/touch move workflow.

### 28. Global Search Has Weak Combobox Semantics And Stale-Result Risk

Severity: low/medium

Evidence:

- Search input relies on placeholder text.
- Selected result state is mostly CSS-only.
- Concurrent searches are not aborted or sequenced.

Plan:

- Add accessible label and combobox/listbox attributes.
- Track active descendant state.
- Use `AbortController` or request IDs so slow responses cannot overwrite newer
  searches.

Tests:

- Delayed old response does not replace current results.
- Keyboard navigation announces selected results.

## P4: Account And Invitation Hardening

### 29. Invitations Need Abuse And Recipient Controls

Severity: low/medium

Status: complete. Invitation sends now validate and case-normalize recipient
emails, reject self- and existing-friend invitations, reuse an existing
unexpired pending invitation for the same sender/recipient, and apply a
per-sender cache-backed send limit. Acceptance is bound to the invited email:
logged-in users must own the invited email, allauth email matches must be
verified, and invitation signup stores the token until allauth confirms the
matching invited email.

Evidence:

- Sending invitations has no obvious rate limit, recipient normalization, or duplicate
  suppression.
- Accepting an invitation while logged in creates friendship for the current account,
  not necessarily the invited email address.

Plan:

- Add per-user invitation rate limiting. Done.
- Normalize recipient email and prevent duplicate active invitations. Done for
  sequential sends without a schema change.
- Bind invitation acceptance to the invited email. Done.
- Complete post-signup/post-verification automatic acceptance. Done for the
  same-browser invitation signup flow; users can still accept by revisiting the
  invitation link after authentication.

Tests:

- Duplicate invitations are handled deterministically.
- Rate limit blocks excessive sends.
- Forwarded invitation links cannot be accepted by the wrong account.
- Unverified allauth email rows do not satisfy the invited-email binding.
- Signup with a pending invitation rejects any email other than the invited email.
- Confirming the invited email accepts the pending invitation and creates the
  friendship.

## Cross-Cutting Remediation Plan

### Phase 1: Authorization Lockdown

Goal: remove privilege escalation and unauthorized sharing.

Status: complete. Implemented central permission mutation checks, hardened sharing and
edit/delete guards, restricted gift tag updates to accessible objects, closed the
share-management policy as owner-only, and added viewer/editor/owner regression tests.

Work:

- Create a central permission mutation service for share/edit/delete checks.
- Fix `ShareObjectsView`.
- Fix `BaseUpdateView` and subclasses.
- Fix `PermissionUpdateMixin` and `EditPermissionMixin`.
- Fix `GiftTagUpdateView` queryset.
- Add regression tests for viewer/editor/owner behavior.

Exit criteria:

- Viewer cannot edit, delete, or share onward unless explicitly allowed.
- Owner/editor behavior is consistent across object types.
- Forged UUID and non-friend POST tests pass.

### Phase 2: XSS And Frontend Safety

Goal: make Grid.js rendering safe by default.

Status: complete. Grid.js HTML helpers now escape dynamic text/attributes, templates
route unsafe cell rendering through shared helpers, `mark_safe()`/`SafeString` usage
was removed from Grid.js template tags, medium+ Bandit warnings are clean, and
hostile-input Node and Playwright browser regression tests cover the formatters.

Work:

- Add central HTML escaping helpers.
- Replace unsafe `gridjs.html()` text interpolation.
- Audit and reduce `mark_safe()`.
- Add hostile-input Playwright tests.

Exit criteria:

- Hostile names render as text.
- Bandit warnings are fixed or documented with justification.
- Browser tests prove no execution from list/detail cells.

### Phase 3: Production And Supply Chain Hardening

Goal: make builds, deploys, and runtime operations predictable.

Status: complete for repository controls. Production Compose no longer exposes the
web/db/Redis/debug ports, nginx rejects unknown hosts, builds no longer mutate the
database, dependencies are upgraded and locked, CI uses frozen installs, CSP is
enforced with pinned transitional CDN assets, and Bandit, pip-audit, migration drift,
Compose config, and production settings checks are blocking. A real clean-volume
startup remains deployment-environment evidence.

Work:

- Update vulnerable dependencies and lockfile.
- Make pip-audit/Bandit blocking by policy.
- Switch CI to frozen lockfile installs.
- Fix production compose DB SSL/static/nginx/Redis/web-port issues.
- Add CSP/SRI or self-hosted assets.
- Align `.dockerignore` with secret patterns.
- Remove migration execution from build.

Exit criteria:

- Clean production compose startup works.
- CI and Docker use consistent dependency versions.
- Security scans fail for unacceptable findings.
- Build does not mutate the database.

### Phase 4: Backups And Recovery

Goal: prevent unrecoverable data loss.

Status: complete for repository controls. Encrypted PostgreSQL/media backup scripts,
checksum-verified restore, pre-migration snapshots, monitoring/upload hooks for both
database and media backups, systemd timer templates, and the restore runbook are
present. The first real off-host restore drill remains deployment-environment
evidence.

Work:

- Add encrypted scheduled PostgreSQL backups.
- Add media backup if media becomes user data.
- Document restore procedure.
- Add pre-migration snapshot step.
- Schedule restore drills.

Exit criteria:

- A fresh environment can be restored from backup.
- Backup failures alert operators.
- Migration runbook includes rollback/recovery steps.

### Phase 5: Logic, Data Integrity, And UX Polish

Goal: fix correctness issues and reduce user-facing confusion.

Status: complete in the current working tree. Hierarchy cache invalidation now clears
stale ancestor/descendant entries after relationship changes, group inherited
permissions are treated as product behavior for effective access, relation recipients
are database-constrained, recurrent events persist their anchor date, search/status
handlers are hardened, gift tag stats are user-filtered, delete-vs-leave semantics
are explicit, and the Phase 5 frontend accessibility contracts have static coverage.

Work:

- Fix hierarchy cache invalidation.
- Resolve permission inheritance contract.
- Add `Relation` recipient constraint.
- Fix recurrent event date form handling.
- Fix HTMX search stale fields.
- Fix gift tag stats filtering.
- Split delete vs leave-access operations.
- Improve HTMX invalid form responses, status update errors, share page Bootstrap 5
  markup, ARIA states, accessible reparenting, and global search.

Exit criteria:

- Model invariants are database-backed.
- Recurrence and search bugs have regression tests.
- Core forms no longer show false success.
- Key workflows are keyboard and mobile accessible.

## Suggested Test Matrix

Backend targeted tests:

- `gift_manager/tests/test_permissions.py`
- `gift_manager/tests/views/test_sharing.py`
- `gift_manager/tests/test_inline_editing.py`
- New tests for update-view viewer denial.
- New tests for gift tag private edit denial.
- New tests for relation recipient DB constraint.
- New tests for recurrent event form/dashboard behavior.
- New tests for hierarchy cache invalidation.

Frontend/e2e tests:

- Hostile-name XSS rendering.
- HTMX invalid form stays open.
- Exactly one toast/refresh per save.
- Status update error handling.
- Share page keyboard operation.
- Filter panel ARIA state.
- Group reparent keyboard/mobile workflow.
- Global search stale-response handling.

Operations checks:

- `manage.py check --deploy` with real production-like env.
- `pip-audit` against frozen requirements.
- `bandit` with medium+ severity.
- Clean production Compose startup.
- `nginx -t`.
- Backup restore drill.
- Image secret scan.

## Closed Product Decisions

- Bulk sharing and permission management require `OWNER`; `EDITOR` users can edit but
  cannot share onward or mutate object permissions.
- Person group permission inheritance is a supported product contract when
  `inherit_permissions=True`; effective access uses the highest direct or inherited
  permission.
- Viewers can explicitly leave directly shared objects, but cannot delete the
  underlying object. Inherited child-group access is removed by changing the inherited
  parent permission.

## Open Product Decisions

- Will media uploads ever contain private user data?

## Immediate Next Steps

1. Run the deployment-environment evidence checks for Phases 3-4: clean production
   Compose startup, `nginx -t`, image secret scan, and a fresh restore drill.
2. Resolve the remaining product decision around private media expectations.
