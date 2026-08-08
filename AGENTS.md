# AGENTS.md

Shared instructions for AI-assisted work on Gift Manager.

## Project Snapshot

Gift Manager is a Django application for managing gifts, people, events, relations,
groups, tags, and sharing permissions.

Primary stack:

- Django 5.1, PostgreSQL, django-allauth, django-modeltranslation.
- Bootstrap, HTMX, Grid.js, and vanilla JavaScript.
- pytest, tox, Playwright, ruff, pre-commit, and GitHub Actions.

Useful references:

- Detailed historical Claude guide: `docs/ai/legacy-claude-guide.md`.
- Assistant maintenance notes: `docs/ai/assistant-maintenance.md`.
- Architecture notes: `docs/ai/architecture.md`.
- Testing notes: `docs/ai/testing.md`.

## Shared Agent Skills

- Canonical cross-agent skills live under `skills/`.
- When asked to add or document a future improvement idea, read and follow
  `skills/add-idea/SKILL.md`.
- Agent-specific discovery entries may link to a canonical skill. Keep the
  canonical skill as the single source of truth rather than copying it.

## Working Rules

- Read the relevant code before changing it. Prefer existing local patterns over new abstractions.
- Keep changes scoped to the requested behavior. Do not refactor unrelated code.
- Preserve user work. Do not revert changes you did not make.
- Use `rg` for search and targeted file reads for context.
- In Codex shell sessions for this repo, prefix shell commands with `rtk` when available.
- Use `apply_patch` for manual file edits.
- Ask clarification only when a safe, reasonable assumption is not possible.

## Implementation Flow

- For non-trivial implementation work, use one focused reviewer, code-reviewer, or
  architect-reviewer subagent when the tool is available. Keep the delegated task
  read-only unless its write set is explicitly disjoint.
- Prefer narrow implementation slices and targeted verification.
- When adding behavior, add or update tests close to the changed surface.
- Do not add production dependencies without a clear reason and user-visible note.

## Verification

Prefer targeted checks before broader suites:

```bash
tox run -e py311 -- gift_manager/tests/path/to/test_file.py
tox run -e py311 -- -k "keyword"
tox run -e lint
tox run -e e2e -- gift_manager/tests/e2e/path_to_test.py
```

Use PostgreSQL for work involving Grid.js queries, JSONB, permissions, or e2e
tests. SQLite is only acceptable for quick local model-level checks.

Common commands:

```bash
python manage.py check
python manage.py migrate
python manage.py makemigrations
python manage.py runserver
python manage.py makemessages -l fr
python manage.py compilemessages
docker compose up
docker compose exec web python manage.py migrate
```

## Architecture Notes

- Keep business rules in services or model/query helpers, not templates.
- Use `PermissionService` and the permission facade instead of duplicating access logic.
- Group and tag hierarchies need cycle checks and cache invalidation.
- HTMX views should return partial templates for HTMX requests and full templates for normal requests.
- Template partials live in `gift_manager/templates/gift_manager/includes/`.
- Static JavaScript lives under `gift_manager/static/gift_manager/`.
- Keep translations current for user-facing strings.

## Frontend Notes

- Match the existing Bootstrap/HTMX/Grid.js style.
- Preserve progressive enhancement: forms and core flows should work without custom JavaScript when practical.
- Do not put feature explanations or keyboard shortcut documentation into the UI unless the user asks.
- Verify mobile and e2e-sensitive UI changes with Playwright when behavior or layout changes.

## Security And Data

- Never commit or expose `.env`, private keys, certificates, production secrets, or real user data.
- Treat `.env.example` as documentation only.
- Do not read or edit `.git/`, generated reports, local media, or secret files unless explicitly asked.
- Avoid broad shell permissions in assistant config. Prefer command-specific allow rules.
- Review generated migrations before committing them.

## Review Defaults

When asked to review a PR, branch, or merge candidate:

- Compare against `main` unless another base is specified.
- Start read-only.
- Lead with correctness, security, regression, and missing-test findings.
- Do not make source changes during review unless explicitly asked.
