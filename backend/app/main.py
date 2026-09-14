"""FastAPI app assembly: REST API + MCP (fastmcp) + built frontend."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .errors import ApiError
from .mcp_server import mcp_app
from .routes import admin, api

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # fastmcp requires its session manager lifespan for Streamable HTTP.
    async with mcp_app.lifespan(mcp_app):
        yield


app = FastAPI(title="AI Team Event Organizer", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


app.include_router(api.router, prefix="/api")
app.include_router(admin.router, prefix="/api/admin")

# The MCP streamable endpoint lives at /mcp/ inside the mounted app; send the
# bare path there explicitly (registered before the mount). Some MCP clients
# don't re-send POST bodies after redirects, so they should prefer /mcp/.
@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
def mcp_slash_redirect() -> Response:
    return Response(status_code=307, headers={"Location": "/mcp/"})


app.mount("/mcp", mcp_app)


@app.get("/api/health")
def health():
    return {"ok": True}


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(html=True, directory=str(FRONTEND_DIST)), name="frontend")
else:
    @app.get("/")
    def frontend_missing():
        return JSONResponse(
            status_code=200,
            content={
                "hint": "Frontend not built. Run: cd frontend && npm install && npm run build "
                "(or use the Vite dev server: npm run dev, http://localhost:5173). "
                "API and MCP are live under /api and /mcp.",
            },
        )
