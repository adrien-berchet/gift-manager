# Idea: Reminders And Calendar Feed

## Status

Implemented

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

## Decisions

The operational runbook is `docs/operations/reminders.md`.

- **Birthdays are in the digest** (idea `0002` shipped first). They come from
  `build_upcoming_birthdays` with the user's lookahead as window and are flagged when no
  gift plan covers them yet.
- **Events without plans are in the digest**, but only the *next* occurrence of an event
  inside the lookahead window, and only one-time and yearly events (daily, weekly and
  monthly events would appear in every email; they stay in the calendar feed through an
  `RRULE`). An event counts as having a plan when the user can see a non-abandoned plan on it
  that is due within `PLAN_COVERAGE_DAYS` before the occurrence or on it, or an open plan
  without a due date, so a plan given for last year's occurrence never hides the next one.
- **Urgency rules are shared with the dashboard:** `_build_gift_plan_action_groups` takes a
  `due_soon_days` argument; the digest passes the user's lookahead (7, 14 or 30 days, default
  14) and uses its `overdue` and `upcoming` groups.
- **Preferences on `Profile`:** `digest_frequency` (`off` by default, `weekly`, `daily`),
  `digest_lookahead_days`, `preferred_language` (empty means the site language, used for the
  email and the feed) and `calendar_token`. The profile page edits them.
- **Scheduling:** the command is meant to run once a day from a plain scheduler (systemd timer
  units and a cron line are documented); weekly digests are sent on Mondays. No last-sent state
  is stored, so running it twice on the same day sends twice.
- **Links** are built from the `SITE_BASE_URL` setting, which the command requires.
- **Unsubscribe:** a signed link (`django.core.signing`, no login). GET asks for confirmation,
  POST turns the digest off; the POST is CSRF-exempt so it also serves RFC 8058 one-click
  unsubscribe (`List-Unsubscribe-Post`).
- **Calendar feed:** `/calendar/<token>.ics`, no login, all-day events for open plans with a
  due date, scheduled events and birthdays (yearly `RRULE`; February 29 falls on the last day
  of February). The token is stored as is, created when the user enables the feed, replaced by
  "Generate a new link" (the old URL then returns 404) and removed by "Disable".
- **No new production dependency:** the iCalendar document is serialized by
  `gift_manager/calendar_feed.py`; `icalendar` is only a test dependency used to parse it back.
- **Known limits:** no per-user send log (a failed run is retried by running the command again,
  which re-sends to users who already got it); the feed token is not hashed in the database;
  monthly events on days 29 to 31 follow the RFC 5545 rule of skipping months without that day
  in the calendar feed.
