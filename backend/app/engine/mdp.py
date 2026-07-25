"""Policy search over story decisions — the RL / MDP capability.

Formalises cliffhanger optimisation as a Markov Decision Process:

* **State** = the story-so-far grounded in the canon graph (world state) plus the
  current audience response.
* **Action** = a candidate next beat / cliffhanger (proposed by the LLM).
* **Reward** = the simulated hook-score from the audience panel — i.e. the
  audience simulator IS the environment / reward model.
* **Transition** = adopting the chosen action becomes the next state.

Each iteration samples actions, estimates their Q-values via the reward model,
does greedy policy improvement, and carries the best action forward. No gradient
training — this is a demonstrable policy-search loop over the simulator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.config import settings
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.engine.search import _mean_hook, _swap, _variants
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.llm.base import LLMClient
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import MdpResult, MdpStep, Story

logger = logging.getLogger(__name__)


async def policy_search(
    story: Story,
    weak_excerpt: str,
    llm: LLMClient,
    cache: Cache,
    iterations: int = 4,
    candidates_per_iter: int = 3,
    on_event: Callable[[dict], None] | None = None,
) -> MdpResult:
    """Run greedy policy search; the audience simulator provides the reward."""
    canon = render_canon_memory(await fetch_canon_subgraph(story))
    canon_fp = canon_fingerprint(canon)
    panel = fan_out_audience(load_personas("audience"), min(10, settings.audience_fanout))
    audience_model = settings.model_for("audience")

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    async def reward(ending: str) -> float:
        target = Story(
            title=story.title, episode=story.episode, text=_swap(story.text, weak_excerpt, ending)
        )
        pairs = await run_reactions(
            panel, target, llm, cache, model=audience_model, canon=canon, canon_fp=canon_fp
        )
        return round(_mean_hook(pairs), 1)

    baseline = await reward(weak_excerpt)
    emit({"type": "baseline", "reward": baseline})

    current = weak_excerpt
    best_reward = baseline
    best_text = weak_excerpt
    steps: list[MdpStep] = []

    for it in range(1, iterations + 1):
        actions = await _variants(llm, story, current, candidates_per_iter)
        if not actions:
            break
        q_values = await asyncio.gather(*[reward(a) for a in actions])
        best_idx = max(range(len(q_values)), key=lambda i: q_values[i])
        chosen, chosen_r = actions[best_idx], q_values[best_idx]
        if chosen_r > best_reward:
            best_reward, best_text = chosen_r, chosen
        current = chosen  # transition: adopt the chosen action as the next state

        step = MdpStep(
            iteration=it,
            chosen_action_id=f"a{it}.{best_idx + 1}",
            reward=chosen_r,
            best_reward=best_reward,
            q_values=[float(q) for q in q_values],
        )
        steps.append(step)
        emit({
            "type": "iteration_done",
            "iteration": it,
            "reward": chosen_r,
            "best_reward": best_reward,
            "q_values": step.q_values,
            "preview": chosen[:140],
        })

    return MdpResult(
        steps=steps,
        baseline_reward=baseline,
        final_reward=best_reward,
        best_action_text=best_text,
        policy="greedy",
    )
