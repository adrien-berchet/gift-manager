---
name: deep-code-review
description: Perform a deep, read-only code review of a branch, pull request, or merge candidate against a base branch. Analyzes diffs, runs static analysis and targeted test suites, inspects code across multiple dimensions (correctness, regressions, security, CSS/responsive styling, accessibility, localization, and repository documentation conventions), and produces a structured, prioritized report with clickable file links. Use whenever asked to review code, PRs, branches, or merge candidates.
---

# Deep Code Review

Perform a thorough, multi-dimensional code review of a git branch or pull request before it is merged into the base branch.

This review process is **strictly read-only**: the reviewer analyzes code, runs verification checks, and produces a structured findings report. It does not modify source files during the review unless explicitly asked by the user in a subsequent step.

---

## Review Workflow

```
1. Scope & Diff Analysis ──> 2. Automated Verification ──> 3. Multi-Dimensional Deep Inspection ──> 4. Prioritized Report ──> 5. (Post-Fix) Re-Verification
```

---

## Phase 1: Scope & Diff Analysis

1. **Identify the Comparison Base:**
   - Default to `main` (or the repository's default branch `git symbolic-ref refs/remotes/origin/HEAD`) unless the user explicitly specifies a different base branch.
   - Run `git rev-parse --abbrev-ref HEAD` to identify the current branch.
   - Run `git log --oneline <base>..HEAD` to review the commit history and intent.

2. **Inspect Changed Files & Diff:**
   - Run `git diff --stat <base>...HEAD` to understand the blast radius and touch points.
   - Run `git diff <base>...HEAD` (or targeted file diffs) to inspect every change in detail.

3. **Maintain Read-Only Posture:**
   - Do not make source code changes during the review phase.
   - If tests or linters fail, record the diagnostic output as findings rather than attempting unrequested edits.

---

## Phase 2: Automated Verification & Diagnostics

1. **Discover Project Verification Commands:**
   - Check repository instructions (e.g. `AGENTS.md`, `README.md`, `docs/`, `CONTRIBUTING.md`).
   - Identify linters, static analyzers, and test runners (e.g. `tox`, `pre-commit`, `ruff`, `flake8`, `pytest`, `npm test`, `cargo check`).

2. **Run Linters & Static Analysis:**
   - Execute the project's linter suite (e.g. `tox run -e lint` or `pre-commit run --all-files`).
   - Check line length constraints, import ordering, unused variables, typing issues, and formatting.

3. **Environment-Aware Test Execution:**
   - Check whether dependencies (Docker containers, databases, cache servers) require specific configurations or ports (e.g. checking running containers via `docker ps` for custom mapped ports like `DB_PORT=5433`).
   - Run targeted test suites closest to the changed surface first (e.g. unit tests, view tests, template tags).
   - If UI/browser changes are involved, run end-to-end / Playwright tests across mobile and desktop viewports.

4. **Failure Handling (Option A: Continue & Record):**
   - If any linter or test command fails, **do not halt execution**.
   - Capture the command output and traceback.
   - Record the failure as a **Blocker** in the report and proceed with deep code inspection.

---

## Phase 3: Multi-Dimensional Deep Inspection

Examine the diff across each of the following dimensions:

### 1. Correctness & Business Logic
- **Edge cases & boundaries:** Off-by-one errors, empty querysets, zero values, null/None handling.
- **Cycles & Recursion:** Tree/graph modifications (e.g. parent/child relationship cycles, infinite loops).
- **Security & Authorization:** Permission checks, authentication gating, cross-tenant data leaks, CSRF protection, URL validation.
- **Data Integrity:** Database transactions, migration compatibility, unique constraints.

### 2. Styling, CSS Cascading & Responsive Layout
- **CSS Specificity Clashes:**
  - Check whether global or attribute-scoped styles (such as `[data-theme="dark"] a:not(.btn)`) inadvertently override component-level classes (e.g. active tab colors, custom button states).
  - Verify that dark mode (`[data-theme="dark"]`) provides sufficient color contrast between active and inactive states.
- **Box Model & Fluid Sizing:**
  - Look for hardcoded pixel widths (`width: 400px`) that cause horizontal overflow on small screens (e.g. 320px–360px phones) or awkward gaps on wider screens (e.g. 430px phones, 768px+ tablets).
  - Verify that modal/offcanvas sheets and sticky bars use fluid widths (`width: 100%`) or responsive max-widths.
- **Device Safe Areas & Notches:**
  - When `viewport-fit=cover` is present, check that fixed headers, bottom bars, and sheets set both vertical and horizontal safe-area insets (`env(safe-area-inset-bottom)`, `env(safe-area-inset-left)`, `env(safe-area-inset-right)`) so items are not clipped in landscape orientation.
- **Progressive Enhancement:**
  - Verify that critical layouts do not hide essential content when JavaScript is disabled or loading (e.g. provide CSS fallback padding for fixed bottom/top navigation bars).
- **Print Styles:**
  - Ensure fixed navigation bars, action sheets, and toggles are hidden in `@media print`.

### 3. Accessibility (a11y) & Semantic HTML
- **Landmark Labelling:**
  - When multiple landmarks of the same type exist (e.g. top `<nav>` and mobile bottom `<nav>`), ensure each has a unique, descriptive `aria-label`.
- **Keyboard Navigation & Focus States:**
  - Ensure all interactive elements have visible `:focus-visible` outlines.
  - Verify focus restoration when dialogs, modals, or offcanvases close.
  - Check that clickable list items provide adequate touch target sizes (at least 44x44px or 48px height) and touch/hover feedback.
- **State Indicators:**
  - Use `aria-current="page"` on active navigation links.
  - Ensure `aria-expanded`, `aria-controls`, and `aria-hidden` attributes reflect live state accurately.

### 4. Localization & Internationalization (i18n)
- **String Coverage:**
  - Ensure all user-facing strings in templates, forms, and JavaScript are marked for translation (e.g. `{% trans %}`, `gettext`, `_()`).
  - Check that translation catalogs (e.g. `locale/<lang>/LC_MESSAGES/django.po`) include the new msgids and corresponding compiled binaries (`.mo`) are updated if required by the repo.
- **Layout Tolerance:**
  - Verify that UI controls (e.g. segmented button groups, tab bars) don't overflow when rendered in languages with longer average string lengths (e.g. French, German).

### 5. Architecture, Modularity & DRY
- **Clean Abstractions:**
  - Replace repetitive multi-condition checks in templates or views with clean, centralized helpers (e.g. custom template tags, model methods, or service functions).
  - Keep business logic in services or model helpers, not in templates.
- **Consistency:**
  - Follow existing patterns in the codebase rather than introducing conflicting architectural styles.

### 6. Repository Documentation & Contribution Conventions
- **Process & Lifecycle Tracking:**
  - If the project tracks proposals, ideas, or RFCs (e.g. `docs/ideas/`), verify that completed items have their status updated and are moved to their respective lifecycle directories (e.g. `implemented/` or `archived/`), and that central registries are kept synchronized.
- **Documentation Integrity:**
  - Preserve unrelated comments and docstrings. Update relevant documentation if public APIs or developer workflows changed.

---

## Phase 4: Structured Reporting Format

Deliver a structured review report organized by severity:

```markdown
## Code Review: `<branch-name>` vs `<base-branch>`

### Summary & Verdict
- **Verdict:** [Ready to Merge | Changes Requested | Informational]
- Brief summary of the changes and overall quality.

---

### 1. Blockers (Must Fix Before Merge)
Issues that prevent a safe merge:
- Failing CI checks, linters, or broken builds.
- Critical regressions, security flaws, or breaking bugs.

### 2. High-Priority Correctness & Visual Regressions
- Broken layouts across common devices / viewports (e.g. 320px phone or tablet).
- Dark/light mode contrast losses or severe CSS specificity clashes.
- Incomplete authorization or unhandled runtime exceptions.

### 3. Medium-Priority Functional & Architecture Findings
- Incomplete route/state matching.
- Missing keyboard/accessibility attributes or focus indicators.
- Repository convention gaps (e.g. RFC/idea lifecycle moves).
- Duplicate logic that should be unified.

### 4. Minor Improvements & Polish
- Print stylesheet exclusions.
- Progressive enhancement fallbacks.
- Micro-interactions, icon alignment, or touch-feedback styling.

---

### 5. Test Suite & Verification Results
- Summary of executed checks (linting, unit tests, e2e browser tests, i18n coverage) with runtimes and outcomes.
- Any missing tests that should be added to prevent future regressions.
```

*Note on file references:* Always format all file paths and symbols as clickable markdown links using the `file://` scheme (e.g. `[filename.py](file:///path/to/filename.py#L10-L25)`).

---

## Phase 5: Post-Fix Re-Verification

When the user or author applies fixes addressing the review findings:
1. Re-inspect `git status -s`, `git log`, and `git diff` against the base branch.
2. Re-run linters and static checks (`tox run -e lint` or equivalent).
3. Re-run affected unit tests and end-to-end browser suites.
4. Verify that each finding was addressed accurately and no new regressions were introduced.
5. Provide a final verdict on whether the branch is now ready to merge.
