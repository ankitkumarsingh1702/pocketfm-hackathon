"""
Mood-First Search — the orchestrator.

Turns a parsed MoodQuery into the `list[Shelf]` the frozen contract expects.
This is the object the H0 mock swaps its fakes for; the response shapes do not
move.

Shelves are built in parallel. Three sequential rerank calls would put the
whole demo at ~3.6s; run concurrently they cost one rerank (~1.2s), which is
the difference between "thinking" and "broken". The retrieval underneath is
pure numpy and holds the GIL only in microseconds, so threads are the right
primitive here -- the wait is network, not CPU.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, Sequence

from app.mood.entrypoint import resolve_entry
from app.mood.mood_config import (
    SHELF_COPY, rank_destinations, resolve_target, slider_deltas_to_axis_deltas,
)
from app.mood.rerank import HeuristicReranker, RerankedItem
from app.mood.retrieval import Retriever, ScoringWeights
from app.mood.schemas import Destination, MoodAxes, MoodQuery, ResultCard, Shelf
from app.mood.store import MoodStore

RESULTS_PER_SHELF = 3
RETRIEVE_K = 8

# How much filter room a full slider drag buys on the axes it touched.
# GAIN tuned so a full drag visibly churns the shelf; CAP keeps intent intact.
SLACK_GAIN = 1.8
SLACK_CAP = 0.40


@dataclass(slots=True)
class ShelfDebug:
    """Why a shelf looks the way it does. Eval and debug UI only."""

    destination: str
    pool_size: int
    blocked_count: int
    dropped_by_reranker: int
    entry_swaps: int
    latency_ms: int


class MoodSearchEngine:
    def __init__(
        self,
        store: MoodStore,
        retriever: Optional[Retriever] = None,
        reranker=None,
        refine_reranker=None,
    ) -> None:
        self.store = store
        self.retriever = retriever or Retriever(store)
        self.reranker = reranker or HeuristicReranker()
        # The refine path gets its OWN reranker, always heuristic by default.
        # This is a latency contract, not a preference: `refine` is the sub-200ms
        # slider path, and the shared `reranker` is an LLM whenever credentials
        # resolve -- i.e. exactly on demo day. Sharing it put a network round trip
        # behind every drag while three separate comments claimed the path was
        # LLM-free. Pass one explicitly only if you have measured it.
        self.refine_reranker = refine_reranker or HeuristicReranker()
        self.last_debug: list[ShelfDebug] = []

    # -- one shelf --------------------------------------------------------

    def build_shelf(
        self,
        query: MoodQuery,
        destination: Destination,
        target: Optional[MoodAxes] = None,
        axis_slack: Optional[dict[str, float]] = None,
        weights: Optional[ScoringWeights] = None,
        affinity=None,
        reranker=None,
    ) -> tuple[Optional[Shelf], ShelfDebug]:
        t0 = time.time()
        # `resolve_target` calibrates the destination centroid to this listener's
        # intensity/tolerance. An explicit `target` (refine, eval) is used as
        # given -- it has already been calibrated and then steered by hand.
        target = target if target is not None else resolve_target(query, destination)

        candidates = self.retriever.retrieve(
            query, destination, target, k=RETRIEVE_K,
            axis_slack=axis_slack, weights=weights, affinity=affinity,
        )
        judge = reranker or self.reranker
        judged: Sequence[RerankedItem] = judge.rerank(query, destination, candidates)
        kept = [r for r in judged if not r.dropped]

        cards: list[ResultCard] = []
        swaps = 0
        for item in kept[:RESULTS_PER_SHELF]:
            fp = item.candidate.fingerprint
            entry = resolve_entry(item.candidate, self.store, target)
            swaps += int(entry.swapped_for_earlier)
            cards.append(
                ResultCard(
                    content_id=fp.content_id,
                    series_id=fp.series_id,
                    series_title=fp.series_title,
                    arc_label=entry.arc_label,
                    entry_episode=entry.episode,
                    entry_label=entry.label,
                    explanation=item.explanation,
                    vibe_sentence=fp.vibe_sentence,
                    duration_min=fp.duration_min,
                    audio_verified=fp.audio_verified,
                    score=round(item.score, 3),
                )
            )

        debug = ShelfDebug(
            destination=destination,
            pool_size=len(candidates),
            blocked_count=len(self.retriever.debug_blocked(query)),
            dropped_by_reranker=len(judged) - len(kept),
            entry_swaps=swaps,
            latency_ms=int((time.time() - t0) * 1000),
        )

        if not cards:
            # Never ship an empty shelf. A missing shelf reads as "we understood
            # you three ways and one didn't apply"; an empty one reads as broken.
            return None, debug

        label, subtitle = SHELF_COPY[destination]
        shelf = Shelf(
            id=f"shelf_{destination}",
            label=label,
            subtitle=subtitle,
            destination=destination,
            target_axes=target,
            results=cards,
        )
        return shelf, debug

    # -- all shelves ------------------------------------------------------

    def search(self, query: MoodQuery, profile=None) -> list[Shelf]:
        """`profile` is an optional ListenerProfile. Absent = anonymous, and
        the affinity term drops out entirely rather than defaulting to
        something."""
        destinations = rank_destinations(query)

        affinity = None
        if profile is not None:
            from app.mood.persona import AffinityScorer

            affinity = AffinityScorer(self.store, profile)

        weights = ScoringWeights.for_query(query.sparsity_score) if affinity else None

        with ThreadPoolExecutor(max_workers=len(destinations)) as pool:
            results = list(pool.map(
                lambda d: self.build_shelf(
                    query, d, affinity=affinity, weights=weights
                ),
                destinations,
            ))

        self.last_debug = [dbg for _, dbg in results]
        return [shelf for shelf, _ in results if shelf is not None]

    # -- slider refinement ------------------------------------------------

    def refine(
        self,
        query: MoodQuery,
        destination: Destination,
        current_axes: MoodAxes,
        slider_deltas: dict[str, float],
        profile=None,
    ) -> Optional[Shelf]:
        """The sub-200ms path. Pure vector math when the reranker is heuristic.

        Takes the raw slider positions rather than pre-nudged axes, because the
        engine needs to know WHICH axes the listener steered -- not just where
        they ended up. That is what earns the per-axis slack below; without it
        the destination filter silently swallows the drag and the slider does
        nothing.

        The destination itself never changes. The listener is nudging within an
        intent, not switching intent -- letting a slider quietly cross into
        another destination's territory is how "warmer" starts returning
        bedtime stories.

        `profile` must be threaded through. It is not here for the affinity
        score -- that term is nearly irrelevant post-drag -- but for
        `AffinityScorer.exclusion_mask`, the HARD mask on series the listener has
        already finished. Omitting it silently downgraded a stated invariant to
        "applies on first search only", so a drag could resurface a show they
        finished last month.
        """
        axis_deltas = slider_deltas_to_axis_deltas(slider_deltas)
        new_axes = current_axes.nudge(axis_deltas)

        affinity = None
        if profile is not None:
            from app.mood.persona import AffinityScorer

            affinity = AffinityScorer(self.store, profile)

        # An explicit drag earns room on the axis it touched, proportional to
        # how hard it was pulled, capped so intent still holds.
        slack = {
            axis: min(SLACK_CAP, abs(delta) * SLACK_GAIN)
            for axis, delta in axis_deltas.items()
            if abs(delta) > 0.01
        }

        shelf, debug = self.build_shelf(
            query, destination, new_axes,
            axis_slack=slack, weights=ScoringWeights.for_refine(),
            affinity=affinity, reranker=self.refine_reranker,
        )
        self.last_debug = [debug]
        return shelf

    def refine_to_axes(
        self, query: MoodQuery, destination: Destination, new_axes: MoodAxes
    ) -> Optional[Shelf]:
        """Direct-target variant with no slack. Used by eval, not by the UI."""
        shelf, debug = self.build_shelf(query, destination, new_axes)
        self.last_debug = [debug]
        return shelf
