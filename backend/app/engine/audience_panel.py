"""Shared reward-panel resolver for the planning / agent lenses.

The Audience Simulator persists a real, *stateful* listener population in the
knowledge graph (``:AudienceMember`` nodes with ``REACTED_TO`` memory edges).
The planning capabilities — beam search (``engine/search``), MDP policy search
(``engine/mdp``) — and the showrunner state-graph agent (``lenses/showrunner``)
all use the audience as their **reward / scoring model**. So when that persisted
population exists, they should plan against the *same* agents the user watches
react on the Audience tab, not a throwaway default roster.

``resolve_reward_panel`` returns that living population when it exists (capped to
``size`` for latency), and falls back to the built-in archetypes fanned out to
``size`` when the graph is empty or disabled — so behaviour is unchanged out of
the box, and becomes grounded in the real audience the moment one is generated.
"""

from __future__ import annotations

from app.graph.audience_store import load_audience_members
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import Persona


async def resolve_reward_panel(size: int, source: str) -> tuple[list[Persona], str]:
    """Return ``(panel, audience_source)`` for scoring — living audience first.

    ``audience_source`` is ``"living"`` when the panel came from the persisted
    Audience Simulator population, else ``"default"``. Best-effort: any graph
    failure inside ``load_audience_members`` falls through to the built-in roster,
    so this never breaks a run.
    """
    size = max(1, size)
    members = await load_audience_members(source=source)
    if members:
        # Use the real population; inflate only if the saved audience is smaller
        # than the scoring panel (keeps a full, fast panel without inventing
        # personas when the user already generated hundreds).
        panel = members[:size] if len(members) >= size else fan_out_audience(members, size)
        return panel, "living"
    return fan_out_audience(load_personas("audience"), size), "default"
