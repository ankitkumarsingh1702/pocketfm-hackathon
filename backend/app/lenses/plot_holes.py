"""Plot Hole Hunter lens — graph-grounded continuity/contradiction detection.

Traverses the story-canon graph for structural contradiction candidates
(conflicting facts, dangling clues) and hands them, with the episode script, to
the LLM to verify, rank, and catch semantic/tonal issues. Falls back to a pure
long-context LLM scan when the graph is empty — so it works with or without a
populated canon.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.config import settings
from app.db.firestore import save_simulation
from app.graph.store import fetch_contradiction_candidates
from app.llm.factory import get_llm
from app.schemas import PlotHole, PlotHoleResult, Story

logger = logging.getLogger(__name__)


class _PlotHoles(BaseModel):
    """Private LLM output wrapper."""

    holes: list[PlotHole]


_SYSTEM = (
    "You are a continuity editor — a 'Plot Hole Hunter' — for a serialized audio "
    "drama. Using the canon-graph facts AND the episode script, find contradictions, "
    "timeline conflicts, unresolved/dangling threads, and tonal inconsistencies. For "
    "each issue give a severity (high/medium/low), the location, a short kind, a clear "
    "description, supporting evidence, and a concrete fix. Prefer issues grounded in the "
    "provided canon facts; do not invent facts that aren't supported."
)


def _story_text(story: Story) -> str:
    episode = story.episode or "-"
    return f"TITLE: {story.title}\nEPISODE: {episode}\nSCRIPT:\n{story.text}"


def _render_candidates(cand: dict) -> str:
    """Render graph-traversal candidates into a compact prompt block."""
    lines: list[str] = []
    if cand.get("conflicts"):
        lines.append("STRUCTURAL CONTRADICTIONS found by traversing the canon graph:")
        for c in cand["conflicts"]:
            lines.append(f"- {c['subject']} · {c['predicate']}: '{c['a']}' vs '{c['b']}'")
    if cand.get("dangling_clues"):
        lines.append("DANGLING CLUES (introduced but never advanced or paid off):")
        lines.append("- " + ", ".join(cand["dangling_clues"]))
    if cand.get("facts"):
        lines.append("KNOWN CANON FACTS (from earlier episodes):")
        for f in cand["facts"][:40]:
            lines.append(f"- {f['subject']} · {f['predicate']} = {f['object']}")
    return "\n".join(lines)


async def find_plot_holes(story: Story) -> PlotHoleResult:
    """Detect plot holes for ``story``, grounded in the canon graph."""
    llm = get_llm()
    cand = await fetch_contradiction_candidates()
    canon_used = bool(cand.get("facts") or cand.get("conflicts") or cand.get("dangling_clues"))
    rendered = _render_candidates(cand)

    prompt = (
        (rendered + "\n\n" if rendered else "")
        + "EPISODE SCRIPT:\n"
        + _story_text(story)
        + "\n\nList the plot holes and continuity issues, most severe first."
    )

    try:
        res = await llm.structured(
            system=_SYSTEM,
            prompt=prompt,
            schema=_PlotHoles,
            model=settings.model_for("experts"),
        )
        holes = res.holes
    except Exception as exc:  # noqa: BLE001 - degrade to no findings rather than 500
        logger.warning("Plot-hole detection failed: %s", exc)
        holes = []

    result = PlotHoleResult(
        holes=holes, canon_used=canon_used, episodes_scanned=int(cand.get("episode_count", 0))
    )
    save_simulation("plot_holes", story, result.model_dump())
    return result
