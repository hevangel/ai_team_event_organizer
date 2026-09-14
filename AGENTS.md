# AI Team Event Organizer — Agent Handbook

This file has two parts: **1) the product spec** (requirements, unchanged) and
**2) implementation notes for AI agents** (you, in a future session). Read
both before changing anything. Also read [CONTRIBUTING.md](CONTRIBUTING.md):
this repo is AI-authored; changes go through normal PR flow.

---

## Part 1 — Product spec (requirements)

This is a webapp that allows both real humans and humans-via-AI-agent to
organize and vote for team events. Whatever function a human can do on the
GUI, an AI agent can do via the MCP server (or the REST API).

- Single page webapp. Before login, just a login screen. Okta SSO is wired up
  but can't be tested from a home PC (fix at work). In testing mode, a user
  just types their userid — we trust everyone is honest and no one makes typos.
- All data lives in a local SQLite database.
- The organizer designates the admin when starting the web server. The admin
  can set/change, from the admin page (gear icon):
  - budget (per head or total)
  - headcount limit (first-come-first-served when set)
  - date/timeslot options
  - location: office address centers the voters' map; admin adds multiple
    event venues and marks which date/timeslots each venue is compatible
    with. Optional: allow voters to suggest new venues live. Venues are typed
    **food** or **activity** (an event is usually a meal + doing something
    together; the activity can be optional).
  - anonymous voting, and/or hiding live vote counts during voting
  - when voting closes
- If the admin hasn't set constraints, the first person to log in is the admin
  and the view defaults to the admin view. An existing admin can also grant or
  revoke admin for other users (admin panel People tab, `admin_set_admin`).
- Tasteful, elegant GUI. Date/time setup: pick week(s) or date(s) first, then
  the time slots. Location setup starts with a Google map to search an address
  and accept it.
