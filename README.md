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
