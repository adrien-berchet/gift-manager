---
paths:
  - "gift_manager/templates/**/*.html"
  - "gift_manager/static/**/*.js"
  - "gift_manager/static/**/*.css"
---

# Frontend Rules

- Match existing Bootstrap, HTMX, Grid.js, and vanilla JavaScript conventions.
- Keep HTMX partials under `gift_manager/templates/gift_manager/includes/`.
- Preserve non-JavaScript fallbacks when changing forms or navigation.
- Verify layout-sensitive changes with Playwright when possible.
- Keep user-facing strings translation-ready.
