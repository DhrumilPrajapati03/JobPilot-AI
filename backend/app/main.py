"""JobPilot AI - FastAPI Application Entry Point.

Main application module that configures the FastAPI app,
registers middleware, and includes API routers.
"""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config import settings
from app.services import autopilot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    print("🚀 JobPilot AI API starting up...")
    scheduler = None
    if settings.DISCOVERY_AUTO_SCAN and autopilot.server_ready():
        scheduler = asyncio.create_task(autopilot.scheduler_loop())
        print("🌙 Autopilot: nightly scans and morning digests are on")
    yield
    if scheduler:
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler
    # Shutdown
    print("👋 JobPilot AI API shutting down...")


app = FastAPI(
    title="JobPilot AI API",
    description=(
        "Autonomous Job Application Intelligence System. "
        "AI-powered resume tailoring, cold email generation, "
        "and application tracking."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip().rstrip("/") for o in settings.FRONTEND_URL.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint to verify the API is running."""
    return {
        "status": "healthy",
        "service": "JobPilot AI API",
        "version": "1.0.0",
    }


from app.services.websocket import manager


@app.websocket("/ws/agent-stream/{run_id}")
async def agent_stream(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming agent progress in real-time.

    Clients connect to receive live updates as the agent pipeline
    processes a job application (parsing JD, tailoring resume, etc.).

    Args:
        websocket: The WebSocket connection.
        run_id: Unique identifier for the agent run to stream.
    """
    # Replays any events already emitted for this run before streaming new ones
    if not await manager.connect(run_id, websocket):
        return
    try:
        while True:
            # Wait for any incoming messages to keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
        print(f"Client disconnected from agent stream: {run_id}")
