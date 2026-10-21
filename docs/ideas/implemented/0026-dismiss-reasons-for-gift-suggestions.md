# Idea: Dismiss Reasons For Gift Suggestions

## Status

Implemented

## Summary

Allow users to optionally specify a reason when dismissing an AI or catalogue
gift suggestion (e.g. "Already owned or practiced", "Not their taste", "Too
expensive", or a short custom note).

The default action remains an instant one-click dismissal via a split button,
while a dropdown menu allows choosing a reason or entering a brief note. This
feedback steers subsequent AI generation requests and catalogue scoring,
ensuring that dismissing an unsuitable idea does not mistakenly discourage the
system from recommending gifts in a category that the recipient actually loves.

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
reason eliminates this ambiguity:
- In AI suggestion generation, the LLM can recommend complementary gear,
  upgrades, or accessories instead of abandoning the domain.
- In catalogue scoring, the system can treat "already owned or practiced" as a
  positive affinity signal for matching tags rather than penalizing or ignoring
  them.

## User Value

- **Gift planners:** Can dismiss redundant or inappropriate ideas without fear
  of skewing future AI suggestions away from the recipient's true passions.
- **Recipients:** Benefit from higher quality, better-calibrated suggestions
  that match their real experience and ownership status.
- **Usability:** Retains rapid workflow through progressive enhancement:
  one-click dismissal remains available on the primary button, while explicit
  reasons or a short note can be selected from an adjacent dropdown.

## Possible Scope

- **Data Model:**
  - Add optional `dismiss_reason` (choices: `already_owned_or_practiced`,
    `dislikes`, `too_expensive`, `custom`, `unspecified`) and optional
    `dismiss_comment` (short text, max 120 characters) to `GiftSuggestion`.
  - Update `GiftSuggestionService.dismiss_suggestion` to accept and persist the
    reason and comment.
- **UI & Views:**
  - Update `gift_manager/templates/gift_manager/includes/gift_suggestion_item.html`
    to render a Bootstrap split button:
    - Primary button: one-click instant dismiss (sets `unspecified`).
    - Dropdown toggle: menu offering common quick reasons (*"Already owned or practiced"*,
      *"Not their taste"*, *"Too expensive"*), plus an *"Other reason..."* option
      revealing an inline text input (or small modal/popover) capped at 120 chars.
  - Update `person_suggestion_dismiss` and `group_suggestion_dismiss` in
    `gift_manager/views/suggestions.py` to accept optional `reason` and `comment`
    parameters in the POST body.
- **Privacy & Scrubbing:**
  - Ensure any freeform `dismiss_comment` sent to external AI providers is
    strictly scrubbed through `scrub_text` (matching known names, emails, and
    identifiers) in `_clean_rejected_directions` before inclusion in the payload.
- **AI Strategy & Prompting:**
  - Include `reason` and optional scrubbed `comment` in `rejected_directions`
    dictionaries in `gift_manager/suggestions/ai/strategy.py`.
  - Update `SYSTEM_PROMPT` in `gift_manager/suggestions/ai/prompt.py` (Rule 4)
    with explicit guidelines for interpreting dismissal reasons:
    - `already_owned_or_practiced` (or comments indicating existing practice):
      keep the category or interest active; recommend upgrades, complementary
      accessories, or consumables rather than basic starter items or
      introductory experiences.
    - `dislikes`: steer clear of the theme or style.
    - `too_expensive`: favor budget-conscious alternatives in that domain.
- **Catalogue Scoring:**
  - In `gift_manager/suggestions/catalogue.py`, incorporate dismissed
    suggestions with `already_owned_or_practiced` into `_build_profile`:
    while the dismissed gift itself remains excluded, its visible tags contribute
    a positive signal to the recipient's tag profile, helping other relevant
    catalogue gifts surface.
  - Conversely, dismissals marked `dislikes` can apply a negative signal to
    those tags.
- **Localization:**
  - Provide French translations for all new dismissal reason labels and UI
    strings.

## Out Of Scope

- Unbounded, rich-text, or multi-line comment entry (strictly capped at 120
  characters).
- Mandatory reasons (dismissing must never block or force a prompt on users who
  prefer one-click dismissal).
- Retroactive prompting for reasons on previously dismissed suggestions.
- Changes to the restore/undo behavior of dismissed suggestions.

## Implementation Notes For AI Agent

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `docs/ideas/implemented/0001-gift-plan-suggestions-for-recipient.md`
- `gift_manager/models.py` (`GiftSuggestion` model, `State` choices, new `DismissReason` enum)
- `gift_manager/suggestions/service.py` (`GiftSuggestionService.dismiss_suggestion`, `_recipient_filter`)
- `gift_manager/suggestions/catalogue.py` (`_build_profile`, `_item_signal`, catalogue candidate scoring)
- `gift_manager/suggestions/ai/strategy.py` (`_build_rejected_directions`, `_resolve_blocked_names`)
- `gift_manager/suggestions/ai/prompt.py` (`SYSTEM_PROMPT`, `_clean_rejected_directions`, `build_ai_payload`)
- `gift_manager/views/suggestions.py` (`person_suggestion_dismiss`, `group_suggestion_dismiss`, `_handle_dismiss`)
- `gift_manager/templates/gift_manager/includes/gift_suggestion_item.html` (HTMX dismiss split button and forms)
- `gift_manager/tests/suggestions/test_ai_service.py`, `gift_manager/tests/suggestions/test_catalogue_service.py`, and `gift_manager/tests/views/test_suggestions_views.py`

Key technical details:

- **Progressive enhancement & mobile ergonomics:** The split button ensures that
  users on mobile or desktop can tap "Dismiss" directly without interacting with
  the dropdown.
- **Anonymisation:** Any user-entered text in `dismiss_comment` must pass
  through `scrub_text` in `_clean_rejected_directions` before sending to the LLM.
- **Catalogue Profile:** In `catalogue.py:L62-L86`, `_build_profile` can query
  accessible dismissed suggestions for the recipient with `reason="already_owned_or_practiced"`
  and add their tags to the positive profile with an appropriate weight.
- **Migrations:** Add `dismiss_reason` and `dismiss_comment` with `blank=True, default=""`
  to ensure safe, backward-compatible migration.

## Acceptance Criteria

- The Dismiss action is rendered as a split button: direct click dismisses
  immediately as `unspecified`; the dropdown offers standard reasons and a
  custom short text option.
- When a reason (and optional comment) is submitted, both are persisted on the
  `GiftSuggestion` model.
- Dismissals marked as `already_owned_or_practiced` contribute positively to
  matching tag weights in catalogue scoring, while keeping the specific gift
  excluded.
- AI suggestion generation payload includes the dismissal reason and scrubbed
  comment in `rejected_directions`.
- Prompt guidelines instruct the AI model to treat `already_owned_or_practiced`
  as an active hobby signal, recommending accessories, upgrades, or consumables.
- Custom comments containing personal names or emails are scrubbed before reaching
  the external AI provider.
- All unit, integration, and e2e tests pass, covering split button interaction,
  reason persistence, catalogue scoring, and AI payload scrubbing.
- User-facing reason labels and UI elements are localized in French.

## Tag Sibling & Hierarchy Dynamics

- **Dislikes Hierarchy Isolation:** When a suggestion is dismissed with "Not their
  taste" (`dislikes`), the `-INTEREST_SIGNAL` penalty applies to direct tags but does
  not propagate upward to parent/ancestor tags. This prevents disliking a specific
  category or sub-genre (e.g. "Paragliding" under "Sport", or "Horror" under "Books")
  from polluting parent categories and suppressing unrelated sibling branches
  ("Running", "Sci-Fi").
- **Automatic Descendant Cascade:** Because candidate gifts inherit the scores of their
  ancestors during scoring, disliking a category tag (e.g. "Horror") continues
  to automatically apply to its child sub-genres ("Gothic Horror").
- **Multi-Tag Leaf Isolation:** When a dismissed gift is tagged with both a broad container
  tag and a specific sub-tag (e.g. `["Books", "Romance"]`), ancestor tags that have descendants
  on the same gift are shielded, focusing the dislike strictly on the specific leaf tag.
  (If an intermediate tag is unshared with the user, ancestor resolution operates over
  the visible hierarchy).
- **Sole Broad Tag Consideration:** If a dismissed gift is tagged solely with a broad
  root tag (e.g. exclusively "Books" with no sub-tags), that tag receives the negative signal.
  Full-lifecycle history ratings (1–2★ ratings or abandoned plans) continue to propagate
  across the full ancestor hierarchy as verified recipient history.

## Dependencies Or Related Ideas

- `0001-gift-plan-suggestions-for-recipient.md`: Original suggestion system and
  dismissal baseline.
- `0006-recipient-notes-and-interests.md`: Recipient interest tags and notes.

## Open Questions

None identified.
