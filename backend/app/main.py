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
from app.engine.cache import Cache
from app.engine.mdp import policy_search
from app.engine.search import beam_search
from app.engine.streaming import ndjson_events
from app.graph.driver import graph_enabled, graph_probe
from app.graph.extract import extract_canon
from app.graph.store import fetch_full_graph, ingest_extraction
from app.lenses.audience import run_audience
from app.lenses.cliffhanger import run_cliffhanger
from app.lenses.plot_holes import find_plot_holes
from app.lenses.showrunner import run_showrunner
from app.lenses.writers_room import run_writers_room, stream_writers_room
from app.llm.factory import get_llm
from app.personas.loader import load_personas
from app.schemas import (
    AudienceResult,
    CanonGraph,
    CliffhangerRequest,
    CliffhangerResult,
    IngestRequest,
    IngestResult,
    MdpRequest,
    PlanRequest,
    PlotHoleResult,
    PlotHolesRequest,
    ShowrunnerRequest,
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
        "graph": {
            "configured": settings.graph_configured,
            "enabled": graph_enabled(),
        },
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
        return await run_writers_room(req.story, req.experts, req.audience)
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
            async for event in stream_writers_room(req.story, req.experts, req.audience):
                yield (json.dumps(event) + "\n").encode("utf-8")
        except Exception as e:  # noqa: BLE001 - emit a terminal error line, never 500 mid-stream
            yield (json.dumps({"type": "error", "error": str(e)}) + "\n").encode("utf-8")

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Knowledge graph (Story Canon) — shared, persistent agent memory
# ---------------------------------------------------------------------------


@app.get("/api/canon/health")
async def canon_health() -> dict:
    """Report whether the knowledge graph is configured and live-reachable."""
    return {"configured": settings.graph_configured, "online": await graph_probe()}


@app.get("/api/canon/graph", response_model=CanonGraph)
async def canon_graph() -> CanonGraph:
    """Return the full story-canon graph (nodes + edges) for visualization."""
    return await fetch_full_graph()


@app.post("/api/canon/ingest", response_model=IngestResult)
async def canon_ingest(req: IngestRequest) -> IngestResult:
    """Extract an episode's canon via the LLM and merge it into the graph."""
    try:
        extraction = await extract_canon(req.story, get_llm())
        return await ingest_extraction(req.story, extraction)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Planning — Tree & Graph Search
# ---------------------------------------------------------------------------


@app.post("/api/lenses/plot-holes", response_model=PlotHoleResult)
async def plot_holes(req: PlotHolesRequest) -> PlotHoleResult:
    """Plot Hole Hunter: graph-grounded continuity/contradiction detection."""
    try:
        return await find_plot_holes(req.story)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plan/cliffhanger/stream")
async def plan_cliffhanger_stream(req: PlanRequest) -> StreamingResponse:
    """Beam-search cliffhanger rewrites, streaming each scored candidate."""
    llm = get_llm()
    cache = Cache(settings.cache_dir)

    async def run(emit) -> dict:
        tree = await beam_search(
            req.story, req.weak_excerpt, llm, cache,
            beam_width=req.beam_width or 3, depth=req.depth or 2, on_event=emit,
        )
        return tree.model_dump()

    return StreamingResponse(ndjson_events(run), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Actions — State Graph agent (showrunner)
# ---------------------------------------------------------------------------


@app.post("/api/agent/showrunner/stream")
async def showrunner_stream(req: ShowrunnerRequest) -> StreamingResponse:
    """Run the showrunner state-graph agent, streaming each node as it fires."""

    async def run(emit) -> dict:
        return await run_showrunner(req.story, req.weak_excerpt, emit)

    return StreamingResponse(ndjson_events(run), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# RL — MDP policy search
# ---------------------------------------------------------------------------


@app.post("/api/mdp/optimize/stream")
async def mdp_optimize_stream(req: MdpRequest) -> StreamingResponse:
    """Policy-search over cliffhangers; the audience simulator is the reward."""
    llm = get_llm()
    cache = Cache(settings.cache_dir)

    async def run(emit) -> dict:
        result = await policy_search(
            req.story, req.weak_excerpt, llm, cache,
            iterations=req.iterations or 4,
            candidates_per_iter=req.candidates_per_iter or 3,
            on_event=emit,
        )
        return result.model_dump()

    return StreamingResponse(ndjson_events(run), media_type="application/x-ndjson")


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
