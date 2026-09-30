# Idea: Reminders And Calendar Feed

## Status

Proposed

## Summary

Notify users about gift plans that need attention without requiring them to
open the app. First slice: an opt-in digest email listing overdue and due-soon
gift plans. Second slice: a per-user private `.ics` feed so due dates and
events show up in external calendars.

## Motivation

Everything the dashboard surfaces ("Overdue", "Due soon") is only visible when
the user visits. The only outbound email in the codebase is the friend
invitation (`send_mail` in `gift_manager/views/profile.py`). A gift planner that
cannot reach out before a due date loses most of its value.

## User Value

- Fewer missed occasions and last-minute purchases.
- Due dates live in the calendar the user already checks.
- Users control frequency and can opt out.

## Possible Scope

- Profile preferences: digest frequency (off, weekly, daily) and lookahead
  window, stored on `Profile`.
- A management command (for example `send_gift_digest`) designed to run from a
  scheduler (cron, platform scheduler), producing one email per user with
  overdue and due-soon plans, translated to the user's language.
- Per-user secret-token `.ics` URL listing due dates and scheduled events, with
  a way to regenerate the token.
- Unsubscribe link in the email.

## Out Of Scope

- Push notifications, SMS or in-app notification center.
- Two-way calendar sync.
- Introducing a task queue such as Celery; the command must work from a plain
  scheduler.

## Implementation Notes For AI Agent

- Reuse the dashboard bucket logic (`_build_gift_plan_action_groups` in
  `gift_manager/views/common.py`) instead of re-implementing urgency rules.
- `Profile` preferences live in `gift_manager/models.py`; the preferences form
  is in `gift_manager/views/profile.py` and
  `gift_manager/templates/gift_manager/profile_detail.html`.
- Existing management commands: `gift_manager/management/commands/`.
- Permissions: only include plans from `Relation.objects.accessible_by(user)`.
- Email content must not leak data for plans the user lost access to.
- Email addresses and some person data are encoded; see
  `gift_manager/email_encoding.py` before touching them.
- Translations must be activated per recipient when rendering.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/operations/`

## Acceptance Criteria

- A user can opt in or out of the digest from the profile page; default is off.
- The command sends at most one email per opted-in user per run and sends
  nothing when no plan qualifies.
- The email lists only accessible plans and is rendered in the user's language.
- The `.ics` feed validates in at least one standard calendar client and cannot
  be read without the token; regenerating the token invalidates the old URL.
- Tests cover selection, permission filtering, opt-out and token handling.

## Dependencies Or Related Ideas

- Benefits from birthdays (`0002`).

## Open Questions

- Which scheduler do production deployments use (see `docs/operations/`)?
- Should the digest include events without plans?
