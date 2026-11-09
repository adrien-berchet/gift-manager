# Idea: Browser Bookmarklet For Quick Gift And Wish Entry

## Status

Proposed

## Summary

Provide an installable browser bookmarklet ("Add to Gift Manager") that users can drag to their browser's bookmarks bar. When clicked while browsing any online retail store, the bookmarklet extracts product metadata client-side (title, canonical URL, price, and currency from Open Graph tags, Twitter cards, or Schema.org JSON-LD scripts) and opens Gift Manager in a new tab with those fields pre-filled. The user can choose to save the product either as a personal wish on their wishlist or as a planned gift for a recipient via the guided plan creation flow.

By performing metadata extraction entirely within the user's browser, this approach bypasses the severe challenges of server-side scraping on serverless hosting (such as Vercel): bot detection, CAPTCHAs, IP address blocks from cloud providers, SSRF risks, and serverless execution timeouts.

## Motivation

When browsing online shops (Amazon, Etsy, local boutiques, bookstores), copying and pasting product titles, links, prices, and notes into Gift Manager is repetitive and friction-heavy. Users frequently defer capturing gift ideas or wishes because of this manual effort.

Platforms like GiftList solve this with browser extensions. However, server-side URL unfurling inside Gift Manager is technically fraught because production is deployed on Vercel serverless functions, where scraping external e-commerce sites leads to Cloudflare/bot blocks, IP bans, and request timeouts. A lightweight, client-side browser bookmarklet runs directly inside the user's authenticated browser session on their home IP address, reading already-rendered DOM metadata without server overhead, external scraper infrastructure, or scraping risks.

## User Value

- Users save gift ideas and personal wishes in seconds while shopping online.
- Eliminates manual typing of product titles, URLs, and prices.
- Seamless gift planning: feeds directly into the guided gift plan flow (`relation_guided_create`), allowing the user to pick a recipient, event, and surprise status immediately.
- Zero-installation barrier: works across desktop browsers (Chrome, Firefox, Safari, Edge) without requiring third-party extension store reviews, developer accounts, or extension installations.
- Fast and reliable: bypasses anti-bot blocks and cloud IP bans since it runs in the user's browser on the page they are viewing.

## Possible Scope

- A "Browser Bookmarklet" section on the user's profile or display settings page (`gift_manager/templates/gift_manager/profile_detail.html`) with an interactive drag-and-drop link (`javascript:...`) and clear setup instructions.
- Client-side extraction logic in the bookmarklet:
  - Canonical URL (`link[rel='canonical']` or `window.location.href`).
  - Title (`meta[property='og:title']`, `meta[name='twitter:title']`, or `document.title`).
  - Price hint and currency (`meta[property='og:price:amount']`, `meta[property='product:price:amount']`, `meta[property='og:price:currency']`, or JSON-LD `offers.price` and `offers.priceCurrency`).
  - Optional short description (truncated to ≤150 characters to avoid marketing copy, or left empty for manual notes).
- A small authenticated landing page (e.g. `capture/`) that receives the extracted fields as query parameters, shows a preview, and offers two buttons: "Add to my wishlist" and "Plan for someone". The bookmarklet always opens this single URL, so it never shows a `confirm()`/`prompt()` inside the shop's page and its code stays small and stable when the target flows change.
- Target flows reached from the landing page via query parameters:
  - **Plan for a recipient (primary)**: `RelationGuidedCreateView` (`relations/guided/`, named `gift_manager:relation_guided_create`), pre-filling the gift step's new-gift sub-form (name, URL, and price).
  - **Wish for me**: `WishCreateView` (`profile/wishlist/add/`, named `gift_manager:wish_create`), pre-filling `title`, `url`, `price_hint`, and `notes`.
  - **Standalone catalog gift (fallback)**: `GiftCreateView` (`gifts/create/`, named `gift_manager:gift_create`), pre-filling `name`, `url`, and `price`.
- Currency verification:
  - The bookmarklet passes detected currency alongside the price. The landing page compares it against `Profile.currency` (EUR, USD, GBP, CHF or CAD; default EUR); if currencies differ, price is left blank to avoid currency unit confusion (e.g. interpreting $50 USD as 50€).

