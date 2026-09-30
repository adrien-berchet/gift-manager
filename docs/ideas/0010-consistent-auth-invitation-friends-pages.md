# Idea: Consistent Login, Invitation And Friends Pages

## Status

Proposed

## Summary

Bring the pages that still look unfinished in line with the rest of the app:
the login page, the send-invitation page and the friends section of the
profile.

## Motivation

- `registration/login.html` renders `{{ form.as_p }}` and has an untranslated
  "Login" button.
- `gift_manager/send_invitation.html` is a bare card with one field and does not
  use the shared form components introduced by the unified form system.
- The friends list in `profile_detail.html` is a plain table, and removing a
  friend deserves a clearer confirmation.

These are first-touch pages for new users and for the friend-sharing flow.

## User Value

- Better first impression and trust at sign-in.
- Clearer invite flow with feedback on what happens after sending.
- Less risk of removing a friend by mistake.

## Possible Scope

- Restyle login using the shared field and error partials
  (`includes/forms/field.html`, `includes/forms/errors.html`).
- Redesign send-invitation with validation feedback, success message and a
  list of pending invitations.
- Friends list as cards or a responsive list with a confirmation modal on
  removal.

## Out Of Scope

- Changing authentication backends or allauth behaviour.
- Social login changes.

## Implementation Notes For AI Agent

- Allauth templates are customised under `gift_manager/templates/account/` and
  `gift_manager/templates/allauth/`; keep them consistent.
- `Invitation` model and views: `gift_manager/models.py`,
  `gift_manager/views/profile.py`.
- Use the existing delete-confirmation modal pattern for friend removal.
- Preserve non-JavaScript fallbacks.

Recommended starting context:

- `docs/ai/testing.md`
- `gift_manager/tests/test_authentication.py`

## Acceptance Criteria

- Login, invitation and friends pages use shared form components and are usable
  on mobile and with the keyboard.
- All strings are translated.
- Removing a friend requires confirmation.
- Existing authentication and invitation tests pass.

## Dependencies Or Related Ideas

- Shares the confirmation pattern with `0018`.

## Open Questions

- Should pending invitations be cancellable?
