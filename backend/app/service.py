"""Business logic shared by the REST API and the MCP server."""

import json
import secrets
import sqlite3
from datetime import datetime
from typing import Any

from .config import CONFIG
from .db import (
    ADMIN_SETTING_KEYS,
    SESSION_COOKIE,
    db,
    get_settings,
    now_iso,
    set_setting,
)
from .errors import ApiError
from .footer import load_footer

VENUE_TYPES = ("food", "activity")
AVAILABILITY_LEVELS = ("yes", "weak", "strong")


# ------------------------------------------------------------------- users

def _get_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()


def _ensure_user(conn: sqlite3.Connection, user_id: str, display_name: str = "") -> sqlite3.Row:
    row = _get_user(conn, user_id)
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, display_name, is_admin, created_at) VALUES (?, ?, 0, ?)",
            (user_id, display_name or user_id, now_iso()),
        )
        row = _get_user(conn, user_id)
    elif display_name and display_name != row["display_name"]:
        conn.execute(
            "UPDATE users SET display_name = ? WHERE user_id = ?",
            (display_name, user_id),
        )
        row = _get_user(conn, user_id)
    return row


def promote_admin_on_login(conn: sqlite3.Connection, user_id: str) -> bool:
    """Apply the admin rule at login time.

    The organizer may designate the admin at server start (`--admin USERID`);
    that user is promoted when they log in. If nobody was designated and no
    admin exists yet, the first person to log in becomes the admin.
    """
    settings = get_settings(conn)
    designated = settings.get("admin_user_id")
    admin_exists = conn.execute("SELECT 1 FROM users WHERE is_admin = 1").fetchone()
    if designated == user_id:
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        return True
    if designated is None and admin_exists is None:
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        set_setting(conn, "admin_user_id", user_id)
        return True
    return False


def get_user_or_404(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = _get_user(conn, user_id)
    if row is None:
        raise ApiError(404, f"Unknown user: {user_id}")
    return row


def require_admin(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = get_user_or_404(conn, user_id)
    if not row["is_admin"]:
        raise ApiError(403, "Admin access required")
    return row


def mcp_identity(user_id: str) -> str:
    """An MCP call acts for a human, so it counts as a login: create the user
    if needed and apply the first-login-admin rule (same as testing login)."""
    user_id = (user_id or "").strip()
    if not user_id:
        raise ApiError(400, "user_id is required")
    with db() as conn:
        _ensure_user(conn, user_id)
        promote_admin_on_login(conn, user_id)
    return user_id


# ---------------------------------------------------------------- sessions

def create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, now_iso()),
    )
    return token


def user_for_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.user_id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()


def drop_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def login_testing(user_id: str, display_name: str = "") -> dict[str, Any]:
    user_id = user_id.strip()
    if not user_id:
        raise ApiError(400, "userid is required")
    if not CONFIG.testing_mode:
        raise ApiError(403, "Testing-mode login is disabled; sign in with Okta")
    with db() as conn:
        token, user = _login_user(conn, user_id, display_name.strip())
        return {"token": token, "user": user}


def login_okta(user_id: str, display_name: str) -> dict[str, Any]:
    with db() as conn:
        token, user = _login_user(conn, user_id, display_name)
        return {"token": token, "user": user}


def _login_user(
    conn: sqlite3.Connection, user_id: str, display_name: str
) -> tuple[str, dict[str, Any]]:
    # The user row must exist before the admin rule runs.
    _ensure_user(conn, user_id, display_name)
    promoted = promote_admin_on_login(conn, user_id)
    row = _get_user(conn, user_id)
    token = create_session(conn, row["user_id"])
    return token, _user_dict(row, promoted or bool(row["is_admin"]))


def _user_dict(row: sqlite3.Row, is_admin: bool | int) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"] or row["user_id"],
        "is_admin": bool(is_admin),
    }


# ----------------------------------------------------------------- voting

