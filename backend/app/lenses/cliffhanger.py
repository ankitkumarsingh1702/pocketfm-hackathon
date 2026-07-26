"""Cliffhanger lens — rewrite a weak ending and A/B test it on a mini panel.

The LLM rewrites the soft excerpt into a gripping cliffhanger, then a small
audience panel scores the episode before and after the swap. The lift in
average hook score quantifies the improvement.

``run_cliffhanger`` accepts an optional ``emit`` callback. When the streaming
endpoint passes one, the lens narrates its own work as it happens — the rewrite,
then each listener-agent's hook score for the original and the optimized ending
as it lands — so the UI can show a live, CLI-style run log instead of an opaque
spinner. With the default no-op emit, behaviour is identical to before.
"""

from __future__ import annotations

from collections.abc import Callable

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


def _noop(_event: dict) -> None:
    """Default emit sink — used when the caller doesn't want a live stream."""


def _mean_hook(pairs: list[tuple[Persona, PersonaReaction]]) -> float:
    """Average hook score over a set of reactions (0.0 when empty)."""
    if not pairs:
        return 0.0
    return sum(reaction.hook_score for _, reaction in pairs) / len(pairs)


def _agent_emitter(
    emit: Callable[[dict], None],
    phase: str,
    total: int,
) -> Callable[[Persona, PersonaReaction, bool], None]:
    """Build an ``on_reaction`` hook that streams one event per scored agent.

    Each event carries the listener's identity, its hook score, whether it was a
    cache hit, and the running mean so far — enough for the client to render a
    live log with a climbing panel average.
    """
    state = {"done": 0, "sum": 0.0}

    def _on(persona: Persona, reaction: PersonaReaction, cached: bool) -> None:
        state["done"] += 1
        state["sum"] += reaction.hook_score
        emit(
            {
                "type": "agent_scored",
                "phase": phase,
                "done": state["done"],
                "total": total,
                "persona": {
                    "id": persona.id,
                    "name": persona.name,
                    "segment": persona.segment or "General",
                },
                "hook_score": reaction.hook_score,
                "cached": cached,
                "running_mean": round(state["sum"] / state["done"], 1),
            }
        )

    return _on


async def run_cliffhanger(
    story: Story,
    weak_excerpt: str,
    emit: Callable[[dict], None] = _noop,
) -> CliffhangerResult:
    """Rewrite `weak_excerpt` into a cliffhanger and measure the hook-score lift.

    ``emit`` receives progress events (see module docstring). It defaults to a
    no-op so the plain (non-streaming) endpoint is unaffected.
    """
    llm = get_llm()

    cache = Cache(settings.cache_dir)
    panel = fan_out_audience(load_personas("audience"), min(12, settings.audience_fanout))
    panel_size = len(panel)
    rewrite_model = settings.model_for("rewrite")
    audience_model = settings.model_for("audience")

    emit(
        {
            "type": "run_started",
            "panel_size": panel_size,
            "rewrite_model": rewrite_model,
            "audience_model": audience_model,
            "weak_excerpt": weak_excerpt,
        }
    )

    emit({"type": "phase", "phase": "rewrite", "status": "start"})
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
        model=rewrite_model,
    )
    emit(
        {
            "type": "phase",
            "phase": "rewrite",
            "status": "done",
            "rewrite": rewrite.rewrite,
            "rationale": rewrite.rationale,
        }
    )

    before_story = story
    if weak_excerpt in story.text:
        after_text = story.text.replace(weak_excerpt, rewrite.rewrite)
    else:
        after_text = story.text + "\n" + rewrite.rewrite
    after_story = Story(title=story.title, episode=story.episode, text=after_text)

    # Same canon for both A/B runs (memory is the show's, not the excerpt's), so
    # only the rewritten ending differs between before/after.
    canon = render_canon_memory(await fetch_canon_subgraph(story, source="Cliffhanger"))
    canon_fp = canon_fingerprint(canon)

    emit({"type": "phase", "phase": "panel_before", "status": "start", "total": panel_size})
    before_pairs = await run_reactions(
        panel,
        before_story,
        llm,
        cache,
        model=audience_model,
        canon=canon,
        canon_fp=canon_fp,
        on_reaction=_agent_emitter(emit, "before", panel_size),
    )
    before_score = _mean_hook(before_pairs)
    emit(
        {
            "type": "phase",
            "phase": "panel_before",
            "status": "done",
            "score": round(before_score, 1),
            "rated": len(before_pairs),
        }
    )

    emit({"type": "phase", "phase": "panel_after", "status": "start", "total": panel_size})
    after_pairs = await run_reactions(
        panel,
        after_story,
        llm,
        cache,
        model=audience_model,
        canon=canon,
        canon_fp=canon_fp,
        on_reaction=_agent_emitter(emit, "after", panel_size),
    )
    after_score = _mean_hook(after_pairs)
    emit(
        {
            "type": "phase",
            "phase": "panel_after",
            "status": "done",
            "score": round(after_score, 1),
            "rated": len(after_pairs),
        }
    )

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
