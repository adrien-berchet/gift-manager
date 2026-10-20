---
name: loop-with-claude
description: Iteratively deliberate with Claude CLI on a specific technical decision, diagnosis, architectural change, or implementation plan until mutual consensus is reached before implementing changes. Use when asked to loop, consult, align, debate, or reach consensus with Claude on a problem, proposal, or plan.
---

# Loop with Claude

Iteratively deliberate with Claude via the Claude CLI on a specific technical decision, bug diagnosis, or implementation plan until mutual consensus is reached before making code changes.

This skill pairs the agent with Claude as an independent peer reviewer, pressure-testing diagnoses and proposals to prevent regressions, brittle test fixes, and architectural drift.

---

## Deliberation Workflow

```
1. Frame Problem & Proposal ──> 2. Summon Claude (Session Init) ──> 3. Evaluate & Deliberate (Loop) ──> 4. Consensus Reached ──> 5. Implement & Verify
```

---

## Phase 1: Invocation Setup & Environment

### 1. Claude Binary Discovery

Locate the target Claude executable in the following order of preference:
1. User-specified path (e.g. `/home/adrien/.local/share/claude/versions/2.1.304`).
2. Latest installed version under `~/.local/share/claude/versions/`.
3. Standard path `~/.local/bin/claude` or `which claude`.
4. Versioned cache under `~/.config/Claude/claude-code/<version>/claude`.

### 2. Environment Variables & Authentication

> [!IMPORTANT]
> If `ANTHROPIC_API_KEY` is present in the environment with an invalid or third-party token, Claude CLI will fail to authenticate with its local user subscription.
> Always prefix commands with `env -u ANTHROPIC_API_KEY` to ensure Claude uses its active local OAuth/subscription session:
> ```bash
> env -u ANTHROPIC_API_KEY <claude-bin> ...
> ```

### 3. Execution Permissions

Running the Claude CLI requires network access to Anthropic API endpoints. In tool-governed environments (e.g. Antigravity sandbox), execute commands with:
- `BypassSandbox: true`

### 4. Model and Effort Parameters

- **Model:**
  - Default: `--model opus` (or specific alias such as Opus 5.5 when available).
  - Alternative: `--model sonnet` when fast turnaround or lighter review is preferred.
- **Thinking / Effort:**
  - Default: `--effort high` for deep architectural analysis, bug diagnoses, and test failure reviews.
  - Alternatives: `medium`, `low`, or `max`.
- **Headless Mode:**
  - Always use `-p "<prompt>"` (or `--print`) for non-interactive execution.

### 5. Multi-Turn Session Management

To ensure conversational memory across multiple deliberation rounds without re-explaining the entire context:
1. Generate a UUID for the consultation session:
   ```bash
   SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
   ```
2. **Turn 1 (Initial consultation):**
   ```bash
   env -u ANTHROPIC_API_KEY <claude-bin> --session-id "$SESSION_ID" --model opus --effort high -p "<framing_prompt>"
   ```
3. **Turns 2..N (Subsequent deliberation turns):**
   ```bash
   env -u ANTHROPIC_API_KEY <claude-bin> --resume "$SESSION_ID" --model opus --effort high -p "<deliberation_prompt>"
   ```

---

## Phase 2: Deliberation Protocol

### Step 1: Frame the Initial Prompt

Construct a clear, self-contained prompt for Claude containing:
1. **Background & Symptom:** The exact user request, CI failure, or architectural goal.
2. **Evidence & Logs:** Exact stack traces, error output, or relevant code spans (with file paths and line numbers).
3. **Root Cause Analysis (RCA):** The mechanism explaining why the issue occurs or why the change is necessary.
4. **Proposed Plan:** Specific, actionable plan detailing files to modify and the proposed implementation.
5. **Call for Deliberation:** Explicitly prompt Claude:
   - Does it agree with the diagnosis and proposed plan?
   - What risks, edge cases, or unintended consequences does it identify?
   - If it disagrees, what specific alternative does it propose and why?

### Step 2: Turn 1 Consultation

Invoke Claude with `--session-id "$SESSION_ID"` and wait for the response to complete.

### Step 3: Critical Evaluation & Synthesis

Review Claude's response against the codebase reality:
- **Do not blindly defer or rubber-stamp:** Check whether Claude's observations match the real repository code and actual test behavior.
- **Identify high-value insights:** Claude often spots subtler underlying issues (e.g. identifying that dropped clicks stem from resize debounce races rather than slow animations, or that string-matching pseudo-elements can be normalized in JS rather than weakened in Python).
- **Determine alignment status:**
  - **Full Agreement:** Both agents agree on the diagnosis and the implementation details. Proceed directly to Phase 3.
  - **Divergence / Counter-Proposal:** Claude disagrees or suggests modifications that require further discussion or verification.

### Step 4: Deliberation Loop (Iterative Alignment)

If alignment is not yet reached:
1. Conduct any necessary local code checks or exploratory test runs to verify Claude's counter-proposal.
2. Formulate a focused response addressing the specific point of divergence:
   - Acknowledge accepted suggestions.
   - Present evidence (code snippets, test run results, DOM behavior) for any counter-arguments.
   - Propose an updated, synthesized plan.
3. Call Claude using `--resume "$SESSION_ID"`.
4. Repeat until both agents converge on an agreed plan.
5. **Safety Exit:** If after 4 turns genuine consensus cannot be reached, summarize the differing perspectives and present the trade-offs to the user for a decision.

---

## Phase 3: Implementation & Verification

Once mutual agreement is reached:
1. **Implement:** Apply the agreed changes cleanly, keeping modifications strictly scoped to the agreed plan.
2. **Verify:** Run all relevant checks:
   - Static analysis: `tox run -e lint` (or `pre-commit run --all-files`).
   - Unit & view tests: `tox run -e py311 -- <test_paths>`.
   - Browser / E2E tests: `tox run -e e2e -- <e2e_test_paths>`.
   - Cross-browser checks if relevant: `--browser firefox`, `--browser webkit`.
3. **Commit:** Create a clear commit following repository conventions (e.g. `commitlint` sentence-case format).
4. **Report:** Provide a concise summary to the user outlining:
   - The points agreed upon with Claude.
   - The implemented changes with clickable file links.
   - The verification test results.

---

## Example Deliberation Invocations

### Initial Consultation
```bash
SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
env -u ANTHROPIC_API_KEY /home/adrien/.local/share/claude/versions/2.1.304 \
    --session-id "$SESSION_ID" \
    --model opus \
    --effort high \
    -p "We are investigating a test failure in test_card_view_polish.py.

Error:
  assert field['label'] in field['before']
  AssertionError: {'before': '\"\uf075\u2002\" attr(data-label)', 'label': 'Comment'}

Analysis:
  Firefox 144 in CI serializes getComputedStyle(td, '::before').content literally.

Proposed Plan:
  Resolve attr() in JS helper before returning string to Python.

Do you agree with this plan or do you recommend an alternative?"
```

### Follow-up Deliberation Turn
```bash
env -u ANTHROPIC_API_KEY /home/adrien/.local/share/claude/versions/2.1.304 \
    --resume "$SESSION_ID" \
    --model opus \
    --effort high \
    -p "Your suggestion to normalize pseudo-element content via regex replace in JS works cleanly across all browsers.
    For the second issue regarding mobile orientation changes, your observation about the 250ms resize debounce race in grid-utils.js is accurate.
    Setting the viewport before navigation completely removes the race.
    We are aligned on both points. I will proceed with implementation."
```