- Voters see a single page: first pick the date/timeslots they're **available**
  (not the impossible ones — admin can enable strong/weak preference). The
  selection must be visual and calendar-like; a list of click boxes is NOT
  acceptable. Alternatively the user asks their AI agent ("I'm not free after
  3p everyday, I am good Mon/Wed") and the agent talks to the webapp.
- Then they vote on what to do: venues (admin can disable extra suggestions),
  suggestions are tagged with the suggester, description + estimated cost,
  separate food and activity selections on the map.
- If the admin allows it, voters see who voted for what in real time.
- A save button. Votes can be changed any time before close. No history, no
  undo — the DB keeps only the current saved vote.

---

## Part 2 — Implementation notes (for AI agents)

### Stack & commands

- **Backend**: Python 3.12, FastAPI, SQLite (stdlib `sqlite3`, WAL mode),
  FastMCP **v4** (`fastmcp` package, currently 4.0.3), run with **uv**.
- **Frontend**: Vite 8, React 19, TypeScript, Tailwind CSS 4 (`@utility`
  directives in `src/index.css` — composing custom classes with `@apply`
  requires `@utility`, plain classes won't work).
- CLI: `uv run python -m app [--admin USER] [--mcp-hostname H]
  [--mcp-port P] [--mcp-subpath S]` — the `--mcp-*` flags only change the
  MCP URL displayed in the login-page setup hints (`config.mcp_url_override`
  in `/api/state`; null = frontend derives it from `window.location`).
- Backend tests: `cd backend && uv run python scripts/smoke_test.py` (43
  checks; uses a throwaway DB via `DB_PATH` env read at import time — keep
  env-setting **before** `from app.main import app`).
- Frontend build (includes `tsc -b`): `cd frontend && npm run build`.
- Run all: `uv run python -m app [--admin USER] [--port 8000]` +
  `npm run dev` (Vite proxies `/api` and `/mcp`) or `npm run build` and let
  FastAPI serve `frontend/dist`.

### Architecture map

```
backend/app/
  config.py      env config, read once at import (TESTING_MODE, OKTA_*, BASE_URL, GOOGLE_MAPS_API_KEY, DB_PATH)
  db.py          schema + settings key/value store (JSON-encoded); one connection per op, context manager db()
  service.py     ALL business logic — shared by REST and MCP; raises ApiError(status, msg)
  auth.py        session cookies + Okta OIDC (auth-code flow, JWKS-verified id_token)
  routes/api.py    /api: login, /auth/okta/*, logout, /state, PUT /vote, POST /venues
  routes/admin.py  /api/admin: PUT settings, PUT slots, venue CRUD, GET votes
  mcp_server.py  FastMCP tools; `mcp_app = mcp.http_app(path="/")` mounted at /mcp
  main.py        assembly: combined lifespan (mcp_app.lifespan) + init_db + static
  __main__.py    CLI entry (`python -m app`)
```

- **One source of truth**: REST handlers and MCP tools both call
  `service.py`. Never implement logic in a route or tool directly.
- `/api/state` is the one-call bootstrap: public (unauthenticated →
  `authenticated: false` + config/settings), and with session → adds `me`,
  `my_availability`, `my_vote`, privacy-filtered `results`. The SPA polls it
  every 5s; the voter's *draft* selection lives in React state and is only
  sent by the Save button (`PUT /api/vote`).

### Data model (SQLite)

- `settings` — JSON per key, merged over `DEFAULT_SETTINGS`; admin-writable
  keys are whitelisted in `ADMIN_SETTING_KEYS`. `admin_user_id` is reserved
  (set by `--admin` CLI or first-login rule).
- `users`, `sessions` (token in httpOnly cookie), `time_slots` (date +
  start/end `HH:MM`), `availability` (user × slot, level `yes|weak|strong`),
  `venues` (type `food|activity`, `slot_ids` JSON = compatible slots,
  `suggested_by` NULL = admin), `votes` (one row per user: food/activity
  venue id arrays). Deleting a venue strips it from all saved votes.
- Availability rows are only written by `save_vote` — same for venues. There
  is intentionally no vote history.

### Rules encoded in service.py (don't break them)

- **Admin rule**: `--admin USER` stored at startup; that user promoted on
  login. If no designation and no admin exists, **first login wins** (and
  records itself as designated). MCP calls count as logins (`mcp_identity`).
  Admins can promote/demote others (`admin_set_admin`): self-demotion and
  demoting the last admin are rejected; demotion clears the startup
  designation so the login rule can't re-promote the demoted user.
- **Closed voting** = manual `voting_closed` flag OR `now >= voting_closes_at`
  → blocks `save_vote` and `suggest_venue` (403).
- **Results visibility**: anonymous → counts only for *everyone including
  admin*; `hide_live_counts` → voters see nothing until close; admin
  (non-anonymous) always sees full detail. Logic in `compute_results`.
- **Headcount limit**: enforced at save time, first-come-first-served —
  once full, only users with an existing vote may update.
- **Preference mode**: `simple` maps any level to `yes` on save;
  `strong_weak` keeps `strong|weak`.

### MCP (fastmcp v4) gotchas

- fastmcp v4: `await mcp.get_tools()` is gone — use `Client.list_tools()`.
  The in-process client (`Client(mcp)`) is used by the smoke test; real
  clients hit `http://host:port/mcp` (Starlette 307-redirects to `/mcp/`).
- Tool functions are wrapped by `_tool` with `@functools.wraps` (fastmcp
  builds schemas from the signature — keep `functools.wraps`, don't use
  `*args/**kwargs` without it) and translate `ApiError` → `ToolError`.
- The client raises `ToolError` on tool errors; it does **not** return error
  results (the smoke test asserts with try/except).

### Frontend notes

- Tailwind 4: custom classes live in `src/index.css` under `@utility`. Class
  names must appear literally in source (no dynamic `slot-level-${x}`
  strings) or Tailwind won't generate them — see `LEVEL_CLASS` map in
  `AvailabilityGrid.tsx`.
- Google Maps loads lazily (`loadGoogleMaps` in `components/ui.tsx`); without
  a key, `MapPanel` renders a graceful placeholder and address inputs become
  plain text. Key resolution: admin-panel setting (DB) overrides env var.
- Polling never clobbers the unsaved draft: `Draft.loadedFor` re-inits only
  when the signed-in user changes.
- Dev servers: backend 8000, Vite 5173 (proxy). Production: `npm run build`,
  backend serves `dist` (mount skipped at import if dist absent — build
  before start, or restart after building).

### Testing at home (no Okta, no Maps key)

Everything works: testing-mode login, admin panel (schedule picker, venue
CRUD, settings), voting, live suggestions, live results, MCP. Okta needs a
real tenant (`OKTA_*` env vars + redirect URI `{BASE_URL}/api/auth/okta/callback`).
Google Maps needs a key with Maps JavaScript + Places APIs.

### Verified end-to-end (2026-09-13)

Smoke test (61 checks) + full browser walkthrough: first-login admin,
schedule saved via admin panel, office + 2 venues, second voter sees live
results, venue suggestion with suggester tag, save flow, admin votes grid,
MCP over HTTP (`get_state`, `save_vote`, admin guard), AI footer (admin
always / voters configurable), multi-admin management (promote via
People tab, demoted user loses the gear icon immediately, self-demote and
last-admin guardrails), and the login-page MCP hints (address-bar-derived
URL, plus the `--mcp-hostname/--mcp-port/--mcp-subpath` override).

---

## Part 3 — Pre-commit rule (mandatory for every agent, every commit)

Before running `git commit`, the contributing agent **must** update
[`backend/app/footer.json`](backend/app/footer.json) — the file that powers
the webapp's AI-attribution footer (repo link + which agent built it + how
much has been spent so far). The footer is always visible in the admin view;
voters see it only when the admin enables `show_footer_to_voters`.

1. **Append or update your entry** in `entries` (one per session/PR):
   `date` (YYYY-MM-DD), `agent` (tool, e.g. "ZCode CLI"), `model`,
   `work` (one-line summary of what this commit adds), `tokens_in`,
   `tokens_out`, `cost_usd`, and `"estimated": true` unless you have exact
   billing numbers. If you already have an entry for the same work, update it
   instead of appending a duplicate.
2. **Recompute `totals`** as the sum of all entries (keep the `estimated`
   flag). "Spent so far" must always cover the whole history, not just your
   session.
3. Keep the file **valid JSON** — the smoke test asserts `footer.json` loads
   and that `/api/state` exposes it; a broken file fails CI.
4. Update the `work` summary honestly and briefly; reviewers read it.

Then run the standard checks before committing: `uv run python
scripts/smoke_test.py` (backend) and `npm run build` (frontend).

> Enforcement note: since every commit in this repo is authored by an agent
> (see CONTRIBUTING.md), AGENTS.md is the pre-commit hook. Reviewers should
> reject PRs where the footer log wasn't updated for the change it contains.
