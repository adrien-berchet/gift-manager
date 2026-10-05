# Architecture Notes For Assistants

## Boundaries

- Django project settings live in `GiftManager/settings/`.
- Application code lives in `gift_manager/`.
- Domain views are split under `gift_manager/views/`.
- Reusable view behavior lives in `gift_manager/views/base.py` and `gift_manager/mixins/`.
- Template partials live in `gift_manager/templates/gift_manager/includes/`.
- Static JavaScript lives in `gift_manager/static/gift_manager/`.
- Tests live in `gift_manager/tests/`, with browser tests under `gift_manager/tests/e2e/`.

## Patterns

- Use `PermissionService` and the permission facade for object access decisions.
- Keep permission inheritance logic centralized.
- Preserve group and tag hierarchy cycle protection.
- Prefer model/query helpers for reusable data access.
- Keep HTMX responses partial-aware and normal requests full-page-aware.
- Keep form validation in forms or services, not templates or ad hoc JavaScript.
- Keep UI changes compatible with existing Bootstrap, HTMX, and Grid.js conventions.
- Occasions derived from data (person birthdays) are computed, never stored as `Event` rows; see
  `gift_manager/birthdays.py` and `Person.next_birthday`.
- `Event.is_global` events (the Birthday event) are visible to every user with a VIEWER floor
  (`EventQuerySet.accessible_by`, `PermissionService.get_effective_permission`). Sharing code that
  cascades a plan's access to its event must go through `SharingService.needs_cascade_grant`.
  Its stored name is English; reading `Event.name` translates it (`EventNameField`), so code reading
  names straight from the database (`values()`) must translate with `event_display_name`.
- Reminders: `gift_manager/reminders.py` builds the digest email content (reusing the dashboard
  buckets and `build_upcoming_birthdays`) and `gift_manager/calendar_feed.py` serializes the private
  `.ics` feed. Both read through `accessible_by(user)` and render in `Profile.language`. The digest is
  sent by `gift_manager/digest_sending.py`, run by `manage.py send_gift_digest` from a plain scheduler or
  by the Vercel Cron endpoint `/cron/send-gift-digest/`; see `docs/operations/reminders.md`.
- Duplicating a plan and "Plan again" (recreating a repeating event's last occurrence as `Idea`
  plans, Birthday event included) live in `gift_manager/plan_repeat.py`; copies are owned by the
  creating user only and never carry reactions or sharing.
- Plan coordination: `gift_manager/plan_coordination.py` holds the claim, release, comment and
  surprise-flag rules on top of `PermissionService`; views in `views/plan_coordination.py` look plans
  up through `accessible_by` (404, never 403, for users who cannot see a plan). A surprise plan
  (`Relation.is_surprise`) is hidden from its recipient, and from every member of a targeted group
  (nested groups included), inside `RelationQuerySet.accessible_by`; users who own the plan are never
  hidden. Code that reads plans outside `accessible_by` (prefetches, reverse accessors, counts) must
  use `Relation.objects.hidden_surprises_for(user)` or go through `accessible_by`;
  `tests/test_surprise_surfaces.py` pins every surface. Losing access to a plan (the
  `RelationPermission` row is deleted) releases the claim the user held.

## Risk Areas

- Permission changes can create privacy regressions. Test owner, editor, viewer, and no-access paths.
- Hierarchy changes can create stale caches or cycles.
- Grid.js and JSONB-related queries need PostgreSQL.
- E2E tests depend on live-server behavior, static assets, and Playwright browser setup.
- User-facing strings need translation updates.
