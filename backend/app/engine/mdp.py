"""Policy search over story decisions — the RL / MDP capability.

Formalises cliffhanger optimisation as a Markov Decision Process:

* **State** = the story-so-far grounded in the canon graph (world state) plus the
  current audience response.
* **Action** = a candidate next beat / cliffhanger (proposed by the LLM).
* **Reward** = the simulated hook-score from the audience panel — i.e. the
  audience simulator IS the environment / reward model.
* **Transition** = adopting the chosen action becomes the next state.

Each iteration samples actions, scores their one-step Q-values via the reward
model, does greedy policy improvement with a discounted (γ) one-step Bellman
look-ahead on the chosen action (V(s') ≈ best reward reachable next), and carries
it forward as the next state. No gradient training — this is a demonstrable,
finite-horizon policy-search loop over the simulator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.config import settings
from app.engine.audience_panel import resolve_reward_panel
from app.engine.cache import Cache
from app.engine.runner import run_reactions
from app.engine.search import _mean_hook, _swap, _variants
from app.graph.store import canon_fingerprint, fetch_canon_subgraph, render_canon_memory
from app.llm.base import LLMClient
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
    """Run the MDP policy search; the audience simulator provides the reward.

    State transitions each step (the adopted beat becomes the next state), and the
    chosen action's value uses a discounted one-step Bellman look-ahead so the
    policy is value-based, not purely myopic.
    """
    canon = render_canon_memory(await fetch_canon_subgraph(story, source="MDP Optimizer"))
    canon_fp = canon_fingerprint(canon)
    # Reward model = the persisted "Living Audience" when available, else defaults.
    panel, audience_source = await resolve_reward_panel(
        min(10, settings.audience_fanout), "MDP Optimizer"
    )
    audience_model = settings.model_for("audience")
    gamma = settings.mdp_discount
    lookahead = max(0, settings.mdp_lookahead)

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    def _story_with(ending: str) -> Story:
        """The story state with ``ending`` adopted in place of the weak beat."""
        return Story(
            title=story.title, episode=story.episode, text=_swap(story.text, weak_excerpt, ending)
        )

    async def reward(ending: str) -> float:
        pairs = await run_reactions(
            panel, _story_with(ending), llm, cache,
            model=audience_model, canon=canon, canon_fp=canon_fp,
        )
        return round(_mean_hook(pairs), 1)

    def _state_label(ending: str, it: int) -> str:
        head = " ".join((ending or "").split())[:120]
        return f"s{it}: …{head}" if head else f"s{it}"

    baseline = await reward(weak_excerpt)
    emit({
        "type": "baseline",
        "reward": baseline,
        "audience_source": audience_source,
        "panel_size": len(panel),
        "discount": gamma,
    })

    current = weak_excerpt
    best_reward = baseline
    best_text = weak_excerpt
    discounted_return = 0.0
    steps: list[MdpStep] = []

    for it in range(1, iterations + 1):
        # Actions are sampled from the CURRENT state (running story with the
        # adopted beat), so the search is grounded in where the story now stands.
        state_story = _story_with(current)
        actions = await _variants(llm, state_story, current, candidates_per_iter)
        if not actions:
            break
        q_immediate = await asyncio.gather(*[reward(a) for a in actions])
        best_idx = max(range(len(q_immediate)), key=lambda i: q_immediate[i])
        chosen, chosen_r = actions[best_idx], q_immediate[best_idx]

        # One-step Bellman look-ahead for the chosen action: V(s') ≈ the best
        # reward reachable from the next state. Bounded + best-effort, and skipped
        # on the horizon's final step. Falls back to the immediate reward.
        value_next = chosen_r
        if lookahead and it < iterations:
            try:
                children = await _variants(llm, _story_with(chosen), chosen, lookahead)
                if children:
                    child_r = await asyncio.gather(*[reward(c) for c in children])
                    value_next = max(child_r)
            except Exception as exc:  # noqa: BLE001 - look-ahead is best-effort
                logger.warning("MDP look-ahead failed: %s", exc)

        q_chosen = round(chosen_r + gamma * value_next, 1)
        discounted_return = round(discounted_return + (gamma ** (it - 1)) * chosen_r, 1)

        if chosen_r > best_reward:
            best_reward, best_text = chosen_r, chosen
        current = chosen  # transition: adopt the chosen action as the next state

        step = MdpStep(
            iteration=it,
            chosen_action_id=f"a{it}.{best_idx + 1}",
            reward=chosen_r,
            best_reward=best_reward,
            q_values=[float(q) for q in q_immediate],
            state=_state_label(current, it),
            value=q_chosen,
        )
        steps.append(step)
        emit({
            "type": "iteration_done",
            "iteration": it,
            "reward": chosen_r,
            "best_reward": best_reward,
            "q_values": step.q_values,
            "q_chosen": q_chosen,
            "value_next": round(value_next, 1),
            "discount": gamma,
            "discounted_return": discounted_return,
            "state": step.state,
            "preview": chosen[:140],
        })

    return MdpResult(
        steps=steps,
        baseline_reward=baseline,
        final_reward=best_reward,
        best_action_text=best_text,
        policy="greedy-lookahead" if lookahead else "greedy",
        discount=gamma,
        discounted_return=discounted_return,
        audience_source=audience_source,
    )
