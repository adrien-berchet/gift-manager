# Idea: Measure And Reduce Static Asset Load Cost

## Status

Proposed

## Summary

Every page loads 13 local stylesheets and 15 local scripts from `base.html`,
plus 4 CDN stylesheets and 5 CDN scripts spread over three third-party domains.
Static files are split between the root of `static/gift_manager/`, its `css/`
and `js/` folders, and a stray `static/css/forms.css` outside the app namespace.

Clean up the directory layout first, as a move-only refactor. Then measure real
page-load performance and act only on what the numbers show. Prefer
self-hosting or preconnecting vendor assets, deferring scripts and loading
page-specific assets only where they are used. Hand-merging files into bundles
is not the goal.

## Motivation

- The asset layout is inconsistent: 10 CSS and 14 JS files sit at the root of
  `static/gift_manager/`, 12 CSS files in `static/gift_manager/css/` and
  15 JS files in `static/gift_manager/js/`. New files have no obvious home.
- `gift_manager/static/css/forms.css` is not namespaced under `gift_manager/`.
  Django's static finders serve the first `css/forms.css` they find, so another
  app shipping that path could silently replace it.
- The 13 stylesheets depend on their load order, which makes precedence hard
  to reason about when styles conflict.
- Every page downloads roughly 220 KB of local CSS (`theme.css` alone is about
  89 KB) and about 200 KB of local JS before compression. Part of that, such as
  `detail-views.*` on list pages or touch-gesture code on desktop, is unused on
  the page that loads it.
- No script in `base.html` uses `defer` or `async`.

Merging files into bundles would reduce the request count, but it is a poor
fit here:

- Local files come from one domain. Production serves them through WhiteNoise's
  `CompressedManifestStaticFilesStorage` (compressed, hashed names, long-term
  caching). If the host also serves HTTP/2, as most modern hosts do, the
  requests share one connection, so merging gains little after the first visit.
- Bundling does not reduce the bytes sent.
- A bundle makes caching coarser: editing one stylesheet invalidates all of
  them.
- Merging by hand keeps the same order dependency inside one large file and
  produces a diff that is hard to review.
- A real bundler adds build tooling, which idea `0017` lists as out of scope.

## User Value

- Developers and agents find, place and review static files predictably.
- Visitors on slow or high-latency connections, mostly first visits on mobile,
  get faster first loads, if measurements show there is time to gain.
- Style precedence becomes explicit instead of an accident of load order.

## Possible Scope

- **Layout (first slice, no behaviour change):** move the root-level CSS files
  of `static/gift_manager/` into `static/gift_manager/css/` and the root-level
  JS files into `static/gift_manager/js/`. Move `static/css/forms.css` to
  `static/gift_manager/css/forms.css`. Update every `{% static %}` reference.
  Do not merge or edit file contents.
- **Measurement:** record a baseline with Lighthouse or browser DevTools on a
  production-like build (`collectstatic`, WhiteNoise, `DEBUG=False`) for a few
  representative pages (dashboard, a Grid.js list page, a detail page), on
  desktop and on a throttled mobile profile. Note request counts, transferred
  bytes, render-blocking resources and the main timings.
- **Targeted improvements, each done only if the baseline justifies it:**
  - Self-host the CDN assets (Bootstrap, Font Awesome, flatpickr, HTMX,
    Grid.js, the Inter font), or add `preconnect` hints for their domains.
  - Load the scripts in `base.html` with `defer`, keeping their relative order.
  - Move page-specific CSS and JS out of `base.html` into the templates that
    need them, as the Grid.js list pages already do for their scripts.
- **Style precedence, only if real conflicts are found:** declare explicit CSS
  cascade layers (for example `@layer base, components, overrides`) instead of
  relying on stylesheet order.

## Out Of Scope

- Introducing a bundler, a JS build step or a frontend framework (see `0017`).
- Hand-merging stylesheets or scripts into bundles.
- Visual changes and rewrites of the CSS itself.
- Large refactors of individual files such as `grid-utils.js` or `theme.css`.

## Implementation Notes For AI Agent

Recommended starting context:

- `gift_manager/templates/gift_manager/base.html`: local stylesheets at about
  lines 43-64, CDN assets at about lines 16-24 and 365-375, local scripts at
  about lines 366 and 445-471.
- `gift_manager/static/gift_manager/` (root, `css/`, `js/`, `vendor/`) and
  `gift_manager/static/css/forms.css`.
- `GiftManager/settings/base.py`: `STORAGES` uses WhiteNoise's
  `CompressedManifestStaticFilesStorage`. `GiftManager/settings/testing.py`
  overrides it for tests.
- `.claude/rules/frontend.md`, `docs/ai/architecture.md`, `docs/ai/testing.md`.
- `docs/ideas/implemented/0017-extract-inline-scripts-and-styles-from-base.md`,
  which moved the `base.html` inline code into static files and excluded a
  bundler.

Notes:

- Root-level assets are referenced about 106 times across 21 templates. Find
  them with
  `rg "static '(css/forms\.css|gift_manager/[a-z-]+\.(css|js))'" gift_manager/templates`.
  Some tests also reference asset paths, including
  `gift_manager/tests/test_grid_xss_safety.py`,
  `gift_manager/tests/views/test_advanced_list_tools.py` and
  `gift_manager/tests/e2e/test_unsaved_changes_snapshots.py`.
- Keep the layout move as its own commit, separate from performance changes,
  so it stays easy to review and `git log --follow` keeps file history.
- Run `python manage.py collectstatic --noinput` after moving files. With
  manifest storage, a template referencing a missing file fails to render, so
  broken references surface as errors.
- Adding `defer` changes when scripts run. Inline scripts in templates that
  rely on globals such as `GridUtils` or `gridjs` must still run after those
  libraries load. Check the scripts at the end of `base.html` and the list
  templates before deferring.
- If vendor assets are self-hosted, put them under
  `static/gift_manager/vendor/`, next to the existing `gridjs-mermaid.css`.

## Acceptance Criteria

- No CSS or JS file remains directly under `static/gift_manager/`, and
  `static/css/` no longer exists. Every asset lives under
  `static/gift_manager/css/`, `static/gift_manager/js/` or
  `static/gift_manager/vendor/`.
- No template or test references an old asset path, and
  `python manage.py collectstatic --noinput` succeeds.
- The layout move changes no file contents. A rename-aware diff
  (`git diff -M --stat`) shows only renames plus the reference updates.
- Pages look and behave the same. The unit and e2e suites pass on PostgreSQL
  (`tox run -e py311`, `tox run -e e2e`).
- A baseline measurement, with the method used, is recorded in this file or in
  the pull request before any performance change.
- Each performance change shows a measured improvement against that baseline,
  or is dropped.

## Dependencies Or Related Ideas

- `0017` Extract Inline Scripts And Styles From The Base Template, which moved
  the inline code that the layout move now touches and kept bundlers out of
  scope.

## Open Questions

- Does the production host serve static files over HTTP/2? This decides how
  much request count still matters.
- Should vendor assets be self-hosted (fewer third-party domains, works on
  restricted networks) or kept on CDNs with `preconnect` (less to maintain)?
- What first-load target counts as good enough on mobile, so that the
  performance slice has a clear stopping point?
