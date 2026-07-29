---
paths:
  - "gift_manager/tests/**/*.py"
  - "tox.ini"
  - "pyproject.toml"
  - ".github/workflows/**/*.yml"
---

# Testing Rules

- Prefer targeted tests before broad suites.
- Use tox commands from `AGENTS.md` and `docs/ai/testing.md`.
- Keep report paths aligned with `tox.ini`.
- Use PostgreSQL for Grid.js, JSONB, permission, and e2e work.
- Mark browser tests with the existing frontend/e2e/mobile markers.
