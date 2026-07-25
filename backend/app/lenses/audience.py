"""Audience lens — simulate a representative panel of listeners for one episode.

Fans a small set of base audience personas out to `n` listeners, gathers a
structured reaction from each (with caching for instant re-runs), and folds the
reactions into an :class:`AudienceResult` (binge rate, hook score, drop-off
curve, per-segment stats, churn reasons, and a few sample reactions).
"""

from __future__ import annotations

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.aggregate import aggregate_audience
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.graph.store import (
    canon_fingerprint,
    fetch_canon_subgraph,
    render_canon_memory,
    write_audience_verdict,
)
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import AudienceResult, Story


async def run_audience(story: Story, n: int | None = None) -> AudienceResult:
    """Run the audience simulation for `story` across `n` listeners.

    Listeners react with the story-canon memory injected (when available), so
    they behave as returning listeners; their per-segment verdicts are written
    back to the graph as `REACTED_TO` edges.
    """
    personas = load_personas("audience")
    n = n or settings.audience_fanout
    personas = fan_out_audience(personas, n)

    llm = get_llm()
    cache = Cache(settings.cache_dir)

    canon = render_canon_memory(await fetch_canon_subgraph(story, source="Audience"))
    pairs = await run_reactions(
        personas,
        story,
        llm,
        cache,
        model=settings.model_for("audience"),
        canon=canon,
        canon_fp=canon_fingerprint(canon),
    )
    result = aggregate_audience(pairs)

    save_simulation("audience", story, result.model_dump())
    await write_audience_verdict(
        story,
        [
            {"segment": s.segment, "following_pct": s.binge_pct, "avg_hook": s.avg_hook}
            for s in result.segments
        ],
        source="Audience",
    )
    return result
