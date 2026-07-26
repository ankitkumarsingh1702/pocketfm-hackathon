"""FastAPI entrypoint for the Simulated Studio engine.

Run from the `backend/` dir:

    uv run uvicorn app.main:app --reload --port 8000

Exposes a health check, the persona roster, and the three simulation lenses.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import BACKEND_DIR, settings
from app.db.activity import get_recent_activity_durable
from app.engine.cache import Cache
from app.engine.mdp import policy_search
from app.engine.search import beam_search
from app.engine.streaming import ndjson_events
from app.graph.driver import graph_enabled, graph_probe
from app.graph.extract import extract_canon
from app.graph.store import (
    fetch_contradiction_candidates,
    fetch_full_graph,
    ingest_extraction,
    reset_canon_batch,
)
from app.lenses.audience import run_audience
from app.lenses.audience_sim import (
    generate_audience,
    list_audience,
    stream_audience_sim,
)
from app.lenses.cliffhanger import run_cliffhanger
from app.lenses.plot_holes import find_plot_holes
from app.lenses.showrunner import run_showrunner
from app.lenses.story_scan import scan_story
from app.lenses.writers_room import run_writers_room, stream_writers_room
from app.llm.factory import get_llm
from app.personas.loader import load_personas
from app.schemas import (
    ActivityFeed,
    AudienceLibrary,
    AudienceResult,
    AudienceSimRequest,
    CanonGraph,
    CanonPreviewResult,
    CanonResetRequest,
    CanonResetResult,
    CliffhangerRequest,
    CliffhangerResult,
    GeneratePersonasRequest,
    IngestRequest,
    IngestResult,
    MdpRequest,
    PlanRequest,
    PlotHoleResult,
    PlotHolesRequest,
    ShowrunnerRequest,
    SimulateRequest,
    StoryScanRequest,
    StoryScanResult,
    WritersRoomRequest,
    WritersRoomResult,
)

app = FastAPI(title="Simulated Studio API")
# Bounded gate on expensive agent runs: allow up to settings.max_concurrent_runs
# at once (was a single Lock) so concurrent demos / judges don't block one
# another, while still capping total in-flight load. Semaphore.acquire()/
# release() keep the existing call sites unchanged; .locked() is True when full.
_expensive_job_lock = asyncio.Semaphore(settings.max_concurrent_runs)


def _reject_if_expensive_job_active() -> None:
    if _expensive_job_lock.locked():
        raise HTTPException(
            status_code=429,
            detail=(
                f"{settings.max_concurrent_runs} large agent runs are already in "
                "flight. Try again in a moment."
            ),
        )

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
    return {
        "configured": settings.graph_configured,
        "online": await graph_probe(),
        "browser_url": settings.graph_browser_url,
    }


@app.get("/api/canon/graph", response_model=CanonGraph)
async def canon_graph(batch: str | None = None) -> CanonGraph:
    """Return full canon, or exactly one browser session when ``batch`` is set."""
    return await fetch_full_graph(batch=batch)


@app.post("/api/canon/preview", response_model=CanonPreviewResult)
async def canon_preview(req: IngestRequest) -> CanonPreviewResult:
    """Extract canon for the live UI preview without writing to Neo4j."""
    try:
        extraction = await extract_canon(
            req.story,
            get_llm(),
            model=settings.model_for("audience"),
        )
        return CanonPreviewResult(
            extraction=extraction,
            entity_count=len(extraction.entities),
            relation_count=len(extraction.relations),
            fact_count=len(extraction.facts),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/canon/ingest", response_model=IngestResult)
async def canon_ingest(req: IngestRequest) -> IngestResult:
    """Extract an episode's canon via the LLM and merge it into the graph."""
    try:
        extraction = await extract_canon(req.story, get_llm())
        return await ingest_extraction(req.story, extraction, batch=req.batch)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/canon/reset", response_model=CanonResetResult)
async def canon_reset(req: CanonResetRequest) -> CanonResetResult:
    """Clear only one session's memberships and session-owned graph records."""
    return await reset_canon_batch(req.batch)


@app.get("/api/canon/activity", response_model=ActivityFeed)
async def canon_activity(limit: int = 50) -> ActivityFeed:
    """Recent knowledge-graph reads/writes — live proof agents share memory.

    Each event names the agent (``source``), whether it read or wrote, and a
    human-readable detail. Reads from the durable Neo4j log so the counts survive
    a cold start / redeploy. Feeds the DB / Memory tab; observational only.
    """
    events, totals = await get_recent_activity_durable(limit)
    return ActivityFeed(
        events=events,
        reads=totals["reads"],
        writes=totals["writes"],
        total=totals["total"],
    )


@app.get("/api/canon/facts")
async def canon_facts(batch: str | None = None) -> dict:
    """Atomic canon facts + structural contradictions + dangling clues.

    Powers the DB / Memory "Facts tracked" drill-down. ``record=False`` so this
    read (which the tab polls) never pollutes the activity feed.
    """
    return await fetch_contradiction_candidates(
        source="DB / Memory",
        record=False,
        batch=batch,
    )


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


