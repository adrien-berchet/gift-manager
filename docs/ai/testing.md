# Testing Notes For Assistants

## Targeted Checks

Use the smallest check that covers the change first:

```bash
tox run -e py311 -- gift_manager/tests/test_permissions.py
tox run -e py311 -- gift_manager/tests/views/test_base.py
tox run -e py311 -- -k "permission"
tox run -e lint
```

Browser/UI behavior:

```bash
tox run -e e2e -- gift_manager/tests/e2e/test_crud_workflows.py
tox run -e e2e-mobile
tox run -e py311-playwright
```

## Direct Django Checks

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Database Notes

- `GiftManager.settings.testing` is the default pytest settings module.
- PostgreSQL is recommended for all integration, Grid.js, JSONB, permission, and e2e work.
- SQLite fallback is only for quick local checks that do not depend on PostgreSQL behavior.

## Coverage And Reports

tox writes reports under `reports/`, including:

- `reports/coverage-<env>.xml`
- `reports/coverage-<env>/`
- `reports/pytest-<env>.xml`
- `reports/pytest-<env>.html`

Do not rely on root-level `coverage.xml`, `htmlcov/`, or `test-results.xml`
unless a workflow explicitly creates them.
