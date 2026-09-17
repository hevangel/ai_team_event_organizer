"""MCP server (fastmcp) exposing the webapp's capabilities to AI agents.

Every tool a human can perform on the GUI is available here.

Identity: in testing mode the caller-supplied `user_id` is trusted — the same
honesty policy as the userid login. With SSO (TESTING_MODE=false) the call must
also carry the caller's web session, as the `session` cookie or an
`Authorization: Bearer <session token>` header, and it must belong to the
submitted userid. Otherwise any MCP client could act as any voter or admin.

Mounted into the FastAPI app at /mcp (Streamable HTTP), e.g.:
    uv run python -m app
    MCP URL: http://localhost:8000/mcp
"""

from functools import wraps
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers

from .db import SESSION_COOKIE
from .errors import ApiError
from . import service

mcp: FastMCP = FastMCP(
    name="team-event-organizer",
    instructions=(
        "Tools for a team-event voting webapp. Voters mark which date/time "
        "slots they are available, then vote for food and activity venues. "
        "Admins configure budget, headcount, schedule, venues and privacy. "
        "Call get_state(user_id=...) first: it returns settings, slots, "
        "venues, the user's current vote and privacy-filtered results. "
        "Slot and venue ids referenced by other tools come from that payload."
    ),
)


def _session_token() -> str | None:
    """Pull the caller's web session out of the HTTP request carrying this tool
    call, if there is one. Accepts the browser cookie or a bearer token so a
    CLI agent can be configured with a header. Returns None for in-process
    clients (no HTTP layer), which only testing mode accepts.
    """
    try:
        headers = get_http_headers()
    except Exception:  # noqa: BLE001 - no HTTP context (in-process client)
        return None
    if not headers:
        return None
    authorization = headers.get("authorization") or ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    for part in (headers.get("cookie") or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == SESSION_COOKIE and value:
            return value
    return None


def _tool(func):
    """MCP calls act for a human: authenticate/normalize user_id (see the
    module docstring) and translate ApiError into MCP tool errors with a
    readable message."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            kwargs["user_id"] = service.mcp_identity(kwargs.get("user_id"), _session_token())
            return func(*args, **kwargs)
        except ApiError as exc:
            raise ToolError(exc.message) from exc
    return wrapper


# ------------------------------------------------------------------ voting

@mcp.tool
@_tool
def get_state(user_id: str) -> dict[str, Any]:
    """Full current state for a user: settings, status, time slots, venues,
    their saved vote, and results as this user is allowed to see them.
    Call this first; all ids used by other tools come from here."""
    return service.get_state(user_id)


@mcp.tool
@_tool
def save_vote(
    user_id: str,
    availability: list[dict[str, Any]] | None = None,
    food_venue_ids: list[int] | None = None,
    activity_venue_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Save the user's current vote (replaces it entirely, like the Save button).

    availability: list of {"slot_id": int, "level": "yes"|"weak"|"strong"}.
      - In simple preference mode use level "yes" for every slot the user is
        available for; omit slots they cannot attend.
      - In strong_weak mode, mark best slots "strong" and acceptable ones "weak".
    food_venue_ids / activity_venue_ids: venue ids the user votes for.

    Example: 'I am good Mon/Wed and any time before 3pm' -> map the user's
    words onto slot ids from get_state, then call this with those ids."""
    return service.save_vote(user_id, availability, food_venue_ids, activity_venue_ids)


@mcp.tool
@_tool
def suggest_venue(
    user_id: str,
    name: str,
    type: str,
    description: str = "",
    estimated_cost: float | None = None,
    address: str = "",
    lat: float | None = None,
    lng: float | None = None,
    slot_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Suggest a new venue into the live vote. type must be 'food' or
    'activity'. The venue is tagged with the suggester. Rejected if the admin
    disabled suggestions or voting is closed. If lat/lng are omitted but an
    address is given, the server geocodes the address so the venue still
    appears on the map."""
    venue_id = service.suggest_venue(
        user_id,
        {
            "name": name,
            "type": type,
            "description": description,
            "estimated_cost": estimated_cost,
            "address": address,
            "lat": lat,
            "lng": lng,
            "slot_ids": slot_ids or [],
        },
    )
    return {"venue_id": venue_id}


# ------------------------------------------------------------------- admin

def _admin_fields(
    name: str | None = None,
    type: str | None = None,
    description: str | None = None,
    estimated_cost: float | None = None,
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    slot_ids: list[int] | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    fields = {}
    if name is not None:
        fields["name"] = name
    if type is not None:
        fields["type"] = type
    if description is not None:
        fields["description"] = description
    if estimated_cost is not None:
        fields["estimated_cost"] = estimated_cost
    if address is not None:
        fields["address"] = address
    if lat is not None:
        fields["lat"] = lat
    if lng is not None:
        fields["lng"] = lng
    if slot_ids is not None:
        fields["slot_ids"] = slot_ids
    if active is not None:
        fields["active"] = active
    return fields


@mcp.tool
@_tool
def admin_set_settings(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Update event settings (admin only). Recognized patch keys:
    event_title, event_description, budget_amount, budget_type ('per_head'|'total'),
    headcount_limit (int or null), preference_mode ('simple'|'strong_weak'),
    allow_venue_suggestions (bool), anonymous_voting (bool),
    hide_live_counts (bool), voting_closes_at ('YYYY-MM-DDTHH:MM' or null),
    voting_closed (bool), office_address, office_lat, office_lng,
    google_maps_api_key. Setting office_address without lat/lng geocodes it."""
    return service.admin_update_settings(user_id, patch)


@mcp.tool
@_tool
def admin_set_slots(user_id: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the candidate date/time slots (admin only). Each slot is
    {"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}.
    This wipes and recreates the schedule, so send the complete list."""
    return service.admin_set_slots(user_id, slots)


@mcp.tool
@_tool
def admin_add_venue(
    user_id: str,
    name: str,
    type: str,
    description: str = "",
    estimated_cost: float | None = None,
    address: str = "",
    lat: float | None = None,
    lng: float | None = None,
    slot_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Add a venue as the admin (admin only). type must be 'food' or
    'activity'; slot_ids limits which time slots the venue fits (empty = any).
    If lat/lng are omitted but an address is given, the server geocodes the
    address so the venue still appears on the map."""
    fields = _admin_fields(
        name=name,
        type=type,
        description=description or "",
        estimated_cost=estimated_cost,
        address=address or "",
        lat=lat,
        lng=lng,
        slot_ids=slot_ids or [],
    )
    venue_id = service.admin_add_venue(user_id, fields)
    return {"venue_id": venue_id}


@mcp.tool
@_tool
def admin_update_venue(user_id: str, venue_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    """Edit a venue (admin only). patch keys: name, type, description,
    estimated_cost, address, lat, lng, slot_ids, active."""
    service.admin_update_venue(user_id, venue_id, patch)
    return {"ok": True}


@mcp.tool
@_tool
def admin_remove_venue(user_id: str, venue_id: int) -> dict[str, Any]:
    """Remove a venue from the vote (admin only). Also stripped from saved votes."""
    service.admin_remove_venue(user_id, venue_id)
    return {"ok": True}


@mcp.tool
@_tool
def admin_close_voting(user_id: str, closed: bool) -> dict[str, Any]:
    """Manually close or re-open voting (admin only). Note that
    voting_closes_at (set via admin_set_settings) also auto-closes voting."""
    service.admin_update_settings(user_id, {"voting_closed": closed})
    return {"ok": True}


@mcp.tool
@_tool
def admin_list_users(user_id: str) -> list[dict[str, Any]]:
    """List all known users with their admin flags (admin only). Each row has
    user_id, display_name, is_admin, created_at and has_vote."""
    return service.admin_list_users(user_id)


@mcp.tool
@_tool
def admin_set_admin(user_id: str, target_user_id: str, is_admin: bool) -> dict[str, Any]:
    """Grant or revoke admin rights for another user (admin only). Granting
    for an unknown userid creates the user so the flag waits at first login.
    An admin cannot revoke their own access, and the last admin cannot be
    demoted."""
    return service.admin_set_admin(user_id, target_user_id, is_admin)


@mcp.tool
@_tool
def admin_get_votes(user_id: str) -> dict[str, Any]:
    """Detailed votes for the admin panel (admin only): per-user availability
    and venue picks. If voting is anonymous, identities and per-person detail
    are hidden from admins too."""
    return service.admin_get_votes(user_id)


# ------------------------------------------------------------- ASGI app

mcp_app = mcp.http_app(path="/")  # mounted by main.py at /mcp
