# Idea: Dismiss Reasons For Gift Suggestions

## Status

Proposed

## Summary

Allow users to optionally specify a reason when dismissing an AI or catalogue
gift suggestion (e.g. "Already owned or practiced", "Not their taste", "Too
expensive").

This structured feedback is provided to subsequent AI generation requests and
catalogue scoring, ensuring that dismissing an unsuitable idea does not
mistakenly discourage the system from recommending gifts in a category that the
recipient actually loves.

## Motivation

Currently, dismissing an AI or catalogue suggestion is an unannotated, binary
action (`state=DISMISSED`). The suggestion's normalized name is added to the
exclusion list (`avoid`), and for AI suggestions, the name and its tags are
forwarded to the LLM in `rejected_directions`.

However, users frequently dismiss suggestions not because the recipient dislikes
the hobby, but because the specific suggestion is redundant or inappropriate for
their skill level. For example, dismissing a beginner "Tandem paragliding
flight" for an experienced paraglider currently risks signaling to the LLM that
paragliding gifts in general should be avoided. Capturing a lightweight dismissal
reason eliminates this ambiguity, allowing future suggestions to focus on
complementary gear, advanced accessories, or specialized consumables instead of
abandoning the domain.

## User Value

- **Gift planners:** Can dismiss redundant or inappropriate ideas without fear
  of skewing future AI suggestions away from the recipient's true passions.
- **Recipients:** Benefit from higher quality, better-calibrated suggestions
  that match their real experience and ownership status.
- **Usability:** Retains rapid workflow through progressive enhancement:
  one-click dismissal remains available, while explicit reasons can be selected
  in a single extra gesture (e.g. split button, popover, or quick-choice menu).

## Possible Scope

- **Data Model:**
  - Add an optional `dismiss_reason` field to `GiftSuggestion` using a choices
    enumeration (e.g. `ALREADY_OWNED_OR_PRACTICED`, `DISLIKES`, `TOO_EXPENSIVE`,
    `OTHER`).
  - Update `GiftSuggestionService.dismiss_suggestion` to accept and persist the
    reason.
- **AI Strategy & Prompting:**
  - Include the dismissal reason in `rejected_directions` payloads generated in
    `_build_rejected_directions` (`gift_manager/suggestions/ai/strategy.py`).
  - Update `SYSTEM_PROMPT` in `gift_manager/suggestions/ai/prompt.py` (Rule 4)
    with explicit guidelines for interpreting dismissal reasons:
    - `already_owned_or_practiced`: Keep the category or interest active;
      recommend upgrades, complementary accessories, or consumables rather than
      introductory experiences or basic starter items.
    - `dislikes`: Steer clear of the theme or style.
    - `too_expensive`: Favor budget-conscious alternatives in that domain.
- **UI & Views:**
  - Enhance `gift_manager/templates/gift_manager/includes/gift_suggestion_item.html`
    with an optional reason selector (e.g. Bootstrap dropdown on a split Dismiss
    button or quick-action popover).
  - Update `person_suggestion_dismiss` and `group_suggestion_dismiss` in
    `gift_manager/views/suggestions.py` to accept the optional reason in the POST
    body.
- **Localization:**
  - Provide French translations for all new dismissal reason labels.

## Out Of Scope

- Freeform text comment entry on dismissals (to prevent latency, UI clutter,
  and sensitive data scrubbing complexity).
- Prompting retroactively for reasons on previously dismissed suggestions.
- Changes to the restore/undo behavior of dismissed suggestions.
- Complex machine learning re-ranking models for catalogue scoring in the initial
  slice (catalogue scoring can simply avoid penalizing tags when dismissed as
  `already_owned_or_practiced`).

## Implementation Notes For AI Agent

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/ideas/implemented/0001-gift-plan-suggestions-for-recipient.md`
- `gift_manager/models.py` (`GiftSuggestion` model, `State` and proposed `DismissReason` choices)
- `gift_manager/suggestions/service.py` (`GiftSuggestionService.dismiss_suggestion`)
- `gift_manager/suggestions/ai/strategy.py` (`_build_rejected_directions`, `_resolve_blocked_names`)
- `gift_manager/suggestions/ai/prompt.py` (`SYSTEM_PROMPT`, `_clean_rejected_directions`, `build_ai_payload`)
- `gift_manager/views/suggestions.py` (`person_suggestion_dismiss`, `group_suggestion_dismiss`, `_handle_dismiss`)
- `gift_manager/templates/gift_manager/includes/gift_suggestion_item.html` (HTMX dismiss form and buttons)
- `gift_manager/tests/suggestions/test_ai_service.py` and `gift_manager/tests/views/test_suggestions_views.py`

Key technical details:

- Maintain progressive enhancement and mobile ergonomics: single-tap dismiss
  must remain functional without forcing users through a multi-step modal.
- Ensure `_clean_rejected_directions` in `prompt.py` safely validates allowed
  reason enum values without unintended text scrubbing.
- Ensure migrations cleanly handle existing records with a nullable default.

## Acceptance Criteria

- Users can optionally select a structured reason when dismissing a suggestion.
- Dismissing without picking a reason continues to work seamlessly as an
  unspecified dismissal.
- The chosen dismissal reason is saved on the `GiftSuggestion` model.
- AI request payload includes the dismissal reason for each item in
  `rejected_directions`.
- Prompt instructions guide the LLM to treat `already_owned_or_practiced` as an
  indicator of active hobby interest rather than a negative signal against the
  entire tag/category.
- All unit and integration tests pass, including new tests for reason
  persistence and AI payload structure.
- User-facing reason labels are translated to French.

## Dependencies Or Related Ideas

- `0001-gift-plan-suggestions-for-recipient.md`: Original suggestion system and
  dismissal baseline.
- `0006-recipient-notes-and-interests.md`: Recipient interest tags and notes.

## Open Questions

- Should a standard click on "Dismiss" default to `unspecified` with an adjacent
  caret for specific reasons, or should it trigger a lightweight popover offering
  the 3-4 options?
- Should catalogue suggestion scoring treat `already_owned_or_practiced` as a
  positive interest signal (similar to a rating 4-5) for matching tag
  hierarchies?
