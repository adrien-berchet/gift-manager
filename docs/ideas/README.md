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
| 0001 | Gift Plan Suggestions For A Recipient | Proposed | Gift Plans | Catalogue scoring plus AI new-gift ideas per recipient, with persisted dismissals. |
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
| 0015 | Mobile Bottom Navigation Bar | Proposed | Navigation | Bottom tab bar with quick-create action on small screens. |
| 0016 | Guided Gift Plan Creation | Proposed | Gift Plans | Three-step creation flow with inline gift and event creation. |
| 0017 | Extract Inline Scripts And Styles From The Base Template | Implemented | Frontend | base.html inline code moved to static files; moved to `implemented/`. |
| 0018 | Unify Delete Confirmation | Implemented | Frontend | Single shared delete flow; moved to `implemented/`. |
| 0019 | Scope Form Loading State To Form Submissions | Implemented | Frontend | Only form submissions lock a form, and controls unlock when the request ends; moved to `implemented/`. |

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
