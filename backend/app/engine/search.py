"""Tree search over candidate cliffhangers, scored by the audience simulator.

This is the "planning" capability: instead of generating one rewrite, we grow a
search tree — each round the LLM proposes variants of the surviving beam, each
variant is scored by fanning it out to the (canon-aware) audience panel, and the
top-k survive. The audience simulator is the scoring function, so planning is
grounded in simulated retention, not vibes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from pydantic import BaseModel

from app.config import settings
from app.engine.cache import Cache
from app.engine.cliffhanger_swarm import (
    ci95,
    mean_score,
    persist_experiment_memory,
    run_cliffhanger_panel,
    stratified_sample,
)
from app.graph.audience_store import recall_members_memories, save_audience_members
from app.graph.driver import graph_probe
from app.graph.store import fetch_canon_subgraph, render_canon_memory
from app.lenses.audience_sim import resolve_audience
from app.llm.base import LLMClient
from app.schemas import AudienceSimRequest, PlanCandidate, SearchTree, Story

logger = logging.getLogger(__name__)


class _Variants(BaseModel):
    rewrites: list[str]


async def _stateful_graph_ready() -> bool:
    return settings.sim_agentic and settings.graph_configured and await graph_probe()


async def _variants(
    llm: LLMClient, story: Story, current_ending: str, n: int
) -> list[str]:
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
    panel_size: int = 1000,
    scout_size: int = 100,
    finalist_count: int = 3,
    on_event: Callable[[dict], None] | None = None,
) -> SearchTree:
    """Search with scouts, then verify finalists on one stateful full cohort."""

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    beam_width = max(1, min(beam_width, 5))
    depth = max(1, min(depth, 2))
    panel_size = max(1, min(panel_size, settings.sim_panel_max))
    scout_size = max(1, min(scout_size, panel_size))
    finalist_count = max(1, min(finalist_count, beam_width))
    model = settings.model_for("audience")
    if not await _stateful_graph_ready():
        raise RuntimeError(
            "The persistent audience graph is unavailable. "
            "This planner will not fall back to prompt-only personas."
        )

    emit(
        {
            "type": "phase_started",
            "phase": "loading",
            "label": f"Loading {panel_size:,} persistent listener identities",
        }
    )
    panel, audience_source = await resolve_audience(
        AudienceSimRequest(story=story, n=panel_size, use_library=True)
    )
    actual_panel_size = len(panel)
    if not panel:
        raise RuntimeError("No audience agents were available for the planner")
    persisted = await save_audience_members(panel, source="Cliffhanger Planner")
    if persisted != actual_panel_size:
        raise RuntimeError(
            f"Only {persisted} of {actual_panel_size} listener identities were persisted; "
            "the planner stopped before scoring."
        )

    canon = render_canon_memory(
        await fetch_canon_subgraph(story, source="Cliffhanger Planner")
    )
    memories = (
        await recall_members_memories(
            [member.id for member in panel],
            show=story.title,
            source="Cliffhanger Planner",
        )
        if settings.sim_agentic
        else {}
    )
    memory_hits = sum(1 for member in panel if memories.get(member.id))

    emit(
        {
            "type": "phase_started",
            "phase": "generation",
            "label": "Writing distinct cliffhanger candidates",
        }
    )
    raw_candidates: list[dict] = []
    text_by_id: dict[str, str] = {"root": weak_excerpt}
    beam = ["root"]
    counter = 0
    rounds_completed = 0

    for d in range(1, depth + 1):
        round_ids: list[str] = []
        variant_groups = await asyncio.gather(
            *(
                _variants(llm, story, text_by_id[parent_id], beam_width)
                for parent_id in beam
            )
        )
        for parent_id, variants in zip(beam, variant_groups, strict=True):
            for text in variants:
                counter += 1
                cid = f"c{counter}"
                text_by_id[cid] = text
                raw_candidates.append(
                    {
                        "id": cid,
                        "text": text,
                        "parent_id": parent_id,
                        "depth": d,
                    }
                )
                round_ids.append(cid)
                emit(
                    {
                        "type": "candidate_generated",
                        "id": cid,
                        "parent_id": parent_id,
                        "depth": d,
                        "preview": text[:140],
                    }
                )
        # Depth is capped at two; all first-round variants seed refinement.
        beam = round_ids[:beam_width]
        if not beam:
            break
        rounds_completed = d

    scout_members = stratified_sample(panel, min(scout_size, actual_panel_size))
    all_alternatives = [("root", weak_excerpt)] + [
        (candidate["id"], candidate["text"]) for candidate in raw_candidates
    ]
    emit(
        {
            "type": "run_started",
            "unique_agents": actual_panel_size,
            "panel_requested": panel_size,
            "scout_size": len(scout_members),
            "candidate_count": len(raw_candidates),
            "finalist_count": min(finalist_count, len(raw_candidates)),
            "audience_source": audience_source,
            "model": model,
            "agentic": settings.sim_agentic,
            "memory_hits": memory_hits,
            "shared_canon_loaded": bool(canon),
        }
    )

    scout_ratings: dict = {"root": []}
    scout_dropped = 0
    scout_cached = 0
    if raw_candidates:
        emit(
            {
                "type": "phase_started",
                "phase": "scout",
                "label": f"Exploring {len(raw_candidates)} rewrites with {len(scout_members)} scout agents",
                "total": len(scout_members),
            }
        )
        scout_ratings, scout_dropped, scout_cached = await run_cliffhanger_panel(
            members=scout_members,
            story=story,
            weak_excerpt=weak_excerpt,
            alternatives=all_alternatives,
            canon=canon,
            memories=memories,
            llm=llm,
            cache=cache,
            model=model,
            phase="scout",
            emit=emit,
        )

    scout_baseline_ratings = [rating for _, rating in scout_ratings.get("root", [])]
    scout_baseline = mean_score(scout_baseline_ratings)
    scout_scores: dict[str, float] = {}
    for candidate in raw_candidates:
        candidate_id = candidate["id"]
        ratings = [rating for _, rating in scout_ratings.get(candidate_id, [])]
        score = mean_score(ratings)
        scout_scores[candidate_id] = score
        emit(
            {
                "type": "candidate_scored",
                "stage": "scout",
                "id": candidate_id,
                "parent_id": candidate["parent_id"],
                "depth": candidate["depth"],
                "hook_score": score,
                "delta": round(score - scout_baseline, 1),
                "sample_size": len(ratings),
                "ci95": ci95(ratings),
                "preview": candidate["text"][:140],
            }
        )

    finalist_ids = sorted(
        scout_scores,
        key=lambda candidate_id: scout_scores[candidate_id],
        reverse=True,
    )[:finalist_count]
    emit(
        {
            "type": "round_done",
            "round": depth,
            "kept": finalist_ids,
            "scout_dropped": scout_dropped,
        }
    )

    verification_alternatives = [("root", weak_excerpt)] + [
        (candidate_id, text_by_id[candidate_id]) for candidate_id in finalist_ids
    ]
    scout_planned = len(scout_members) * len(all_alternatives) if raw_candidates else 0
    planned_evaluations = scout_planned + actual_panel_size * len(
        verification_alternatives
    )
    emit(
        {
            "type": "phase_started",
            "phase": "verification",
            "label": (
                f"Verifying the original and {len(finalist_ids)} finalist"
                f"{'s' if len(finalist_ids) != 1 else ''} with all {actual_panel_size:,} agents"
            ),
            "total": actual_panel_size,
            "planned_evaluations": planned_evaluations,
        }
    )
    (
        verified_ratings,
        verification_dropped,
        verified_cached,
    ) = await run_cliffhanger_panel(
        members=panel,
        story=story,
        weak_excerpt=weak_excerpt,
        alternatives=verification_alternatives,
        canon=canon,
        memories=memories,
        llm=llm,
        cache=cache,
        model=model,
        phase="verification",
        emit=emit,
    )
    baseline_ratings = [rating for _, rating in verified_ratings.get("root", [])]
    baseline = mean_score(baseline_ratings)
    emit(
        {
            "type": "baseline",
            "score": baseline,
            "sample_size": len(baseline_ratings),
            "ci95": ci95(baseline_ratings),
        }
    )

    candidates: list[PlanCandidate] = [
        PlanCandidate(
            id="root",
            text=weak_excerpt,
            hook_score=baseline,
            delta=0.0,
            parent_id=None,
            depth=0,
            sample_size=len(baseline_ratings),
            ci95=ci95(baseline_ratings),
            stage="baseline",
        )
    ]
    for candidate in raw_candidates:
        candidate_id = candidate["id"]
        is_finalist = candidate_id in finalist_ids
        pairs = (
            verified_ratings.get(candidate_id, [])
            if is_finalist
            else scout_ratings.get(candidate_id, [])
        )
        ratings = [rating for _, rating in pairs]
        score = mean_score(ratings)
        comparison_baseline = baseline if is_finalist else scout_baseline
        stage = "verified" if is_finalist else "scout"
        plan_candidate = PlanCandidate(
            id=candidate_id,
            text=candidate["text"],
            hook_score=score,
            delta=round(score - comparison_baseline, 1),
            parent_id=candidate["parent_id"],
            depth=candidate["depth"],
            sample_size=len(ratings),
            ci95=ci95(ratings),
            stage=stage,
        )
        candidates.append(plan_candidate)
        if is_finalist:
            emit(
                {
                    "type": "candidate_scored",
                    "stage": "verified",
                    "id": candidate_id,
                    "parent_id": candidate["parent_id"],
                    "depth": candidate["depth"],
                    "hook_score": score,
                    "delta": plan_candidate.delta,
                    "sample_size": len(ratings),
                    "ci95": plan_candidate.ci95,
                    "preview": candidate["text"][:140],
                }
            )

    verified_candidates = [
        candidate
        for candidate in candidates
        if candidate.id == "root" or candidate.stage == "verified"
    ]
    best = max(verified_candidates, key=lambda candidate: candidate.hook_score)
    winner_pairs = verified_ratings.get(best.id, [])
    emit(
        {
            "type": "phase_started",
            "phase": "memory_write",
            "label": "Archiving the winning experiment in the graph",
        }
    )
    experiment_archived = (
        await persist_experiment_memory(
            story,
            best.text,
            weak_excerpt,
            verified_ratings.get("root", []),
            winner_pairs,
        )
        if settings.sim_agentic
        else False
    )
    emit(
        {
            "type": "experiment_archived",
            "archived": experiment_archived,
            "evaluations": len(winner_pairs) if experiment_archived else 0,
        }
    )

    completed_evaluations = sum(len(pairs) for pairs in scout_ratings.values()) + sum(
        len(pairs) for pairs in verified_ratings.values()
    )
    return SearchTree(
        candidates=candidates,
        best_id=best.id,
        rounds=rounds_completed,
        baseline_score=baseline,
        panel_requested=panel_size,
        panel_actual=actual_panel_size,
        panel_completed=len(baseline_ratings),
        panel_dropped=verification_dropped,
        scout_size=len(scout_members),
        finalist_count=len(finalist_ids),
        planned_evaluations=planned_evaluations,
        completed_evaluations=completed_evaluations,
        memory_hits=memory_hits,
        cached_agents=scout_cached + verified_cached,
        verification_cached_agents=verified_cached,
        audience_source=audience_source,
        model=model,
        agentic=settings.sim_agentic,
        experiment_archived=experiment_archived,
    )
