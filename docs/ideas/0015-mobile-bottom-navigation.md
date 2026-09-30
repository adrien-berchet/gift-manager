# Idea: Mobile Bottom Navigation Bar

## Status

Proposed

## Summary

On small screens, replace the hamburger-only navigation with a bottom tab bar
(Dashboard, Gift Plans, Recipients, Gifts) plus a central "+" action that opens
quick creation. The top navbar stays for desktop and for secondary items.

## Motivation

The navbar collapses on mobile into a menu with a dozen items (main sections,
"More" dropdown, search, theme, admin, profile, language, sign out). Reaching a
section takes two taps and the create actions are buried. A gift list is often
used on a phone while shopping, where thumb-reachable navigation matters.

## User Value

- One-tap access to the main sections.
- Fast creation from anywhere.
- Less scrolling inside the collapsed menu.

## Possible Scope

- Fixed bottom bar below the `lg` breakpoint with icons and labels, active
  state, and safe-area padding.
- "+" button opening a small sheet (new gift plan, gift, person, event) using
  the existing `data-action="create"` offcanvas behaviour.
- Top navbar keeps search, profile, language and "More" items on mobile.

## Out Of Scope

- Native app shell or gestures beyond what `touch-gestures.js` provides.
- Redesigning the desktop navbar.

## Implementation Notes For AI Agent

- Navbar markup and inline styles: `gift_manager/templates/gift_manager/base.html`;
  mobile styles: `static/gift_manager/css/mobile-responsive.css`.
- The body padding script (`adjustBodyPadding`) only accounts for the top bar;
  add bottom padding so content is not hidden.
- Offcanvas panels and toasts must not be covered by the bar.
- Keep active-state logic consistent with the `resolver_match.url_name` checks.
- Mobile tests: `gift_manager/tests/test_mobile_responsiveness_property.py` and
  e2e tests under `gift_manager/tests/e2e/`.

Recommended starting context:

- `docs/ai/testing.md`
- `docs/ux-roadmap.md` (mobile layouts checklist item)

## Acceptance Criteria

- Below the breakpoint the bottom bar shows four sections and "+", with the
  current section highlighted; it is hidden on desktop.
- No content, panel or toast is obscured by the bar, including on devices with
  a home indicator.
- All targets are at least 44px and keyboard accessible.
- A Playwright check at a phone viewport passes.

## Dependencies Or Related Ideas

- "+" can open the guided creation flow (`0016`).

## Open Questions

- Should the bar hide on scroll down?
