# Project Audit Findings And Remediation Plan

Original audit date: 2026-07-30

Last relevance review: 2026-08-05

Code baseline reviewed before this document update: `39d5722`

Scope: Gift Manager Django application, including security, authorization, backend
logic, frontend UX/UI, accessibility, dependencies, CI/CD, deployment, backups, and
operational readiness.

## Current Summary

Most original audit findings have been remediated in the current code, subject to the
partial items and evidence gaps called out below. The old high-risk authorization and
Grid.js XSS issues should be treated as historical context rather than active
production claims.

The remaining relevant work is narrower:

- Split delete and leave-access behavior all the way through default UI/request paths.
- Strengthen runtime/e2e coverage for frontend accessibility and global search behavior.
- Add deployment-environment evidence for clean production startup, restore drills,
  outage behavior, and built-image secret scanning.
- Tighten supply-chain posture for pinned GitHub Actions, digest-pinned container
  images, and CDN integrity or self-hosting.
- Add or document coverage around irreversible data-cleanup migrations.

## Status Legend

- Solved: the original finding is no longer current in code.
- Partially remediated: meaningful controls exist, but a claim or exit criterion is
  still incomplete, weakly verified, or only repository-local.
- Deployment evidence outstanding: repository controls exist, but the result must be
  proven in the real deployment environment.
- Historical wording obsolete: the underlying bug is fixed through a newer design, so
  the old field names or workflow no longer describe the code.

## Verification From The 2026-08-05 Review

Sub-agent split:

- Authorization/security: sharing, edit guards, permission mutation, inline editing,
  friend removal, and delete/leave semantics.
- Backend/data integrity: hierarchy caches, inherited permissions, relation
  constraints, recurrence, search, gift-tag stats, and backend Phase 5 claims.
- Frontend/UX: Grid.js XSS, HTMX form/status flows, Bootstrap 5 share page,
  accessibility contracts, reparenting, and global search.
- Operations/supply chain: production settings, Compose, CI, dependencies, backups,
  Docker context, CSP, hosts, and deployment evidence.

Local checks run during the review:

```bash
tox run -e py311 -- gift_manager/tests/views/test_profile.py
```

Result: 35 passed.

```bash
bandit -r gift_manager -x gift_manager/tests --severity-level medium --confidence-level medium
```

Result: passed.

```bash
uv export --quiet --frozen --no-dev --no-emit-project --format requirements.txt --output-file /tmp/gift-manager-requirements.txt
pip-audit --requirement /tmp/gift-manager-requirements.txt --no-deps --disable-pip
```

Result: no known vulnerabilities found.

```bash
python manage.py check --deploy --fail-level WARNING
```

Result: passed with dummy but structurally valid production environment values.

```bash
DJANGO_ENV=testing python manage.py makemigrations --check --dry-run
```

Result: no model changes detected. A local database migration-history warning was
emitted because the default database connection was unavailable.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

Result: passed with all required dummy production and nginx environment values.

No source files were changed during the relevance review. Secret files such as
`.env` were not read.

## Finding Status

### 1. Bulk Sharing Trusted Posted Users And Object IDs

Status: solved.

Original issue: bulk sharing accepted arbitrary posted user IDs and object UUIDs.

Current state: recipients are restricted to the caller's friends, posted objects are
loaded through access-aware querysets, unauthorized IDs reject the operation, sharing
requires owner-level effective permission, and relation/group cascades re-check each
related object. Covered by sharing regression tests.

### 2. Viewers Could Edit Objects And Self-Elevate

Status: solved.

Original issue: update views allowed users with viewer access to save objects and gain
editor permission as a side effect.

Current state: update handling enforces effective editor access before edit
processing, normal updates no longer grant editor permission, and `user_link` is not
rewritten on update. Covered by viewer/editor/owner update tests.

### 3. Permission Update Endpoints Lacked Actor Authorization

Status: solved.

Original issue: permission mutation endpoints accepted posted target users and levels
without checking whether the actor could manage the object.

Current state: permission mutation is centralized through owner-only service checks,
target permission values are validated, non-friend targets are rejected, and
last-owner protection is enforced across HTMX/AJAX and form paths. Covered by
permission mutation tests.

### 4. Private Gift Tags Were Editable By UUID

Status: solved.

Original issue: `GiftTagUpdateView` used an unrestricted queryset.

Current state: gift-tag updates use `GiftTag.objects.accessible_by(request.user)`,
inherit the base editor guard, and filter parent-tag choices to accessible valid tags.
Covered by gift-tag authorization tests.

### 5. Stored XSS Through Grid.js HTML Formatters

Status: implemented; verification wording corrected.

Original issue: Grid.js renderers and template helpers inserted user-controlled names
as HTML.

Current state: Grid.js formatting uses centralized escaping helpers, template tags use
safe JSON plus `format_html`, and no remaining `mark_safe` or `SafeString` usage was
found under `gift_manager/`.

