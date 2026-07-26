"""Mood-First Search — the enhanced matching logic.

These tests exist because of a pattern the feature notes call out explicitly:
the earlier suite asserted that fields were *populated* rather than that the
product *behaved*, which is how a dead slider and a collapsed entry point both
shipped green. Each test below pins a behaviour that a plausible refactor would
otherwise silently revert.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.mood.contraindications import derive_listener_codes, event_codes_in
from app.mood.embeddings import HashingEmbedder
from app.mood.mood_config import (
    DESTINATION_TARGETS,
    SESSION_SLACK,
    resolve_target,
)
from app.mood.parser import heuristic_parse
from app.mood.rerank import _REASONS, MIN_REASONS_PER_DESTINATION, HeuristicReranker
from app.mood.retrieval import AFFINITY_CEILING, Retriever, ScoringWeights
from app.mood.schemas import MoodQuery, Situation
from app.mood.search import MoodSearchEngine
from app.mood.seed_catalog import build_seed_catalog
from app.mood.store import MoodStore

TRAP_IDS = {f"trap_{i}" for i in range(3)}


@pytest.fixture(scope="module")
def store() -> MoodStore:
    s = MoodStore(HashingEmbedder())
    s.add(build_seed_catalog())
    return s


@pytest.fixture(scope="module")
def engine(store: MoodStore) -> MoodSearchEngine:
    return MoodSearchEngine(store)


# ---------------------------------------------------------------------------
# The safety fix: raw event queries must keep their contraindication codes
# ---------------------------------------------------------------------------

# Each of these names an EVENT and contains no word from the parser's mood list,
# so under the old intensity gate they all parsed at 0.3 and lost protection.
@pytest.mark.parametrize(
    "text,expected_code",
    [
        ("just got dumped", "breakup"),
        ("my grandmother died last week", "fresh_grief"),
        ("she left me", "breakup"),
        ("we broke up yesterday", "breakup"),
        ("uske papa nahi rahe", "fresh_grief"),
        ("usne chhod diya", "breakup"),
    ],
)
def test_event_queries_keep_contraindication_codes(text, expected_code):
    """A named event must survive the intensity gate.

    This is the regression that matters most in the whole module: the gate used
    to strip fresh_grief/breakup below intensity 0.45, and these phrases parse
    low precisely because they describe an event rather than name a feeling.
    """
    query = heuristic_parse(text)
    assert expected_code in event_codes_in(text)
    assert expected_code in derive_listener_codes(query), (
        f"{text!r} lost its {expected_code} code — the safety layer is inert here"
    )


def test_event_queries_are_high_intensity():
    """The parser must not read a calm sentence about a death as mild."""
    assert heuristic_parse("my grandmother died last week").intensity >= 0.75
    assert heuristic_parse("just got dumped").intensity >= 0.75


def test_mild_mood_words_are_still_gated():
    """The gate must still work: a mildly wistful listener is not contraindicated,
    or we over-block and empty shelves for no reason."""
    mild = MoodQuery(raw_text="feeling a bit heartbreak-y I guess",
                     felt_state=["heartbreak"], intensity=0.2)
    assert "breakup" not in derive_listener_codes(mild)

    raw = MoodQuery(raw_text="heartbreak", felt_state=["heartbreak"], intensity=0.9)
    assert "breakup" in derive_listener_codes(raw)


def test_traps_blocked_for_every_raw_event_query(store):
    """All three trap arcs must be unreachable for every raw listener.

    Grief is the case that used to leak. Only ONE of the three traps writes
    "raw grief" in its contraindications, so the closed-vocabulary layer alone
    blocked one arc and let the other two through for anyone whose state parsed
    as fresh_grief rather than breakup -- despite all three being equally
    harmful. The axis rule is what closes that.
    """
    retr = Retriever(store)
    for text in ("just got dumped", "my grandmother died last week", "she left me",
                 "uske papa nahi rahe"):
        query = heuristic_parse(text)
        blocked = set(dict(retr.debug_blocked(query)))
        assert TRAP_IDS <= blocked, f"traps reachable for {text!r}"

        shelves = MoodSearchEngine(store).search(query)
        surfaced = {c.content_id for s in shelves for c in s.results}
        assert not (surfaced & TRAP_IDS), f"trap surfaced on a shelf for {text!r}"


def test_despair_rule_separates_traps_from_legitimate_sad_content(store):
    """The rule must catch despair without eating the shelf a sad listener wants.

    `sit_with` content is bleak and heavy by design -- that IS the product. The
    rule must therefore key on hopelessness, not sadness. Asserted as a margin,
    because a threshold nudge that starts excluding legitimate sit_with arcs
    would be invisible otherwise.
    """
    from app.mood.contraindications import DESPAIR_HOPE_MAX, is_despair_shaped

    traps = [fp for fp in store.fingerprints if fp.content_id in TRAP_IDS]
    assert traps and all(is_despair_shaped(fp.axes) for fp in traps)

    # A grieving listener must still get a usable sit_with shelf.
    query = heuristic_parse("my grandmother died last week")
    shelf, _ = MoodSearchEngine(store).build_shelf(query, "sit_with")
    assert shelf is not None and shelf.results, (
        "despair rule emptied the shelf a grieving listener most needs"
    )
    for card in shelf.results:
        fp = next(f for f in store.fingerprints if f.content_id == card.content_id)
        assert fp.axes.hope > DESPAIR_HOPE_MAX


def test_despair_rule_does_not_apply_to_neutral_listeners(store):
    """State-dependent, not a blacklist. Someone browsing calmly can still be
    shown a bleak arc -- that is a legitimate thing to want."""
    neutral = MoodQuery(raw_text="something rainy and slow", felt_state=[], intensity=0.3)
    assert not derive_listener_codes(neutral)
    blocked = set(dict(Retriever(store).debug_blocked(neutral)))
    assert not (TRAP_IDS & blocked)


def test_heuristic_reranker_drops_contraindicated_items(store):
    """The offline path must check contraindications too — it used to check none,
    while the module docstring claimed they were checked twice."""
    query = heuristic_parse("just got dumped")
    trap_row = next(
        i for i, fp in enumerate(store.fingerprints) if fp.content_id in TRAP_IDS
    )
    from app.mood.store import Candidate

    cand = Candidate(
        row=trap_row,
        fingerprint=store.fingerprints[trap_row],
        axis_distance=0.1,
        semantic=0.9,
        tag_overlap=1.0,
        score=0.95,
    )
    judged = HeuristicReranker().rerank(query, "sit_with", [cand])
    assert judged[0].dropped is True
    assert judged[0].drop_reason


# ---------------------------------------------------------------------------
# Target calibration: intensity / tolerance / session length now do something
# ---------------------------------------------------------------------------


def test_tolerance_moves_heaviness_both_ways():
    base = DESTINATION_TARGETS["sit_with"]
    heavy_ok = resolve_target(
        MoodQuery(raw_text="x", intensity=0.5, intensity_tolerance=1.0), "sit_with"
    )
    fragile = resolve_target(
        MoodQuery(raw_text="x", intensity=0.5, intensity_tolerance=0.0), "sit_with"
    )
    assert heavy_ok.weight > base.weight > fragile.weight
    assert heavy_ok.catharsis > fragile.catharsis


def test_rawness_asks_for_more_holding_and_never_more_dread():
    base = DESTINATION_TARGETS["sit_with"]
    raw = resolve_target(
        MoodQuery(raw_text="x", intensity=1.0, intensity_tolerance=0.5), "sit_with"
    )
    assert raw.warmth > base.warmth
    assert raw.companionship > base.companionship
    # The one direction we must never move: more tension for someone already raw.
    assert raw.tension <= base.tension


def test_neutral_query_leaves_the_centroid_alone():
    """Defaults must be a no-op, or every existing tuning silently shifts."""
    neutral = MoodQuery(raw_text="x", intensity=0.5, intensity_tolerance=0.5)
    for dest, base in DESTINATION_TARGETS.items():
        assert resolve_target(neutral, dest).model_dump() == base.model_dump()


def test_target_stays_in_range_at_the_extremes():
    for intensity in (0.0, 1.0):
        for tol in (0.0, 1.0):
            axes = resolve_target(
                MoodQuery(raw_text="x", intensity=intensity, intensity_tolerance=tol),
                "sit_with",
            )
            assert -1.0 <= axes.valence <= 1.0
            for name in ("warmth", "weight", "catharsis", "tension", "companionship"):
                assert 0.0 <= getattr(axes, name) <= 1.0


def test_session_length_excludes_arcs_that_cannot_finish(store):
    """A stated session length is a real constraint, applied when it can be."""
    short = MoodQuery(raw_text="10 min hai", session_length_min=10)
    cands = Retriever(store).retrieve(short, "company")
    if cands:  # only assert when the constraint left a workable pool
        assert all(
            c.fingerprint.duration_min <= 10 * SESSION_SLACK for c in cands
        )


def test_session_length_yields_rather_than_starving(store):
    """An impossibly short session must not produce an empty shelf."""
    impossible = MoodQuery(raw_text="1 min", session_length_min=1)
    assert Retriever(store).retrieve(impossible, "company"), (
        "duration filter starved the shelf instead of yielding"
    )


# ---------------------------------------------------------------------------
# MMR: relevance must actually influence selection
# ---------------------------------------------------------------------------


def test_mmr_respects_relevance_not_just_distance(store):
    """The previous formula used a constant for relevance, so this ordering was
    determined by distance alone. With lambda high, the top-scored rows must win.
    """
    retr = Retriever(store, ScoringWeights(mmr_lambda=0.99))
    order = list(range(min(12, len(store))))
    score = np.zeros(len(store), dtype=np.float32)
    # Give the LAST rows in pool order the best scores. A pure diversity
    # maximiser ignores this; real MMR must surface them.
    for rank, row in enumerate(order):
        score[row] = float(rank) / len(order)

    chosen = retr._mmr(order, 4, score)
    assert chosen[0] == order[0]  # seed is always the top-ranked row
    # With relevance dominating, later picks skew to the high-scoring tail.
    assert max(chosen[1:]) >= order[len(order) // 2]


def test_mmr_still_diversifies_when_lambda_is_low(store):
    retr = Retriever(store, ScoringWeights(mmr_lambda=0.01))
    order = list(range(min(12, len(store))))
    score = np.full(len(store), 0.5, dtype=np.float32)
    chosen = retr._mmr(order, 4, score)
    assert len(chosen) == len(set(chosen)) == 4


def test_scores_are_normalised_into_unit_range(store):
    """Un-normalised, the terms summed past 1.0 and both rerankers clamp — so the
    top of the ranking saturated at exactly 1.0 and lost its ordering."""
    query = heuristic_parse("something that feels like a rainy Sunday after heartbreak")
    for cand in Retriever(store).retrieve(query, "sit_with"):
        assert 0.0 <= cand.score <= 1.0


# ---------------------------------------------------------------------------
# Refine: no LLM, and the finished-series mask still applies
# ---------------------------------------------------------------------------


def test_refine_never_uses_the_llm_reranker(store):
    """The latency contract. `refine` must not inherit an LLM reranker."""

    class ExplodingReranker:
        def rerank(self, *_a, **_k):  # pragma: no cover - must never be called
            raise AssertionError("refine path reached the LLM reranker")

    eng = MoodSearchEngine(store, reranker=ExplodingReranker())
    query = heuristic_parse("something that feels like a rainy Sunday after heartbreak")
    shelf, _ = eng.build_shelf(query, "sit_with", reranker=HeuristicReranker())
    refined = eng.refine(query, "sit_with", shelf.target_axes, {"heavier": 1.0})
    assert refined is not None and refined.results


def test_refine_keeps_the_finished_series_mask(store):
    """A slider drag must not resurface a series the listener already finished."""
    from app.mood.persona import ListenerProfile, WatchRecord

    query = heuristic_parse("something that feels like a rainy Sunday after heartbreak")
    eng = MoodSearchEngine(store)
    shelf, _ = eng.build_shelf(query, "sit_with")
    finished = shelf.results[0].series_id

    profile = ListenerProfile(
        persona_id="t1",
        display_name="Test",
        history=[
            WatchRecord(series_id=finished, episodes_listened=24, completed=True)
        ],
    )
    refined = eng.refine(
        query, "sit_with", shelf.target_axes, {"heavier": 1.0}, profile=profile
    )
    if refined is not None:
        assert all(c.series_id != finished for c in refined.results), (
            "refine resurfaced a finished series — exclusion mask was dropped"
        )


# ---------------------------------------------------------------------------
# Copy and invariants
# ---------------------------------------------------------------------------


def test_every_destination_has_enough_explanation_lines():
    """Fewer lines than results guarantees a visibly repeated explanation."""
    for destination, pool in _REASONS.items():
        assert len(pool) >= MIN_REASONS_PER_DESTINATION, destination


def test_template_reason_is_stable_across_processes():
    """Was keyed on hash(str), which is PYTHONHASHSEED-salted, so the 'offline
    deterministic' path picked different copy on every restart."""
    from app.mood.rerank import _template_reason
    from app.mood.store import Candidate

    fp = build_seed_catalog()[0]
    cand = Candidate(row=0, fingerprint=fp, axis_distance=0.1, semantic=0.5,
                     tag_overlap=0.0, score=0.5)
    # Precomputed from blake2b, independent of interpreter hash seed.
    import hashlib

    pool = _REASONS[list(_REASONS)[0]]
    digest = hashlib.blake2b(fp.content_id.encode(), digest_size=4).digest()
    expected_index = int.from_bytes(digest, "little") % len(pool)
    assert _template_reason(list(_REASONS)[0], cand) == pool[expected_index]


def test_affinity_ceiling_stays_under_the_stated_line():
    """History informs a thin query; it never owns one."""
    assert AFFINITY_CEILING < 0.25
    assert AFFINITY_CEILING < ScoringWeights().axis
    for sparsity in (0.0, 0.5, 1.0):
        assert ScoringWeights.for_query(sparsity).affinity <= AFFINITY_CEILING


def test_situation_still_drives_tags():
    from app.mood.retrieval import situation_tags

    tags = situation_tags(MoodQuery(
        raw_text="x",
        situation=Situation(weather="rain", time_of_day="night", solitude="alone"),
    ))
    assert {"rain", "night", "small-room"} <= set(tags)
