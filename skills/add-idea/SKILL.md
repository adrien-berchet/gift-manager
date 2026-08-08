---
name: add-idea
description: Create a new Gift Manager improvement idea in `docs/ideas/` from the repository's `docs/ideas/template.md` and register it in `docs/ideas/README.md`. Use when a user asks to capture, propose, document, or add a future product or technical idea for this repository.
---

# Add Idea

Create one self-contained idea document and keep the idea registry consistent.

## Gather The Idea

1. Read `docs/ideas/README.md` and `docs/ideas/template.md` before writing.
2. Inspect relevant project documentation or code only when needed to make the idea accurate and actionable.
3. Derive the title, motivation, user value, scope boundaries, and acceptance criteria from the request.
4. Ask focused questions when missing information would materially change the idea. Otherwise, make conservative assumptions and record unresolved details under `Open Questions`.

Do not implement the idea. This workflow only captures it unless the user explicitly requests implementation separately.

## Allocate The Idea ID

1. Extract IDs only from Markdown filenames matching `NNNN-*.md` directly under `docs/ideas/`, `docs/ideas/implemented/`, and `docs/ideas/archived/`.
2. Extract IDs independently from data rows in the index table in `docs/ideas/README.md`; treat the index as a first-class registry.
3. Stop before writing and report the exact inconsistency if an ID is duplicated among files, duplicated among index rows, present in a file but absent from the index, or present in the index but absent from all scanned files. Do not repair existing inconsistencies unless the user requests it.
4. Choose one greater than the highest ID found across both sources, starting with `0001` when neither contains an ID.
5. Never reuse or renumber an ID.
6. Create a concise kebab-case slug and name the file `NNNN-short-title.md`.

## Write The Idea

1. Copy the current structure and heading order from `docs/ideas/template.md`; do not rely on a remembered or bundled copy.
2. Replace every placeholder with content specific to the idea. Remove placeholder examples.
3. Default the status to `Proposed`. Accept `Considering` or `Ready` when explicitly requested. Do not create a new idea as `Implemented` or `Archived`; those statuses belong to the later lifecycle moves described in the README.
4. Make the summary understandable without the original conversation.
5. Separate likely first-slice scope from explicit out-of-scope boundaries.
6. Point implementation notes to concrete, relevant code areas, documentation, patterns, services, templates, or tests. Do not invent paths or behavior; inspect uncertain references first.
7. Write observable, testable acceptance criteria, including regression and verification expectations where relevant.
8. Use `None identified.` when dependencies or open questions are genuinely absent rather than leaving placeholders.

## Update The Registry

Add exactly one row to the index table in `docs/ideas/README.md`:

```text
| NNNN | Human-Readable Title | Status | Area | Brief note |
```

Keep the title and status consistent with the idea file. Choose a short, existing project area when possible. Keep the note concise and useful; do not remove or reorder existing rows.

## Verify

1. Confirm the ID is unique across active, implemented, and archived files and the README index.
2. Confirm the filename matches `NNNN-short-kebab-case-title.md`.
3. Compare the new file's headings and order with the current template.
4. Search for leftover template placeholders and resolve all of them.
5. Review the diff to ensure only the new idea file and the README index changed unless the user requested more.
6. Report the created file, allocated ID, status, and any assumptions or open questions.
