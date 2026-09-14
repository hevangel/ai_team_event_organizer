"""CLI entrypoint: uv run python -m app [--admin USERID] [--host H] [--port P]

--admin designates the organizer's admin user up front. When omitted and no
admin exists in the database yet, the first person to log in becomes admin.
"""

import argparse
from pathlib import Path

import uvicorn

from .config import CONFIG
from .db import init_db
from .service import designated_admin_startup


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Team Event Organizer server")
    parser.add_argument("--admin", default=None, help="userid of the event organizer (admin)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload (development)")
    parser.add_argument("--db", default=None, help="path to the SQLite database file")
    parser.add_argument(
        "--mcp-hostname",
        default=None,
        help="hostname shown in the login-page MCP setup hints (default: whatever host the browser uses)",
    )
    parser.add_argument("--mcp-port", type=int, default=None, help="port shown in the MCP setup hints")
    parser.add_argument(
        "--mcp-subpath",
        default=None,
        help="sub-path prefix shown in the MCP hints, e.g. 'team' when behind a reverse proxy",
    )
    args = parser.parse_args()

    if args.db:
        CONFIG.db_path = Path(args.db)
    if args.mcp_hostname is not None:
        CONFIG.mcp_public_hostname = args.mcp_hostname
    if args.mcp_port is not None:
        CONFIG.mcp_public_port = args.mcp_port
    if args.mcp_subpath is not None:
        CONFIG.mcp_public_subpath = args.mcp_subpath

    init_db()
    designated_admin_startup(args.admin)

    if args.admin:
        print(f"Designated admin: {args.admin}")
    else:
        print("No --admin given: the first person to log in becomes the admin.")

    print(f"Database: {CONFIG.db_path}")
    print(f"Testing-mode login: {'ON' if CONFIG.testing_mode else 'OFF'}")
    print(f"REST API: http://{args.host}:{args.port}/api  |  MCP: http://{args.host}:{args.port}/mcp")
    mcp_display = CONFIG.mcp_display_base_url()
    if mcp_display:
        print(f"Login-page MCP hints point at: {mcp_display}/mcp")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