def voting_is_closed(settings: dict[str, Any], at: datetime | None = None) -> bool:
    if settings.get("voting_closed"):
        return True
    closes_at = settings.get("voting_closes_at")
    if not closes_at:
        return False
    at = at or datetime.now()
    try:
        return at >= datetime.fromisoformat(str(closes_at))
    except ValueError:
        return False


def close_reason(settings: dict[str, Any]) -> str | None:
    if settings.get("voting_closed"):
        return "manual"
    if voting_is_closed(settings):
        return "time"
    return None


def _load_vote(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM votes WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return {"food_venue_ids": [], "activity_venue_ids": [], "has_vote": False}
    return {
        "food_venue_ids": json.loads(row["food_venue_ids"]),
        "activity_venue_ids": json.loads(row["activity_venue_ids"]),
        "has_vote": True,
    }


def headcount_taken(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM votes").fetchone()
    return int(row["n"])


def save_vote(
    user_id: str,
    availability: list[dict[str, Any]] | None,
    food_venue_ids: list[int] | None,
    activity_venue_ids: list[int] | None,
) -> dict[str, Any]:
    """Replace the caller's current vote. This is the 'save button'."""
    with db() as conn:
        user = get_user_or_404(conn, user_id)
        settings = get_settings(conn)
        if voting_is_closed(settings):
            raise ApiError(403, "Voting is closed; your selection can no longer be changed")

        availability = availability or []
        food_venue_ids = [int(v) for v in (food_venue_ids or [])]
        activity_venue_ids = [int(v) for v in (activity_venue_ids or [])]

        # Validate availability levels against the preference mode. In simple
        # mode anything maps to plain "yes".
        simple = settings.get("preference_mode", "simple") == "simple"
        clean_availability: list[tuple[int, str]] = []
        seen_slots: set[int] = set()
        for item in availability:
            slot_id = int(item["slot_id"])
            if slot_id in seen_slots:
                continue
            seen_slots.add(slot_id)
            level = str(item.get("level", "yes"))
            if level not in AVAILABILITY_LEVELS:
                raise ApiError(422, f"Invalid availability level: {level}")
            if simple:
                level = "yes"
            clean_availability.append((slot_id, level))
        valid_slots = {
            row["id"]
            for row in conn.execute("SELECT id FROM time_slots")
        }
        unknown = seen_slots - valid_slots
        if unknown:
            raise ApiError(422, f"Unknown time slot ids: {sorted(unknown)}")

        # Validate venue picks.
        for venue_type, ids in (("food", food_venue_ids), ("activity", activity_venue_ids)):
            if not ids:
                continue
            placeholders = ",".join("?" * len(ids))
            found = {
                row["id"]
                for row in conn.execute(
                    f"SELECT id FROM venues WHERE type = ? AND active = 1 AND id IN ({placeholders})",
                    (venue_type, *ids),
                )
            }
            missing = set(ids) - found
            if missing:
                raise ApiError(422, f"Unknown or inactive {venue_type} venue ids: {sorted(missing)}")

        # Headcount limit is first-come-first-served: once full, only people
        # who already have a saved vote may update theirs.
        limit = settings.get("headcount_limit")
        existing = conn.execute(
            "SELECT 1 FROM votes WHERE user_id = ?", (user["user_id"],)
        ).fetchone()
        if (
            limit
            and existing is None
            and (food_venue_ids or activity_venue_ids or clean_availability)
            and headcount_taken(conn) >= int(limit)
        ):
            raise ApiError(403, f"Headcount limit reached ({limit}); the event is full")

        conn.execute("DELETE FROM availability WHERE user_id = ?", (user["user_id"],))
        conn.executemany(
            "INSERT INTO availability (user_id, slot_id, level) VALUES (?, ?, ?)",
            [(user["user_id"], slot_id, level) for slot_id, level in clean_availability],
        )
        conn.execute(
            "INSERT INTO votes (user_id, food_venue_ids, activity_venue_ids, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET food_venue_ids = excluded.food_venue_ids, "
            "activity_venue_ids = excluded.activity_venue_ids, updated_at = excluded.updated_at",
            (
                user["user_id"],
                json.dumps(food_venue_ids),
                json.dumps(activity_venue_ids),
                now_iso(),
            ),
        )
        return {"saved": True, "slots": len(clean_availability)}


def suggest_venue(user_id: str, fields: dict[str, Any]) -> int:
    """Live venue suggestion by a voter (admin uses admin_add_venue)."""
    with db() as conn:
        user = get_user_or_404(conn, user_id)
        settings = get_settings(conn)
        if voting_is_closed(settings):
            raise ApiError(403, "Voting is closed; new venue suggestions are not accepted")
        if not settings.get("allow_venue_suggestions", True):
            raise ApiError(403, "The admin has disabled venue suggestions")
        venue_id = _insert_venue(conn, fields, suggested_by=user["user_id"])
        return venue_id


def _validate_venue_fields(fields: dict[str, Any], partial: bool) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    if not partial or "name" in fields:
        name = str(fields.get("name") or "").strip()
        if not name:
            raise ApiError(422, "Venue name is required")
        clean["name"] = name
    if not partial or "type" in fields:
        vtype = str(fields.get("type") or "").strip()
        if vtype not in VENUE_TYPES:
            raise ApiError(422, "Venue type must be 'food' or 'activity'")
        clean["type"] = vtype
    for key in ("description", "address"):
        if not partial or key in fields:
            clean[key] = str(fields.get(key) or "")
    if not partial or "estimated_cost" in fields:
        cost = fields.get("estimated_cost")
        clean["estimated_cost"] = None if cost in (None, "") else float(cost)
    for key in ("lat", "lng"):
        if not partial or key in fields:
            value = fields.get(key)
            clean[key] = None if value in (None, "") else float(value)
    if not partial or "slot_ids" in fields:
        clean["slot_ids"] = [int(s) for s in (fields.get("slot_ids") or [])]
    if not partial or "active" in fields:
        clean["active"] = 1 if fields.get("active") in (True, 1, "1") else 0
    return clean


def _insert_venue(
    conn: sqlite3.Connection, fields: dict[str, Any], suggested_by: str | None
) -> int:
    clean = _validate_venue_fields(fields, partial=False)
    cursor = conn.execute(
        "INSERT INTO venues (name, type, description, estimated_cost, address, lat, lng, "
        "suggested_by, slot_ids, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (
            clean["name"],
            clean["type"],
            clean.get("description", ""),
            clean.get("estimated_cost"),
            clean.get("address", ""),
            clean.get("lat"),
            clean.get("lng"),
            suggested_by,
            json.dumps(clean.get("slot_ids", [])),
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


# ---------------------------------------------------------------- results

def compute_results(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    closed: bool,
    is_admin: bool,
) -> dict[str, Any]:
    """Aggregate results, filtered by the admin's privacy choices.

    - anonymous_voting hides who-voted-what from everyone, admin included.
    - hide_live_counts hides all results from voters until voting closes.
    """
    anonymous = bool(settings.get("anonymous_voting"))
    hide_live = bool(settings.get("hide_live_counts"))

    include = True
    include_names = not anonymous
    if not closed:
        if is_admin and not anonymous:
            include, include_names = True, True
        elif hide_live:
            include = False
    elif anonymous:
        include_names = False

    if not include:
        return {
            "visible": False,
            "reason": "hidden_until_close",
            "availability": {},
            "food": {},
            "activity": {},
            "voters": [],
            "headcount_taken": headcount_taken(conn),
        }

    availability: dict[str, dict[str, int]] = {}
    for row in conn.execute(
        "SELECT slot_id, level, COUNT(*) AS n FROM availability GROUP BY slot_id, level"
    ):
        entry = availability.setdefault(str(row["slot_id"]), {"yes": 0, "weak": 0, "strong": 0, "total": 0})
        entry[row["level"]] = int(row["n"])
        entry["total"] += int(row["n"])

    def venue_results(column: str) -> dict[str, dict[str, Any]]:
        counts: dict[str, int] = {}
        voters_by_venue: dict[str, list[str]] = {}
        rows = conn.execute(
            f"SELECT v.user_id, v.{column} AS ids FROM votes v WHERE v.{column} != '[]'"
        ).fetchall()
        names = {
            r["user_id"]: r["display_name"] or r["user_id"]
            for r in conn.execute("SELECT user_id, display_name FROM users")
        }
        for row in rows:
            for venue_id in json.loads(row["ids"]):
                key = str(venue_id)
                counts[key] = counts.get(key, 0) + 1
                if include_names:
                    voters_by_venue.setdefault(key, []).append(names.get(row["user_id"], row["user_id"]))
        out: dict[str, dict[str, Any]] = {
            key: {"count": count} for key, count in counts.items()
        }
        if include_names:
            for key, voters in voters_by_venue.items():
                out[key]["voters"] = voters
        return out

    voters = []
    if include_names:
        voters = [
            r["display_name"] or r["user_id"]
            for r in conn.execute(
                "SELECT u.display_name, u.user_id FROM votes v JOIN users u ON u.user_id = v.user_id"
            )
        ]
    return {
        "visible": True,
        "reason": "closed" if closed else "live",
        "availability": availability,
        "food": venue_results("food_venue_ids"),
        "activity": venue_results("activity_venue_ids"),
        "voters": voters,
        "headcount_taken": headcount_taken(conn),
    }


# ------------------------------------------------------------------ state

def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Settings safe to show to any logged-in user."""
    return {k: v for k, v in settings.items() if k != "admin_user_id"}


def get_venues(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    venues = []
    for row in conn.execute(
        "SELECT v.*, u.display_name AS suggester_name FROM venues v "
        "LEFT JOIN users u ON u.user_id = v.suggested_by "
        "WHERE v.active = 1 ORDER BY v.type, v.id"
    ):
        venue = dict(row)
        venue["slot_ids"] = json.loads(venue["slot_ids"])
        venue["active"] = bool(venue["active"])
        venue["suggested_by"] = venue["suggested_by"] or None
        venues.append(venue)
    return venues


def get_state(user_id: str | None = None) -> dict[str, Any]:
    """Everything the single-page app needs, in one payload."""
    with db() as conn:
        user = _get_user(conn, user_id) if user_id else None
        if user_id and user is None:
            raise ApiError(404, f"Unknown user: {user_id}")
        is_admin = bool(user["is_admin"]) if user else False
        settings = get_settings(conn)
        closed = voting_is_closed(settings)
        slots = [
            dict(row) for row in conn.execute(
                "SELECT id, date, start_time, end_time FROM time_slots ORDER BY date, start_time"
            )
        ]
        my_availability: dict[str, str] = {}
        my_vote: dict[str, Any] = {"food_venue_ids": [], "activity_venue_ids": [], "has_vote": False}
        if user:
            my_availability = {
                str(r["slot_id"]): r["level"]
                for r in conn.execute(
                    "SELECT slot_id, level FROM availability WHERE user_id = ?", (user["user_id"],)
                )
            }
            my_vote = _load_vote(conn, user["user_id"])
        payload = {
            "authenticated": user is not None,
            "server_time": now_iso(),
            "config": {
                "testing_mode": CONFIG.testing_mode,
                "okta_enabled": CONFIG.okta_enabled,
                "maps_api_key": settings.get("google_maps_api_key") or CONFIG.maps_api_key,
                "mcp_url_override": CONFIG.mcp_display_base_url(),
            },
            "settings": public_settings(settings),
            "status": {"closed": closed, "reason": close_reason(settings)},
            "slots": slots,
            "venues": get_venues(conn),
            "footer": load_footer(),
        }
        if user:
            payload["me"] = _user_dict(user, is_admin)
            payload["my_availability"] = my_availability
            payload["my_vote"] = my_vote
            payload["results"] = compute_results(conn, settings, closed, is_admin)
        else:
            payload["config"]["testing_mode"] = CONFIG.testing_mode
        return payload


# ---------------------------------------------------------- admin actions

def admin_update_settings(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with db() as conn:
        require_admin(conn, user_id)
        settings = get_settings(conn)
        unknown = set(patch) - set(ADMIN_SETTING_KEYS)
        if unknown:
            raise ApiError(422, f"Unknown setting keys: {sorted(unknown)}")
        if "preference_mode" in patch and patch["preference_mode"] not in ("simple", "strong_weak"):
            raise ApiError(422, "preference_mode must be 'simple' or 'strong_weak'")
        if "budget_type" in patch and patch["budget_type"] not in ("per_head", "total"):
            raise ApiError(422, "budget_type must be 'per_head' or 'total'")
        if "voting_closes_at" in patch and patch["voting_closes_at"]:
            try:
                datetime.fromisoformat(str(patch["voting_closes_at"]))
            except ValueError:
                raise ApiError(422, "voting_closes_at must be an ISO datetime like 2026-09-20T18:00")
        for key, value in patch.items():
            set_setting(conn, key, value)
        return public_settings(get_settings(conn))


def admin_set_slots(user_id: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Full replacement of the candidate time slots (admin date/time setup)."""
    clean = []
    for item in slots:
        date = str(item.get("date") or "").strip()
        start = str(item.get("start_time") or "").strip()
        end = str(item.get("end_time") or "").strip()
        try:
            datetime.strptime(date, "%Y-%m-%d")
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError:
            raise ApiError(422, f"Invalid slot: {item!r} (need date YYYY-MM-DD, times HH:MM)")
        if end <= start:
            raise ApiError(422, f"Slot end must be after start: {start}-{end}")
        clean.append((date, start, end))
    clean.sort()
    with db() as conn:
        require_admin(conn, user_id)
        conn.execute("DELETE FROM time_slots")
        conn.executemany(
            "INSERT INTO time_slots (date, start_time, end_time) VALUES (?, ?, ?)", clean
        )
        return {"slot_count": len(clean)}


def admin_add_venue(user_id: str, fields: dict[str, Any]) -> int:
    with db() as conn:
        require_admin(conn, user_id)
        return _insert_venue(conn, fields, suggested_by=None)


def admin_update_venue(user_id: str, venue_id: int, patch: dict[str, Any]) -> None:
    with db() as conn:
        require_admin(conn, user_id)
        row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
        if row is None:
            raise ApiError(404, f"Venue {venue_id} not found")
        clean = _validate_venue_fields(dict(row) | {"slot_ids": json.loads(row["slot_ids"])} | patch, partial=True)
        updates, values = [], []
        for key, value in clean.items():
            updates.append(f"{key} = ?")
            values.append(json.dumps(value) if key == "slot_ids" else value)
        if updates:
            values.append(venue_id)
            conn.execute(f"UPDATE venues SET {', '.join(updates)} WHERE id = ?", values)


def admin_remove_venue(user_id: str, venue_id: int) -> None:
    with db() as conn:
        require_admin(conn, user_id)
        row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
        if row is None:
            raise ApiError(404, f"Venue {venue_id} not found")
        conn.execute("UPDATE venues SET active = 0 WHERE id = ?", (venue_id,))
        # Drop it from everyone's saved votes.
        for column in ("food_venue_ids", "activity_venue_ids"):
            for vote in conn.execute(
                f"SELECT user_id, {column} AS ids FROM votes WHERE {column} LIKE ?",
                (f"%{venue_id}%",),
            ).fetchall():
                ids = [v for v in json.loads(vote["ids"]) if v != venue_id]
                conn.execute(
                    f"UPDATE votes SET {column} = ? WHERE user_id = ?",
                    (json.dumps(ids), vote["user_id"]),
                )


def admin_list_users(user_id: str) -> list[dict[str, Any]]:
    """All known users with their admin flags, for the admin's People tab."""
    with db() as conn:
        require_admin(conn, user_id)
        users = []
        for row in conn.execute(
            "SELECT u.user_id, u.display_name, u.is_admin, u.created_at, "
            "(SELECT COUNT(*) FROM votes v WHERE v.user_id = u.user_id) AS vote_count "
            "FROM users u ORDER BY u.created_at"
        ):
            users.append(
                {
                    "user_id": row["user_id"],
                    "display_name": row["display_name"] or row["user_id"],
                    "is_admin": bool(row["is_admin"]),
                    "created_at": row["created_at"],
                    "has_vote": bool(row["vote_count"]),
                }
            )
        return users


def admin_set_admin(user_id: str, target_user_id: str, is_admin: bool) -> dict[str, Any]:
    """Grant or revoke admin for another user.

    Guardrails: an admin cannot revoke their own access (ask another admin)
    and the last remaining admin cannot be demoted. Revoking clears the
    `--admin` startup designation if it pointed at the demoted user, so the
    login rule does not silently re-promote them.
    """
    with db() as conn:
        require_admin(conn, user_id)
        target_user_id = (target_user_id or "").strip()
        if not target_user_id:
            raise ApiError(400, "target user_id is required")
        target = _get_user(conn, target_user_id)

        if is_admin:
            if target is None:
                # Grant admin to someone who hasn't logged in yet; the flag
                # waits for them in the users table.
                _ensure_user(conn, target_user_id)
            conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_user_id,))
            return {"user_id": target_user_id, "is_admin": True}

        if target is None:
            raise ApiError(404, f"Unknown user: {target_user_id}")
        if target_user_id == user_id:
            raise ApiError(422, "You cannot revoke your own admin access; ask another admin")
        admin_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM users WHERE is_admin = 1").fetchone()["n"]
        )
        if admin_count <= 1:
            raise ApiError(422, "Cannot revoke the last admin")
        conn.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_user_id,))
        if get_settings(conn).get("admin_user_id") == target_user_id:
            set_setting(conn, "admin_user_id", None)
        return {"user_id": target_user_id, "is_admin": False}


