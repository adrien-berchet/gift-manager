@AGENTS.md

## Claude Code

- Keep this file Claude-specific. Shared project guidance belongs in `AGENTS.md`.
- Keep startup memory compact; detailed references belong in `docs/ai/` or `.claude/rules/`.
- Path-scoped Claude rules live in `.claude/rules/`.
- Project skills live in `.claude/skills/`.
- Project subagents live in `.claude/agents/`.
- Personal project preferences belong in `CLAUDE.local.md` or `.claude/settings.local.json`; do not commit them.
- Run `/context` when instructions look stale, and `/doctor` when Claude Code customizations behave unexpectedly.

Detailed historical notes from the old root guide are archived at
`docs/ai/legacy-claude-guide.md`.
