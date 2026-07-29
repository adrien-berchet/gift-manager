---
description: Run and summarize targeted verification for a Gift Manager change. Use when the user asks to test, verify, or check a local change.
allowed-tools: Bash(rtk tox run:*), Bash(tox run:*), Bash(rtk python manage.py check:*), Bash(python manage.py check:*)
---

# Verify Change

1. Identify the changed files and choose the smallest relevant check.
2. Prefer targeted tox runs before broad suites.
3. Run `python manage.py check` when Django configuration, models, forms, or views changed.
4. Run `tox run -e lint` when Python code, formatting, imports, or documentation changed.
5. Summarize commands run, pass/fail status, and any remaining risk.
