# Idea: Installable PWA Or Removal Of Dead Offline Code

## Status

Implemented

Resolved with Option B: `offline-sync.js` and `offline-forms.js` (about 1,760
lines, never loaded by any template) were removed. No other code referenced
them. An installable PWA can still be proposed later as a separate idea.

## Summary

Resolve the half-finished offline work. Either ship a real installable
Progressive Web App (web manifest, service worker, offline fallback page,
"add to home screen"), or delete the unused offline code.

## Motivation

`gift_manager/static/gift_manager/js/offline-sync.js` and `offline-forms.js`
describe a "Gift Manager PWA" and reference a service worker and an
`/<lang>/api/auth/status/` endpoint, but no template loads them, no service
worker or manifest exists in the repository, and the endpoint could not be
confirmed. The code is dead weight and misleads contributors, while a
gift-planning app used in shops is a natural fit for an installable mobile app.

## User Value

- PWA option: install on the home screen, faster loads, graceful offline page.
- Removal option: a smaller, honest codebase.

## Possible Scope

Option A (PWA):

- `manifest.webmanifest`, icons and theme colour; link in `base.html`.
- Service worker caching static assets and an offline fallback page; no
  caching of authenticated HTML or API data in the first slice.
- Install prompt guidance only where appropriate.

Option B (cleanup):

- Remove `offline-sync.js`, `offline-forms.js`, related CSS, tests and docs.

## Out Of Scope

- Offline editing with background sync and conflict resolution (large, needs
  its own idea).
- Push notifications (see `0003`).

## Implementation Notes For AI Agent

- Check `gift_manager/static/gift_manager/js/`, `gift_manager/tests/` and
  `gift_manager/templates/gift_manager/fallback/` for references before
  deleting.
- The service worker must be served from the site root scope; check the URL
  configuration in `GiftManager/urls.py` and static file handling in
  `nginx.conf` and `vercel.json`.
- Never cache responses containing user data or CSRF tokens.
- Remove the hidden debug override mentioned in `docs/ux-roadmap.md` if any
  trace remains.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/operations/`

## Acceptance Criteria

- Option A: Lighthouse reports the app as installable, the offline page shows
  when the network is down, and authenticated pages are not cached.
- Option B: no references to removed files remain; the test suite passes.
- Either way, `offline-sync.js` no longer sits unused.

## Dependencies Or Related Ideas

- Related to the mobile navigation idea (`0015`).

## Open Questions

- Does the product want an installable app at all? This decides A versus B.
