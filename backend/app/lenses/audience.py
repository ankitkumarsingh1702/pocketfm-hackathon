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
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import AudienceResult, Story


async def run_audience(story: Story, n: int | None = None) -> AudienceResult:
    """Run the audience simulation for `story` across `n` listeners."""
    personas = load_personas("audience")
    n = n or settings.audience_fanout
    personas = fan_out_audience(personas, n)

    llm = get_llm()
    cache = Cache(settings.cache_dir)

    pairs = await run_reactions(
        personas, story, llm, cache, model=settings.model_for("audience")
    )
    result = aggregate_audience(pairs)

    save_simulation("audience", story, result.model_dump())
    return result
