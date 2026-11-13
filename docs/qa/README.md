# QA Passes

Browser QA passes of Gift Manager, run by AI agents with the `qa-pass` skill
(`skills/qa-pass/SKILL.md`). Each pass writes one report in this folder; the journeys to test
live in `scenarios.md`.

## Severity

- **Blocker**: data loss, security or privacy breach, or a main flow impossible.
- **High**: a main flow broken for some users, or wrong data shown.
- **Medium**: a flow works with a clear defect (unreadable text, misleading state, error page
  on a reachable link).
- **Low**: cosmetic or copy issues, rare edge cases.

## Finding IDs

Prefix by area and number them within the report: `R` for the feature under test, `A` for the
rest of the app, `N` for findings of a follow-up pass, `Q` for open product questions.

## Rules

- Report only; do not fix or commit during the pass.
- Never use the superuser to test access or sharing.
- Re-check every error alone before reporting it, and confirm saves in the database.
- Separate facts from product decisions.
- Record every piece of data the pass created, changed or deleted.

## Report Template

```markdown
# <Topic> QA report — <YYYY-MM-DD>

Branch / commit, environment (Docker, accounts used).

## Summary

Two or three sentences: overall state, blockers, most important findings.

## Scope and method

What was tested, how (scripts, browser scenarios, themes, widths, languages).

## Findings

| ID | Severity | Finding |
|----|----------|---------|

**<ID> — <title> (<severity>).** Steps or URL, expected vs actual, evidence, cause (file:line)
when known.

## Decisions needed

## Verified as working

## Test environment notes

## Data changed
```
