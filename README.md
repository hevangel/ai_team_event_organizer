# 🎉 AI Team Event Organizer

A single-page webapp where a team organizes and votes on events — with a twist:
**everything a human can do in the GUI, an AI agent can do too** through an
[MCP](https://modelcontextprotocol.io) server. Say *"I'm not free after 3pm
any day, and I'm good Mon/Wed"* to your agent and it votes for you.

Humans pick their availability on a visual calendar (never a list of
checkboxes), then vote on food places and activities — live, alongside
everyone else.

## Features

- **Testing-mode login** — type a userid and you're in (trusted, no passwords).
  **Okta SSO** is wired up (OIDC authorization-code flow) for production use.
- **Admin** (designated at server start, or automatically the first person to
  log in) configures: budget (per-head or total), headcount limit
  (first-come-first-served), date/time slot options, office location + venues
  on a Google map, live venue suggestions, anonymous voting, hidden live
  counts, and when voting closes. Admins can also promote other users to
  admin (People tab) — with guardrails: no self-demotion, last admin can't be
  removed.
- **Voters** mark which slots they can make (optionally with strong/weak
  preference), vote for food & activity venues, and can suggest new venues
  live — suggestions are tagged with who suggested them.
- **Live results** — see who's free when and who voted for what in real time,
  filtered by the admin's privacy choices (anonymity hides identities from
  everyone, including the admin).
- **Changeable until close** — everyone can edit their vote until voting
  closes; only the current vote is kept.
- **Agent access** — a [FastMCP](https://gofastmcp.com) server (v4+) at `/mcp`
  exposes every GUI capability to AI agents.
- **AI-attribution footer** — repo link plus which AI agent built the app and
  roughly how many tokens/dollars have been spent so far (logged in
  `backend/app/footer.json`, updated before every commit — see the
  pre-commit rule in [AGENTS.md](AGENTS.md)). Always visible to the admin;
  the admin chooses whether voters see it.

## Stack

| Layer    | Tech                                                                |
| -------- | ------------------------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, SQLite (WAL), FastMCP v4, uv                  |
| Frontend | Vite, React 19, TypeScript, Tailwind CSS 4                          |
| Maps     | Google Maps JS + Places (optional; degrades gracefully without)     |
| Auth     | Testing-mode userid or Okta SSO (OIDC + JWKS verification)          |

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/) and Node.js 20+.

```bash
# 1. Backend (creates the SQLite DB automatically)
cd backend
uv sync
uv run python -m app --admin yourname        # add --host 0.0.0.0 to expose

# 2. Frontend — production build served by the backend (port 8000)
cd ../frontend
npm install
npm run build
# -> open http://127.0.0.1:8000
```

The first person to sign in becomes the admin (or the `--admin` user does).
An admin panel gear icon appears in the header; on a fresh event the admin
view opens automatically.

### Development (hot reload)

```bash
# terminal 1
cd backend && uv run python -m app --reload
# terminal 2
cd frontend && npm run dev
# -> open http://localhost:5173 (Vite proxies /api and /mcp to :8000)
```

### Configuration

Copy `.env.example` to `.env` (or export the vars) for Okta and Google Maps
settings. Nothing is required for local testing. A Google Maps API key needs
"Maps JavaScript API" + "Places API" enabled; without a key the app still
works — venues are managed by address and the map shows a friendly placeholder.

## AI agents (MCP)

Point any MCP client at:

```
http://localhost:8000/mcp
```

The login page shows ready-to-copy setup commands for **Claude Code**
(`claude mcp add --transport http …`) and **Codex** (`codex mcp add …`), using
the address you're browsing to by default. If the server is reachable under a
different name (reverse proxy, LAN hostname), override what's displayed at
startup:

```bash
uv run python -m app --mcp-hostname events.example.com --mcp-port 443 --mcp-subpath team
```

### Agent identity

