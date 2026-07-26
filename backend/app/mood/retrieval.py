"""
Mood-First Search — retrieval.

Pipeline per shelf:

    hard axis filters (+ language, avoid_tags)
        -> relax if starved
    contraindication block                    <- the safety-critical step
    fused score  = axis + semantic + tags + affinity   (normalised to 0..1)
    MMR + one-arc-per-series dedupe
        -> top k candidates for the reranker

Ordering is deliberate. Filters and blocks run BEFORE scoring so a
contraindicated item can never reach the reranker and get talked back in by a
persuasive vibe sentence. Cheap exact rules first, expensive fuzzy judgement
last -- and never the other way round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from app.mood.contraindications import (
    derive_listener_codes,
    in_raw_state,
    is_blocked,
    is_despair_shaped,
)
from app.mood.mood_config import (
    DESTINATION_FILTERS,
    SESSION_SLACK,
    resolve_target,
)
from app.mood.schemas import Destination, MoodAxes, MoodQuery
from app.mood.store import Candidate, MoodStore


# Hard ceiling on the listening-history term, whatever sparsity asks for. Sits
# under the axis weight (0.45) and under the 0.25 line the design notes draw.
AFFINITY_CEILING = 0.22


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    """Axis distance dominates on purpose.

    The axes are the thing we specifically built and the thing the sliders
    steer; if embeddings outvoted them, dragging 'heavier' would produce
    results that don't get heavier and the feature would look broken.
    Semantics catch nuance the nine axes can't hold. Tags are a precision
    booster for situational queries ("rainy", "raat ko"). Affinity is listening
    history and is deliberately the smallest term -- see `for_query` for why it
    moves with query sparsity and where its ceiling sits.

    The terms are normalised by their total in `_score`, so a candidate's score
    is a genuine 0..1 quantity rather than something that saturates the
    rerankers' clamp.
    """

    axis: float = 0.45
    semantic: float = 0.30
    tags: float = 0.20
    affinity: float = 0.12

    mmr_lambda: float = 0.72
    max_per_series: int = 1

    relax_steps: tuple[float, ...] = (0.0, 0.10, 0.22, 0.40)
    min_pool: int = 12

    @classmethod
    def for_query(cls, sparsity: float) -> "ScoringWeights":
        """Scale the affinity term by how little the query told us.

        Affinity should matter most exactly where the query is weakest. On
        "something that feels like a rainy Sunday after heartbreak" the mood
        evidence is rich and specific, and leaning on six months of listening
        history would be overriding what the listener just said. On "bore ho
        raha hoon" there is almost no mood signal at all, and history is the
        only real evidence in the room.

        So the weight moves with sparsity rather than sitting fixed. This is
        also why the demo shows personalization more clearly on thin queries
        than on the hero query -- that is the system behaving correctly, not
        the feature underperforming.

        THE CEILING, STATED IN NUMBERS because this is the invariant most
        likely to be eroded one plausible tweak at a time. The base weight is
        0.12 and sparsity can raise it, but never past AFFINITY_CEILING = 0.22 --
        which keeps it under both the axis term (0.45) and the 0.25 line past
        which this stops being mood search with a personalization nudge and
        becomes a collaborative filter wearing mood search as a costume.
        History informs a thin query; it never owns one.

        (This previously read "capped at 0.12" while the code allowed 0.252 --
        over that 0.25 line. The number below is now the number in the comment.)
        """
        base = cls()
        scaled = base.affinity * (0.5 + 1.6 * max(0.0, min(1.0, sparsity)))
        return cls(
            axis=base.axis, semantic=base.semantic, tags=base.tags,
            affinity=min(AFFINITY_CEILING, scaled),
        )

    @classmethod
    def for_refine(cls) -> "ScoringWeights":  # noqa: D401
        """Weights for the post-drag ranking. Axes dominate. This is not tuning.

        MEASURED: under the default weights, semantic + tags are 50% of the
        score and they are CONSTANT across a refine -- the query embedding
        never changes, only the target axes do. A full slider drag moved just
        22% of what already separated candidates, so the ranking was pinned and
        `faster` and `stranger` were literally no-ops at maximum drag. Widening
        the filters (axis_slack) did not help, because the filter was never the
        binding constraint; the frozen half of the score was.

        The principled correction: on the first query, text is the only
        evidence we have. After a drag, the listener has stated something in
        axis terms that their sentence never contained -- strictly better
        evidence, and it should carry the ranking. Semantics stay in the mix at
        low weight so refinement cannot wander off-topic entirely.
        """
        return cls(axis=0.78, semantic=0.10, tags=0.07, affinity=0.05)


# Situation fields -> sensory tags the fingerprinter uses.
_SITUATION_TAGS: dict[str, dict[str, str]] = {
    "weather": {"rain": "rain", "monsoon": "monsoon", "storm": "rain",
                "winter": "winter", "cold": "winter", "heat": "summer"},
    "time_of_day": {"night": "night", "late_night": "night", "evening": "evening",
                    "morning": "morning", "afternoon": "afternoon"},
    "place": {"home": "small-room", "room": "small-room", "car": "open-road",
              "train": "crowd", "office": "crowd", "outside": "open-road"},
    "activity": {"driving": "open-road", "commute": "crowd", "walking": "open-road",
                 "sleeping": "winter-quilt", "cooking": "small-room"},
}


def situation_tags(query: MoodQuery) -> list[str]:
    tags: list[str] = []
    sit = query.situation.model_dump()
    for field, mapping in _SITUATION_TAGS.items():
        value = sit.get(field)
        if not value:
            continue
        for needle, tag in mapping.items():
            if needle in str(value).lower():
                tags.append(tag)
                break
    if query.situation.solitude == "alone":
        tags.append("small-room")
    return list(dict.fromkeys(tags))


class Retriever:
    def __init__(self, store: MoodStore, weights: ScoringWeights | None = None) -> None:
        self.store = store
        self.w = weights or ScoringWeights()

    # -- filtering --------------------------------------------------------

    def _base_mask(self, query: MoodQuery) -> np.ndarray:
        mask = (
            self.store.language_mask(query.language)
            & self.store.avoid_mask(query.avoid_tags)
        )

        # Session length is applied only if it leaves a workable pool. It is a
        # real constraint, but it is also the one most likely to be a rough
        # estimate, so it yields rather than starving the shelf -- and because
        # it sits in the un-relaxable base mask, a hard version of it could not
        # be widened back open later.
        if query.session_length_min:
            with_duration = mask & self.store.duration_mask(
                query.session_length_min * SESSION_SLACK
            )
            if int(with_duration.sum()) >= self.w.min_pool:
                mask = with_duration
        return mask

    def _filtered_mask(
        self,
        query: MoodQuery,
        destination: Destination,
        axis_slack: Optional[dict[str, float]] = None,
    ) -> tuple[np.ndarray, float]:
        """Apply destination bounds, widening until the pool is workable.

        Starving a shelf is a worse product outcome than a slightly off-target
        one -- an empty shelf reads as 'it's broken', an approximate shelf reads
        as 'close, let me nudge it'. We return the relaxation actually used so
        callers can log it; a shelf that habitually relaxes means the bounds in
        DESTINATION_FILTERS are wrong, not that the catalog is thin.

        `axis_slack` widens specific bounds only. This exists because of a real
        bug: sliders steer the axes that DESTINATION_FILTERS clamps, so
        `faster` on a `sit_with` shelf moved the target into a region the
        filter had already emptied -- a full drag changed literally nothing.
        Two individually-correct designs (hard intent bounds; steer within
        intent) cancelled each other out and produced a dead feature that no
        unit test noticed.

        Resolution: an explicit drag is stronger evidence than the destination
        default, so it earns room -- but only on the axis it touched, and only
        proportionally. `warmer` on a sleep shelf gets warmer sleep, never a
        thriller.
        """
        bounds = dict(DESTINATION_FILTERS.get(destination, {}))
        if axis_slack:
            for axis, slack in axis_slack.items():
                if axis in bounds and slack > 0:
                    lo, hi = bounds[axis]
                    bounds[axis] = (lo - slack, hi + slack)
        base = self._base_mask(query)

        for relax in self.w.relax_steps:
            mask = base & self.store.axis_mask(bounds, relax=relax)
            if int(mask.sum()) >= self.w.min_pool:
                return mask, relax
        return base, float("inf")  # bounds abandoned; base constraints hold

    # -- scoring ----------------------------------------------------------

    def _score(
        self,
        query: MoodQuery,
        target: MoodAxes,
        mask: np.ndarray,
        query_vec: np.ndarray,
        weights: Optional[ScoringWeights] = None,
        affinity: Optional[np.ndarray] = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        w = weights or self.w
        axis_d = self.store.axis_distances(target)
        semantic = self.store.semantic_scores(query_vec)
        tags = self.store.tag_overlap(situation_tags(query))
        aff = affinity if affinity is not None else np.zeros(len(self.store), dtype=np.float32)

        # axis_d is a distance in [0, ~1]; invert to a similarity.
        # semantic is a cosine in [-1, 1]; clamp negatives, they mean "unrelated"
        # not "opposite" for this kind of text.
        score = (
            w.axis * (1.0 - np.clip(axis_d, 0.0, 1.0))
            + w.semantic * np.clip(semantic, 0.0, 1.0)
            + w.tags * tags
            + w.affinity * aff
        )
        # Normalise by the weight total so the result is a true 0..1 score.
        # Unnormalised, the terms sum to more than 1 once affinity is active,
        # and both rerankers clamp to [0,1] -- so the top of the ranking
        # saturated at exactly 1.0 and lost its ordering. Dividing by a constant
        # cannot change the ranking, only the scale it is expressed on.
        total = w.axis + w.semantic + w.tags + w.affinity
        if total > 0:
            score = score / total
        score = np.where(mask, score, -np.inf)
        return score, axis_d, semantic, tags

    # -- diversity --------------------------------------------------------

    def _mmr(
        self,
        order: Sequence[int],
        k: int,
        score: np.ndarray,
        weights: Optional[ScoringWeights] = None,
    ) -> list[int]:
        """Maximal marginal relevance in mood space.

        Three arcs that are individually perfect and mutually identical make a
        shelf feel broken -- the listener reads it as one recommendation
        repeated, not three options. Diversity is measured on the axes, not the
        embeddings, so 'different' means different *feel* rather than different
        wording.

        BUG THIS REPLACES: the relevance term used to be the literal constant
        `mmr_lambda * 1.0`. Being constant across candidates, it cancelled in the
        argmax, so the objective reduced to pure distance-maximisation with a
        0.001-per-rank tiebreak -- this selected the most mood-DISTANT arcs in
        the pool, nearly independently of how well they matched. Every slot after
        the first was effectively chosen by novelty alone. The diversity test
        passed throughout, because a diversity maximiser trivially satisfies a
        minimum-spread assertion.

        Both terms are now on a comparable 0..1 footing: relevance is the fused
        score min-max normalised within the pool, and redundancy is the weighted
        mood distance to the nearest already-selected arc -- the same weighted
        metric used for ranking, not the unweighted raw-axis norm this used
        before (which lived on a different scale, ~0..3, and so silently
        dominated whatever it was compared against).
        """
        if not order:
            return []

        rows = list(order)
        raw = score[rows]
        lo, hi = float(raw.min()), float(raw.max())
        span = hi - lo
        # Degenerate pool (all equal): relevance carries no information, so fall
        # back to pool order, which is already relevance-sorted.
        rel = (raw - lo) / span if span > 1e-9 else np.ones(len(rows), dtype=np.float32)
        rel_by_row = {row: float(r) for row, r in zip(rows, rel)}

        # Read lambda off the per-call weights, not just the retriever default,
        # so a caller that tunes it (refine, eval) is actually honoured.
        lam = (weights or self.w).mmr_lambda
        selected: list[int] = [rows[0]]
        pool = rows[1:]

        while pool and len(selected) < k:
            best, best_val = None, -np.inf
            for row in pool:
                redundancy = 1.0 - self._nearest_distance(row, selected)
                val = lam * rel_by_row[row] - (1.0 - lam) * redundancy
                if val > best_val:
                    best, best_val = row, val
            selected.append(best)  # type: ignore[arg-type]
            pool.remove(best)  # type: ignore[arg-type]
        return selected

    def _nearest_distance(self, row: int, selected: Sequence[int]) -> float:
        """Weighted mood distance from `row` to the closest selected arc, in the
        same 0..1 metric `axis_distances` uses so it is comparable to relevance."""
        dists = self.store.row_distances(row, selected)
        if dists.size == 0:
            return 1.0
        return float(np.clip(np.min(dists), 0.0, 1.0))

    # -- public -----------------------------------------------------------

    def retrieve(
        self,
        query: MoodQuery,
        destination: Destination,
        target: Optional[MoodAxes] = None,
        k: int = 8,
        pool: int = 40,
        axis_slack: Optional[dict[str, float]] = None,
        weights: Optional[ScoringWeights] = None,
        affinity: Optional["AffinityScorer"] = None,
    ) -> list[Candidate]:
        if len(self.store) == 0:
            return []

        target = target if target is not None else resolve_target(query, destination)
        mask, _relax = self._filtered_mask(query, destination, axis_slack)

        # Already-finished series drop out before scoring, not after. A
        # penalty large enough to bury them is indistinguishable from a mask
        # and much harder to reason about.
        aff_scores = None
        if affinity is not None:
            mask = mask & affinity.exclusion_mask()
            aff_scores = affinity.scores()

        listener_codes = derive_listener_codes(query)
        blocked: dict[int, str] = {}
        if listener_codes:
            for row, codes in enumerate(self.store.codes):
                if not mask[row]:
                    continue
                hit, code = is_blocked(codes, listener_codes)
                if hit:
                    mask[row] = False
                    blocked[row] = code  # type: ignore[assignment]

        # Structural net on top of the written contraindications: a listener in a
        # raw state is not served despair-shaped content even when no one wrote a
        # contraindication for it. Catches the arcs the fingerprinter's prose
        # missed -- see contraindications.RAW_STATES for why prose isn't enough.
        if in_raw_state(listener_codes):
            mask = mask & ~self.store.despair_mask()

        if not mask.any():
            return []

        query_vec = self.store.embedder.encode([query.raw_text])[0]
        score, axis_d, semantic, tags = self._score(
            query, target, mask, query_vec, weights, aff_scores
        )

        ranked = [int(i) for i in np.argsort(-score)[:pool] if np.isfinite(score[i])]

        # One arc per series. A listener asking for a feeling wants options, not
        # a table of contents for one show.
        seen: dict[str, int] = {}
        deduped: list[int] = []
        for row in ranked:
            sid = self.store.fingerprints[row].series_id
            if seen.get(sid, 0) >= self.w.max_per_series:
                continue
            seen[sid] = seen.get(sid, 0) + 1
            deduped.append(row)

        chosen = self._mmr(deduped, k, score, weights)

        return [
            Candidate(
                row=row,
                fingerprint=self.store.fingerprints[row],
                axis_distance=float(axis_d[row]),
                semantic=float(semantic[row]),
                tag_overlap=float(tags[row]),
                score=float(score[row]),
            )
            for row in chosen
        ]

    def debug_blocked(self, query: MoodQuery) -> list[tuple[str, str]]:
        """What the contraindication layer removed, and why.

        Not user-facing. This drives the trap-avoidance metric in eval and is
        the first thing to look at when a shelf comes back thin.
        """
        listener_codes = derive_listener_codes(query)
        raw = in_raw_state(listener_codes)
        out = []
        for fp, codes in zip(self.store.fingerprints, self.store.codes):
            hit, code = is_blocked(codes, listener_codes)
            if hit:
                out.append((fp.content_id, code))  # type: ignore[arg-type]
            elif raw and is_despair_shaped(fp.axes):
                # Reported distinctly from a code hit so the Lab trace shows
                # which layer caught it -- the whole point of adding the second
                # layer was that the first one missed these.
                out.append((fp.content_id, "despair_shaped"))
        return out
