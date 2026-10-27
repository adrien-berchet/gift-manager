# Idea: Recipient Preference Profiles And Feedback Persistence

## Status

Implemented

Plan: `docs/superpowers/plans/2026-10-22-recipient-preference-profiles.md`

## Summary

Build durable, cumulative recipient preference profiles from their entire gift history and provide lightweight, opt-in actions to persist feedback (e.g. from dismissed suggestions or abandoned plans) directly into the recipient's profile notes or interests.

Currently, suggestion generation caps historical plans to the 50 most recent items and dismissed ideas to 15 items, meaning long-term constraints or preferences from older plans fade from the AI context. Furthermore, valuable signals entered when dismissing a suggestion or abandoning a plan (such as allergy notes, lifestyle changes, or strong dislikes) remain tied to ephemeral records rather than being promoted to the recipient's permanent profile. This idea introduces:
1. An aggregated recipient profile summary (synthesizing all-time positive/negative tag affinities and constraints) to feed suggestion models efficiently without prompt bloat.
2. An opt-in mechanism to persist notes or adjust interest tags on the recipient's profile when dismissing a suggestion or marking a plan as abandoned.

## Motivation

Gift Manager collects high-value signals across multiple workflows:
- Ratings (1–5) and reaction notes on given plans.
- Reasons and comments on abandoned plans (e.g. "Too expensive", "Allergic to wool", "Already has one").
- Structured dismissal reasons and custom comments on gift suggestions (Idea 0026).

However, these signals currently stay fragmented:
- **Context window limits:** Because `build_ai_payload` caps history at 50 items and dismissals at 15 items to control latency, cost, and LLM attention, insights from older plans eventually fall out of the prompt.
- **Lost negative signals:** If a user abandons a plan with a note like "Stopped drinking alcohol", that detail is stored only on that specific plan and is not elevated to the recipient's profile notes, requiring the user to manually copy it over.
- **Siloed suggestion feedback:** Suggestion dismissals are private to the requesting user (`GiftSuggestion`), while recipient notes and interests are shared across all planners who collaborate on that recipient. Providing a seamless way to promote a private dismissal note into a shared recipient note ensures collaboration benefits from individual research.

## User Value

- **Gift planners:** Do not have to remember to manually navigate to the Person edit page to record preferences discovered while planning, discarding, or reviewing gifts.
- **Recipients:** Benefit from higher quality, better-calibrated suggestions over multi-year periods because permanent constraints (allergies, hard dislikes, preferred styles) are never forgotten regardless of how many gifts have been given since.
- **Collaborating groups:** Planners sharing a recipient benefit immediately when one planner records a key discovery through a plan abandonment or suggestion dismissal.
- **Performance & Cost:** Summarized, aggregated preference representations provide richer context to LLMs using a fraction of the token budget compared to sending dozens of raw transaction logs.

## Implemented Scope

- **Aggregated History Profile for Suggestion Engine:**
  - Deterministic preference aggregator in `gift_manager/suggestions/history.py` (`PreferenceProfile`, `build_preference_profile`) computing all-time tag affinities across 100% of the recipient's history (liked, owned/practiced, disliked).
  - Compact profile included in `build_ai_payload` alongside recent raw items with bumped `PROMPT_VERSION = 3`.
  - Line-aware `window_person_notes` preserving up to 400 chars of baseline bio plus recent provenance lines up to 800 chars total budget, scrubbing sensitive terms prior to truncation.
- **Promoting Suggestion Dismissals to Recipient Profile:**
  - Suggestion dismissal dropdown includes an opt-in checkbox to remember the preference in recipient's profile (`promote_to_profile`).
  - Appends formatted provenance note `[YYYY-MM-DD - Suggestion: <Item>]: <Comment>` to `Person.notes`.
  - For "Already owned or practiced" dismissals, promotes visible tags into `Person.interests`.
- **Promoting Plan Reactions to Recipient Profile:**
  - `RelationForm` and `relation_reaction` views support opt-in promotion checkboxes.
  - Automatically appends provenance note (`[YYYY-MM-DD - Abandoned gift plan: <Gift>]: <Comment>` or `[YYYY-MM-DD - Gift plan: <Gift>]: <Reaction>`).
  - Automatically promotes gift tags to `Person.interests` for 4–5★ reactions.
- **Privacy & Safety Guards:**
  - `promotion_target` helper strictly enforces that only individual recipients (`Person`) with edit permissions can be updated.
  - Secret surprise plans (`is_surprise=True`) and group plans are strictly blocked from promoting notes to prevent privacy leaks.
  - Profile notes remain completely hidden from non-planners / recipients who have a linked user account in view mode.
- **Localization:**
  - Full French translation for all new user-facing strings and notifications.

## Dependencies Or Related Ideas

- Related to `docs/ideas/implemented/0001-gift-plan-suggestions-for-recipient.md` (initial suggestions engine).
- Related to `docs/ideas/implemented/0006-recipient-notes-and-interests.md` (recipient notes and interests model).
- Related to `docs/ideas/implemented/0026-dismiss-reasons-for-gift-suggestions.md` (suggestion dismissal reasons and comments).
