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

## Risk Areas

- Permission changes can create privacy regressions. Test owner, editor, viewer, and no-access paths.
- Hierarchy changes can create stale caches or cycles.
- Grid.js and JSONB-related queries need PostgreSQL.
- E2E tests depend on live-server behavior, static assets, and Playwright browser setup.
- User-facing strings need translation updates.
