"""Audience Simulator lens — the "Living Audience".

Runs a large panel of genuine, stateful listener-agents against a posted
episode/teaser (text + optional image) and streams each reaction live.

Roster resolution (in priority order):
1. an edited roster sent from the UI (agent profiles) — honoured verbatim;
2. the audience persisted in the knowledge graph (a reusable population),
   sampled down to the requested size;
3. freshly LLM-synthesised personas, persisted to the graph for reuse.

After the run, reactions are archived to Firestore and written back to the
knowledge graph (per-member + per-segment edges) so agents remember next time.
Everything degrades gracefully when the graph/Firestore are unavailable.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.aggregate import aggregate_sim
from app.engine.audience_agent import run_social_reactions
from app.engine.cache import Cache
from app.graph.audience_store import (
    load_audience_members,
    save_audience_members,
    write_member_reactions,
)
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.llm.factory import get_llm
from app.personas.generator import generate_personas
from app.personas.loader import load_personas
from app.schemas import (
    AudienceLibrary,
    AudienceSimRequest,
    GeneratePersonasRequest,
    Persona,
)

_SOURCE = "Audience Simulator"


async def resolve_audience(req: AudienceSimRequest) -> tuple[list[Persona], str]:
    """Return ``(members, source)`` for a run — provided / graph / generated."""
    n = min(req.n or settings.sim_panel_default, settings.sim_panel_max)

    # 1. Edited roster from the UI wins (non-empty). Empty falls through.
    if req.audience:
        members = req.audience[: settings.sim_panel_max]
        await save_audience_members(members, source="Provided Audience")
        return members, "provided"

    # 2. Reuse the persisted audience population when available.
    if req.use_library:
        members = await load_audience_members(limit=settings.sim_panel_max)
        if len(members) >= n:
            return random.sample(members, n) if len(members) > n else members, "graph"
        if members:
            missing = n - len(members)
            generated = await generate_personas(missing)
            await save_audience_members(generated, source="Persona Synthesis")
            return members + generated, "graph+generated"

    # 3. Synthesise a fresh, diverse audience and persist it for reuse.
    members = await generate_personas(n)
    await save_audience_members(members, source="Persona Synthesis")
    return members, "generated"


async def stream_audience_sim(
    req: AudienceSimRequest, emit: Callable[[dict], None]
) -> dict:
    """Run the simulator, emitting live events; return the aggregated result dict.

    Designed to be driven by :func:`app.engine.streaming.ndjson_events`, which
    appends the terminal ``done`` line carrying this return value.
    """
    llm = get_llm()
    cache = Cache(settings.cache_dir)
    model = settings.model_for("sim")

    members, source = await resolve_audience(req)
    emit(
        {
            "type": "run_started",
            "total": len(members),
            "audience_source": source,
            "model": model,
            "has_image": bool(req.story.image_base64),
            "agentic": settings.sim_agentic,
        }
    )

    # Ground the agents in shared story memory (best-effort; empty when no graph).
    canon = render_canon_memory(await fetch_canon_subgraph(req.story, source=_SOURCE))

    pairs, dropped = await run_social_reactions(
        members,
        req.story,
        llm,
        cache,
        model=model,
        canon=canon,
        canon_fp=canon_fingerprint(canon),
        on_event=emit,
        source=_SOURCE,
    )

    result = aggregate_sim(pairs, dropped=dropped)

    # Persist: Firestore archive + knowledge-graph write-back (agent memory).
    save_simulation("audience_sim", req.story, result.model_dump())
    await write_member_reactions(req.story, pairs, source=_SOURCE)

    return result.model_dump()


async def generate_audience(req: GeneratePersonasRequest) -> AudienceLibrary:
    """Synthesise a diverse audience and (optionally) persist it to the graph."""
    n = min(req.n or settings.sim_panel_default, settings.sim_panel_max)
    members = await generate_personas(n, brief=req.brief, seed_segments=req.seed_segments)
    if req.persist:
        await save_audience_members(members, source="Persona Synthesis")
    return AudienceLibrary(members=members, total=len(members), source="generated")


async def list_audience() -> AudienceLibrary:
    """Return the persisted audience population, or default archetypes if empty."""
    members = await load_audience_members()
    if members:
        return AudienceLibrary(members=members, total=len(members), source="graph")
    defaults = load_personas("audience")
    return AudienceLibrary(members=defaults, total=len(defaults), source="defaults")
