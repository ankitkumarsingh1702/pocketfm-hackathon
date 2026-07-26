"""Plot Hole Hunter lens — graph-grounded continuity/contradiction detection.

Traverses the story-canon graph for structural contradiction candidates
(conflicting facts, dangling clues) and hands them, with the episode script, to
the LLM to verify, rank, and catch semantic/tonal issues. Falls back to a pure
long-context LLM scan when the graph is empty — so it works with or without a
populated canon.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel

from app.config import settings
from app.db.firestore import save_simulation
from app.graph.store import fetch_contradiction_candidates
from app.llm.factory import get_llm
from app.schemas import PlotHole, PlotHoleResult, Story

logger = logging.getLogger(__name__)

# Rough continuity burden a serialized audio-drama episode represents, so the UI
# can translate canon size into "≈ pages a human would have to re-read". An
# estimate, always shown with a "≈". Mirrored by frontend PAGES_PER_EPISODE.
_PAGES_PER_EPISODE = 40


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
            ea, eb = c.get("ep_a", ""), c.get("ep_b", "")
            cite = f" ({ea} vs {eb})" if ea or eb else ""
            lines.append(
                f"- {c['subject']} · {c['predicate']}: '{c['a']}' vs '{c['b']}'{cite}"
            )
    if cand.get("dangling_clues"):
        lines.append("DANGLING CLUES (introduced but never advanced or paid off):")
        lines.append("- " + ", ".join(cand["dangling_clues"]))
    if cand.get("facts"):
        lines.append("KNOWN CANON FACTS (from earlier episodes):")
        for f in cand["facts"][:40]:
            lines.append(f"- {f['subject']} · {f['predicate']} = {f['object']}")
    return "\n".join(lines)


def _structural_holes(cand: dict) -> list[PlotHole]:
    """Turn graph-found contradictions + dangling clues into guaranteed findings.

    These come straight from traversing the canon graph, so they surface every
    time — even if the LLM verify step is slow or fails. This is the honest proof
    that the graph reasoned across the whole show: each carries the two episodes
    it spans.
    """
    holes: list[PlotHole] = []
    for c in cand.get("conflicts", []):
        pred = str(c.get("predicate", "")).replace("_", " ")
        ea, eb = c.get("ep_a", ""), c.get("ep_b", "")
        holes.append(
            PlotHole(
                severity="high",
                location=f"{ea} ↔ {eb}".strip(" ↔"),
                kind="fact conflict",
                description=(
                    f"{c['subject']} — {pred} is '{c['a']}' in {ea} "
                    f"but '{c['b']}' in {eb}. The canon contradicts itself across episodes."
                ),
                evidence=[
                    f"{ea}: {c['subject']} · {pred} = {c['a']}",
                    f"{eb}: {c['subject']} · {pred} = {c['b']}",
                ],
                fix=f"Reconcile {c['subject']}'s {pred} between {ea} and {eb} before publishing.",
                episodes=[e for e in (ea, eb) if e],
            )
        )
    for name in cand.get("dangling_clues", []):
        holes.append(
            PlotHole(
                severity="medium",
                location="unresolved across the season",
                kind="dangling clue",
                description=f"The clue “{name}” is introduced but never advanced or paid off.",
                evidence=[f"Canon graph: “{name}” has no follow-up link."],
                fix=f"Resolve, reference, or cut “{name}” before the finale.",
                episodes=[],
            )
        )
    return holes


def _dedupe(llm_holes: list[PlotHole], conflicts: list[dict]) -> list[PlotHole]:
    """Drop LLM holes that merely restate a graph-found structural conflict.

    Conservative: only drops a hole whose text names the conflict's subject AND
    one of its two clashing values — so genuine, distinct LLM findings survive.
    """
    kept: list[PlotHole] = []
    for h in llm_holes:
        d = (h.description or "").lower()
        dup = False
        for c in conflicts:
            subj = str(c.get("subject", "")).lower()
            a = str(c.get("a", "")).lower()
            b = str(c.get("b", "")).lower()
            if subj and subj in d and ((a and a in d) or (b and b in d)):
                dup = True
                break
        if not dup:
            kept.append(h)
    return kept


async def find_plot_holes(
    story: Story, emit: Callable[[dict], None] | None = None
) -> PlotHoleResult:
    """Detect plot holes for ``story``, grounded in the canon graph.

    When ``emit`` is supplied, streams real phase events (read canon → counts →
    LLM verify → done) so the UI can show the run CLI-style. Passing ``None``
    reproduces the original one-shot behaviour.
    """
    def phase(pid: str, label: str, status: str, detail: str = "") -> None:
        if emit:
            emit({"type": "phase", "id": pid, "label": label, "status": status, "detail": detail})

    llm = get_llm()

    phase("read_canon", "Reading the whole show canon", "running")
    cand = await fetch_contradiction_candidates(source="Plot Hole Hunter")
    canon_used = bool(cand.get("facts") or cand.get("conflicts") or cand.get("dangling_clues"))
    ep_count = int(cand.get("episode_count", 0))
    fact_count = int(cand.get("fact_count", 0)) or len(cand.get("facts", []))
    pages = ep_count * _PAGES_PER_EPISODE
    conflicts = cand.get("conflicts", [])
    dangling = cand.get("dangling_clues", [])
    phase(
        "read_canon", "Read the whole show canon", "done",
        f"{fact_count} facts across {ep_count} episode(s) (≈{pages} pages)",
    )

    # Cross-check every episode via the graph — the reasoning no human can do by
    # hand across thousands of pages. These structural findings are guaranteed.
    phase("traverse", "Cross-checking every episode for contradictions", "running")
    structural = _structural_holes(cand)
    phase(
        "traverse", "Cross-checked every episode for contradictions", "done",
        f"{len(conflicts)} contradiction(s) · {len(dangling)} dangling clue(s) "
        f"— grounded across {ep_count} episode(s)",
    )

    rendered = _render_candidates(cand)
    prompt = (
        (rendered + "\n\n" if rendered else "")
        + "EPISODE SCRIPT:\n"
        + _story_text(story)
        + "\n\nList the plot holes and continuity issues, most severe first."
    )

    phase("verify", "Reading the new episode against the canon", "running")
    try:
        res = await llm.structured(
            system=_SYSTEM,
            prompt=prompt,
            schema=_PlotHoles,
            model=settings.model_for("experts"),
        )
        extra = _dedupe(res.holes, conflicts)
        holes = structural + extra
        phase("verify", "Read the new episode against the canon", "done",
              f"{len(extra)} more issue(s) from the script · {len(holes)} total")
    except Exception as exc:  # noqa: BLE001 - graph findings still stand if the LLM fails
        logger.warning("Plot-hole LLM verify failed: %s", exc)
        holes = structural
        phase("verify", "Read the new episode against the canon", "failed",
              f"{str(exc)[:120]} — showing {len(structural)} graph-grounded issue(s)")

    result = PlotHoleResult(
        holes=holes,
        canon_used=canon_used,
        episodes_scanned=ep_count,
        facts_scanned=fact_count,
        pages_estimate=pages,
    )
    save_simulation("plot_holes", story, result.model_dump())
    return result
