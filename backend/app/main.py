"""FastAPI entrypoint for the Simulated Studio engine.

Run from the `backend/` dir:

    uv run uvicorn app.main:app --reload --port 8000

Exposes a health check, the persona roster, and the three simulation lenses.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.lenses.audience import run_audience
from app.lenses.cliffhanger import run_cliffhanger
from app.lenses.writers_room import run_writers_room, stream_writers_room
from app.personas.loader import load_personas
from app.schemas import (
    AudienceResult,
    CliffhangerRequest,
    CliffhangerResult,
    SimulateRequest,
    WritersRoomRequest,
    WritersRoomResult,
)

app = FastAPI(title="Simulated Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Liveness + active-provider snapshot for the frontend."""
    location = (
        settings.vertex_location
        if settings.llm_provider == "gemini"
        else settings.claude_location
    )
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "project": settings.google_cloud_project,
        "location": location,
        "firestore": settings.use_firestore,
    }


@app.get("/api/personas")
async def personas() -> dict:
    """Return the audience and expert persona rosters."""
    return {
        "audience": load_personas("audience"),
        "experts": load_personas("expert"),
    }


@app.post("/api/simulate/audience", response_model=AudienceResult)
async def simulate_audience(req: SimulateRequest) -> AudienceResult:
    """Audience lens: simulate a listener panel for one episode."""
    try:
        return await run_audience(req.story, req.n)
    except Exception as e:  # noqa: BLE001 - surface as HTTP 500 to the client
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lenses/writers-room", response_model=WritersRoomResult)
async def writers_room(req: WritersRoomRequest) -> WritersRoomResult:
    """Writers' Room lens: expert panel critique + consensus."""
    try:
        return await run_writers_room(req.story)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lenses/cliffhanger", response_model=CliffhangerResult)
async def cliffhanger(req: CliffhangerRequest) -> CliffhangerResult:
    """Cliffhanger lens: rewrite a weak ending and A/B test the hook lift."""
    try:
        return await run_cliffhanger(req.story, req.weak_excerpt)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lenses/writers-room/stream")
async def writers_room_stream(req: WritersRoomRequest) -> StreamingResponse:
    """Writers' Room lens (streaming): NDJSON events as each agent finishes."""

    async def gen():
        import json

        try:
            async for event in stream_writers_room(req.story):
                yield (json.dumps(event) + "\n").encode("utf-8")
        except Exception as e:  # noqa: BLE001 - emit a terminal error line, never 500 mid-stream
            yield (json.dumps({"type": "error", "error": str(e)}) + "\n").encode("utf-8")

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Static SPA (single-service Cloud Run deploy)
# ---------------------------------------------------------------------------
# Serve the built frontend when it is bundled into the image. This mount MUST
# stay LAST so its catch-all "/" never shadows /health or the /api/* routes
# declared above. When no build is present (local dev), this is a no-op.
import os  # noqa: E402,F401
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.config import BACKEND_DIR  # noqa: E402

static_dir = BACKEND_DIR / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="spa")
