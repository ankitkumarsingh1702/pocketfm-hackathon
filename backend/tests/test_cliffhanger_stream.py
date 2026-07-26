"""Offline coverage for the streaming Cliffhanger lens (`run_cliffhanger` emits).

Verifies that a real emit callback narrates the run — the rewrite, then one
`agent_scored` event per listener for both the original and the optimized ending,
bookended by phase start/done events — without any network, LLM, cache, or graph.
"""

from __future__ import annotations

import asyncio

from app.lenses import cliffhanger as lens
from app.lenses.cliffhanger import _Rewrite, run_cliffhanger
from app.schemas import CanonGraph, Persona, PersonaReaction, Story

REWRITE_TOKEN = "LOCK-TURNS-REWRITE"


class _FakeCache:
    """In-memory no-op cache so the lens never touches disk."""

    def make_key(self, *parts) -> str:
        return "k:" + "|".join(str(p) for p in parts)

    def get(self, _key):
        return None

    def set(self, _key, _value) -> None:
        return None


class _FakeLLM:
    name = "fake"

    async def structured(self, system, prompt, schema, **_kwargs):
        # The rewrite call asks for _Rewrite; the panel asks for PersonaReaction.
        if schema is _Rewrite:
            return _Rewrite(rewrite=f"{REWRITE_TOKEN} — the line goes dead.", rationale="tension")
        # The optimized ending carries the rewrite token; the original does not.
        optimized = REWRITE_TOKEN in prompt
        return PersonaReaction(
            will_continue=optimized,
            hook_score=80 if optimized else 40,
            drop_point="cliffhanger" if optimized else "middle",
            reason="matched listener judgment",
            emotion="tense" if optimized else "bored",
        )


def _panel(_personas, _n):
    return [
        Persona(
            id=f"listener-{i}",
            name=f"Listener {i}",
            kind="audience",
            segment="Metro" if i % 2 == 0 else "Town",
            system_prompt="You are a returning listener.",
        )
        for i in range(3)
    ]


def _patch(monkeypatch):
    monkeypatch.setattr(lens, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(lens, "Cache", lambda _dir: _FakeCache())
    monkeypatch.setattr(lens, "load_personas", lambda _kind: [])
    monkeypatch.setattr(lens, "fan_out_audience", _panel)

    async def _fake_fetch(*_args, **_kwargs):
        return CanonGraph()

    monkeypatch.setattr(lens, "fetch_canon_subgraph", _fake_fetch)
    monkeypatch.setattr(lens, "render_canon_memory", lambda _graph: "")
    monkeypatch.setattr(lens, "save_simulation", lambda *a, **k: None)


def test_stream_emits_rewrite_then_per_agent_scores(monkeypatch):
    _patch(monkeypatch)
    events: list[dict] = []

    story = Story(title="Aakhiri Ghanti", episode="1", text="Full episode. Weak close.")
    result = asyncio.run(run_cliffhanger(story, "Weak close.", emit=events.append))

    types = [e["type"] for e in events]
    assert types[0] == "run_started"
    assert events[0]["panel_size"] == 3

    # Rewrite phase is narrated and carries the rewritten text.
    assert {"type": "phase", "phase": "rewrite", "status": "start"} in events
    rewrite_done = next(
        e for e in events if e["type"] == "phase" and e["phase"] == "rewrite" and e["status"] == "done"
    )
    assert REWRITE_TOKEN in rewrite_done["rewrite"]

    # One agent_scored per listener, for each of the two panels.
    before = [e for e in events if e["type"] == "agent_scored" and e["phase"] == "before"]
    after = [e for e in events if e["type"] == "agent_scored" and e["phase"] == "after"]
    assert len(before) == 3 and len(after) == 3
    # Each event is a glass box: who scored, their score, cache state, running mean.
    sample = before[0]
    assert sample["persona"]["name"].startswith("Listener")
    assert sample["hook_score"] == 40
    assert sample["cached"] is False
    assert sample["total"] == 3
    assert "running_mean" in sample
    # done counts climb 1..N so the client can render a live counter.
    assert [e["done"] for e in after] == [1, 2, 3]

    # Panel phase-done events report the aggregate scores.
    before_done = next(
        e for e in events if e["type"] == "phase" and e["phase"] == "panel_before" and e["status"] == "done"
    )
    after_done = next(
        e for e in events if e["type"] == "phase" and e["phase"] == "panel_after" and e["status"] == "done"
    )
    assert before_done["score"] == 40.0
    assert after_done["score"] == 80.0

    # The returned result matches the streamed scores and shows the lift.
    assert result.before_score == 40.0
    assert result.after_score == 80.0
    assert result.lift == 40.0


def test_default_emit_is_noop(monkeypatch):
    """Without an emit callback the lens still returns a normal result."""
    _patch(monkeypatch)
    story = Story(title="Aakhiri Ghanti", episode="1", text="Full episode. Weak close.")
    result = asyncio.run(run_cliffhanger(story, "Weak close."))
    assert result.after_score == 80.0
    assert result.lift == 40.0
