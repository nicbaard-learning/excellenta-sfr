import sys
import traceback

# --- Early startup log ---
print("=== SFR app.main.py: startup ===", flush=True)



try:



    import logging
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    from app.config import settings
    from app.database import engine, Base

    # ── Register API routers ──────────────────────────────────────────────
    from app.api import frameworks, controls, compare, recommend, reference, system, evidence, translation, maturity, roadmap, risk_intelligence  # noqa: E402
    from app.ui import router as ui_router  # noqa: E402
    from app.auth import router as oauth_router  # noqa: E402
    from dotenv import load_dotenv
    import os
    
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path)  # Load environment variables from .env file


    logger = logging.getLogger(__name__)

    # ── Background task: GitHub update check ─────────────────────────────
    import asyncio
    from app.services.github_service import check_for_updates

    async def github_update_checker(interval_hours: int = 24):
        """Background task that checks for SCF updates every N hours."""
        while True:
            try:
                logger.info("Running scheduled GitHub update check...")
                # Run the sync check in a thread pool to avoid blocking
                from app.database import SessionLocal
                def _run_check():
                    session = SessionLocal()
                    try:
                        check_for_updates(session)
                    finally:
                        session.close()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _run_check)
                logger.info("GitHub update check completed")
            except Exception as exc:
                logger.warning("GitHub update check background task failed: %s", exc)
            await asyncio.sleep(interval_hours * 3600)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan – startup/shutdown hooks."""
        logger.info("Starting SFR – Shared Framework Repository")
        # Create tables if they don't exist (for dev/POC convenience)
        Base.metadata.create_all(bind=engine)
        # Start background GitHub update checker
        task = asyncio.create_task(github_update_checker(24))
        yield
        task.cancel()
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

    from starlette.middleware.base import BaseHTTPMiddleware

    class ForceConnectionClose(BaseHTTPMiddleware):
        """Force HTTP/1.1 connections to close after each response.

        Skips SSE endpoints (/mcp/) since SSE requires a persistent connection
        to stream events (including tool definitions to MCP clients).
        """
        async def dispatch(self, request, call_next):
            # SSE requires a persistent connection — skip the Connection: close header
            if request.url.path.startswith("/mcp/"):
                return await call_next(request)
            response = await call_next(request)
            response.headers["Connection"] = "close"
            return response

    app.add_middleware(ForceConnectionClose)

    # ── Static files ──────────────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(ui_router)
    app.include_router(frameworks.router)
    app.include_router(controls.router)
    app.include_router(compare.router)
    app.include_router(recommend.router)
    app.include_router(reference.router)
    app.include_router(system.router)
    app.include_router(evidence.router)
    app.include_router(translation.router)
    app.include_router(maturity.router)
    app.include_router(roadmap.router)
    app.include_router(risk_intelligence.router)

    # ── OAuth 2.0 ────────────────────────────────────────────────────────
    # Endpoints for Claude.ai connector authentication.
    # Auto-discovery: GET /.well-known/oauth-authorization-server
    # Auth flow:      GET  /oauth/authorize
    #                 POST /oauth/token
    app.include_router(oauth_router)

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
