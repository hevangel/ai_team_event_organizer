"""Admin-only REST endpoints."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import service
from ..errors import ApiError
from ..routes.api import current_user

router = APIRouter()


def require_admin_user(request: Request) -> dict:
    user = current_user(request)
    if not user["is_admin"]:
        raise ApiError(403, "Admin access required")
    return user


class SettingsPatch(BaseModel):
    patch: dict[str, Any]


class SlotsBody(BaseModel):
    slots: list[dict[str, Any]]


class VenueBody(BaseModel):
    """All fields optional; callers send only what they want to set
    (routes use exclude_unset, so absent keys never clobber data)."""

    name: str | None = None
    type: str | None = None
    description: str | None = None
    estimated_cost: float | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    slot_ids: list[int] | None = None
    active: bool | None = None


class AdminFlagBody(BaseModel):
    is_admin: bool


@router.get("/users")
def list_users(request: Request):
    user = require_admin_user(request)
    return service.admin_list_users(user["user_id"])


@router.put("/users/{target_user_id}/admin")
def set_admin(target_user_id: str, body: AdminFlagBody, request: Request):
    user = require_admin_user(request)
    return service.admin_set_admin(user["user_id"], target_user_id, body.is_admin)


@router.put("/settings")
def update_settings(body: SettingsPatch, request: Request):
    user = require_admin_user(request)
    return service.admin_update_settings(user["user_id"], body.patch)


@router.put("/slots")
def set_slots(body: SlotsBody, request: Request):
    user = require_admin_user(request)
    return service.admin_set_slots(user["user_id"], body.slots)


@router.post("/venues")
def add_venue(body: VenueBody, request: Request):
    user = require_admin_user(request)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("active", None)  # newly added venues are always active
    venue_id = service.admin_add_venue(user["user_id"], fields)
    return {"venue_id": venue_id}


@router.put("/venues/{venue_id}")
def update_venue(venue_id: int, body: VenueBody, request: Request):
    user = require_admin_user(request)
    service.admin_update_venue(user["user_id"], venue_id, body.model_dump(exclude_unset=True))
    return {"ok": True}


@router.delete("/venues/{venue_id}")
def remove_venue(venue_id: int, request: Request):
    user = require_admin_user(request)
    service.admin_remove_venue(user["user_id"], venue_id)
    return {"ok": True}


@router.get("/votes")
def get_votes(request: Request):
    user = require_admin_user(request)
    return service.admin_get_votes(user["user_id"])
