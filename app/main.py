import sys
import traceback

# --- Early startup log ---
print("=== SFR app.main.py: startup ===", flush=True)

try:
"""SFR – Shared Framework Repository — FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, Base

# ── Register API routers ──────────────────────────────────────────────
from app.api import frameworks, controls, compare, recommend, reference  # noqa: E402
from app.ui import router as ui_router  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan – startup/shutdown hooks."""
    logger.info("Starting SFR – Shared Framework Repository")
    # Create tables if they don't exist (for dev/POC convenience)
    Base.metadata.create_all(bind=engine)
    yield
    logger.info("Shutting down SFR")


    app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Shared Framework Repository (SFR) – a canonical compliance control library "
        "backed by the Secure Controls Framework (SCF). Supports TPRM vendor assessment "
        "and GRC framework comparison workflows."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Static files ──────────────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────
    app.include_router(ui_router)
    app.include_router(frameworks.router)
    app.include_router(controls.router)
    app.include_router(compare.router)
    app.include_router(recommend.router)
    app.include_router(reference.router)

# ── MCP (SSE transport) ──────────────────────────────────────────────
    # Mounts the Model Context Protocol server for AI-agent access.
    # Clients connect via GET /mcp/sse and POST /mcp/messages.
    from app.mcp.server import create_sse_app  # noqa: E402
    app.mount("/mcp", create_sse_app(), name="mcp")


# ── Global exception handler ──────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all exception handler returning structured JSON."""
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
        )

    @app.get("/health")
    async def health():
        """Health-check endpoint."""
        return {"status": "healthy"}

    print("=== SFR app.main.py: app created ===", flush=True)

except Exception as exc:
    print("=== SFR app.main.py: EXCEPTION DURING STARTUP ===", flush=True)
    traceback.print_exc()
    sys.exit(1)
