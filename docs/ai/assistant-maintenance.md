# Assistant Maintenance

This repository is intentionally optimized for AI-assisted development. Keep the
configuration small, shared, and enforceable where possible.

## File Responsibilities

- `AGENTS.md`: canonical shared instructions for Codex and other agents.
- `CLAUDE.md`: Claude Code loader file that imports `AGENTS.md` and adds Claude-only notes.
- `.codex/config.toml`: project-scoped Codex defaults and custom agent roles.
- `.codex/agents/*.toml`: Codex custom agent definitions.
- `.claude/settings.json`: shared Claude Code tool policy.
- `.claude/settings.local.json`: personal Claude Code permissions; ignored and not committed.
- `.claude/rules/*.md`: path-scoped Claude Code instructions.
- `.claude/skills/*/SKILL.md`: reusable Claude Code workflows.
- `.claude/agents/*.md`: Claude Code subagents.
- `docs/ai/*.md`: reference material that should not load into every session.

## Maintenance Rules

- Put durable project facts in `AGENTS.md`.
- Put long procedures, examples, and deep architecture notes in `docs/ai/`.
- Put path-specific behavior in `.claude/rules/`.
- Put repeatable multi-step workflows in skills.
- Put mechanical enforcement in settings, hooks, CI, or pre-commit rather than prose.
- Keep local paths, personal preferences, and broad permissions out of committed settings.

## When Agents Drift

1. Check whether the relevant startup file actually loads.
2. Remove duplicated or contradictory instructions.
3. Make the rule more specific and closer to the files it affects.
4. Add or update a test, hook, or CI check if the behavior must be enforced.
