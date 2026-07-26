"""Offline tests for the knowledge-graph layer — no Neo4j, no LLM.

Covers the pure helpers (id/slug/relation sanitisation, memory rendering,
fingerprinting), the canon prompt-injection behaviour, and the cache-key
regression guard (injecting memory MUST change the reaction cache key).
"""

from __future__ import annotations

import pytest

from app.engine.cache import Cache
from app.engine.runner import build_reaction_prompt
from app.graph.store import (
    _node_id,
    _sanitize_rel,
    _slug,
    canon_fingerprint,
    fetch_contradiction_candidates,
    fetch_full_graph,
    ingest_extraction,
    render_canon_memory,
    reset_canon_batch,
)
from app.schemas import (
    CanonEdgeView,
    CanonExtraction,
    CanonGraph,
    CanonNodeView,
    ExtractedEntity,
    ExtractedFact,
    Persona,
    Story,
)


def _persona() -> Persona:
    return Persona(
        id="p1", name="Asha", kind="audience", segment="Metro", system_prompt="React."
    )


def test_slug_and_ids_are_stable_and_clean():
    assert _slug("Flat 6B") == "flat-6b"
    assert _slug("Naina!", "the girl") == "naina-the-girl"
    assert _node_id("Character", "Naina") == "Character:naina"
    # Same name → same id across episodes (entity resolution).
    assert _node_id("Character", "Naina") == _node_id("Character", "naina")


def test_sanitize_rel_whitelists_to_cypher_safe_types():
    assert _sanitize_rel("appears in") == "APPEARS_IN"
    assert _sanitize_rel("located-at") == "LOCATED_AT"
    assert _sanitize_rel("") == "RELATES_TO"
    # A non-letter-initial (or otherwise unusable) type falls back to a safe
    # constant rather than producing an invalid/injectable Cypher label.
    assert _sanitize_rel("123 weird;;") == "RELATES_TO"
    assert _sanitize_rel("SUSPECTS") == "SUSPECTS"


def test_canon_fingerprint_empty_and_stable():
    assert canon_fingerprint("") == "nocanon"
    fp = canon_fingerprint("STORY SO FAR: Naina knows flat 6B.")
    assert len(fp) == 16
    assert fp == canon_fingerprint("STORY SO FAR: Naina knows flat 6B.")
    assert fp != canon_fingerprint("STORY SO FAR: something else.")


def test_render_canon_memory_groups_and_truncates():
    empty = render_canon_memory(CanonGraph())
    assert empty == ""  # empty graph → no memory (keeps today's behaviour)

    graph = CanonGraph(
        nodes=[
            CanonNodeView(id="Character:naina", label="Character", name="Naina",
                          props={"description": "investigator"}),
            CanonNodeView(id="Location:flat-6b", label="Location", name="Flat 6B",
                          props={"description": "sealed since 1998"}),
        ],
        edges=[CanonEdgeView(source="Character:naina", target="Location:flat-6b", type="LOCATED_AT")],
    )
    mem = render_canon_memory(graph)
    assert "Naina" in mem and "Flat 6B" in mem
    assert "Characters:" in mem and "Locations:" in mem
    assert "located at" in mem  # relationship rendered in plain language


def test_canon_injection_changes_prompt_and_cache_key():
    persona, story = _persona(), Story(title="T", episode="7", text="script")

    # No canon → today's prompt, unchanged.
    _s0, u0 = build_reaction_prompt(persona, story)
    assert "WHAT YOU REMEMBER" not in u0 and u0.endswith("React now.")

    # With canon → memory appears in the user turn.
    _s1, u1 = build_reaction_prompt(persona, story, "STORY SO FAR: Naina knows 6B.")
    assert "WHAT YOU REMEMBER SO FAR:" in u1 and "Naina knows 6B" in u1

    # Regression guard: the canon component MUST change the reaction cache key,
    # otherwise injected memory would replay a stale, amnesiac cached reaction.
    cache = Cache(".cache")
    base = ("gemini", "m", persona.id, "fp", "storyhash")
    key_nocanon = cache.make_key(*base, "nocanon", "reaction")
    key_canon = cache.make_key(*base, canon_fingerprint("STORY SO FAR: Naina knows 6B."), "reaction")
    assert key_nocanon != key_canon


# --- session-scoped canon (best-effort paths, no Neo4j needed) --------------


def test_reset_canon_batch_never_wipes_without_a_batch():
    # An empty/whitespace batch is a hard no-op: this endpoint must never be able
    # to delete the whole graph (only what a specific session tagged).
    import asyncio

    assert asyncio.run(reset_canon_batch("")) == 0
    assert asyncio.run(reset_canon_batch("   ")) == 0


@pytest.mark.asyncio
async def test_ingest_echoes_batch_and_extraction_when_graph_disabled(monkeypatch):
    # Force the graph-disabled path (deterministic, never touches a real Neo4j):
    # the write no-ops, but the result still echoes the session batch + the
    # extraction so the composer can render "what got added".
    monkeypatch.setattr("app.graph.store.get_driver", lambda: None)
    story = Story(title="Meera", episode="1", text="Meera comes home to a quiet house.")
    extraction = CanonExtraction(
        entities=[ExtractedEntity(key="meera", type="Character", name="Meera")],
        facts=[ExtractedFact(subject_key="meera", predicate="mood", object="uneasy")],
    )
    res = await ingest_extraction(story, extraction, batch="session-abc123")
    assert res.batch == "session-abc123"
    assert res.nodes_added == 0  # graph disabled → nothing persisted
    assert res.extraction is not None
    assert res.extraction.entities[0].name == "Meera"


@pytest.mark.asyncio
async def test_scoped_reads_are_empty_when_graph_disabled(monkeypatch):
    monkeypatch.setattr("app.graph.store.get_driver", lambda: None)
    graph = await fetch_full_graph(batch="session-abc123")
    assert graph.nodes == [] and graph.edges == []
    facts = await fetch_contradiction_candidates(batch="session-abc123")
    assert facts["facts"] == [] and facts["conflicts"] == [] and facts["fact_count"] == 0
