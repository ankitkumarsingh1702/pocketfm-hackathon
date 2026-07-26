"""
Mood-First Search — entry point resolution.

Principle 3 from the PRD: return a doorway, not a title. A 200-episode series
is not an answer to "I feel like this" -- it is a commitment decision wearing
the costume of a recommendation.

Two jobs:
  1. pick the episode
  2. say it in a way that lowers, rather than raises, the activation energy

Job 2 is not cosmetic. "Episode 34 of 212" reads as *you are 178 episodes
behind*. "Start at Ep 34 -- the monsoon arc, no catch-up needed" reads as an
invitation. Same number, opposite conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.mood.schemas import MoodAxes
from app.mood.store import Candidate, MoodStore

# How much matching quality we will trade to hand someone an earlier, lower
# friction doorway into the same series.
#
# TUNED DOWN FROM 0.04 AFTER MEASURING. At 0.04 the swap fired on essentially
# every result and collapsed every entry point to episode 1 -- which silently
# deletes the entire "start at Ep 34" proposition and turns arc-level indexing
# into an expensive way to recommend series. Tests still passed, because
# "returns a valid episode" was the assertion. The lesson: assert the PRODUCT
# behaviour (entry points are varied and sometimes deep), not just that the
# field is populated. test_retrieval now does.
EARLIER_ARC_EPSILON = 0.015

# A swap must also be worth making. Moving someone from Ep 140 to Ep 8 is a
# real gift; moving them from Ep 14 to Ep 11 is churn that costs match quality
# for nothing.
MIN_EPISODE_SAVING = 0.35

# Beyond this, a mid-series entry needs reassurance that they can follow it --
# and below it, an entry point is not a barrier worth optimising away.
DEEP_ENTRY_EPISODE = 12


@dataclass(slots=True)
class EntryPoint:
    episode: int
    label: str
    arc_label: str
    is_deep: bool
    swapped_for_earlier: bool = False


def _commitment_hint(fp, episode: int) -> str:
    """Short reassurance for deep entries.

    Only emitted when the arc is self-contained enough to survive it. We infer
    that from axes_variance: a low-variance arc holds one emotional register
    throughout, which is exactly the kind you can drop into cold. A
    high-variance arc swings, and dropping in mid-swing is confusing -- so we
    stay quiet rather than promise something the content won't honour.
    """
    if episode <= DEEP_ENTRY_EPISODE:
        return ""
    if fp.axes_variance <= 0.18:
        return " — starts clean, no catch-up needed"
    return ""


def resolve_entry(
    candidate: Candidate,
    store: Optional[MoodStore] = None,
    target: Optional["MoodAxes"] = None,
) -> EntryPoint:
    """Resolve one candidate arc to a listenable doorway.

    When `store` and `target` are supplied we look for an earlier arc in the
    same series that scores within EARLIER_ARC_EPSILON on mood distance. If one
    exists we take it: a near-equal match at episode 8 beats a marginal winner
    at episode 140 every time, because the second one is really a request to
    start a relationship, not to press play.
    """
    fp = candidate.fingerprint
    episode = fp.entry_episode
    arc_label = fp.arc_label
    swapped = False

    if store is not None and target is not None and episode > DEEP_ENTRY_EPISODE:
        # Only trade match quality for accessibility when the entry point is
        # actually a barrier. A shallow entry needs no rescuing.
        ceiling = episode * (1.0 - MIN_EPISODE_SAVING)
        best: Optional[tuple[int, float]] = None
        for row, dist in same_series_arcs(store, fp.series_id, target):
            other = store.fingerprints[row]
            if other.entry_episode > ceiling:
                continue
            if dist - candidate.axis_distance > EARLIER_ARC_EPSILON:
                continue
            if best is None or other.entry_episode < store.fingerprints[best[0]].entry_episode:
                best = (row, dist)
        if best is not None:
            fp = store.fingerprints[best[0]]
            episode = fp.entry_episode
            arc_label = fp.arc_label
            swapped = True

    is_deep = episode > DEEP_ENTRY_EPISODE

    if episode <= 1:
        label = "Start from the beginning"
    else:
        label = f"Start at track {episode} \u2014 {arc_label}{_commitment_hint(fp, episode)}"

    return EntryPoint(
        episode=episode,
        label=label,
        arc_label=arc_label,
        is_deep=is_deep,
        swapped_for_earlier=swapped,
    )


def same_series_arcs(
    store: MoodStore, series_id: str, target: "MoodAxes"
) -> list[tuple[int, float]]:
    """(row, axis_distance_to_target) for every arc of a series, nearest first.

    Distances are recomputed here rather than reused: the retriever keeps only
    one arc per series, so the sibling arcs were never scored.
    """
    distances = store.axis_distances(target)
    rows = [i for i, fp in enumerate(store.fingerprints) if fp.series_id == series_id]
    return sorted(((r, float(distances[r])) for r in rows), key=lambda x: x[1])
