# Session record — issue #1 audit bugfixes

- **Captured:** 2026-09-15 (last update 2026-09-16 00:10 local)
- **Agent / model:** Kiro, Claude Opus 5
- **Conversation chain UUID:** not available — this Kiro session did not expose a
  conversation UUID to the agent and no `.mimosa/hook-state/sess_*.json` file was
  written for it (the newest one, `sess_1753ab80-37de-4f10-877d-eada84b44314`, is
  from the 2026-09-14 run). Recorded as unknown rather than invented; a future
  turn in this same chain should update *this* file rather than create a new one.
- **Repo state:** branch `fix/issue-1-audit-bugfixes`, cut from `main` @ `854478b`.

## Request

"Read the github issue of the repo and apply the bugfix", then commit and push.

## Work completed

GitHub issue [#1](https://github.com/hevangel/ai_team_event_organizer/issues/1)
listed 15 audit findings. All 15 were implemented (the issue's own "fixes are
implemented in the working tree" claim referred to the reporter's tree; this
repo had none of them).

| # | Finding | Where |
| - | ------- | ----- |
| 1 | `AutocompleteService.getPredictions` doesn't exist → `getPlacePredictions`; debounce cancelled on pick; Places session token cleared after `getDetails`; typed-but-unpicked address no longer dropped | `frontend/src/components/AddressSearch.tsx` |
| 2 | Venue text interpolated into InfoWindow HTML → DOM nodes + text nodes; `markerKey` now includes venue text | `frontend/src/components/MapPanel.tsx` |
| 3 | Okta callback mutated the injected `Response` then returned another one, losing `Set-Cookie` → one redirect response carrying session cookie + cleared state cookie | `backend/app/routes/api.py`, `backend/app/auth.py` |
| 4 | `id_token` nonce never checked → nonce is the login `state`, verified with `compare_digest` | `backend/app/auth.py` |
| 5 | MCP trusted a bare `user_id` in SSO mode → session (cookie or bearer) required and must match the userid | `backend/app/mcp_server.py`, `service.py`, `McpSetup.tsx`, `README.md` |
| 6 | Malformed ids / costs / coordinates / settings reached business logic → shared `_require_*` validators, `ApiError(422)` | `backend/app/service.py` |
| 7 | Duplicate venue ids stored twice and counted twice | `backend/app/service.py` |
| 8 | Empty ballots bypassed the headcount limit; check+insert not serialized → limit applies to every new vote, `BEGIN IMMEDIATE` on save | `backend/app/service.py` |
| 9 | Schedule replace recreated every slot id, orphaning availability and venue compatibility → reconcile by `(date, start, end)`, dedupe, prune `venues.slot_ids` | `backend/app/service.py`, `AdminPanel.tsx`, `App.tsx` |
| 10 | Deactivation / re-categorization / removal left stale ids in saved votes → single `_strip_venue_from_votes` path | `backend/app/service.py` |
| 11 | Anonymous admin view still returned per-voter ballots → aggregate only, no `people` rows | `backend/app/service.py` |
| 12 | Offset-aware deadline vs naive `now()` raised `TypeError` → `_as_aware()` normalization | `backend/app/service.py` |
| 13 | Voter drafts kept slots/venues an admin had deleted → prune effect on poll | `frontend/src/App.tsx` |
| 14 | Schedule dirty-state compared counts only; temp slots shared `id: -1` → content fingerprint + distinct temp ids | `frontend/src/components/AdminPanel.tsx` |
| 15 | Vite blocked the deployment hostname and hardcoded the proxy port → `allowedHosts`, `VITE_API_TARGET` | `frontend/vite.config.ts` |

Docs updated as part of the change: `AGENTS.md` (new invariants in "Rules
encoded in service.py", frontend notes, verification section), `README.md`
(MCP "Agent identity" section, check count), and `backend/app/footer.json`
(mandatory pre-commit entry + recomputed totals).

## Validation status

- `cd backend && uv run python scripts/smoke_test.py` → **106 passed, 0 failed**
  (61 pre-existing checks kept passing; 45 new regression checks added, one per
  finding that is observable from the backend).
- `cd frontend && npm run build` (includes `tsc -b`) → clean. Bundle inspected
  to confirm `getPlacePredictions` is present and `getPredictions(` is gone.
- Concurrency check proven meaningful: with `BEGIN IMMEDIATE` disabled, all 6
  racers claimed 2 seats (repeated 3×); restored, exactly 2 succeed.
- Okta is covered by a **mocked** tenant (fake `httpx`/`jwt` in `okta_checks`),
  not a real Okta round-trip — that still needs a walkthrough at work.
- **Not** re-verified in a browser this session, and Google Maps / Places was
  not exercised live (no API key used here), so findings 1, 2, 13 and 14 are
  verified by build and code review only.

## Model-call evidence / cost

Kiro does not expose exact per-model token totals to the agent, so no exact
counts are recorded here. Available evidence: this was a single Kiro Vibe
session on Claude Opus 5 with roughly 55 tool invocations (file reads, edits,
`git`, `uv`, `npm`). The `footer.json` entry for 2026-09-15 carries an
agent-estimated 415k in / 47k out / $1.9, flagged `"estimated": true` as
required by AGENTS.md — those are estimates, not billing data.

## Duration

Single continuous session on 2026-09-15 (roughly 23:30 → 00:10 local by the
build and smoke-test timestamps).
