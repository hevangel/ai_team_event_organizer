"""Voter-facing REST API. All state-changing rules live in service.py."""

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from .. import auth, service
from ..db import db
from ..errors import ApiError

router = APIRouter()


def current_user(request: Request):
    """Resolve the logged-in user from the session cookie, or raise 401."""
    token = auth.token_from_request(request)
    if not token:
        raise ApiError(401, "Not signed in")
    with db() as conn:
        user = service.user_for_token(conn, token)
        if user is None:
            raise ApiError(401, "Session expired; please sign in again")
        return dict(user)


class LoginBody(BaseModel):
    userid: str
    display_name: str = ""


class VoteBody(BaseModel):
    availability: list[dict[str, Any]] | None = None
    food_venue_ids: list[int] | None = None
    activity_venue_ids: list[int] | None = None


class VenueSuggestionBody(BaseModel):
    name: str
    type: str  # food | activity
    description: str = ""
    estimated_cost: float | None = None
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    slot_ids: list[int] = []


@router.post("/login")
def login(body: LoginBody, response: Response):
    result = service.login_testing(body.userid, body.display_name)
    response.headers["Set-Cookie"] = auth.session_cookie(result["token"])
    return {"user": result["user"]}


@router.get("/auth/okta/login")
def okta_login():
    url, state = auth.okta_login_url()
    return Response(
        status_code=302,
        headers={
            "Location": url,
            "Set-Cookie": auth.okta_state_cookie(state),
        },
    )


@router.get("/auth/okta/callback")
def okta_callback(code: str, state: str, request: Request, response: Response):
    received = auth._cookie_value(request.headers.get("cookie"), auth.STATE_COOKIE)
    claims = auth.okta_exchange_code(code, state, received)
    user_id, display_name = auth.okta_identity(claims)
    result = service.login_okta(user_id, display_name)
    response.headers["Set-Cookie"] = auth.session_cookie(result["token"])
    return Response(status_code=302, headers={"Location": "/"})


@router.post("/logout")
def logout(request: Request, response: Response):
    token = auth.token_from_request(request)
    if token:
        with db() as conn:
            service.drop_session(conn, token)
    response.headers["Set-Cookie"] = auth.clear_session_cookie()
    return {"ok": True}


@router.get("/state")
def state(request: Request):
    """Public bootstrap: unauthenticated callers get settings/config only."""
    token = auth.token_from_request(request)
    user = None
    if token:
        with db() as conn:
            user = service.user_for_token(conn, token)
    return service.get_state(user["user_id"] if user else None)


@router.put("/vote")
def save_vote(body: VoteBody, request: Request):
    user = current_user(request)
    return service.save_vote(
        user["user_id"], body.availability, body.food_venue_ids, body.activity_venue_ids
    )


@router.post("/venues")
def suggest_venue(body: VenueSuggestionBody, request: Request):
    user = current_user(request)
    venue_id = service.suggest_venue(user["user_id"], body.model_dump())
    return {"venue_id": venue_id}
