"""Business logic shared by the REST API and the MCP server."""

import json
import math
import secrets
import sqlite3
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
PREFERENCE_MODES = ("simple", "strong_weak")
BUDGET_TYPES = ("per_head", "total")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Sanity bounds. Money is a REAL column, so anything astronomically large is a
# typo or an attack rather than a real per-head budget.
MAX_MONEY = 1_000_000_000.0


# ---------------------------------------------------------------- validation
#
# Everything that crosses the API boundary (REST body, MCP tool argument)
# passes through here. Without it, `int("x")` / `float(None)` surface as a 500
# and out-of-range values reach SQLite as permanently invalid state.

def _require_id(value: Any, what: str) -> int:
    """A row id: a positive integer. Accepts the JSON-ish forms clients send
    (int, or a digit string) and rejects floats, bools and junk."""
    if isinstance(value, bool):
        raise ApiError(422, f"{what} must be a positive integer, got {value!r}")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().lstrip("+").isdigit():
        number = int(value.strip())
    else:
        raise ApiError(422, f"{what} must be a positive integer, got {value!r}")
    if number <= 0:
        raise ApiError(422, f"{what} must be a positive integer, got {number}")
    return number


def _require_number(value: Any, what: str, low: float, high: float) -> float:
    """A finite float inside [low, high]. NaN/inf are rejected: they would
    poison every later comparison and aggregate."""
    if isinstance(value, bool):
        raise ApiError(422, f"{what} must be a number, got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(422, f"{what} must be a number, got {value!r}") from None
    if not math.isfinite(number):
        raise ApiError(422, f"{what} must be a finite number, got {value!r}")
    if not low <= number <= high:
        raise ApiError(422, f"{what} must be between {low} and {high}, got {number}")
    return number


def _require_bool(value: Any, what: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0"):
        return value.strip().lower() in ("true", "1")
    raise ApiError(422, f"{what} must be true or false, got {value!r}")


def _require_text(value: Any, what: str, max_length: int = 2000) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ApiError(422, f"{what} must be text, got {value!r}")
    text = str(value)
    if len(text) > max_length:
        raise ApiError(422, f"{what} must be at most {max_length} characters")
    return text


def _require_choice(value: Any, what: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ApiError(422, f"{what} must be one of {list(choices)}, got {value!r}")
    return value


def _require_id_list(value: Any, what: str) -> list[int]:
    """De-duplicated, order-preserving list of row ids."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ApiError(422, f"{what} must be a list of positive integers, got {value!r}")
    out: list[int] = []
    for item in value:
        number = _require_id(item, f"{what} entry")
        if number not in out:
            out.append(number)
    return out


class _RefuseRedirects(HTTPRedirectHandler):
    """The geocoder talks only to the allowlisted host; never follow redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


# ----------------------------------------------------------------- geocoding

def _maps_api_key(settings: dict[str, Any]) -> str:
    """Same resolution the frontend gets in /api/state: admin-set key wins."""
    return str(settings.get("google_maps_api_key") or "").strip() or CONFIG.maps_api_key


def _geocode_address(address: str, api_key: str) -> tuple[float, float] | None:
    """Server-side geocode for locations added without coordinates — the
    typical case when an AI agent creates a venue over MCP with just an
    address string. Best-effort: any failure returns None and the caller
    stores the venue without a pin rather than erroring.

    Outbound boundary: the request goes to the hardcoded Google Maps host
    over https only. The user-supplied address is confined to the
    fully percent-encoded query string, redirects are refused, and the
    parsed URL is re-checked against the allowlist before sending.
    """
    if not address.strip() or not api_key:
        return None
    url = GEOCODE_URL + "?address=" + quote(address, safe="") + "&key=" + quote(api_key, safe="")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "maps.googleapis.com":
        return None
    try:
        opener = build_opener(_RefuseRedirects)
        request = Request(url, headers={"User-Agent": "ai-team-event-organizer"})
        with opener.open(request, timeout=5) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "OK" or not data.get("results"):
            return None
        location = data["results"][0]["geometry"]["location"]
        return float(location["lat"]), float(location["lng"])
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
        return None


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


def mcp_identity(user_id: str, session_token: str | None = None) -> str:
    """Resolve (and authenticate) the human an MCP call is acting for.

    Testing mode keeps the honesty policy of the userid login: the
    caller-supplied user_id is trusted, the user row is created if needed and
    the first-login-admin rule applies.

    With SSO (testing mode off) a bare userid would let any MCP client
    impersonate a voter or an admin, so the call must carry the caller's web
    session — either the `session` cookie or the same token as an
    `Authorization: Bearer` header — and that session must belong to the
    submitted userid.
    """
    user_id = (user_id or "").strip()
    if not user_id:
        raise ApiError(400, "user_id is required")

    if not CONFIG.testing_mode:
        token = (session_token or "").strip()
        if not token:
            raise ApiError(
                401,
                "MCP calls require your web session: sign in to the webapp and send the "
                "session token as an Authorization: Bearer header (or the session cookie)",
            )
        with db() as conn:
            row = user_for_token(conn, token)
            if row is None:
                raise ApiError(401, "Session expired or unknown; sign in to the webapp again")
            if row["user_id"] != user_id:
                raise ApiError(403, f"Session does not belong to {user_id}")
        return user_id

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

def _as_aware(value: datetime) -> datetime:
    """Interpret a naive timestamp in the server's timezone.

    Deadlines are usually stored as naive local strings (`2026-09-20T18:00`
    from a datetime-local input) but a client may send one with an offset.
    Comparing the two kinds raises TypeError, so both sides are normalized to
    aware instants while keeping the server-local reading of legacy values.
    """
    if value.tzinfo is None:
        return value.astimezone()
    return value


def voting_is_closed(settings: dict[str, Any], at: datetime | None = None) -> bool:
    if settings.get("voting_closed"):
        return True
    closes_at = settings.get("voting_closes_at")
    if not closes_at:
        return False
    try:
        deadline = datetime.fromisoformat(str(closes_at))
    except (TypeError, ValueError):
        return False
    return _as_aware(at or datetime.now()) >= _as_aware(deadline)


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
    availability = availability or []
    if isinstance(availability, (str, bytes)) or not isinstance(availability, (list, tuple)):
        raise ApiError(422, "availability must be a list of {slot_id, level} objects")
    # De-duplicated up front: the same venue id twice must not store two
    # selections nor count the voter twice in the results.
    food_venue_ids = _require_id_list(food_venue_ids, "food_venue_ids")
    activity_venue_ids = _require_id_list(activity_venue_ids, "activity_venue_ids")

    with db() as conn:
        user = get_user_or_404(conn, user_id)
        settings = get_settings(conn)
        if voting_is_closed(settings):
            raise ApiError(403, "Voting is closed; your selection can no longer be changed")

        # Validate availability levels against the preference mode. In simple
        # mode anything maps to plain "yes".
        simple = settings.get("preference_mode", "simple") == "simple"
        clean_availability: list[tuple[int, str]] = []
        seen_slots: set[int] = set()
        for item in availability:
            if not isinstance(item, dict):
                raise ApiError(422, f"availability entry must be an object, got {item!r}")
            slot_id = _require_id(item.get("slot_id"), "slot_id")
            if slot_id in seen_slots:
                continue
            seen_slots.add(slot_id)
            level = _require_choice(item.get("level", "yes"), "availability level", AVAILABILITY_LEVELS)
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
        # who already have a saved vote may update theirs. Claiming a place
        # counts even with an empty ballot — a saved row *is* the reservation,
        # so exempting empty ballots would let anyone slip past a full event.
        #
        # BEGIN IMMEDIATE takes SQLite's write lock before the count is read,
        # so two simultaneous first-time saves cannot both see the last free
        # place and overbook.
        limit = settings.get("headcount_limit")
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT 1 FROM votes WHERE user_id = ?", (user["user_id"],)
        ).fetchone()
        if limit and existing is None and headcount_taken(conn) >= int(limit):
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
        name = _require_text(fields.get("name"), "Venue name", 200).strip()
        if not name:
            raise ApiError(422, "Venue name is required")
        clean["name"] = name
    if not partial or "type" in fields:
        vtype = _require_text(fields.get("type"), "Venue type", 20).strip()
        if vtype not in VENUE_TYPES:
            raise ApiError(422, "Venue type must be 'food' or 'activity'")
        clean["type"] = vtype
    if not partial or "description" in fields:
        clean["description"] = _require_text(fields.get("description"), "Venue description", 2000)
    if not partial or "address" in fields:
        clean["address"] = _require_text(fields.get("address"), "Venue address", 500)
    if not partial or "estimated_cost" in fields:
        cost = fields.get("estimated_cost")
        clean["estimated_cost"] = (
            None
            if cost in (None, "")
            else _require_number(cost, "estimated_cost", 0, MAX_MONEY)
        )
    for key, bound in (("lat", 90.0), ("lng", 180.0)):
        if not partial or key in fields:
            value = fields.get(key)
            clean[key] = None if value in (None, "") else _require_number(value, key, -bound, bound)
    if not partial or "slot_ids" in fields:
        clean["slot_ids"] = _require_id_list(fields.get("slot_ids"), "slot_ids")
    if not partial or "active" in fields:
        clean["active"] = 1 if _require_bool(fields.get("active", False), "active") else 0
    return clean


def _check_slot_ids_exist(conn: sqlite3.Connection, slot_ids: list[int]) -> None:
    """A venue's compatibility list must reference real time slots, otherwise
    the venue silently never matches anything."""
    if not slot_ids:
        return
    placeholders = ",".join("?" * len(slot_ids))
    known = {
        row["id"]
        for row in conn.execute(f"SELECT id FROM time_slots WHERE id IN ({placeholders})", slot_ids)
    }
    missing = [s for s in slot_ids if s not in known]
    if missing:
        raise ApiError(422, f"Unknown time slot ids in slot_ids: {missing}")


def _insert_venue(
    conn: sqlite3.Connection, fields: dict[str, Any], suggested_by: str | None
) -> int:
    clean = _validate_venue_fields(fields, partial=False)
    _check_slot_ids_exist(conn, clean.get("slot_ids", []))
    if clean.get("lat") is None or clean.get("lng") is None:
        coords = _geocode_address(clean.get("address", ""), _maps_api_key(get_settings(conn)))
        if coords:
            clean["lat"], clean["lng"] = coords
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
            # One voter counts once per venue even if a legacy row (or a
            # client bug) stored the same id twice.
            seen: set[str] = set()
            for venue_id in json.loads(row["ids"]):
                key = str(venue_id)
                if key in seen:
                    continue
                seen.add(key)
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

def _validate_settings_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Coerce and range-check an admin settings patch.

    Settings are stored as JSON blobs, so an untyped value written here stays
    wrong forever (a string budget breaks every later comparison, a NaN
    coordinate breaks the map). Every recognized key gets a type here.
    """
    if not isinstance(patch, dict):
        raise ApiError(422, "settings patch must be an object")
    unknown = set(patch) - set(ADMIN_SETTING_KEYS)
    if unknown:
        raise ApiError(422, f"Unknown setting keys: {sorted(unknown)}")

    clean: dict[str, Any] = {}
    for key, value in patch.items():
        if key in ("event_title", "event_description", "office_address", "google_maps_api_key"):
            clean[key] = _require_text(value, key, 4000)
        elif key in ("allow_venue_suggestions", "anonymous_voting", "hide_live_counts",
                     "show_footer_to_voters", "voting_closed"):
            clean[key] = _require_bool(value, key)
        elif key == "preference_mode":
            clean[key] = _require_choice(value, key, PREFERENCE_MODES)
        elif key == "budget_type":
            clean[key] = _require_choice(value, key, BUDGET_TYPES)
        elif key == "budget_amount":
            clean[key] = None if value in (None, "") else _require_number(value, key, 0, MAX_MONEY)
        elif key == "headcount_limit":
            clean[key] = None if value in (None, "") else _require_id(value, key)
        elif key == "office_lat":
            clean[key] = None if value in (None, "") else _require_number(value, key, -90, 90)
        elif key == "office_lng":
            clean[key] = None if value in (None, "") else _require_number(value, key, -180, 180)
        elif key == "voting_closes_at":
            if value in (None, ""):
                clean[key] = None
            else:
                try:
                    datetime.fromisoformat(str(value))
                except (TypeError, ValueError):
                    raise ApiError(
                        422, "voting_closes_at must be an ISO datetime like 2026-09-20T18:00"
                    ) from None
                clean[key] = str(value)
        else:  # pragma: no cover - ADMIN_SETTING_KEYS and this map are in sync
            clean[key] = value
    return clean


def admin_update_settings(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with db() as conn:
        require_admin(conn, user_id)
        settings = get_settings(conn)
        patch = _validate_settings_patch(patch)
        # Office set by address alone (e.g. an agent over MCP): geocode it so
        # the voters' map centers correctly without extra round-trips.
        if "office_address" in patch and "office_lat" not in patch and "office_lng" not in patch:
            coords = _geocode_address(str(patch["office_address"] or ""), _maps_api_key(settings))
            if coords:
                patch = {**patch, "office_lat": coords[0], "office_lng": coords[1]}
        for key, value in patch.items():
            set_setting(conn, key, value)
        return public_settings(get_settings(conn))


def admin_set_slots(user_id: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile the candidate time slots with the list the admin submitted.

    The payload is still the complete schedule, but a slot is *identified* by
    its (date, start, end): unchanged slots keep their row id. Recreating every
    row would orphan the availability and venue-compatibility that reference
    those ids, so re-saving an untouched schedule used to wipe everyone's
    availability.
    """
    if isinstance(slots, (str, bytes)) or not isinstance(slots, (list, tuple)):
        raise ApiError(422, "slots must be a list of {date, start_time, end_time} objects")
    clean: list[tuple[str, str, str]] = []
    for item in slots:
        if not isinstance(item, dict):
            raise ApiError(422, f"Invalid slot: {item!r} (expected an object)")
        date = _require_text(item.get("date"), "slot date", 10).strip()
        start = _require_text(item.get("start_time"), "slot start_time", 5).strip()
        end = _require_text(item.get("end_time"), "slot end_time", 5).strip()
        try:
            datetime.strptime(date, "%Y-%m-%d")
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError:
            raise ApiError(422, f"Invalid slot: {item!r} (need date YYYY-MM-DD, times HH:MM)") from None
        if end <= start:
            raise ApiError(422, f"Slot end must be after start: {start}-{end}")
        entry = (date, start, end)
        if entry not in clean:  # the same slot listed twice is one slot
            clean.append(entry)
    clean.sort()

    with db() as conn:
        require_admin(conn, user_id)
        existing = {
            (row["date"], row["start_time"], row["end_time"]): row["id"]
            for row in conn.execute("SELECT id, date, start_time, end_time FROM time_slots")
        }
        wanted = set(clean)
        removed_ids = [slot_id for key, slot_id in existing.items() if key not in wanted]
        if removed_ids:
            placeholders = ",".join("?" * len(removed_ids))
            # availability rows cascade with the slot (FK ON DELETE CASCADE).
            conn.execute(f"DELETE FROM time_slots WHERE id IN ({placeholders})", removed_ids)
        conn.executemany(
            "INSERT INTO time_slots (date, start_time, end_time) VALUES (?, ?, ?)",
            [entry for entry in clean if entry not in existing],
        )
        if removed_ids:
            _prune_venue_slots(conn, set(removed_ids))
        return {"slot_count": len(clean)}


def _prune_venue_slots(conn: sqlite3.Connection, removed_ids: set[int]) -> None:
    """Drop deleted slots from every venue's compatibility list.

    A venue that listed specific slots and lost all of them is no longer
    compatible with anything on the schedule. Leaving an empty list behind
    would silently flip it to "fits any slot", so it is deactivated and pulled
    out of saved votes instead.
    """
    for row in conn.execute("SELECT id, slot_ids, active FROM venues").fetchall():
        try:
            slot_ids = [int(s) for s in json.loads(row["slot_ids"])]
        except (TypeError, ValueError):
            slot_ids = []
        if not slot_ids:
            continue
        kept = [s for s in slot_ids if s not in removed_ids]
        if kept == slot_ids:
            continue
        if kept:
            conn.execute("UPDATE venues SET slot_ids = ? WHERE id = ?", (json.dumps(kept), row["id"]))
            continue
        conn.execute(
            "UPDATE venues SET slot_ids = ?, active = 0 WHERE id = ?", (json.dumps([]), row["id"])
        )
        if row["active"]:
            _strip_venue_from_votes(conn, int(row["id"]))


def _strip_venue_from_votes(
    conn: sqlite3.Connection, venue_id: int, columns: tuple[str, ...] = ("food_venue_ids", "activity_venue_ids")
) -> None:
    """Remove a venue id from every saved ballot.

    Saved votes are JSON arrays, so a venue that is deleted, deactivated or
    re-categorized has to be pulled out explicitly — otherwise the stale id
    keeps affecting results and no longer matches the venue the voter sees.
    """
    for column in columns:
        for vote in conn.execute(f"SELECT user_id, {column} AS ids FROM votes").fetchall():
            try:
                ids = [int(v) for v in json.loads(vote["ids"])]
            except (TypeError, ValueError):
                continue
            kept = [v for v in ids if v != venue_id]
            if kept != ids:
                conn.execute(
                    f"UPDATE votes SET {column} = ?, updated_at = ? WHERE user_id = ?",
                    (json.dumps(kept), now_iso(), vote["user_id"]),
                )


def admin_add_venue(user_id: str, fields: dict[str, Any]) -> int:
    with db() as conn:
        require_admin(conn, user_id)
        return _insert_venue(conn, fields, suggested_by=None)


def admin_update_venue(user_id: str, venue_id: int, patch: dict[str, Any]) -> None:
    venue_id = _require_id(venue_id, "venue_id")
    if not isinstance(patch, dict):
        raise ApiError(422, "venue patch must be an object")
    with db() as conn:
        require_admin(conn, user_id)
        row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
        if row is None:
            raise ApiError(404, f"Venue {venue_id} not found")
        clean = _validate_venue_fields(dict(row) | {"slot_ids": json.loads(row["slot_ids"])} | patch, partial=True)
        if "slot_ids" in clean:
            _check_slot_ids_exist(conn, clean["slot_ids"])
        updates, values = [], []
        for key, value in clean.items():
            updates.append(f"{key} = ?")
            values.append(json.dumps(value) if key == "slot_ids" else value)
        if updates:
            values.append(venue_id)
            conn.execute(f"UPDATE venues SET {', '.join(updates)} WHERE id = ?", values)

        # Saved ballots reference this venue by id, so an edit that changes
        # *what* the venue is must not leave stale selections behind:
        #  - deactivating hides it from the UI but the id would keep counting;
        #  - flipping food <-> activity would leave the id in the wrong list,
        #    where it no longer matches the category the voter picked.
        deactivated = "active" in clean and not clean["active"] and row["active"]
        retyped = "type" in clean and clean["type"] != row["type"]
        if deactivated or retyped:
            _strip_venue_from_votes(conn, venue_id)


def admin_remove_venue(user_id: str, venue_id: int) -> None:
    venue_id = _require_id(venue_id, "venue_id")
    with db() as conn:
        require_admin(conn, user_id)
        row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
        if row is None:
            raise ApiError(404, f"Venue {venue_id} not found")
        conn.execute("UPDATE venues SET active = 0 WHERE id = ?", (venue_id,))
        _strip_venue_from_votes(conn, venue_id)


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
        # Anonymity means aggregate-only, for admins too. Returning one row per
        # voter — even with the name blanked — still leaks each individual
        # ballot (and re-identifies people through their pick combination), so
        # no rows are emitted at all; the UI shows the aggregate view instead.
        people: list[dict[str, Any]] = []
        if not anonymous:
            for u in conn.execute("SELECT * FROM users ORDER BY created_at"):
                availability = {
                    str(r["slot_id"]): r["level"]
                    for r in conn.execute(
                        "SELECT slot_id, level FROM availability WHERE user_id = ?", (u["user_id"],)
                    )
                }
                vote = _load_vote(conn, u["user_id"])
                person: dict[str, Any] = {
                    "has_vote": vote["has_vote"],
                    "food_venue_ids": vote["food_venue_ids"],
                    "activity_venue_ids": vote["activity_venue_ids"],
                    "user_id": u["user_id"],
                    "display_name": u["display_name"] or u["user_id"],
                    "availability": availability,
                }
                if u["user_id"] == admin["user_id"]:
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
