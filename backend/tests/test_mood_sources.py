"""Mood-First Search — the source-file contract.

Every test here corresponds to a way that authoring the files exactly as
documented used to fail. They are cheap, they need no LLM and no network, and
each one stands for a defect that produced no error message: a silently empty
result set, a silently missing series, or a whole feature unmounted at import.
"""

from __future__ import annotations

import json

import pytest

from app.mood.catalog_ingest import (
    SYNTHETIC_SOURCES,
    SourceArc,
    SourceSeries,
    _arc_duration_min,
    load_source,
    synthesize_arcs,
)
from app.mood.embeddings import HashingEmbedder
from app.mood.episodes import (
    Episode,
    EpisodeStore,
    build_episode_store,
    derive_stub_episodes,
    load_authored_episodes,
)
from app.mood.persona import load_profiles
from app.mood.retrieval import Retriever
from app.mood.schemas import MoodQuery
from app.mood.seed_catalog import build_seed_catalog
from app.mood.store import MoodStore


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# language — the one that returned nothing at all
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def store():
    s = MoodStore(HashingEmbedder())
    s.add(build_seed_catalog())
    return s


def test_query_has_no_language_preference_by_default():
    """`language` is an exact-match hard filter, so a default of "en" silently
    emptied every shelf for a catalog authored per the documented template
    (which is tagged "hi"). No preference is the only safe default."""
    assert MoodQuery(raw_text="x").language is None


def test_a_non_english_catalog_still_returns_results(store):
    """The regression, end to end: retagging the catalog must not zero it out."""
    hindi = MoodStore(HashingEmbedder())
    hindi.add([fp.model_copy(update={"language": "hi"}) for fp in store.fingerprints])

    query = MoodQuery(raw_text="something like a rainy Sunday after heartbreak")
    assert Retriever(hindi).retrieve(query, "sit_with"), (
        "a Hindi-tagged catalog returned nothing for a query with no language "
        "preference — the hard filter is firing on a default again"
    )


def test_an_explicit_language_is_still_a_hard_filter(store):
    """The flip side: when a listener DOES ask, the filter must still bite."""
    assert Retriever(store).retrieve(MoodQuery(raw_text="x", language="xx"), "sit_with") == []


# ---------------------------------------------------------------------------
# episodes.json — the documented shape must load
# ---------------------------------------------------------------------------


def test_minimal_episode_rows_load(tmp_path):
    """`{"number": 34}` is what the docs invite. It used to raise a
    ValidationError at import time and take all of /api/mood offline."""
    path = _write(tmp_path, "episodes.json", [
        {"series_id": "s1", "episodes": [{"number": 1}, {"number": 34}]},
    ])
    eps = load_authored_episodes(path)
    assert [e.number for e in eps] == [1, 34]
    assert eps[1].title == "Episode 34"  # fallback, not a crash


def test_episode_rows_tolerate_repeated_series_id_and_extra_columns(tmp_path):
    """A spreadsheet export repeats the key column and carries extra ones."""
    path = _write(tmp_path, "episodes.json", [
        {"series_id": "s1", "episodes": [
            {"series_id": "s1", "number": 3, "title": "Teen", "notes": "ignore me"},
        ]},
    ])
    eps = load_authored_episodes(path)
    assert len(eps) == 1 and eps[0].series_id == "s1" and eps[0].number == 3


def test_flat_and_wrapped_episode_shapes_load(tmp_path):
    flat = _write(tmp_path, "flat.json", [{"series_id": "s1", "number": 2}])
    wrapped = _write(tmp_path, "wrapped.json",
                     {"episodes": [{"series_id": "s1", "number": 5}]})
    assert load_authored_episodes(flat)[0].number == 2
    assert load_authored_episodes(wrapped)[0].number == 5


def test_partial_authoring_keeps_the_rest_of_the_series(tmp_path):
    """Authoring 2 of 212 episodes must not delete the other 210 — the docs
    explicitly tell you to author only what you demo."""
    series = SourceSeries(
        series_id="s1", title="T", synopsis="x" * 130, total_episodes=212,
        source="pocketfm_web",
        arcs=[SourceArc("s1_a0", "the opening arc", 1, 212, "")],
    )
    path = _write(tmp_path, "episodes.json", [
        {"series_id": "s1", "episodes": [
            {"number": 1, "title": "Real One", "duration_sec": 1180},
            {"number": 34, "title": "Barsaat", "duration_sec": 1240},
        ]},
    ])
    store = build_episode_store([series], path)
    assert store.total_for("s1") == 212, "stubs were suppressed for the whole series"
    assert store.get("s1", 34).title == "Barsaat"      # authored wins
    assert store.get("s1", 2).title == "Episode 2"     # stub fills the gap


