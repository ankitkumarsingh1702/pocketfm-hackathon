"""Cliffhanger lens — rewrite a weak ending and A/B test it on a mini panel.

The LLM rewrites the soft excerpt into a gripping cliffhanger, then a small
audience panel scores the episode before and after the swap. The lift in
average hook score quantifies the improvement.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import CliffhangerResult, Persona, PersonaReaction, Story


class _Rewrite(BaseModel):
    """Private structured output for the cliffhanger rewrite."""

    rewrite: str
    rationale: str


def _mean_hook(pairs: list[tuple[Persona, PersonaReaction]]) -> float:
    """Average hook score over a set of reactions (0.0 when empty)."""
    if not pairs:
        return 0.0
    return sum(reaction.hook_score for _, reaction in pairs) / len(pairs)


async def run_cliffhanger(story: Story, weak_excerpt: str) -> CliffhangerResult:
    """Rewrite `weak_excerpt` into a cliffhanger and measure the hook-score lift."""
    llm = get_llm()

    rewrite = await llm.structured(
        system="You are a master cliffhanger editor for audio dramas.",
        prompt=(
            "Rewrite this weak ending into a gripping cliffhanger. "
            "Keep it same length-ish. ENDING:\n"
            + weak_excerpt
            + "\n\nCONTEXT (episode):\n"
            + story.text[:2000]
        ),
        schema=_Rewrite,
        model=settings.model_for("rewrite"),
    )

    cache = Cache(settings.cache_dir)
    panel = fan_out_audience(load_personas("audience"), min(12, settings.audience_fanout))

    before_story = story
    if weak_excerpt in story.text:
        after_text = story.text.replace(weak_excerpt, rewrite.rewrite)
    else:
        after_text = story.text + "\n" + rewrite.rewrite
    after_story = Story(title=story.title, episode=story.episode, text=after_text)

    audience_model = settings.model_for("audience")
    # Same canon for both A/B runs (memory is the show's, not the excerpt's), so
    # only the rewritten ending differs between before/after.
    canon = render_canon_memory(await fetch_canon_subgraph(story))
    canon_fp = canon_fingerprint(canon)
    before_pairs = await run_reactions(
        panel, before_story, llm, cache, model=audience_model, canon=canon, canon_fp=canon_fp
    )
    after_pairs = await run_reactions(
        panel, after_story, llm, cache, model=audience_model, canon=canon, canon_fp=canon_fp
    )

    before_score = _mean_hook(before_pairs)
    after_score = _mean_hook(after_pairs)

    result = CliffhangerResult(
        original=weak_excerpt,
        rewrite=rewrite.rewrite,
        before_score=round(before_score, 1),
        after_score=round(after_score, 1),
        lift=round(after_score - before_score, 1),
        rationale=rewrite.rationale,
    )
    save_simulation("cliffhanger", story, result.model_dump())
    return result