## Out Of Scope

- Browser extensions packaged for Chrome Web Store or Firefox Add-ons (can follow later if the bookmarklet proves popular).
- Mobile share target / share sheet integration (requires an installable PWA or native wrapper; deferred per `0014`).
- Local product image uploads and image hosting (deferred per `0004`).
- Server-side headless browser or background scraper workers.

## Implementation Notes For AI Agent

- Form and view pre-filling:
  - Guided flow: inspect `RelationGuidedCreateView` in `gift_manager/views/relation_guided.py` and `GuidedGiftForm` in `gift_manager/guided_plan.py`. The flow has three steps (recipient, gift, occasion); one step is rendered per request and the answers of the other steps travel as hidden inputs. `get()` currently renders an empty step (`self._initial_form(step, {})`). Reuse this mechanism instead of adding a parallel pre-fill path: pass `request.GET` as the initial data so the values are carried from step 1 to step 2, using the existing input names of the gift step — the chooser mode `gift_mode=new` and the prefixed `GiftForm` sub-form fields `new_gift-name`, `new_gift-url`, `new_gift-price`.
  - Currency is checked once, on the landing page, which drops the price before redirecting when it does not match `Profile.currency`. The target views then only receive already-checked values.
  - Inspect `WishCreateView` in `gift_manager/views/wishlist.py` and `WishForm` in `gift_manager/forms.py`. Accept `title`, `url`, `price_hint`, and `notes` from `request.GET` as initial data.
  - Inspect `GiftCreateView` in `gift_manager/views/gift.py` and `GiftForm` in `gift_manager/forms.py` (fields `name`, `comment`, `url`, `price`, `tags`).
- Bookmarklet generation:
  - The bookmarklet code should be rendered on the user's profile page (`gift_manager/templates/gift_manager/profile_detail.html`) or settings.
  - The JavaScript payload should be minified and URI-encoded, referencing the active host (`request.build_absolute_uri('/')`).
  - The bookmarklet only extracts metadata and opens the landing page in a new tab; the wish-or-plan choice is made on the landing page, not in the shop's page.
  - The landing page requires login; Django's login redirect keeps the query string in `next`, so the extracted values survive a login.
  - Keep query parameters within standard 2048-character URL length limits.
- Security:
  - Validate and sanitize incoming GET query parameters through standard Django form validation (`forms.URLField`, decimal parsing for prices).
  - No privileged tokens or CSRF exemptions are needed: the bookmarklet opens a normal authenticated GET view in a new browser tab.

Recommended starting context:

- `docs/ai/architecture.md`
- `gift_manager/views/relation_guided.py`
- `gift_manager/guided_plan.py`
- `gift_manager/views/wishlist.py`
- `gift_manager/views/gift.py`
- `gift_manager/forms.py`

## Acceptance Criteria

- A user can drag the bookmarklet link from their profile page to their browser bookmarks bar.
- Clicking the bookmarklet on a product page with Open Graph / Schema.org metadata opens the Gift Manager landing page in a new tab; choosing "Add to my wishlist" or "Plan for someone" opens `WishCreateView` or `RelationGuidedCreateView` with product title, URL, and price pre-filled.
- In the guided flow, the pre-filled gift values survive the recipient step and appear in the gift step's new-gift form.
- If the detected shop currency does not match the user's currency, the price field is left empty rather than populated with a mismatched numerical value.
- If a shop lacks Open Graph metadata, fallback values (`document.title`, `location.href`) are populated gracefully.
- GET parameters are strictly validated; invalid URLs or prices fall back to empty fields without raising 500 errors.
- Unit and view tests verify the landing page (currency check, both buttons) and query-parameter pre-filling on `RelationGuidedCreateView`, `WishCreateView`, and `GiftCreateView`.

## Dependencies Or Related Ideas

- Builds on `0028` (Wishlists And Collaborative Gift Giving) and `0016` (Guided Gift Plan Creation).
- Complementary to `0004` (Richer Gift Details), which introduced price and URL on gifts.

## Open Questions

- None identified.