Verification note: formatter/helper coverage exists, and Bandit passes at
medium/medium. The previous statement that browser regression tests cover the full
formatter surface was too strong; list/detail template coverage is mostly static or
helper-level.

### 6. Inline Editing Was CSRF-Exempt

Status: solved.

Original issue: inline editing bypassed CSRF checks and started from unrestricted
querysets.

Current state: no current `csrf_exempt` usage was found under `gift_manager`; inline
updates require JSON, use access-aware querysets, require effective editor access, and
the frontend sends the CSRF token. Covered by inline-editing tests.

### 7. Removing A Friend Could Revoke The Friend's Own Object Permissions

Status: solved.

Original issue: friend removal could remove the former friend's permission from their
own object.

Current state: cleanup considers both users' shared objects and deletes only direct
non-owner permissions. Owner permissions and third-party shared objects are preserved.
Covered by friend-removal tests.

### 8. Production Environment Handling Was Fragile

Status: solved for repository controls.

Original issue: production settings could fall back unsafely or accept blank required
values.

Current state: unknown `DJANGO_ENV` fails closed, blank required env vars are rejected,
production requires and validates `EMAIL_ENCRYPTION_KEY`, and production Compose uses
required-variable interpolation for critical values. `manage.py check --deploy
--fail-level WARNING` passes with valid dummy production values.

### 9. Production Compose Had Startup And Exposure Problems

Status: partially remediated.

Original issue: production Compose exposed internal ports, had DB SSL/static/Redis
startup mismatches, and lacked clear readiness checks.

Current state: the original exposure and startup blockers have been addressed in
code/config: production does not publish `web`, `db`, or `redis` ports, Redis requires
a password, `collectstatic` is a one-shot service, and nginx SSL directories are
explicitly mounted. Compose config validates with required production values, but
runtime proof is still pending.

Remaining work:

- Run a clean-volume production Compose startup with real certificates and secrets.
- Add or verify DB/cache-aware readiness separate from the static health endpoint.
- Test login/session behavior during Redis outage and recovery.

### 10. Dependency And CI Security Gates Were Too Weak

Status: partially remediated.

Original issue: dependencies had known vulnerabilities, CI used broad installs, and
Bandit/pip-audit were non-blocking.

Current state: dependency ranges and `uv.lock` are upgraded, the CI workflow is
configured to use frozen `uv` installs, and the CI security-scan steps no longer use
`|| true`. A fresh local `pip-audit` against the frozen production export reported no
known vulnerabilities on 2026-08-05.

Remaining work:

- Decide whether dev tooling such as `django-debug-toolbar`, `uvicorn`, and
  `werkzeug` should remain in production dependencies.
- Pin GitHub Actions and container images by digest or document the project's chosen
  supply-chain policy.
- Align the CI Bandit threshold with the documented medium/medium posture, or document
  why CI enforces high/high while local checks use medium/medium.

### 11. Build And Release Workflow Could Mutate Production

Status: solved.

Original issue: build scripts ran `makemigrations`/`migrate`, and Docker suppressed
`collectstatic` errors.

Current state: `build.sh` no longer runs migrations, uses build-only settings for
static collection, Docker no longer suppresses collectstatic failures at build time,
and production migrations are a controlled release-profile step with runbook support.

### 12. No Backup Or Restore Mechanism Was Present

Status: repository controls present; deployment evidence outstanding.

Original issue: no backup scripts, restore process, or recovery runbook were found.

Current state: encrypted PostgreSQL and media backup scripts, checksum-verified
restore, pre-migration snapshots, monitoring/upload hooks, systemd timer templates,
and a restore runbook are present.

Remaining work:

- Restore the latest off-host backup into a clean database and record the drill.
- Validate operator alert wiring for backup and upload failures.

### 13. Docker Build Context Could Include Local Secrets

Status: partially remediated.

Original issue: `.dockerignore` did not cover enough local secret, certificate,
report, backup, and tool-generated artifacts.

Current state: `.dockerignore` now excludes `.env*`, key/cert material, local tool
directories, reports, coverage, and backup artifacts.

Remaining work:

- Add or run a built-image scan for env, key, cert, report, and backup artifacts.
- Consider a CI guard that fails if secret-like files appear in image layers.

### 14. Host, Origin, CDN, And CSP Hardening Was Missing

Status: partially remediated.

Original issue: production allowed broad host/origin patterns, nginx accepted unknown
hosts, external CDN assets lacked SRI, and no CSP was found.

Current state: production host/origin validation requires exact values, nginx rejects
unknown hosts, and an enforced CSP is configured.

Remaining work:

- Self-host external assets or add SRI attributes.
- Add CSP report-only/monitoring evidence before or alongside enforced changes.
- Add observability for CDN integrity failures if CDN assets remain.

