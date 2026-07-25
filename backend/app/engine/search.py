"""Tree search over candidate cliffhangers, scored by the audience simulator.

This is the "planning" capability: instead of generating one rewrite, we grow a
search tree — each round the LLM proposes variants of the surviving beam, each
variant is scored by fanning it out to the (canon-aware) audience panel, and the
top-k survive. The audience simulator is the scoring function, so planning is
grounded in simulated retention, not vibes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel

from app.config import settings
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.llm.base import LLMClient
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import PersonaReaction, PlanCandidate, Persona, SearchTree, Story

logger = logging.getLogger(__name__)


class _Variants(BaseModel):
    rewrites: list[str]


def _mean_hook(pairs: list[tuple[Persona, PersonaReaction]]) -> float:
    return sum(r.hook_score for _, r in pairs) / len(pairs) if pairs else 0.0


def _swap(text: str, old: str, new: str) -> str:
    return text.replace(old, new) if old and old in text else text + "\n" + new


async def _variants(llm: LLMClient, story: Story, current_ending: str, n: int) -> list[str]:
    """Ask the LLM for ``n`` distinct cliffhanger rewrites of ``current_ending``."""
    try:
        res = await llm.structured(
            system="You are a master cliffhanger editor for audio dramas.",
            prompt=(
                f"Rewrite this ending into {n} DISTINCT, gripping cliffhangers. "
                f"Keep each roughly the same length. Return exactly {n}.\n\n"
                f"ENDING:\n{current_ending}\n\nEPISODE CONTEXT:\n{story.text[:1500]}"
            ),
            schema=_Variants,
            model=settings.model_for("rewrite"),
        )
        return [r for r in res.rewrites if r.strip()][:n]
    except Exception as exc:  # noqa: BLE001 - a barren round just narrows the beam
        logger.warning("Variant generation failed: %s", exc)
        return []


async def beam_search(
    story: Story,
    weak_excerpt: str,
    llm: LLMClient,
    cache: Cache,
    beam_width: int = 3,
    depth: int = 2,
    on_event: Callable[[dict], None] | None = None,
) -> SearchTree:
    """Beam-search cliffhanger rewrites, scoring each on the audience panel."""
    canon = render_canon_memory(await fetch_canon_subgraph(story))
    canon_fp = canon_fingerprint(canon)
    panel = fan_out_audience(load_personas("audience"), min(12, settings.audience_fanout))
    audience_model = settings.model_for("audience")

    async def score(ending: str) -> float:
        candidate_story = Story(
            title=story.title, episode=story.episode, text=_swap(story.text, weak_excerpt, ending)
        )
        pairs = await run_reactions(
            panel, candidate_story, llm, cache,
            model=audience_model, canon=canon, canon_fp=canon_fp,
        )
        return round(_mean_hook(pairs), 1)

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    baseline = await score(weak_excerpt)
    emit({"type": "baseline", "score": baseline})

    candidates: list[PlanCandidate] = [
        PlanCandidate(id="root", text=weak_excerpt, hook_score=baseline, delta=0.0, parent_id=None, depth=0)
    ]
    text_by_id: dict[str, str] = {"root": weak_excerpt}
    score_by_id: dict[str, float] = {"root": baseline}
    beam = ["root"]
    counter = 0

    for d in range(1, depth + 1):
        round_ids: list[str] = []
        for parent_id in beam:
            variants = await _variants(llm, story, text_by_id[parent_id], beam_width)
            for text in variants:
                counter += 1
                cid = f"c{counter}"
                s = await score(text)
                text_by_id[cid] = text
                score_by_id[cid] = s
                candidates.append(
                    PlanCandidate(
                        id=cid, text=text, hook_score=s, delta=round(s - baseline, 1),
                        parent_id=parent_id, depth=d,
                    )
                )
                round_ids.append(cid)
                emit({
                    "type": "candidate_scored",
                    "id": cid, "parent_id": parent_id, "depth": d,
                    "hook_score": s, "delta": round(s - baseline, 1),
                    "preview": text[:140],
                })
        round_ids.sort(key=lambda i: score_by_id[i], reverse=True)
        beam = round_ids[:beam_width]
        emit({"type": "round_done", "round": d, "kept": beam, "best_score": score_by_id[beam[0]] if beam else baseline})
        if not beam:
            break

    best = max(candidates, key=lambda c: c.hook_score)
    return SearchTree(candidates=candidates, best_id=best.id, rounds=depth, baseline_score=baseline)
