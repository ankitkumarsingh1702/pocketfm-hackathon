"""A2A Word-of-Mouth lens — orchestrates one social-cascade run.

Resolves a listener population (reusing the persisted knowledge-graph audience),
builds a homophily social graph, seeds the post to a small cohort, and runs the
round-by-round cascade where a spreading agent's comment is injected into its
peers' prompts. Streams events live; after the run, best-effort persists the
FOLLOWS graph, the agent-to-agent INFLUENCED edges, and each reaction as normal
listener memory. Everything degrades gracefully when the graph is unavailable.

Isolated from the Audience Simulator: it only *imports* pure helpers
(``resolve_canon``) and shared stores; it never modifies that lens.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.a2a_cascade import (
    A2A_AVG_DEGREE,
    A2A_MAX_ROUNDS,
    A2A_POPULATION_CAP,
    A2A_SEED_DEFAULT,
    build_adjacency,
    run_cascade,
)
from app.engine.cache import Cache
from app.graph.a2a_store import save_follow_edges, write_influence_edges
from app.graph.audience_store import (
    load_audience_members,
    save_audience_members,
    write_member_reactions,
)
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.lenses.audience_sim import resolve_canon
from app.llm.factory import get_llm
from app.personas.generator import generate_personas
from app.schemas import A2ACascadeRequest

_SOURCE = "A2A Word-of-Mouth"


async def _resolve_population(req: A2ACascadeRequest) -> list[str] | list:
    """Return the listener population the post can spread through.

    Prefers the persisted knowledge-graph audience (sampled), tops up / falls
    back to freshly synthesised (and persisted) members so the social graph and
    FOLLOWS/INFLUENCED edges always reference real nodes.
    """
    seed = req.seed_n or A2A_SEED_DEFAULT
    # A network several times the seed so word-of-mouth has room to spread.
    target = max(seed + 20, min(seed * 6, A2A_POPULATION_CAP))

    if req.use_library:
        members = await load_audience_members(limit=A2A_POPULATION_CAP, source=_SOURCE)
        if len(members) >= target:
            return random.sample(members, target)
        if members:
            extra = await generate_personas(target - len(members))
            await save_audience_members(extra, source="Persona Synthesis")
            return members + extra

    members = await generate_personas(target)
    await save_audience_members(members, source="Persona Synthesis")
    return members


async def stream_a2a_cascade(req: A2ACascadeRequest, emit: Callable[[dict], None]) -> dict:
    """Run one A2A cascade, emitting live events; return the result dict.

    Driven by :func:`app.engine.streaming.ndjson_events`, which appends the
    terminal ``done`` line carrying this return value.
    """
    llm = get_llm()
    cache = Cache(settings.cache_dir)
    model = settings.model_for("sim")

    population = await _resolve_population(req)
    adjacency = build_adjacency(population, req.avg_degree or A2A_AVG_DEGREE)
    await save_follow_edges(adjacency, source=_SOURCE)

    seed_n = min(req.seed_n or A2A_SEED_DEFAULT, len(population))
    seeds = random.sample(population, seed_n) if len(population) > seed_n else population
    seed_ids = [p.id for p in seeds]

    emit(
        {
            "type": "run_started",
            "seed": len(seed_ids),
            "population": len(population),
            "max_rounds": req.max_rounds or A2A_MAX_ROUNDS,
            "model": model,
            "agentic": settings.sim_agentic,
            "has_image": bool(req.story.image_base64),
        }
    )

    graph_canon = render_canon_memory(await fetch_canon_subgraph(req.story, source=_SOURCE))
    canon = resolve_canon(req.story.story_so_far, graph_canon, settings.canon_max_chars)

    outcome = await run_cascade(
        population,
        adjacency,
        seed_ids,
        req.story,
        llm,
        cache,
        model=model,
        canon=canon,
        canon_fp=canon_fingerprint(canon),
        max_rounds=req.max_rounds or A2A_MAX_ROUNDS,
        on_event=emit,
        source=_SOURCE,
    )

    # Persist (best-effort): the agent-to-agent influence edges + normal memory.
    await write_influence_edges(req.story, outcome["influence"], source=_SOURCE)
    if outcome["pairs"]:
        await write_member_reactions(req.story, outcome["pairs"], source=_SOURCE)
    save_simulation("a2a_cascade", req.story, outcome["result"].model_dump())

    return outcome["result"].model_dump()
