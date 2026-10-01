# Reminder Emails And Calendar Feed

Users can opt in to a reminder digest email from their profile page, and enable a
private calendar (`.ics`) feed. The digest is sent by a management command that
must be run by a scheduler; the web process never sends it.

## Digest Email

```bash
python manage.py send_gift_digest
```

What the command does:

- Considers active users whose digest frequency is `daily`, plus the ones who chose
  `weekly` when the command runs on a Monday (local time, `TIME_ZONE`).
- Sends at most one email per user and per run, in the language chosen on the profile
  (the site language by default), and nothing when there is nothing to report.
- Lists overdue plans, plans due within the user's lookahead (7, 14 or 30 days),
  upcoming birthdays (flagging the ones without a gift plan) and upcoming events that
  have no gift plan. For recurring events only the next occurrence is considered, and
  only yearly recurrences are listed; the other recurrences stay in the calendar feed.
- Only includes what the user can access at the time of the run.
- Adds `List-Unsubscribe` headers and an unsubscribe link (a signed link that turns the
  digest off without logging in).
- Skips users who already got today's digest, logs and counts a failing recipient, keeps going,
  and exits non-zero at the end.

Options:

- `--dry-run`: report how many digests would be sent, send nothing.
- `--include-weekly`: also send weekly digests when it is not Monday.
- `--user USERNAME`: only consider one user (useful to test a deployment).

The day of the last digest sent is stored on the profile (`last_digest_sent_on`), so running the
command again on the same day only emails the users who did not get theirs yet. After a partial
failure (the command exits non-zero and logs the recipients that failed) just run it again.
Nothing is recorded for `--dry-run` or when there was nothing to report. Weekly digests are only
due on Mondays: if the host is down on a Monday, weekly subscribers get nothing that week, unless you run the command once with
`--include-weekly`.

## Required Settings

- `SITE_BASE_URL`: public base URL without trailing slash, for example
  `https://gift.example.com`. Links in the email are built from it, and the command
  refuses to run without it. `docker-compose.prod.yml` passes it to the `web` service.
- The usual email settings (`EMAIL_HOST`, `DEFAULT_FROM_EMAIL`, ...).

## Scheduling

The command works from any plain scheduler. No task queue is needed.

systemd timer on a host that runs the Compose stack (the units mirror the backup units):

```bash
sudo install -m 0644 deploy/systemd/gift-manager-digest.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/gift-manager-digest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gift-manager-digest.timer
```

cron equivalent:

```cron
0 7 * * * cd /opt/gift-manager && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py send_gift_digest
```

Vercel deployments have no process to run management commands: use an external
scheduler that can run the command against the same database and settings.

Check the scheduler once with `--dry-run`, then with `--user <you>` on an opted-in account.

## Calendar Feed

- Each user can enable the feed from the profile page. It is disabled until then.
- The feed URL contains a secret token (`/<language>/calendar/<token>.ics`) and needs no login:
  anyone who has the URL can read the feed. Treat it like a password.
- "Generate a new link" replaces the token, which immediately invalidates the old URL.
  "Disable" removes it.
- The feed holds the user's open gift plans with a due date, scheduled events (with their
  repetition) and people's birthdays, restricted to what the user can access, in the
  language chosen on the profile. Calendar clients refresh it on their own schedule.
- The token is a bearer credential for the whole gift list of the user and is not rotated by a
  password reset or a sharing change: use "Generate a new link" when in doubt. It also travels in
  the URL path, so it shows in access logs and in Sentry request data when a request fails
  (`SENTRY_DSN`); restrict who can read those. The same goes for the signed unsubscribe link, which
  can only turn the digest off.
- Responses are sent with `Cache-Control: private, no-store`, `Referrer-Policy: no-referrer`
  and `X-Robots-Tag: noindex`. Avoid logging full request URLs in front proxies for this path.
