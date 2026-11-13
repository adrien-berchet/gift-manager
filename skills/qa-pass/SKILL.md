---
name: qa-pass
description: Run a browser QA pass of Gift Manager against the local Docker app as one or several users, before a release or after a feature, and write a findings report in docs/qa/. Use when asked to QA, test the app in a browser, do a pre-release check, or verify a feature end to end. Report-only: fixes are a separate step.
---

# QA Pass

Test the running app like a user, find what is broken, and write a report a human can decide
on. Do not fix anything during the pass and do not commit, unless the user asks.

Read `docs/qa/README.md` (report format, severity, rules) and `docs/qa/scenarios.md`
(journeys per feature) before starting.

## 1. Prepare

1. Check the stack: `docker ps` shows the web container, and
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/accounts/login/` returns 200.
   If not, ask the user to run `docker compose up`.
2. Serve the current code: `docker exec <web> python manage.py collectstatic --noinput`, and
   restart the web container after a `.mo` change.
3. Data: the pass changes data. Ask before resetting it with
   `docker exec <web> python manage.py seed_data --flush`.
4. Accounts (seed): `alice` / `alice_password`, `bob` / `bob_password` (ordinary users),
   `testuser` / `testpass123` (**superuser**: it bypasses most permission checks, so never use
   it to test access or sharing). Check friendships and sharing with the Django shell before
   relying on them.
5. Never run `tox` test suites during the pass: they share the test database with Playwright and
   corrupt each other's runs.

## 2. Scope

1. `git diff --stat main...HEAD` and the commit messages: changed features get the full
   journeys from `docs/qa/scenarios.md`, plus new ones you add there.
2. Everything else gets the automated checks and a short smoke test of each main page.
3. Agree a time budget with the user for long passes.

## 3. Automated checks

Run them one at a time, from the repository root:

```bash
python3 skills/qa-pass/scripts/crawl.py alice bob --langs en fr
python3 skills/qa-pass/scripts/cross_user_access.py alice bob --names "<private names>"
.tox/e2e/bin/python skills/qa-pass/scripts/ui_checks.py alice /en/ /en/profile/received-gifts/ \
    --contrast ".future-date-warning" --shots <scratch dir>
```

- Re-request every 500 alone before reporting it: under parallel requests, the debug toolbar
  raises `RuntimeError: dictionary changed size during iteration`, which is not an app bug.
  Read the traceback with `docker logs --since 5m <web>`.
- A 200 from `cross_user_access.py` is a lead, not a finding: open the page and check whether
  it shows anything the visitor should not see.
- Also try bad input by hand on changed forms and URLs: `javascript:` links, out-of-range
  numbers and dates, other users' ids in query parameters, very long text, `<script>` text.

## 4. Browser scenarios

- Prefer Playwright scripts (`.tox/e2e/bin/python`) with one browser context per user, so two
  users can act in the same scenario. Hide `#djDebug`: it intercepts clicks.
- The Claude in Chrome extension also works for exploratory checks. If it stops delivering
  clicks or key presses (no event reaches the page), switch to Playwright instead of retrying.
- Check light and dark themes (`document.documentElement.setAttribute('data-theme', 'dark')`,
  then wait about half a second: colours transition) and a 390 px phone width for every
  changed screen.
- After any action that saves through a side panel or modal, check the page around it updated
  without a reload, and check the result in the database (`docker exec <web> python manage.py
  shell -c "..."`): a success toast does not prove the server received the right data.
- Keep screenshots of each finding.

## 5. Report

Write `docs/qa/<date>-<topic>.md` from the template in `docs/qa/README.md`:

- one ID per finding, a severity, exact steps or URL, expected vs actual, evidence, and the
  file and line when you found the cause;
- what you verified as working;
- "Decisions needed": anything that is a product choice rather than a bug;
- test environment notes and every piece of data you created or deleted.

Then tell the user the headline, the decisions needed, and where the report is.

## 6. After the pass

Fixes happen in a separate step the user starts: tests first, then the fix, then a peer
review (for example with the `loop-with-claude` skill), then a commit. Re-run the affected
journeys on the live app before calling a fix done, and add the journey to
`docs/qa/scenarios.md` if it was missing.
