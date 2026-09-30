# Idea: Gift Plan Suggestions For A Recipient

## Status

Proposed

## Summary

Suggest relevant Gift Plans for a given recipient (a person or a group). On a
recipient's detail page, Gift Manager shows a short, ranked list of gift
suggestions, each with a short reason ("similar to gifts rated 5/5", "shares
tags with past favourites", ...). The user can accept a suggestion, which
creates a Gift Plan in the `Idea` status, or dismiss it permanently.

Suggestions come from two pluggable strategies that are designed together
from the start:

- A **simple scoring model** that ranks gifts already in the database and
  accessible to the user (their own gifts and gifts shared with them), based
  on tags, reaction ratings, statuses and group membership. It is always
  available, free and deterministic.
- An **AI strategy (LLM)** that receives an anonymised summary of the
  recipient's gift history and proposes brand-new gift ideas that do not exist
  anywhere in the database yet, and can also re-rank catalogue candidates. It
  is enabled only when an API key is configured and falls back to the simple
  model on error.

## Motivation

Gift Manager already stores the signals needed to recommend gifts: the gift
catalogue with hierarchical tags, every past Gift Plan per recipient with its
status, and reaction ratings (1-5) plus notes on given or abandoned plans.
Today this history is only used for display. Turning it into suggestions makes
the collected data pay off and addresses the hardest part of gift planning:
finding the first idea, including ideas the user has never written down.

## User Value

- Users who plan gifts for many people get a starting point instead of a blank
  "new Gift Plan" form.
- Past reactions become actionable: gifts or tags that were well received are
  surfaced again, poorly received ones are avoided.
- Genuinely new ideas are proposed by the AI strategy, not only gifts already
  in the catalogue.
- Duplicate gifts are less likely, because already given or planned gifts are
  excluded from suggestions.
- Shared workspaces benefit from gifts other users shared, which the user may
  not have thought about.
- Dismissed suggestions never come back, so the list stays useful over time.

## Possible Scope

Placement and size (recommended, see rationale in the implementation notes):

- A "Suggestions" section on the person detail page and on the person group
  detail page, lazy-loaded via HTMX so it never slows the main page.
- Show **5 suggestions** by default: up to 3 from the catalogue and up to 2
  new AI ideas when AI is enabled (5 catalogue suggestions otherwise). A
  "Show more" action loads the next 5 catalogue suggestions; a "More ideas"
  action asks the AI for another batch on demand.
- Recipients list and dashboard pages do not show suggestions.

Suggestion engine:

- A `GiftSuggestionService` that combines strategies behind a small interface
  (for example `SuggestionStrategy.suggest(user, recipient, context, limit)`),
  returning candidates with a source (`catalogue` or `ai`), a score and a
  human-readable reason.
- A recipient history builder shared by both strategies:
  - For a person: their own Gift Plans plus the Gift Plans of every group they
    belong to (including ancestor groups).
  - For a group: its own Gift Plans plus the Gift Plans of its members
    (`PersonGroup.get_all_members`, including nested groups).
  - Only data accessible to the requesting user (own and shared objects).
- Catalogue strategy (simple model, no new dependency):
  - Candidates: all gifts accessible to the user (own and shared) that are
    not already linked to the recipient by a non-abandoned Gift Plan and not
    dismissed for this recipient.
  - Positive signal: tag overlap (including ancestor tags) with history plans
    rated 4-5; direct recipient history weighs more than group/member history.
  - Negative signal: tag overlap with plans rated 1-2 or abandoned.
  - Fallback when there is no history: gifts with the best average rating
    across the user's accessible plans.
- AI strategy:
  - Sends a minimised, anonymised context: recipient type, pseudonymous labels
    (`Recipient`, `Member 1`, ...), gift names, tags, statuses, ratings,
    reaction notes and comments with known person names and emails scrubbed,
    plus the names of already suggested, planned or dismissed gifts so they
    are not proposed again.
  - Asks for structured output (gift name, short description, suggested
    existing tags, reason) and validates it server-side; invalid items are
    dropped.
  - Drops AI ideas whose normalised name matches an existing accessible gift,
    a dismissed suggestion, or a gift already planned for the recipient.
  - Is disabled unless configured (API key via environment variable), and on
    error or timeout the section still shows catalogue suggestions with a
    discreet notice.
- Persistence with a `GiftSuggestion` model (user, person or group, source,
  optional existing `gift`, name and description for new AI ideas, reason,
  score, state `pending` / `accepted` / `dismissed`, timestamps):
  - AI ideas are stored when generated, so reloading the page does not call
    the API again.
  - Dismissals are stored per user and recipient and exclude the gift (or the
    normalised AI idea name) from all future suggestions for that recipient.
- Actions:
  - "Add as idea" on a catalogue suggestion creates a Gift Plan in `Idea`
    status linking the existing gift to the recipient.
  - "Add as idea" on an AI suggestion first creates a new `Gift` owned by the
    user (name, description as comment, suggested tags limited to tags the user
    can access), then the Gift Plan in `Idea` status.
  - "Dismiss" marks the suggestion as dismissed.
- French translations for all new strings.

## Out Of Scope

- Fetching products, prices or links from external shops or the web.
- Collaborative filtering or trained ML models requiring a training pipeline.
- Automatic creation of Gifts or Gift Plans without user confirmation.
- Suggestions in bulk for all recipients, scheduled generation, or
  notifications.
- Suggestions on the recipients list, dashboard or Gift Plan creation form in
  the first slice (the creation form is a good follow-up).
- Letting the AI create new tags.
- Background task infrastructure (the project has no task queue); AI calls are
  made on demand in a request with a strict timeout.

## Implementation Notes For AI Agent

"Gift Plan" is the user-facing name of the `Relation` model: a link between a
`Gift` and a recipient (`person` or `group`), with `status`, `event`,
`due_date`, `reaction_rating` (1-5) and `reaction_note`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/models.py`: `Relation`, `Gift`, `GiftTag` (hierarchy helpers
  `get_ancestors` / `get_descendants`), `Person`, `PersonGroup`
  (`get_all_members`, `get_ancestors`), and the `accessible_by(user)` query
  helpers.
- `gift_manager/statuses.py`: `is_idea_status`, `is_terminal_status`,
  `is_abandoned_status`, `can_rate_status`.
- `gift_manager/services.py`, `gift_manager/gift_plan_cards.py` and
  `gift_manager/gift_plan_actions.py` for existing service/card patterns.
- `gift_manager/views/person.py` (`PersonDetailView`),
  `gift_manager/views/person_group.py` (`PersonGroupDetailView`) and
  `gift_manager/views/relation.py` (`PersonRelationCreateView`,
  `PersonGroupRelationCreateView`) for where suggestions and the
  "Add as idea" action plug in.
- `gift_manager/templates/gift_manager/person_detail.html` and
  `person_group_detail.html` for the suggestion section placement.

Why detail pages and 5 suggestions:

- Detail pages already scope everything to one recipient, which is exactly
  the suggestion context; list pages would require computing suggestions for
  many recipients (and many AI calls) at once.
- Five items fit in one card without scrolling on mobile and keep the choice
  quick; "Show more" and "More ideas" cover users who want more.
- Mixing 3 catalogue and 2 AI items keeps free, instant suggestions visible
  while still surfacing new ideas; AI generation is on demand after the first
  batch to control cost and latency.

Constraints:

- Privacy is the main risk. Only use gifts, plans, ratings and notes the
  requesting user can access through `accessible_by` / `PermissionService`.
  A suggestion or its reason must never reveal data from plans the user
  cannot see, and suggestions are stored per user.
- Anonymise before sending anything to the AI provider: no person or group
  names, emails or user identifiers; scrub known names from free-text fields.
- Keep ranking and prompt building in services, not in templates or
  JavaScript. Keep the AI client behind a thin adapter so the provider can be
  changed and so tests can mock it.
- Adding an LLM SDK is a new production dependency: note it explicitly, keep
  the API key in environment variables, and document it in `.env.example`.
- Keep queries bounded (prefetch tags and ratings once); respect tag and group
  hierarchy caches.
- Review the generated migration for `GiftSuggestion`.

## Acceptance Criteria

- The person detail page and the group detail page show up to 5 ranked
  suggestions for that recipient, each with a source indicator and a short
  reason, loaded via HTMX, and the pages still work with a full page render.
- A person's suggestions use their own history and their groups' history; a
  group's suggestions use its own history and its members' history.
- Catalogue suggestions include gifts shared with the user by other users.
- Gifts already linked to the recipient through a non-abandoned Gift Plan are
  never suggested.
- Gifts sharing tags with plans rated 4-5 rank above gifts sharing tags with
  plans rated 1-2.
- With AI enabled, new gift ideas that do not exist in the database are shown;
  AI ideas duplicating an existing accessible gift, a planned gift or a
  dismissed suggestion are filtered out.
- With AI disabled, misconfigured, failing or timing out, the section still
  shows catalogue suggestions and no error page is shown.
- The payload sent to the AI provider contains no person or group names,
  emails or user identifiers (asserted in tests with a mocked client).
- "Add as idea" on a catalogue suggestion creates a Gift Plan in `Idea`
  status; on an AI suggestion it creates a new Gift and a Gift Plan in `Idea`
  status; the suggestion then leaves the list.
- A dismissed suggestion is never suggested again for that user and
  recipient, including after reload and after new AI generations.
- A user never sees suggestions or reasons derived from gifts, plans, ratings
  or notes they cannot access (tested for owner, editor, viewer and no-access
  paths).
- Unit tests cover the scoring, history building, anonymisation and AI output
  validation; integration tests cover views, actions and permission
  boundaries on PostgreSQL; an e2e test covers accept and dismiss on a detail
  page; new strings are translated to French.

## Dependencies Or Related Ideas

- Builds on the existing Gift Plan reaction rating feature (`reaction_rating`,
  `reaction_note` on `Relation`).
- Possible follow-ups: suggestions on the Gift Plan creation form, event-aware
  suggestions (birthday vs Christmas), budget-aware suggestions, and a way to
  review or undo dismissed suggestions.

## Open Questions

- Which LLM provider and model should be the default, and should a
  self-hosted option be supported through the same adapter?
- Should there be a per-user daily limit on AI generations to cap cost?
- Should suggestions be private to the user who generated them, or visible to
  other users who share the recipient (the first slice assumes private)?
