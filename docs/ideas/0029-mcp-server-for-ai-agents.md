# Idea: MCP Server So AI Agents Can Use Gift Manager

## Status

Proposed

## Summary

Expose a Model Context Protocol (MCP) server that lets AI agents (Claude Desktop,
Claude Code, or any MCP-capable client) work with a user's Gift Manager data:
listing recipients, gift plans, upcoming occasions and gift history, and later
creating or updating plans. The server would run inside the existing Django project
and be reached over Streamable HTTP, authenticated with a per-user bearer token.
It would reuse the existing service layer and permission rules rather than adding
a parallel data path.

The first slice is read-only. Write tools, if any, come later and only after the
read path and the privacy and authorization rules are proven by tests.

## Motivation

Gift Manager's data is structured (people, relations, gifts, events, tags,
sharing) and most useful questions about it are cross-cutting: "who has no gift
idea for June?", "what did I give Sam last year?", "which plans are still
unclaimed?". Today those questions need the HTML UI. An MCP server gives agents a
typed, discoverable interface to the same data without scraping pages or giving
them database access.

The app has no JSON API today, so this idea also forces a clean boundary between
the domain layer and the views, which benefits other future integrations (mobile
clients, scripts, the calendar feed).

## User Value

- Users who already use an AI assistant can ask about their gift planning in
  natural language and get answers grounded in their real data.
- Agents can prepare work for the user (for example, a list of unclaimed plans
  before a birthday) without the user opening the app.
- Sharing rules keep working: an agent only sees what the token's owner can see,
  including hidden surprise plans that stay hidden from their recipients.
- Self-hosters get a way to automate their own instance without exposing the
  database.

## Possible Scope

First slice (read-only, Streamable HTTP):

- A new `gift_manager/mcp/` package with the MCP server, mounted under a path such
  as `/mcp/` on the existing Django app. Built on the official `mcp` Python SDK.
- Per-user API tokens: created, listed, named, revoked and given an optional expiry
  from the user's account settings. Only a hash is stored; the raw token is shown
  once.
- Bearer-token authentication on every MCP request. Session cookies are not
  accepted on the MCP endpoint.
- Read-only tools, each a thin wrapper over existing querysets or services, for
  example:
  - list and search people (recipients) the user can access;
  - list gift plans with status, recipient, event and claim state;
  - list upcoming occasions, reusing the birthday and occasion helpers;
  - get a recipient's gift history and notes, subject to the same metadata rules
    the UI uses.
- Tool results that are compact, paginated, and labelled as user data.
- A management command or settings flag to enable or disable the MCP endpoint per
  deployment, disabled by default.

Later slices (separate decisions):

- Write tools (create a gift plan, change status, add a comment), each behind
  explicit confirmation on the client side and recorded in an audit log.
- A local stdio transport (`manage.py mcp_stdio`) for self-hosters who run the
  agent on the same machine as their database.
- Per-token scopes (read-only versus read-write) and per-tool allow lists.

## Out Of Scope

- Any tool that deletes records, changes permissions or sharing, or changes
  account and token settings. Agents must not manage access.
- Direct database or SQL access for agents.
- OAuth or an MCP authorization flow for third-party apps in the first slice.
  Personal bearer tokens are enough to start.
- Sending personal data to a model provider on the server side. The MCP server
  returns data to the client the user chose; it does not call an LLM itself.
- Changes to the web UI, templates, or the existing AI suggestion pipeline.
- A separate hosted service that duplicates the permission logic.

## Implementation Notes For AI Agent

The permission rules are the highest-risk part. Every tool must go through the
same paths the web views use, never through `Model.objects.all()`:

- `gift_manager/services.py` (`PermissionService`) is the single source of object
  access decisions. Use the permission facade and `PermissionService` instead of
  adding new access checks.
- Querysets must come from `accessible_by(user)`. Surprise plans are hidden inside
  `RelationQuerySet.accessible_by` and `Relation.objects.hidden_surprises_for(user)`.
  Follow the rules in `docs/ai/architecture.md`, especially the surprise-plan and
  persons-and-accounts notes.
