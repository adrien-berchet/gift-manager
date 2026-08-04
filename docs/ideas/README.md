# Future Improvement Ideas

This folder stores independent ideas for future Gift Manager improvements.
Each idea lives in its own Markdown file so it can be discussed, refined,
implemented, archived, or ignored without changing the meaning of other ideas.

The main audience is a future human or AI agent implementing one idea at a
time. A good idea file should be self-contained enough that an agent can start
from that file, then inspect only the referenced code and documentation.

## Folder Structure

```text
docs/ideas/
  README.md
  template.md
  0001-example-idea.md
  archived/
  implemented/
```

- Active ideas stay directly in `docs/ideas/`.
- Implemented ideas move to `docs/ideas/implemented/`.
- Ideas that are no longer wanted move to `docs/ideas/archived/`.
- `template.md` is copied when creating a new idea.

## Naming

Use this format:

```text
NNNN-short-kebab-case-title.md
```

Keep IDs stable. Do not renumber files when ideas move, merge, or get archived.
When creating a new idea, scan active, implemented, and archived idea files,
then use the next unused number.

## Status Values

- `Proposed`: captured, but not yet evaluated.
- `Considering`: interesting, but needs product or technical shaping.
- `Ready`: detailed enough for an implementation agent to start.
- `Implemented`: shipped or otherwise completed.
- `Archived`: intentionally deferred or no longer relevant.

## Index

This index is the stable registry for all idea IDs, including active,
implemented, and archived ideas. Keep rows when moving idea files, and update the
status and notes to reflect the move.

| ID | Idea | Status | Area | Notes |
| --- | --- | --- | --- | --- |

## Working With Ideas

When adding a new idea:

1. Pick the next unused ID across active, implemented, and archived ideas.
2. Copy `template.md` to a new `NNNN-short-kebab-case-title.md` file.
3. Fill in enough context for the idea to stand alone.
4. Add a row to the index above.
5. Keep acceptance criteria concrete and testable where possible.

When preparing an idea for AI implementation:

1. Move the status to `Ready`.
2. Add code areas and project docs the agent should inspect.
3. Make out-of-scope items explicit.
4. Add open questions only if they do not block the first implementation slice.