### 15. Hierarchy Cache Invalidation Missed Removed Parents

Status: solved.

Original issue: remove/clear operations could leave stale descendant cache entries.

Current state: hierarchy change signals now clear cached ancestor/descendant keys for
both person-group and gift-tag hierarchies after relationship changes. Covered by
regression tests for removed parent cache behavior.

### 16. Group Permission Inheritance Was Not Consistently Honored

Status: implemented; test coverage gap remains.

Original issue: inheritance logic existed but list/detail/form/edit/share/delete paths
mostly used direct `shared_with` checks.

Current state: inherited/effective group permission is now product behavior and is
used in the main querysets and permission checks.

Remaining test gap:

- Add a dedicated regression that revoking parent permissions removes inherited child
  access.

### 17. Relation Recipient Integrity Was Only Form-Level

Status: partially remediated.

Original issue: `Relation.person` and `Relation.group` were nullable, and the database
did not enforce "exactly one recipient".

Current state: the model and migration now enforce exactly one recipient, and tests
cover valid and invalid rows.

Remaining work:

- Add a dedicated migration test or documented migration note for the irreversible
  cleanup path in migration `0026`, which repairs old invalid data by nulling `group`
  or deleting rows.

### 18. Recurrent Event Forms Could Not Persist The Anchor Date

Status: solved; historical wording obsolete.

Original issue: older event forms exposed `date_type`, `absolute_date`, and
`recurrence` without persisting `usual_date`.

Current state: the old field contract has been replaced by the newer schedule model:
events use `schedule_type` plus a single `date`. Form normalization and recurring
occurrence logic have tests.

Remaining test gap:

- Add an end-to-end or view-level regression that a recurring event created through
  the form appears in upcoming occasions.

### 19. HTMX Search Used Stale Field Names

Status: solved.

Original issue: person and gift search serialized stale group/tag ID field names.

Current state: HTMX search prefetches related groups/tags and serializes the current
`group_id` and `tag_id` fields. Covered by search tests.

### 20. Gift Tag Usage Stats Could Leak Inaccessible Counts

Status: solved.

Original issue: gift-tag detail counted all tagged descendant gifts without filtering
by requester access.

Current state: gift-tag stats use a user-filtered gift traversal and detail counts pass
the requester. Covered by gift-tag authorization tests.

### 21. Delete Semantics Were Inconsistent

Status: partially remediated.

Original issue: delete handling mixed "delete object" with "remove my access".

Current state: viewer protection and an explicit `leave_access` intent exist, and
tests cover viewer leave-access behavior.

Remaining issue:

- A normal delete POST on an object with other access holders can still remove the
  requester permission instead of deleting the object. The default delete URL and
  modal request path do not consistently carry an explicit `leave_access` intent.

Next action:

- Fully separate destructive delete from leave-access in route names, modal forms,
  buttons, and backend handling.

### 22. HTMX Validation Errors Could Look Like Successful Saves

Status: solved, with test cleanup recommended.

Original issue: invalid HTMX forms returned 200 and client handlers treated 200/201 as
success.

Current state: invalid HTMX form responses return 422, the panel remains open, and
client handlers focus validation errors instead of firing success behavior.

Test cleanup:

- Some older property tests still allow the old 200 validation response contract. They
  should be tightened to the current 422 behavior.

### 23. Duplicate HTMX Success Handling

Status: solved in code; runtime assertion still missing.

Original issue: inline `hx-on`, global HTMX handlers, swaps, and `HX-Trigger` overlapped.

Current state: managed-form success handling is centralized around `HX-Trigger` and a
single global listener pattern.

Remaining test gap:

- Add a focused runtime test proving one successful save produces exactly one toast and
  one grid/list refresh.

### 24. Status Update Error Handling Could Render Raw JSON

Status: solved.

Original issue: detail/list fetch handlers injected `response.text()` without checking
error status, and replacement HTML missed required state attributes.

Current state: status updates use a shared helper that checks `response.ok`, parses
JSON errors, restores prior UI value on failure, and preserves `data-current-value` in
successful replacement HTML. Covered by formatter/status tests.

### 25. Share Page Used Bootstrap 4 Markup In A Bootstrap 5 App

Status: solved in code; runtime accessibility coverage still light.

Original issue: the share page used Bootstrap 4 form classes and non-button accordion
headers.

Current state: the page uses Bootstrap 5 `form-check`/`badge text-bg-*` classes and
accessible collapse buttons. Static contract tests cover the markup.

Remaining test gap:

- Add focused keyboard and mobile tests for expanding sections and activating labels.

### 26. Advanced Filter Controls Needed Stronger ARIA State

Status: solved in code; runtime accessibility coverage still light.

Original issue: expanded/collapsed, multi-sort, active view, and search-label states
were mostly visual.

