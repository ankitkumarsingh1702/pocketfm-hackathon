"""Showrunner agent — an explicit state-graph over the other capabilities.

This is the "actions" capability: instead of a linear pipeline, the showrunner
is a state machine that ingests the episode into the canon, checks continuity
against the graph, simulates the audience, DECIDES whether there's churn risk,
proposes a fix, re-simulates, and converges — looping the fix once if needed.
Every node reads and/or writes the shared knowledge graph, so the agent is
genuinely stateful: it remembers (canon), reasons over shared memory
(continuity), acts (fix), and records outcomes (write-back).
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.aggregate import aggregate_audience
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.engine.stategraph import StateGraph
from app.graph.extract import extract_canon
from app.graph.store import (
    canon_fingerprint,
    fetch_canon_subgraph,
    ingest_extraction,
    render_canon_memory,
    write_audience_verdict,
)
from app.lenses.plot_holes import find_plot_holes
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import ShowrunnerResult, Story


class _Fix(BaseModel):
    rewrite: str


def _swap(text: str, old: str, new: str) -> str:
    return text.replace(old, new) if old and old in text else text + "\n" + new


def _weak_excerpt(story: Story, provided: str | None) -> str:
    if provided and provided.strip():
        return provided
    blocks = [b.strip() for b in story.text.split("\n\n") if b.strip()]
    return blocks[-1] if blocks else story.text[-400:]


async def run_showrunner(
    story: Story, weak_excerpt: str | None, emit: Callable[[dict], None]
) -> dict:
    """Drive the showrunner state graph and return a ShowrunnerResult dict."""
    llm = get_llm()
    cache = Cache(settings.cache_dir)
    panel = fan_out_audience(load_personas("audience"), min(10, settings.audience_fanout))
    audience_model = settings.model_for("audience")
    weak = _weak_excerpt(story, weak_excerpt)

    async def simulate(target: Story, canon: str, canon_fp: str) -> dict:
        pairs = await run_reactions(
            panel, target, llm, cache, model=audience_model, canon=canon, canon_fp=canon_fp
        )
        result = aggregate_audience(pairs)
        return {"binge_pct": result.binge_pct, "avg_hook": result.avg_hook_score}

    async def rewrite(weak_text: str, canon: str) -> str:
        try:
            res = await llm.structured(
                system="You are a master cliffhanger editor for audio dramas.",
                prompt=(
                    "Rewrite this weak ending into a gripping cliffhanger that stays "
                    "consistent with the known canon. Keep length similar.\n\n"
                    f"ENDING:\n{weak_text}\n\nKNOWN CANON:\n{canon}\n\nCONTEXT:\n{story.text[:1200]}"
                ),
                schema=_Fix,
                model=settings.model_for("rewrite"),
            )
            return res.rewrite
        except Exception:  # noqa: BLE001
            return weak_text

    # --- nodes (closures capture emit + shared context) ---
    async def ingest_node(state: dict) -> dict:
        extraction = await extract_canon(story, llm)
        res = await ingest_extraction(story, extraction)
        sub = await fetch_canon_subgraph(story)
        state["canon"] = render_canon_memory(sub)
        state["canon_fp"] = canon_fingerprint(state["canon"])
        state["transcript"].append({"node": "ingest", "detail": f"canon +{res.nodes_added} nodes, +{res.edges_added} edges"})
        emit({"type": "agent", "node": "ingest", "detail": f"Ingested episode → canon +{res.nodes_added} nodes / +{res.edges_added} edges"})
        return state

    async def continuity_node(state: dict) -> dict:
        ph = await find_plot_holes(story)
        highs = sum(1 for h in ph.holes if h.severity == "high")
        state["contradictions_found"] = len(ph.holes)
        state["high_contradictions"] = highs
        state["transcript"].append({"node": "continuity", "detail": f"{len(ph.holes)} issues, {highs} high"})
        emit({"type": "agent", "node": "continuity", "detail": f"Found {len(ph.holes)} continuity issues ({highs} high-severity) using the canon graph"})
        return state

    async def simulate_node(state: dict) -> dict:
        m = await simulate(story, state["canon"], state["canon_fp"])
        state["audience"] = m
        state["before_score"] = m["avg_hook"]
        state["transcript"].append({"node": "simulate", "detail": f"binge {m['binge_pct']}%, hook {m['avg_hook']}"})
        emit({"type": "agent", "node": "simulate", "detail": f"Audience: {m['binge_pct']}% continue, hook {m['avg_hook']}/100"})
        return state

    async def decide_node(state: dict) -> dict:
        state["iterations"] += 1
        churn = state["audience"]["binge_pct"] < 55 or state.get("high_contradictions", 0) > 0
        state["churn_risk"] = churn
        state["decision"] = "fix" if (churn and state["iterations"] < 2) else "converge"
        state["transcript"].append({"node": "decide", "detail": f"churn_risk={churn} → {state['decision']}"})
        emit({"type": "decision", "node": "decide", "churn_risk": churn, "binge_pct": state["audience"]["binge_pct"], "decision": state["decision"], "iteration": state["iterations"]})
        return state

    async def propose_fix_node(state: dict) -> dict:
        new_ending = await rewrite(weak, state["canon"])
        state["fixed_text"] = _swap(story.text, weak, new_ending)
        state["contradictions_fixed"] = state.get("high_contradictions", 0)
        state["transcript"].append({"node": "propose_fix", "detail": "rewrote the weak beat, canon-consistent"})
        emit({"type": "agent", "node": "propose_fix", "detail": "Rewrote the weak ending to fix churn/continuity"})
        return state

    async def resimulate_node(state: dict) -> dict:
        fixed = Story(title=story.title, episode=story.episode, text=state["fixed_text"])
        m = await simulate(fixed, state["canon"], state["canon_fp"])
        state["audience"] = m
        state["after_score"] = m["avg_hook"]
        state["transcript"].append({"node": "resimulate", "detail": f"hook {m['avg_hook']} (was {state['before_score']})"})
        emit({"type": "agent", "node": "resimulate", "detail": f"Re-simulated fix: hook {m['avg_hook']}/100 (was {state['before_score']})"})
        return state

    async def converge_node(state: dict) -> dict:
        after = state.get("after_score", state["before_score"])
        state["after_score"] = after
        state["transcript"].append({"node": "converge", "detail": f"lift {round(after - state['before_score'], 1)}"})
        emit({"type": "agent", "node": "converge", "detail": f"Converged. Lift {round(after - state['before_score'], 1)}"})
        return state

    graph = StateGraph()
    for name, fn in [
        ("ingest", ingest_node), ("continuity", continuity_node), ("simulate", simulate_node),
        ("decide", decide_node), ("propose_fix", propose_fix_node), ("resimulate", resimulate_node),
        ("converge", converge_node),
    ]:
        graph.add_node(name, fn)
    graph.add_edge("ingest", "continuity")
    graph.add_edge("continuity", "simulate")
    graph.add_edge("simulate", "decide")
    graph.add_edge("decide", "propose_fix", cond=lambda s: s["decision"] == "fix")
    graph.add_edge("decide", "converge", cond=lambda s: s["decision"] == "converge")
    graph.add_edge("propose_fix", "resimulate")
    graph.add_edge("resimulate", "decide")
    graph.set_entry("ingest")

    emit({"type": "run_started", "nodes": ["ingest", "continuity", "simulate", "decide", "propose_fix", "resimulate", "converge"]})
    state: dict = {
        "transcript": [], "iterations": 0, "before_score": 0.0,
        "contradictions_found": 0, "high_contradictions": 0, "weak": weak,
    }
    state = await graph.run(state, on_event=emit)

    before = state.get("before_score", 0.0)
    after = state.get("after_score", before)
    result = ShowrunnerResult(
        transcript=state["transcript"],
        before_score=before,
        after_score=after,
        lift=round(after - before, 1),
        contradictions_found=state.get("contradictions_found", 0),
        contradictions_fixed=state.get("contradictions_fixed", 0),
        converged=True,
        iterations=state.get("iterations", 0),
        final_text=state.get("fixed_text", story.text),
    )
    save_simulation("showrunner", story, result.model_dump())
    if state.get("audience"):
        await write_audience_verdict(
            story,
            [{"segment": "All listeners", "following_pct": state["audience"]["binge_pct"], "avg_hook": after}],
        )
    return result.model_dump()
