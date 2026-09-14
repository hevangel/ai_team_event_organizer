"""SQLite access: schema, connections and key/value settings helpers.

One connection per operation (cheap for SQLite) keeps things safe across
FastAPI's request threadpool. WAL mode allows concurrent readers.
"""

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import CONFIG

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    is_admin     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS time_slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS availability (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    slot_id INTEGER NOT NULL REFERENCES time_slots(id) ON DELETE CASCADE,
    level   TEXT NOT NULL DEFAULT 'yes',
    PRIMARY KEY (user_id, slot_id)
);

CREATE TABLE IF NOT EXISTS venues (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL CHECK(type IN ('food', 'activity')),
    description    TEXT NOT NULL DEFAULT '',
    estimated_cost REAL,
    address        TEXT NOT NULL DEFAULT '',
    lat            REAL,
    lng            REAL,
    suggested_by   TEXT,
    slot_ids       TEXT NOT NULL DEFAULT '[]',
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    user_id            TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    food_venue_ids     TEXT NOT NULL DEFAULT '[]',
    activity_venue_ids TEXT NOT NULL DEFAULT '[]',
    updated_at         TEXT NOT NULL
);
"""

SESSION_COOKIE = "session"

DEFAULT_SETTINGS: dict[str, Any] = {
    "event_title": "Team Event",
    "event_description": "",
    # Set at startup via `--admin USERID` (or first login when absent).
    "admin_user_id": None,
    "budget_amount": None,
    "budget_type": "per_head",  # per_head | total
    "headcount_limit": None,
    "preference_mode": "simple",  # simple (available yes/no) | strong_weak
    "allow_venue_suggestions": True,
    "anonymous_voting": False,
    "hide_live_counts": False,
    "show_footer_to_voters": True,
    "voting_closes_at": None,  # ISO local datetime string, e.g. 2026-09-20T18:00
    "voting_closed": False,  # manual close switch
    "office_address": "",
    "office_lat": None,
    "office_lng": None,
    "google_maps_api_key": "",
}

# Keys the admin is allowed to change through the API (admin_user_id is
# reserved for the --admin startup flag / first-login rule).
ADMIN_SETTING_KEYS = [
    "event_title",
    "event_description",
    "budget_amount",
    "budget_type",
    "headcount_limit",
    "preference_mode",
    "allow_venue_suggestions",
    "anonymous_voting",
    "hide_live_counts",
    "show_footer_to_voters",
    "voting_closes_at",
    "voting_closed",
    "office_address",
    "office_lat",
    "office_lng",
    "google_maps_api_key",
]


def connect() -> sqlite3.Connection:
    CONFIG.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CONFIG.db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------- settings

def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    stored = {
        row["key"]: json.loads(row["value"])
        for row in conn.execute("SELECT key, value FROM settings")
    }
    merged = dict(DEFAULT_SETTINGS)
    for key, value in stored.items():
        if key in merged or key not in DEFAULT_SETTINGS:
            merged[key] = value
    return merged


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


# ------------------------------------------------------------------- utils

def rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