Current state: templates expose ARIA state and labels, and `filter-panel.js` syncs
expanded/pressed states. Static contract tests cover the expected attributes.

Remaining test gap:

- Add runtime Playwright or axe checks for synchronized filter-panel state.

### 27. Group Tree Reparenting Was Drag-Only

Status: solved in code; runtime accessibility coverage still light.

Original issue: group reparenting depended on mouse drag-and-drop.

Current state: the tree includes an explicit Move action and modal, with JavaScript
support for valid targets and non-drag submission. Backend API tests cover the move
operation.

Remaining test gap:

- Add keyboard-only and mobile/touch workflow tests for the Move/Reparent UI.

### 28. Global Search Had Weak Combobox Semantics And Stale-Result Risk

Status: partially remediated.

Original issue: the global search input relied on placeholder text, selected state was
mostly CSS-only, and concurrent searches could overwrite newer results.

Current state: the live modal has combobox/listbox semantics, active-descendant state,
and stale-response guards using `AbortController` plus request IDs.

Remaining issue:

- Browser tests for global search appear stale and target old selectors, while current
  coverage is mostly static contract testing.

Next action:

- Refresh global-search Playwright tests to exercise the live modal, keyboard
  navigation, active descendant state, and delayed-response handling.

### 29. Invitations Needed Abuse And Recipient Controls

Status: solved.

Original issue: invitation sends lacked obvious rate limiting, normalization, duplicate
suppression, and recipient binding.

Current state: invitation sends validate and case-normalize recipient emails, reject
self and existing-friend invitations, reuse an unexpired pending invitation for the
same sender/recipient, and apply a per-sender cache-backed send limit. Acceptance is
bound to the invited email: logged-in users must own the invited email, allauth email
matches must be verified, and same-browser invitation signup stores the token until
allauth confirms the matching email. Covered by profile/invitation tests.

## Phase Status

### Phase 1: Authorization Lockdown

Status: complete for the original authorization findings.

Sharing, edit guards, permission mutation, gift-tag update access, inline editing, and
friend-removal authorization have been remediated and are covered by regression tests.
Delete/leave semantics are tracked separately under finding 21.

### Phase 2: XSS And Frontend Safety

Status: implementation complete for the identified XSS fixes; verification wording
corrected.

Grid.js escaping and template-tag safety are implemented, and Bandit passes at
medium/medium. The prior claim that browser regression tests fully prove list/detail
formatter safety was overstated; current verification is mostly helper-level and
static-template oriented.

### Phase 3: Production And Supply Chain Hardening

Status: partially complete.

Repository controls are much stronger: production settings fail closed, dependencies
are upgraded and frozen, CI workflows use frozen installs and unsuppressed security
scan steps, builds no longer run migrations, production Compose no longer exposes
internal ports, and CSP/host checks exist.

Remaining work:

- Prove clean production startup with real secrets/certificates.
- Add DB/cache-aware readiness and outage/recovery tests.
- Pin Actions and container images by digest or document the policy.
- Self-host CDN assets or add SRI.
- Add built-image secret scanning.

### Phase 4: Backups And Recovery

Status: repository controls complete; deployment evidence outstanding.

Backup, restore, pre-migration snapshot, monitoring/upload hooks, timer templates, and
the runbook are present. The first real off-host restore drill and alert validation
still need to be performed and recorded.

### Phase 5: Logic, Data Integrity, And UX Polish

Status: mostly complete, with partial items.

Backend correctness fixes are largely in place: hierarchy cache invalidation,
effective group access, relation recipient constraints, recurrent scheduling, search
field names, and gift-tag stats are fixed or redesigned.

Remaining work:

- Finish the delete-vs-leave split in default UI/request paths.
- Add migration-safety coverage for relation-recipient cleanup.
- Add a form-to-upcoming-occasions regression for recurring events.
- Replace static-only frontend contracts with focused runtime/e2e tests where user
  behavior matters.
- Refresh stale global-search browser tests.

## Prioritized Remaining Work

1. Fully separate delete-object and leave-access flows in backend routes, generated
   URLs, modals, and tests.
2. Refresh global-search Playwright tests for the current modal and stale-response
   handling.
3. Add runtime accessibility tests for share-page keyboard use, filter-panel ARIA
   state sync, and keyboard/touch group reparenting.
4. Add a migration-safety regression or explicit operator note for migration `0026`.
5. Run and record a clean-volume production Compose startup with real certificates and
   secrets.
6. Restore the latest off-host backup into a clean database and record the drill.
7. Add built-image secret scanning.
8. Tighten supply-chain pinning and CDN integrity according to the project's chosen
   policy.

## Closed Product Decisions

- Bulk sharing and permission management require `OWNER`.
- `EDITOR` users can edit objects but cannot share onward or mutate object
  permissions.
- Inherited group permission is treated as intended product behavior.
