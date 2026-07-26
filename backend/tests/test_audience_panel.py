"""resolve_reward_panel wiring.

The planning / agent lenses (beam search, MDP, showrunner) must score against the
persisted "Living Audience" population when it exists, and fall back cleanly to
the built-in roster when the graph is empty or disabled. Both paths are covered
here without a real Neo4j or any LLM call.
"""

from __future__ import annotations

import asyncio

from app.engine.audience_panel import resolve_reward_panel
from app.schemas import Persona


def test_reward_panel_falls_back_to_default_roster(monkeypatch):
    # Graph disabled → no persisted members → built-in audience, fanned to size.
    monkeypatch.setattr("app.graph.audience_store.get_driver", lambda: None)
    panel, source = asyncio.run(resolve_reward_panel(8, "test"))
    assert source == "default"
    assert len(panel) == 8
    assert all(p.kind == "audience" for p in panel)


def test_reward_panel_prefers_living_audience(monkeypatch):
    living = [
        Persona(
            id=f"m{i}", name=f"L{i}", kind="audience", segment="Seg",
            system_prompt="You are a PocketFM listener.",
        )
        for i in range(3)
    ]

    async def _fake_members(*args, **kwargs):
        return list(living)

    monkeypatch.setattr("app.engine.audience_panel.load_audience_members", _fake_members)

    # Fewer requested than saved → use the real population, truncated.
    panel, source = asyncio.run(resolve_reward_panel(2, "test"))
    assert source == "living" and len(panel) == 2

    # More requested than saved → inflate the real population to fill the panel.
    panel2, source2 = asyncio.run(resolve_reward_panel(5, "test"))
    assert source2 == "living" and len(panel2) == 5
