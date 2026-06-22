"""JobPilot AI - FastAPI Application Entry Point.

Main application module that configures the FastAPI app,
registers middleware, and includes API routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    print("🚀 JobPilot AI API starting up...")
    yield
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
    allow_origins=[settings.FRONTEND_URL],
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


@app.websocket("/ws/agent-stream/{run_id}")
async def agent_stream(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming agent progress in real-time.

    Clients connect to receive live updates as the agent pipeline
    processes a job application (parsing JD, tailoring resume, etc.).

    Args:
        websocket: The WebSocket connection.
        run_id: Unique identifier for the agent run to stream.
    """
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "connected",
            "run_id": run_id,
            "message": "Connected to agent stream. Waiting for updates...",
        })
        # TODO: Integrate with LangGraph agent execution stream
        # This will subscribe to the agent run's event bus and
        # forward step completions, progress updates, and results
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({
                "type": "ack",
                "message": f"Received: {data}",
            })
    except WebSocketDisconnect:
        print(f"Client disconnected from agent stream: {run_id}")
