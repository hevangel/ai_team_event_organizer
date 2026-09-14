"""Loads the AI-attribution footer content from footer.json.

The file is updated by the contributing agent before every commit (see the
pre-commit rule in AGENTS.md), so it is read fresh on every request instead
of cached — a restarted server is never needed after a commit.
"""

import json
from pathlib import Path

FOOTER_FILE = Path(__file__).resolve().parent / "footer.json"

_EMPTY = {
    "repo_url": "",
    "built_by_ai": True,
    "entries": [],
    "totals": {},
    "note": "footer.json missing or invalid",
}


def load_footer() -> dict:
    try:
        data = json.loads(FOOTER_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("footer.json must contain an object")
        return data
    except (OSError, ValueError):
        return dict(_EMPTY)