Every tool takes a `user_id` — the agent acts as that person. How that claim is
authenticated depends on the login mode:

- **Testing mode** (`TESTING_MODE=true`, the default): the `user_id` is trusted
  at face value, exactly like typing your userid on the login page. An MCP call
  counts as a login, so it also creates the user and applies the
  first-login-becomes-admin rule.
- **SSO mode** (`TESTING_MODE=false`): a userid alone is not accepted, otherwise
  any MCP client could impersonate a voter or an admin. Sign in to the webapp
  first, then send that session with the call — either the `session` cookie or
  the same token as `Authorization: Bearer <token>`. The server verifies the
  session belongs to the submitted `user_id` and rejects missing, expired or
  mismatched sessions.

  ```bash
  claude mcp add --transport http \
    --header "Authorization: Bearer $TEAM_EVENT_TOKEN" \
    team-event https://events.example.com/mcp
  ```

Tools:

| Tool                  | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `get_state`           | Everything: settings, slots, venues, your vote, filtered results |
| `save_vote`           | Save availability + venue picks (same as the Save button)        |
| `suggest_venue`       | Suggest a food/activity venue live                               |
| `admin_set_settings`  | Budget, headcount, privacy, close time, office location, …       |
| `admin_set_slots`     | Replace the date/time schedule                                   |
| `admin_add_venue` / `admin_update_venue` / `admin_remove_venue` | Manage venues |
| `admin_list_users`    | List known users with their admin flags                          |
| `admin_set_admin`     | Grant/revoke admin for another user                              |
| `admin_close_voting`  | Close / re-open voting                                           |
| `admin_get_votes`     | Detailed vote view (anonymity-aware)                             |

Typical agent flow: `get_state` → map the user's natural language onto slot
ids → `save_vote`. *"I'm good Mon/Wed but not after 3pm"* becomes: find the
Mon/Wed slots ending before 15:00 and save those ids.

## Tests

```bash
cd backend && uv run python scripts/smoke_test.py
```

106 checks covering login/admin promotion, settings, slots, venue CRUD,
voting, privacy modes, closing, admin management (promote/demote and its
guardrails), the attribution footer, the MCP display-URL override, and every
MCP tool — plus the audit regressions: input validation (422s), vote
de-duplication, headcount enforcement under concurrency, slot-id preservation
across schedule edits, stale-vote cleanup, anonymous aggregate-only results,
offset-aware deadlines, the Okta cookie/nonce handling (mocked tenant) and MCP
session authentication in SSO mode.

## Project layout

```
backend/
  app/
    main.py         FastAPI app: REST + mounted MCP + static frontend
    mcp_server.py   FastMCP v4 tools (mirror of the GUI)
    service.py      Business logic shared by REST and MCP
    db.py           SQLite schema + settings store
    auth.py         Sessions, Okta OIDC flow
    routes/         /api (voter) and /api/admin endpoints
    __main__.py     uv run python -m app [--admin USER]
  scripts/smoke_test.py
frontend/
  src/
    App.tsx             State, polling, save bar, layout
    components/
      AvailabilityGrid  Calendar-style availability picker
      VenueSection      Food/activity voting + live suggestions
      MapPanel          Google Maps wrapper (office + venue markers)
      ResultsPanel      Status + live/final results sidebar
      AdminPanel        Event / schedule / locations / votes tabs
    api.ts, types.ts    Typed API client
```

## Notes & honest limitations

- **Anonymity is real anonymity**: when enabled, who-voted-what is hidden from
  admins too (counts only). Turn it off if you need attendee names.
- Testing-mode login trusts the userid typed — that's the point; it's for
  home/trial use. Flip `TESTING_MODE=false` once Okta works.
- SQLite is per-server; this is a team tool, not a multi-instance service.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — short version: **humans don't write
code here**; all changes are authored by AI agents and go through the normal
PR flow.

## License

[MIT](LICENSE)
