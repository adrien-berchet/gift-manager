# Future Improvement Ideas

This folder stores independent ideas for future Gift Manager improvements.
Each idea lives in its own Markdown file so it can be discussed, refined,
implemented, archived, or ignored without changing the meaning of other ideas.

The main audience is a future human or AI agent implementing one idea at a
time. A good idea file should be self-contained enough that an agent can start
from that file, then inspect only the referenced code and documentation.

## Folder Structure

```text
docs/ideas/
  README.md
  template.md
  0001-example-idea.md
  archived/
  implemented/
```

- Active ideas stay directly in `docs/ideas/`.
- Implemented ideas move to `docs/ideas/implemented/`.
- Ideas that are no longer wanted move to `docs/ideas/archived/`.
- `template.md` is copied when creating a new idea.

## Naming

Use this format:

```text
NNNN-short-kebab-case-title.md
```

Keep IDs stable. Do not renumber files when ideas move, merge, or get archived.
When creating a new idea, scan active, implemented, and archived idea files,
then use the next unused number.

## Status Values

- `Proposed`: captured, but not yet evaluated.
- `Considering`: interesting, but needs product or technical shaping.
- `Ready`: detailed enough for an implementation agent to start.
- `Implemented`: shipped or otherwise completed.
- `Archived`: intentionally deferred or no longer relevant.

## Index

This index is the stable registry for all idea IDs, including active,
implemented, and archived ideas. Keep rows when moving idea files, and update the
status and notes to reflect the move.

