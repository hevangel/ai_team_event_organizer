"""Session-cookie helpers and the Okta SSO (OIDC authorization code) flow.

The Okta flow is wired but only exercisable where OKTA_* env vars point at a
real tenant (see README). Token signatures are verified against Okta's JWKS.
"""

import secrets
from urllib.parse import urlencode

import httpx
import jwt

from .config import CONFIG
from .errors import ApiError

STATE_COOKIE = "okta_state"
SESSION_COOKIE = "session"


# ---------------------------------------------------------------- sessions

def session_cookie(token: str) -> str:
    return f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax"


def clear_session_cookie() -> str:
    return f"{SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def _cookie_value(cookies: str | None, name: str) -> str | None:
    if not cookies:
        return None
    for part in cookies.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return None


def token_from_request(request) -> str | None:
    """request is a Starlette-compatible Request."""
    return _cookie_value(request.headers.get("cookie"), SESSION_COOKIE)


# -------------------------------------------------------------------- okta

def okta_login_url() -> tuple[str, str]:
    """Build the Okta authorize URL; returns (url, state)."""
    if not CONFIG.okta_enabled:
        raise ApiError(404, "Okta SSO is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": CONFIG.okta_client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": CONFIG.okta_redirect_uri,
        "state": state,
        "nonce": secrets.token_urlsafe(16),
    }
    url = f"{CONFIG.okta_issuer}/v1/authorize?{urlencode(params)}"
    return url, state


def okta_state_cookie(state: str) -> str:
    return f"{STATE_COOKIE}={state}; HttpOnly; Path=/; SameSite=Lax; Max-Age=600"


def okta_exchange_code(code: str, expected_state: str, received_state: str | None) -> dict:
    """Exchange the authorization code and return verified id_token claims."""
    if not CONFIG.okta_enabled:
        raise ApiError(404, "Okta SSO is not configured")
    if not received_state or not secrets.compare_digest(received_state, expected_state):
        raise ApiError(400, "Okta state mismatch; please retry the sign-in")

    with httpx.Client(timeout=15) as client:
        token_response = client.post(
            f"{CONFIG.okta_issuer}/v1/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CONFIG.okta_redirect_uri,
                "client_id": CONFIG.okta_client_id,
                "client_secret": CONFIG.okta_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code != 200:
            raise ApiError(502, f"Okta token exchange failed: {token_response.status_code}")
        id_token = token_response.json().get("id_token")
        if not id_token:
            raise ApiError(502, "Okta response did not include an id_token")

        try:
            jwks_client = jwt.PyJWKClient(f"{CONFIG.okta_issuer}/v1/keys")
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=CONFIG.okta_client_id,
                issuer=CONFIG.okta_issuer,
            )
        except jwt.PyJWTError as exc:
            raise ApiError(502, f"Okta id_token verification failed: {exc}")
    return claims


def okta_identity(claims: dict) -> tuple[str, str]:
    user_id = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
    if not user_id:
        raise ApiError(502, "Okta claims missing identity")
    display_name = claims.get("name") or claims.get("given_name") or str(user_id)
    return str(user_id), display_name
