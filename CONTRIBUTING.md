# Contributing

## 🤖 This repo is AI-authored — humans don't write code here

**Contributors must not hand-write code changes.** All code, tests, docs and
configuration in this repository are written and modified by AI coding agents
(e.g. ZCode, Claude Code, Codex, Cursor). Working here means *directing* an
agent, not typing the diff yourself.

Why: this project is deliberately built as a demonstration of agent-first
development — the GUI is for humans, the codebase is maintained by agents.
Keeping authorship uniform keeps the guardrails (AGENTS.md conventions, agent
runnable smoke tests) honest.

### What this means in practice

1. **Use an AI agent for every change** — features, fixes, refactors,
   dependency bumps, even typo fixes in docs. Open your agent in this
   workspace and let it edit; [AGENTS.md](AGENTS.md) tells it how the repo is
   organized.
2. **PRs follow the normal rules.** AI authorship changes nothing about the
   process:
   - one logical change per PR, with a clear title and description;
   - `backend`: `uv run python scripts/smoke_test.py` must pass;
   - `frontend`: `npm run build` (includes `tsc -b`) must pass;
   - a human reviews and approves every PR before merge (human review of
     agent-written code is always in scope);
   - CI/reviewers may ask the agent for changes — iterate through the agent,
     don't patch by hand.
3. **Be transparent**: mention which agent produced the change in the PR
   description if it isn't obvious from the branch.
4. Commits must pass the checks above; keep the diff minimal and focused.

### Not allowed

- Pushing hand-edited code, even "just a one-liner".
- Committing generated artifacts (`backend/data/`, `frontend/dist/`,
  `node_modules/`, `.venv/`) — see [.gitignore](.gitignore).
- Bypassing review because "the agent wrote it and agents are careful".

## Setup for contributors (and their agents)

```bash
cd backend && uv sync && uv run python scripts/smoke_test.py
cd ../frontend && npm install && npm run build
```

Agents: read [AGENTS.md](AGENTS.md) first — it documents architecture,
conventions and gotchas for you.