- `Event.is_global` (the Birthday event) is visible to every user; read event names
  with `EventNameField` or `event_display_name` so labels are translated.
- Birthdays and other computed occasions come from `gift_manager/birthdays.py`
  (`Person.next_birthday`), not stored `Event` rows.
- Reminders and calendar feed code (`gift_manager/reminders.py`,
  `gift_manager/calendar_feed.py`) already read through `accessible_by` and show a
  private, token-based feed. Reuse their reading helpers where they fit; they are
  the closest precedent for token-based access.
- `gift_manager/suggestions/ai/prompt.py` shows the existing scrubbing of names,
  emails and database keys. Tool results may need similar care: return what the
  client needs, not everything in the model.
- Token model, hashing and admin or account UI belong in `gift_manager/` with
  migrations reviewed before commit (AGENTS.md).
- Settings: `GiftManager/settings/base.py`. Add the endpoint toggle there, with the
  default off. Check `GiftManager/urls.py` (or `gift_manager/urls.py`) for mounting.
- Dependency: adding `mcp` to `pyproject.toml` is a production dependency. AGENTS.md
  requires a clear reason and a user-visible note.
- Deployment: `vercel.json` routes all paths to `GiftManager/wsgi.py`, and
  `docker-compose.yml` runs the app. A streamable HTTP transport must work with
  Vercel's function timeouts and cold starts, or the endpoint should be served from
  the Docker deployment. Decide the hosting target before writing transport code.
- Tests: add permission-matrix tests (owner, editor, viewer, no access) for each
  tool, plus surprise-plan hiding, token auth failure, revoked and expired tokens,
  and disabled-endpoint behaviour. Use PostgreSQL for query-heavy tests (AGENTS.md).
  Follow `docs/ai/testing.md` and run `tox run -e py311 -- -k mcp`.

Recommended starting context:

- `docs/ai/architecture.md`
- `docs/ai/testing.md`
- `gift_manager/services.py`
- `gift_manager/birthdays.py`
- `gift_manager/calendar_feed.py`
- `gift_manager/reminders.py`
- `gift_manager/suggestions/ai/prompt.py`

## Acceptance Criteria

- With the endpoint enabled and a valid token, an MCP client can connect over
  Streamable HTTP, list the tools, and call each read-only tool.
- Each tool returns only records that `accessible_by(user)` returns for the token's
  owner. Hidden surprise plans never appear, including through counts or
  aggregates.
- Requests without a token, with an unknown token, with a revoked or expired token,
  or with a session cookie only are rejected with 401, and nothing is returned.
- Tokens are stored hashed. The raw token is shown once at creation and cannot be
  retrieved afterwards.
- Users can create, name, list, revoke and set an expiry on their own tokens, and
  cannot see or revoke other users' tokens.
- With the endpoint disabled (default), the MCP path returns 404 and no tool
  logic runs.
- No new tool deletes records or changes permissions or sharing.
- Existing web UI behaviour, permission tests and e2e tests are unchanged.
- Each read tool has a test in the permission matrix (owner, editor, viewer, no
  access), and the suite passes under PostgreSQL.
- Any user-facing string (token page, settings, errors) is translated per AGENTS.md.

## Dependencies Or Related Ideas

- Builds on the existing permission model and the reminders and calendar-feed
  token pattern (idea 0003).
- Benefits from the birthday and occasion helpers (idea 0002) and gift history
  (idea 0005).
- Follow-up candidates, each a separate idea: write tools with audit logging;
  stdio transport for self-hosters; per-token scopes.

## Open Questions

- Hosting target: should the endpoint run on Vercel, on the Docker deployment, or
  both? This decides whether the transport must be stateless.
- Which read tools matter most for a first release? The list above is a proposal.
- Should tool results be limited in size or redacted by default (for example, no
  free-text notes unless requested), given that the data goes to the client's model
  provider?
- Should the user see a warning in the token UI that connected agents send data to
  the model provider they chose?
- Is a single token per user enough, or should each client get its own token so it
  can be revoked separately?