def admin_get_votes(user_id: str) -> dict[str, Any]:
    """Detailed votes view for the admin panel (respects anonymity)."""
    with db() as conn:
        admin = require_admin(conn, user_id)
        settings = get_settings(conn)
        anonymous = bool(settings.get("anonymous_voting"))
        closed = voting_is_closed(settings)
        slots = [
            dict(row)
            for row in conn.execute(
                "SELECT id, date, start_time, end_time FROM time_slots ORDER BY date, start_time"
            )
        ]
        people: list[dict[str, Any]] = []
        for u in conn.execute("SELECT * FROM users ORDER BY created_at"):
            availability = {
                str(r["slot_id"]): r["level"]
                for r in conn.execute(
                    "SELECT slot_id, level FROM availability WHERE user_id = ?", (u["user_id"],)
                )
            }
            vote = _load_vote(conn, u["user_id"])
            person = {
                "has_vote": vote["has_vote"],
                "food_venue_ids": vote["food_venue_ids"],
                "activity_venue_ids": vote["activity_venue_ids"],
            }
            if not anonymous:
                person["user_id"] = u["user_id"]
                person["display_name"] = u["display_name"] or u["user_id"]
                person["availability"] = availability
            else:
                # Anonymity: identity and per-person detail stay hidden.
                person["user_id"] = None
                person["display_name"] = "(anonymous)"
                person["availability"] = {}
            if u["user_id"] == admin["user_id"] and not anonymous:
                person["is_me"] = True
            people.append(person)
        return {
            "anonymous": anonymous,
            "closed": closed,
            "slots": slots,
            "people": people,
            "results": compute_results(conn, settings, closed, is_admin=True),
        }


def designated_admin_startup(admin_user_id: str | None) -> None:
    """Called once at server start with the --admin argument, if provided."""
    if not admin_user_id:
        return
    with db() as conn:
        set_setting(conn, "admin_user_id", admin_user_id)