@app.post("/api/lenses/story-plot-holes", response_model=StoryScanResult)
async def story_plot_holes(req: StoryScanRequest) -> StoryScanResult:
    """Scan ONE loaded show's episodes for cross-episode contradictions.

    Story-scoped (never the seeded canon) and returns the exact clashing sentence
    on each side so the UI can highlight them like facing pages of a book.
    """
    try:
        return await scan_story(req)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plan/cliffhanger/stream")
async def plan_cliffhanger_stream(req: PlanRequest) -> StreamingResponse:
    """Beam-search cliffhanger rewrites, streaming each scored candidate."""
    _reject_if_expensive_job_active()
    await _expensive_job_lock.acquire()
    llm = get_llm()
    cache = Cache(settings.cache_dir)

    async def run(emit) -> dict:
        tree = await beam_search(
            req.story, req.weak_excerpt, llm, cache,
            beam_width=req.beam_width or 3,
            depth=req.depth or 2,
            panel_size=req.panel_size or settings.planner_panel_default,
            scout_size=req.scout_size or settings.planner_scout_default,
            finalist_count=req.finalist_count or settings.planner_finalists_default,
            canon_batch=req.batch,
            on_event=emit,
        )
        return tree.model_dump()

    async def guarded_events():
        try:
            async for event in ndjson_events(run):
                yield event
        finally:
            _expensive_job_lock.release()

    return StreamingResponse(guarded_events(), media_type="application/x-ndjson")


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
# Audience Simulator ("Living Audience") — stateful, multimodal reaction agents
# ---------------------------------------------------------------------------


@app.get("/api/audience-sim/library", response_model=AudienceLibrary)
async def audience_sim_library() -> AudienceLibrary:
    """The persisted audience population (knowledge graph), or default archetypes."""
    return await list_audience()


@app.post("/api/audience-sim/generate", response_model=AudienceLibrary)
async def audience_sim_generate(req: GeneratePersonasRequest) -> AudienceLibrary:
    """Synthesise a diverse audience of listener-agents and persist it for reuse."""
    _reject_if_expensive_job_active()
    await _expensive_job_lock.acquire()
    try:
        return await generate_audience(req)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _expensive_job_lock.release()


@app.post("/api/audience-sim/run/stream")
async def audience_sim_run_stream(req: AudienceSimRequest) -> StreamingResponse:
    """Run the Audience Simulator, streaming each agent's reaction as it lands."""
    _reject_if_expensive_job_active()
    await _expensive_job_lock.acquire()

    async def run(emit) -> dict:
        return await stream_audience_sim(req, emit)

    async def guarded_events():
        try:
            async for event in ndjson_events(run):
                yield event
        finally:
            _expensive_job_lock.release()

    return StreamingResponse(guarded_events(), media_type="application/x-ndjson")


@app.get("/api/audience-sim/memory")
async def audience_sim_memory(limit: int = 24) -> dict:
    """Expose recent per-listener memories as judge-facing statefulness proof."""
    from app.graph.audience_store import (
        count_audience_members,
        load_audience_members,
        recall_member_memory,
    )

    members = await load_audience_members(limit=limit, source="DB / Memory")
    total = await count_audience_members()
    rows: list[dict] = []
    for persona in members:
        memory = await recall_member_memory(persona.id, limit=3)
        rows.append(
            {
                "id": persona.id,
                "name": persona.name,
                "segment": persona.segment,
                "age": persona.age,
                "city": persona.city,
                "memory": memory,
                "memory_count": len(memory),
            }
        )
    return {
        "members": rows,
        "total": total,
        "shown": len(rows),
        "remembering": sum(1 for row in rows if row["memory_count"] > 0),
    }


# ---------------------------------------------------------------------------
# Mood-First Search — feel-based discovery
# ---------------------------------------------------------------------------
# A self-contained discovery surface: parse a free-text feeling, disambiguate
# into shelves, retrieve at arc granularity, and return doorways. Mounted under
# its own /api/mood prefix so its routes never collide with the studio lenses.
#
# Importing the router builds its in-memory index once at startup. That build is
# best-effort: if it fails, the studio lenses must still come up, so we log the
# failure and leave /api/mood unmounted rather than crashing the whole service.
try:
    from app.mood.api import router as mood_router  # noqa: E402

    app.include_router(mood_router, prefix="/api/mood", tags=["mood"])
except Exception as _mood_err:  # noqa: BLE001 - never let mood take the API down
    import logging

    logging.getLogger("uvicorn.error").exception(
        "Mood-First Search failed to load; /api/mood is unavailable: %s", _mood_err
    )


# ---------------------------------------------------------------------------
# Static SPA (single-service Cloud Run deploy)
# ---------------------------------------------------------------------------
# Serve the built frontend when it is bundled into the image. This mount MUST
# stay LAST so its catch-all "/" never shadows /health or the /api/* routes
# declared above. When no build is present (local dev), this is a no-op.

static_dir = BACKEND_DIR / "static"


class SpaStaticFiles(StaticFiles):
    """Static files with an SPA fallback: unknown paths serve index.html.

    The frontend routes its lenses client-side (/audience, /genre, ...), so a
    reload or deep link on any of those paths must land on the app shell
    rather than a 404.
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


if static_dir.is_dir():
    app.mount("/", SpaStaticFiles(directory=str(static_dir), html=True), name="spa")
