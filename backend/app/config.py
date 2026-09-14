"""Runtime configuration, loaded once from environment variables."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self) -> None:
        self.db_path = Path(
            os.environ.get("DB_PATH", str(BACKEND_DIR / "data" / "event_organizer.db"))
        )
        self.testing_mode = _bool(os.environ.get("TESTING_MODE"), True)
        self.google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        # Okta SSO (OIDC authorization code flow). Not usable from a home PC;
        # wire the values at work and flip TESTING_MODE=false.
        self.okta_domain = os.environ.get("OKTA_DOMAIN", "").strip().rstrip("/")
        self.okta_client_id = os.environ.get("OKTA_CLIENT_ID", "").strip()
        self.okta_client_secret = os.environ.get("OKTA_CLIENT_SECRET", "").strip()
        self.base_url = os.environ.get("BASE_URL", "http://localhost:5173").rstrip("/")
        # Display-only override for the login page's MCP setup hints. Empty
        # means "derive from the browser address bar". The CLI flags
        # (--mcp-hostname/--mcp-port/--mcp-subpath) overwrite these.
        self.mcp_public_hostname = os.environ.get("MCP_PUBLIC_HOSTNAME", "").strip()
        mcp_port = os.environ.get("MCP_PUBLIC_PORT", "").strip()
        self.mcp_public_port = int(mcp_port) if mcp_port.isdigit() else None
        self.mcp_public_subpath = os.environ.get("MCP_PUBLIC_SUBPATH", "").strip()

    @property
    def okta_issuer(self) -> str:
        return self.okta_domain

    @property
    def okta_enabled(self) -> bool:
        return bool(self.okta_domain and self.okta_client_id and self.okta_client_secret)

    @property
    def okta_redirect_uri(self) -> str:
        return f"{self.base_url}/api/auth/okta/callback"

    @property
    def maps_api_key(self) -> str:
        """Env fallback for the Google Maps JS API key. The admin-set value
        lives in the settings table and wins; service.py resolves the two."""
        return self.google_maps_api_key

    def mcp_display_base_url(self) -> str | None:
        """Base URL (no /mcp suffix) shown in the login-page MCP hints when
        the host/port/sub-path were overridden; None means the frontend
        should derive it from the browser address bar."""
        if not (self.mcp_public_hostname or self.mcp_public_port or self.mcp_public_subpath):
            return None
        host = self.mcp_public_hostname or "localhost"
        if host.startswith(("http://", "https://")):
            base = host.rstrip("/")
            scheme = base.split("://", 1)[0]
        else:
            scheme = "https" if self.mcp_public_port == 443 else "http"
            base = f"{scheme}://{host}"
        default_port = {"http": 80, "https": 443}[scheme]
        if self.mcp_public_port and self.mcp_public_port != default_port:
            base = f"{base}:{self.mcp_public_port}"
        sub = self.mcp_public_subpath.strip("/")
        return base + (f"/{sub}" if sub else "")


CONFIG = Config()
