# Reminder Emails And Calendar Feed

Users can opt in to a reminder digest email from their profile page, and enable a
private calendar (`.ics`) feed. The digest is sent by a management command that
must be run by a scheduler; the web process never sends it.

## Digest Email

```bash
python manage.py send_gift_digest
```

What the command does:

- Considers active users whose digest frequency is `daily`, plus the ones who chose `weekly`:
  on Mondays (local time, `TIME_ZONE`), and later in the week for the users who got no digest since
  that Monday (a missed run or a failed send). Someone who never got a digest waits for a Monday,
  so opting in on a Wednesday does not send anything before the next one.
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
- `--include-weekly`: send the digest of every weekly user, whatever the weekday.
- `--user USERNAME`: only consider one user (useful to test a deployment).

The day of the last digest sent is stored on the profile (`last_digest_sent_on`), so running the
command again on the same day only emails the users who did not get theirs yet. After a partial
failure (the command exits non-zero and logs the recipients that failed) just run it again.
Nothing is recorded for `--dry-run` or when there was nothing to report. The weekly catch-up
uses the same date: on a day other than Monday, a weekly user is due when their last digest is dated
before that week's Monday.

## Required Settings

- `SITE_BASE_URL`: public base URL without trailing slash, for example
  `https://gift.example.com`. Links in the email are built from it, and the command
  refuses to run without it. `docker-compose.prod.yml` passes it to the `web` service.
- `CRON_SECRET`: only for the Vercel Cron endpoint (see below).
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

On Vercel, where no management command can run, use the Vercel Cron job described below.

Check the scheduler once with `--dry-run`, then with `--user <you>` on an opted-in account.

### Vercel Cron

`vercel.json` declares a cron job that calls `GET /cron/send-gift-digest/` every day at
06:00 UTC. The endpoint runs the same code as the command (`gift_manager.digest_sending`).

Setup, in the Vercel project settings (Environment Variables, Production):

- `CRON_SECRET`: a random string of at least 16 characters (for example
  `openssl rand -base64 32`). Vercel sends it as `Authorization: Bearer <secret>` when it calls
  the endpoint. While it is unset or shorter than 16 characters the endpoint does not exist (404),
  and any call without the right secret gets a 401.
- `SITE_BASE_URL`: the public URL used in the emails (see above). Without it the endpoint answers 500.

Then deploy to production and check, in the Vercel dashboard:

1. Settings > Cron Jobs lists `/cron/send-gift-digest/`. If the deployment fails on the `crons`
   entry, the configuration is not accepted: report it rather than working around it.
2. Run it once from that page ("Run") and open "View Logs". A 200 with the counts
   (`sent`, `skipped`, `already_sent`, `failed`) is success. The response never contains user data.
   If you get a 400 `DisallowedHost`, add the host Vercel used (shown in the log) to `ALLOWED_HOSTS`.
3. To trigger it yourself, for example to test with an opted-in account:
   `curl -H "Authorization: Bearer $CRON_SECRET" https://<your-domain>/cron/send-gift-digest/`.

What to know:

- Cron expressions are in UTC, and cron jobs only run on the production deployment.
- On the Hobby plan, a daily job runs at some point during the scheduled hour (06:00 to 06:59 UTC),
  and nothing more frequent than daily is allowed. Pro runs it within the scheduled minute.
- Cron calls do not follow redirects, which is why the URL is outside the language prefix and ends
  with a slash. Do not put a redirect in front of it.
- The endpoint answers 500 when a recipient failed (and sends the others). Vercel does not retry:
  the failed users get their digest at the next run, the next day. To retry sooner, call the
  endpoint again with `curl` as above; users already sent today are skipped.
- Vercel delivery is best effort and can occasionally run a job twice. This is safe: the day of the
  last digest is claimed with a conditional database update before each email is sent, so a user
  gets at most one digest per day even when two runs overlap. A missed run is made up by the weekly
  catch-up, and daily subscribers just get their digest the next day.
- The digests of all users are sent one after the other in a single function call, so it is bound by
  the function duration limit of your Vercel plan. If it is not enough with many users, the digests
  that did not go out are sent by the next call (call the endpoint again), and the duration limit
  can be raised on a plan that allows it.
- Do not put the secret in the URL or in logs. Rotate it by changing the variable and redeploying.

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