def test_validate_against_uses_membership_not_a_count():
    """With eps 1 and 34 authored, an entry point at 34 is VALID even though only
    two records exist. Counting instead of checking membership reported the valid
    case as broken and missed the real 404."""
    store = EpisodeStore()
    store.add([
        Episode(series_id="s1", number=1, title="a", duration_sec=60),
        Episode(series_id="s1", number=34, title="b", duration_sec=60),
    ])

    class FP:
        series_id, content_id, series_title = "s1", "s1_a1", "T"
        entry_episode = 34

    assert store.validate_against([FP()]) == []

    FP.entry_episode = 99
    problems = store.validate_against([FP()])
    assert len(problems) == 1 and "404" in problems[0]


# ---------------------------------------------------------------------------
# profiles.json
# ---------------------------------------------------------------------------


def test_documented_history_row_loads(tmp_path):
    """`episodes_listened` is documented optional; it used to be positionally
    required, so the documented row raised a TypeError at import."""
    path = _write(tmp_path, "profiles.json", [
        {"persona_id": "p1", "display_name": "Ananya",
         "attrs": {"listening_time_slot": "late_night"},
         "history": [{"series_id": "s1", "completed": True}]},
    ])
    profiles = load_profiles(path)
    assert profiles[0].history[0].completed is True
    assert profiles[0].history[0].episodes_listened == 0


def test_profiles_tolerate_aliases_wrappers_and_extra_keys(tmp_path):
    path = _write(tmp_path, "profiles.json", {"personas": [
        {"id": "p2", "history": [
            {"series_id": "s1", "completed": False, "watch_seconds": 12},
        ]},
    ]})
    profiles = load_profiles(path)
    assert profiles[0].persona_id == "p2"
    assert profiles[0].display_name == "p2"  # falls back to the id


# ---------------------------------------------------------------------------
# catalog.json
# ---------------------------------------------------------------------------


def test_absent_source_is_not_treated_as_synthetic(tmp_path):
    """It defaults to "unknown" and is ingested as real — which is exactly why
    the validator errors on a missing `source`."""
    path = _write(tmp_path, "catalog.json", [
        {"series_id": "s1", "title": "T", "synopsis": "x" * 130, "total_episodes": 10},
    ])
    series = load_source(path)[0]
    assert series.source == "unknown"
    assert series.is_synthetic is False


@pytest.mark.parametrize("source", ["gpt", "claude", "synthetic", "fixture"])
def test_model_written_sources_are_all_recognised(source):
    """The validator and the loader must agree. They did not: "gpt" and "claude"
    were warned about by one and accepted as real by the other."""
    series = SourceSeries(
        series_id="s", title="T", synopsis="x" * 130, total_episodes=5, source=source,
    )
    assert series.is_synthetic is True
    assert source in SYNTHETIC_SOURCES


def test_arc_duration_comes_from_real_episode_lengths():
    """Hardcoding one duration made every card read the same and left the
    session-length filter unable to discriminate."""
    arc = SourceArc("a", "the monsoon arc", 10, 12, "")
    assert _arc_duration_min(arc, {10: 600, 11: 660, 12: 720}) == 11
    assert _arc_duration_min(arc, None) == 20  # documented fallback


def test_synthesized_arc_starts_are_predictable():
    """The validator recomputes these to check for 404s, so the two must agree."""
    series = SourceSeries(
        series_id="s1", title="T", synopsis="x" * 130, total_episodes=212,
        source="pocketfm_web",
    )
    assert [a.start_episode for a in synthesize_arcs(series)] == [1, 71, 141]


def test_stub_episodes_mark_the_arc_start():
    series = SourceSeries(
        series_id="s1", title="T", synopsis="x" * 130, total_episodes=40,
        source="pocketfm_web",
        arcs=[SourceArc("s1_a1", "the monsoon arc", 34, 40, "")],
    )
    stubs = derive_stub_episodes(series)
    assert [e.number for e in stubs if e.is_arc_start] == [34]
