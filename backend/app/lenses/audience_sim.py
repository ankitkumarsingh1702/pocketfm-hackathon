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
from app.engine.aggregate import aggregate_sim, reaction_view
from app.engine.audience_agent import run_social_reactions
from app.engine.cache import Cache
from app.graph.audience_store import (
    get_audience_member,
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
    Story,
)

_SOURCE = "Audience Simulator"


def resolve_canon(story_so_far: str | None, graph_canon: str | None, cap: int) -> str:
    """Choose the story-so-far context for the reacting agents and bound its size.

    The client-assembled recap (episodes 1..N-1 of the posted show) wins: it is
    episode-scoped — so an agent reacting to episode N can't "remember" future
    episodes — and works for the bundled library shows that never enter the
    knowledge graph. Falls back to the shared graph canon for standalone posts.
    Hard-capped so a long season can't blow the prompt budget.
    """
    return (story_so_far or graph_canon or "")[:cap]


async def resolve_audience(req: AudienceSimRequest) -> tuple[list[Persona], str]:
    """Return ``(members, source)`` for a run — provided / graph / generated."""
    n = min(req.n or settings.sim_panel_default, settings.sim_panel_max)

    # 1. Edited roster from the UI wins (non-empty). Persist it, then top up to n
    #    so an edited/small roster still fans out to the full requested panel size
    #    (Run never silently under-delivers to a handful).
    if req.audience:
        members = req.audience[: settings.sim_panel_max]
        await save_audience_members(members, source="Provided Audience")
        if len(members) < n:
            generated = await generate_personas(n - len(members))
            await save_audience_members(generated, source="Persona Synthesis")
            return members + generated, "provided+generated"
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

    # Ground the agents in the story SO FAR: the client's episode-scoped recap of
    # what precedes this post (episodes 1..N-1), else the shared-graph canon.
    graph_canon = render_canon_memory(await fetch_canon_subgraph(req.story, source=_SOURCE))
    canon = resolve_canon(req.story.story_so_far, graph_canon, settings.canon_max_chars)

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


async def react_one_agent(agent_id: str, story: Story, source: str = "Agent API") -> dict | None:
    """One addressed agent reacts LIVE to a post, and remembers it.

    Loads the persona by id, runs the same perceive→recall→react pipeline the
    panel uses (grounded in the story-so-far / graph canon), persists the reaction
    as a REACTED_TO edge (so the agent's history grows), and returns the reaction
    as an ``AudienceReactionView`` dict. Returns ``None`` when no such agent
    exists. Shared by the per-agent HTTP endpoint and the MCP ``ask_agent`` tool.
    """
    persona = await get_audience_member(agent_id)
    if persona is None:
        return None
    llm = get_llm()
    cache = Cache(settings.cache_dir)
    model = settings.model_for("sim")
    graph_canon = render_canon_memory(await fetch_canon_subgraph(story, source=source))
    canon = resolve_canon(story.story_so_far, graph_canon, settings.canon_max_chars)
    pairs, _ = await run_social_reactions(
        [persona],
        story,
        llm,
        cache,
        model=model,
        canon=canon,
        canon_fp=canon_fingerprint(canon),
        source=source,
    )
    if not pairs:
        return None
    _, reaction = pairs[0]
    await write_member_reactions(story, pairs, source=source)
    return reaction_view(persona, reaction).model_dump()


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
