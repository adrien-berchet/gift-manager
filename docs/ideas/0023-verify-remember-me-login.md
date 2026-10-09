# Idea: Verify The Remember Me Login Checkbox

## Status

Proposed

## Summary

Check that the "Remember me" checkbox on the login page does what users expect,
and add automated tests that lock the behavior in. When the box is checked, the
session should persist across browser restarts for the configured session
lifetime. When it is unchecked, the session should end when the browser closes.

## Motivation

The login template renders django-allauth's `remember` field, but the only
existing test (`test_remember_checkbox_uses_bootstrap_class` in
`gift_manager/tests/test_authentication.py`) checks its CSS class, not its
effect. Nothing verifies that the checkbox changes the session cookie, so a
regression in the form, the template, the allauth configuration or the session
settings could go unnoticed. The app also does not set `ACCOUNT_SESSION_REMEMBER`
explicitly, so the behavior depends on allauth defaults.

## User Value

Users who sign in on a personal device stay signed in as expected, and users on
a shared device who leave the box unchecked are signed out when the browser
closes.

## Possible Scope

- Manually verify both cases in a browser: cookie lifetime in the checked case,
  session-only cookie in the unchecked case.
- Add tests that post the login form with and without `remember` and assert the
  session expiry (`request.session.get_expiry_age()` and
  `get_expire_at_browser_close()`, or the `Set-Cookie` attributes).
- Confirm the checkbox is rendered, labelled and keyboard-accessible on the login
  page, in English and French.
- Decide whether to set `ACCOUNT_SESSION_REMEMBER` explicitly in
  `GiftManager/settings/base.py` so the behavior does not depend on defaults,
  and fix anything found broken.

## Out Of Scope

- Changing the session lifetime (`SESSION_COOKIE_AGE`, currently 2 weeks in
  `GiftManager/settings/production.py`).
- Adding new login methods, two-factor authentication or token-based
  persistent login.
- Restyling the login page.

## Implementation Notes For AI Agent

Relevant code:

- `gift_manager/templates/account/login.html`: renders `form.remember` when the
  field exists.
- `GiftManager/settings/base.py`: allauth `ACCOUNT_*` settings;
  `production.py`: `SESSION_COOKIE_AGE`.
- `gift_manager/tests/test_authentication.py`: existing login page tests.
- Login tests need a user with a verified email, since
  `ACCOUNT_EMAIL_VERIFICATION` is `mandatory`.

Check the installed allauth version's documentation for `ACCOUNT_SESSION_REMEMBER`
and for how an unchecked box is handled before asserting expectations. Keep
translations current if any label changes.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- Relevant files under `gift_manager/`

## Acceptance Criteria

- Logging in with the box checked produces a session whose expiry matches the
  configured session lifetime.
- Logging in with the box unchecked produces a session that expires when the
  browser closes.
- Both cases are covered by automated tests that fail if the behavior changes.
- The checkbox is visible and labelled on the login page in both languages.
- Existing authentication tests keep passing.

## Dependencies Or Related Ideas

None identified.

## Open Questions

- Should the box be checked by default, or stay unchecked as it is now?
- Should `ACCOUNT_SESSION_REMEMBER` be set explicitly, or should the default
  prompt stay?
