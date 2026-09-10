"""
OceanVerse AI - Backend Entry Point
===================================
This is the "main door" of our backend.
When the web server starts, it reads this file first and
sets up all the API routes (doors) that the frontend will use.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.status import router as status_router
from app.api.ocean import router as ocean_router
from app.api.assistant import router as assistant_router
from app.api.monitoring import router as monitoring_router
from app.api.stories import router as stories_router
from app.api.reports import router as reports_router
from app.api.safety import router as safety_router
from app.api.validation import router as validation_router
from app.api.intelligence import router as intelligence_router
from app.modules.ai.safety.live import broadcast_loop


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the background live-broadcast task on boot, stop it on shutdown."""
    task = asyncio.create_task(broadcast_loop())
    try:
        yield
    finally:
        task.cancel()

# Create the FastAPI app instance
# The title, description and version show up on the automatic
# documentation page which is great for judges.
app = FastAPI(
    title="OceanVerse AI",
    description="Interactive 4D Ocean Model Validation & Decision Intelligence Platform - Backend API",
    version="0.1.0",
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
    allow_origins=["*"],  # TODO: restrict to frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Register API Routers ----
# Routers group related endpoints in separate files for clean structure.
app.include_router(status_router)
app.include_router(ocean_router)
app.include_router(assistant_router)
app.include_router(monitoring_router)
app.include_router(stories_router)
app.include_router(reports_router)
app.include_router(safety_router)
app.include_router(validation_router)
app.include_router(intelligence_router)


# ---- Basic Routes (Doors) ----

@app.get("/")
def root():
    """Root endpoint - a friendly hello so we know it works."""
    return {
        "message": "Welcome to OceanVerse AI! The ocean is alive.",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/api/v1/health")
def health_check():
    """Health check - tells us if the backend is running fine."""
    return {"status": "healthy", "service": "OceanVerse AI Backend"}
