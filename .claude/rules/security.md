---
paths:
  - ".env*"
  - "*.pem"
  - "certs/**"
  - "GiftManager/settings/**/*.py"
  - "docker-compose*.yml"
  - "Dockerfile"
---

# Security Rules

- Do not read, edit, or commit real secrets, private keys, or certificates.
- Keep `.env.example` as documentation only.
- Production settings must fail closed for missing required secrets.
- Avoid broad assistant permissions and broad network fetch allowances.
- Be careful with permission, sharing, invitation, and email encryption flows.
