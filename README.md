# Gift Manager

Gift Manager is a Django application for managing gifts, people, events, relations,
groups, tags, and sharing permissions.

## Quick Start

```bash
cp .env.example .env
pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver
```

Docker-based development:

```bash
docker compose up
docker compose exec web python manage.py migrate
```

### Seed Local Development Data

After running migrations, populate the local development database with sample data:

```bash
python manage.py seed_data
```

For Docker-based development:

```bash
docker compose exec web python manage.py seed_data
```

The command refuses to run if seed users, people, or gifts already exist. To reset
and reseed, add `--flush`; this deletes all Gift Manager data and non-superuser
accounts while preserving superuser accounts. Use it only on a disposable local
development database.

## Verification

```bash
tox run -e py311
tox run -e lint
tox run -e e2e
```

Use targeted tests while developing:

```bash
tox run -e py311 -- gift_manager/tests/test_permissions.py
tox run -e py311 -- -k "permission"
```

## AI-Assisted Development

This repository keeps shared AI assistant guidance in `AGENTS.md`.

- Claude Code imports `AGENTS.md` from `CLAUDE.md`.
- Codex reads `AGENTS.md` directly and uses `.codex/config.toml` when the project is trusted.
- Claude Code project rules, skills, and subagents live under `.claude/`.

See `docs/ai/assistant-maintenance.md` for maintenance conventions.
