"""
TidalTwin - Backend Entry Point
===================================
This is the "main door" of our backend.
When the web server starts, it reads this file first and
sets up all the API routes (doors) that the frontend will use.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.api.health import router as health_router
from app.api.demo import router as demo_router
from app.api.status import router as status_router
from app.api.ocean import router as ocean_router
from app.api.assistant import router as assistant_router
from app.api.monitoring import router as monitoring_router
from app.api.stories import router as stories_router
from app.api.reports import router as reports_router
from app.api.safety import router as safety_router
from app.api.validation import router as validation_router
from app.api.intelligence import router as intelligence_router
from app.api.apex import router as apex_router
from app.api.coastal import router as coastal_router
from app.api.twin import router as twin_router
from app.api.currents import router as currents_router
from app.api.edr import router as edr_router
from app.api.lens import router as lens_router
from app.api.tide import router as tide_router
from app.modules.ai.safety.live import broadcast_loop


configure_logging()
logger = logging.getLogger("tidaltwin.startup")


def _warm_tide_cache() -> None:
    """Best-effort warm-up of the expensive TIDE shared inputs.

    Without this, the first TIDE request in a fresh process pays the full
    computation cost (~5s on the live dataset).  Runs off the event loop and
    never blocks or crashes startup.
    """
    from app.core.database import SessionLocal
    from app.modules.ai.tide.engine import TideEngine

    db = SessionLocal()
    try:
        TideEngine(db).rankings()
        logger.info("TIDE shared-input cache warmed.")
    except Exception:  # pragma: no cover - startup resilience
        logger.warning("TIDE cache warm-up skipped.", exc_info=True)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the background live-broadcast task on boot, stop it on shutdown."""
    logger.info("%s v%s starting (environment=%s).", settings.PROJECT_NAME, settings.VERSION, settings.ENVIRONMENT)
    for issue in settings.validate_environment():
        logger.warning("configuration: %s", issue)
    task = asyncio.create_task(broadcast_loop())
    # Warm the expensive TIDE shared inputs BEFORE serving requests. This is
    # awaited (not fire-and-forget) so the first TIDE-heavy request - e.g. the
    # demonstration guide opening /api/v1/demo/status - is fast instead of
    # racing the warm-up and paying the full ~6-13s computation cost. It is
    # bounded by a timeout so a slow/unreachable database cannot block startup.
    try:
        await asyncio.wait_for(asyncio.to_thread(_warm_tide_cache), timeout=60)
    except asyncio.TimeoutError:
        logger.warning("TIDE cache warm-up exceeded 60s; continuing without it.")
    except Exception:  # pragma: no cover - defensive
        logger.warning("TIDE cache warm-up failed; continuing.", exc_info=True)
    try:
        yield
    finally:
        task.cancel()
        logger.info("%s shutting down.", settings.PROJECT_NAME)

# Create the FastAPI app instance
# The title, description and version show up on the automatic
# documentation page which is great for judges.
app = FastAPI(
    title="TidalTwin",
    description="Interactive 4D Ocean Model Validation & Decision Intelligence Platform - Backend API",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---- CORS (Cross-Origin Resource Sharing) ----
# This allows the frontend website (running on a different address)
# to safely talk to our backend. Without this, the browser would
# block requests and nothing would work.
app.add_middleware(
    CORSMiddleware,
    # Configurable via CORS_ORIGINS. Defaults to "*" so the local demo works
    # out of the box; set an explicit list for any deployment.
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log method/path/status/duration only - never bodies, headers or secrets."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed: %s %s", request.method, request.url.path)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    if response.status_code >= 400 or duration_ms >= 1500:
        logger.warning("%s %s -> %s in %.0fms", request.method, request.url.path, response.status_code, duration_ms)
    else:
        logger.debug("%s %s -> %s in %.0fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors and return a clean, non-sensitive 500 payload."""
    logger.exception("unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ---- Register API Routers ----
# Routers group related endpoints in separate files for clean structure.
app.include_router(health_router)
app.include_router(demo_router)
app.include_router(status_router)
app.include_router(ocean_router)
app.include_router(assistant_router)
app.include_router(monitoring_router)
app.include_router(stories_router)
app.include_router(reports_router)
app.include_router(safety_router)
app.include_router(validation_router)
app.include_router(intelligence_router)
app.include_router(apex_router)
app.include_router(coastal_router)
app.include_router(twin_router)
app.include_router(currents_router)
app.include_router(edr_router)
app.include_router(lens_router)
app.include_router(tide_router)


# ---- Basic Routes (Doors) ----

@app.get("/")
def root():
    """Root endpoint - a friendly hello so we know it works."""
    return {
        "message": "Welcome to TidalTwin! The ocean is alive.",
        "status": "online",
        "docs": "/docs",
    }


# Health check endpoints now live in app/api/health.py so they can report
# per-subsystem availability instead of a static "healthy" string.