| ID | Idea | Status | Area | Notes |
| --- | --- | --- | --- | --- |
| 0001 | Gift Plan Suggestions For A Recipient | Implemented | Gift Plans | Catalogue scoring plus AI new-gift ideas per recipient, with persisted dismissals. Moved to `implemented/`. |
| 0002 | Person Birthdays And Personal Occasions | Implemented | Recipients | Birthday on people, dashboard section and one-click plan creation. Moved to `implemented/`. |
| 0003 | Reminders And Calendar Feed | Implemented | Notifications | Opt-in digest email via management command plus private .ics feed. Moved to `implemented/`. |
| 0004 | Richer Gift Details (Link, Price, Image) | Implemented | Gifts | Optional URL and price on gifts and plans, with budget totals; image upload deferred. Moved to `implemented/`. |
| 0005 | Recipient Gift History And Repeat-Gift Warning | Implemented | Recipients | Yearly timeline with reactions and duplicate-gift warning in the plan form. Moved to `implemented/`. |
| 0006 | Recipient Notes And Interests | Implemented | Recipients | Notes and interest tags on people, matched against gift tags. Moved to `implemented/`. |
| 0007 | Coordination On Shared Gift Plans | Implemented | Sharing | Claimed-by marker, plan comments and surprise flag hidden from the recipient. Moved to `implemented/`. |
| 0008 | Duplicate And Repeat Gift Plans | Implemented | Gift Plans | Duplicate action and "plan again" for recurring and birthday events. Moved to `implemented/`. |
| 0009 | Close Translation And Locale Gaps | Implemented | i18n | Locale-aware dates, lang attribute, JS labels; moved to `implemented/`. |
| 0010 | Consistent Login, Invitation And Friends Pages | Implemented | Accounts | Shared-component login, invitation page with cancellable pending invites, confirmed friend removal; moved to `implemented/`. |
| 0011 | Undo Toasts For Low-Risk Actions | Implemented | Interaction | Undo toast on card quick actions; moved to `implemented/`. |
| 0012 | Global Search Improvements | Implemented | Search | Gift plans in results, recent items, create-on-no-result. Moved to `implemented/`. |
| 0013 | Dashboard Polish | Implemented | Dashboard | Next-upcoming empty state and unused data cleanup. Moved to `implemented/`. |
| 0014 | Installable PWA Or Removal Of Dead Offline Code | Implemented | Platform | Dead offline scripts removed; moved to `implemented/`. A real PWA would be a new idea. |
| 0015 | Mobile Bottom Navigation Bar | Implemented | Navigation | Bottom tab bar with quick-create action on small screens. Moved to `implemented/`. |
| 0016 | Guided Gift Plan Creation | Implemented | Gift Plans | Three-step creation flow with inline gift and event creation; status defaults to Idea. Moved to `implemented/`. |
| 0017 | Extract Inline Scripts And Styles From The Base Template | Implemented | Frontend | base.html inline code moved to static files; moved to `implemented/`. |
| 0018 | Unify Delete Confirmation | Implemented | Frontend | Single shared delete flow; moved to `implemented/`. |
| 0019 | Scope Form Loading State To Form Submissions | Implemented | Frontend | Only form submissions lock a form, and controls unlock when the request ends; moved to `implemented/`. |
| 0020 | Remove Redundant Toasts | Implemented | Frontend | Drop toasts and flash messages that repeat a visible result or a page navigation; moved to `implemented/`. |
| 0021 | Unify Card Appearance Across Pages | Implemented | Frontend | Shared card tokens make advanced-page card views match gift plan cards. Moved to `implemented/`. |
| 0022 | Complete Gift Plan Visibility And Bounded Sections | Implemented | Gift Plans | No plan was missing; workspace sections now page two rows of cards each so the last section is reachable. Moved to `implemented/`. |
| 0023 | Verify The Remember Me Login Checkbox | Implemented | Accounts | Test that the checkbox controls session persistence, with tests for both cases. Moved to `implemented/`. |
| 0024 | Polish The Advanced List Card View | Implemented | Frontend | Per-field card icons, dashboard-consistent action buttons in card and list views, overflow menu for delete and share. Moved to `implemented/`. |
| 0025 | Measure And Reduce Static Asset Load Cost | Proposed | Frontend | Move-only cleanup of the static asset folders, then measured fixes (vendor assets, `defer`, per-page assets) instead of bundling. |
| 0026 | Dismiss Reasons For Gift Suggestions | Implemented | Gift Plans | Optional structured dismissal reasons (e.g. already owns/practices, dislikes, too expensive) to steer future AI and catalogue suggestions. Moved to `implemented/`. |
| 0027 | Recipient Preference Profiles And Feedback Persistence | Implemented | Gift Plans | Aggregate all-time recipient preference profiles to avoid history truncation in suggestions, with opt-in feedback promotion to profile notes and interests. Moved to `implemented/`. |
| 0028 | Wishlists And Collaborative Gift Giving | Implemented | Sharing | Person-account link (project A), own profile and wishlist (B), group gifts with a contribution tally (C). Moved to `implemented/`. |
| 0029 | MCP Server For AI Agents | Proposed | Platform | Read-only MCP server inside the Django app with per-user bearer tokens, reusing `accessible_by` and `PermissionService`; writes deferred. |
| 0030 | Received Gifts Log | Implemented | Gift Plans | Private log of received gifts (manual or revealed by friends), with thank-you tracking, wish fulfillment, re-gifting warnings and AI context when giving back. Moved to `implemented/`. |
| 0031 | Browser Bookmarklet For Quick Gift And Wish Entry | Proposed | Interaction | Drag-and-drop browser bookmarklet extracting Open Graph and Schema.org metadata client-side to pre-fill guided plan and wishlist creation without serverless scraping risks. |
| 0032 | Managed Wishlists For Children And Dependents | Proposed | Sharing | Wishlists anchored to owned Person records with query isolation in WishQuerySet and parent-coordination claim visibility rules. |
| 0033 | Read-Only Guest Wishlist Links | Proposed | Sharing | Unguessable token links rendering all active wishes uniformly without claim state to avoid owner surprise leaks, with Referrer-Policy protection. |
| 0034 | Secret Santa Draws For Groups | Considering | Gift Plans | Automated holiday draw pairings with exclusion rules, exchange wishlist grants, and dashboard delivery, leaving anonymous Q&A to a later phase. |
| 0035 | Search Received Gifts And Wishes | Implemented | Search | Global search returns the user's own received gifts and wishes, scoped with `for_user` / `for_wisher`. From the 2026-11-12 QA pass. Moved to `implemented/`. |
| 0036 | Filter Received Gifts By Free-Text Giver | Implemented | Gift Plans | Giver filter also matches free-text givers and the revealed givers shown by name, not only address-book people and groups. From the 2026-11-12 QA pass. Moved to `implemented/`. |
| 0037 | Consistent Price Formatting | Implemented | i18n | One locale-aware price format on the gifts grid and server-rendered pages ("€24.50" in English, "24,50 €" in French). From the 2026-11-12 QA pass. Moved to `implemented/`. |
| 0038 | Delete For Everyone With Copies For Dependent Plans | Proposed | Sharing | The only owner of a shared object deletes it for everyone; owners of dependent plans keep a copy, so no plan is lost and no surprise is revealed. |


## Working With Ideas

When adding a new idea:

1. Pick the next unused ID across active, implemented, and archived ideas.
2. Copy `template.md` to a new `NNNN-short-kebab-case-title.md` file.
3. Fill in enough context for the idea to stand alone.
4. Add a row to the index above.
5. Keep acceptance criteria concrete and testable where possible.

When preparing an idea for AI implementation:

1. Move the status to `Ready`.
2. Add code areas and project docs the agent should inspect.
3. Make out-of-scope items explicit.
4. Add open questions only if they do not block the first implementation slice.
