---
paths:
  - "GiftManager/**/*.py"
  - "gift_manager/**/*.py"
---

# Backend Rules

- Keep permission checks centralized through `PermissionService` or the permission facade.
- Keep form validation in Django forms or services.
- Use queryset/model helpers for reusable data access.
- Review generated migrations before treating them as done.
- Add targeted tests for permission, hierarchy, and sharing behavior.
