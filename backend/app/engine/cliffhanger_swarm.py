"""Stateful, explainable audience scoring for the Cliffhanger Planner.

The planner deliberately separates *search* from *verification*:

* a small, stratified scout cohort rates the full candidate tree;
* the original ending and the strongest finalists are then rated by the same
  full persistent cohort (1,000 by default);
* every listener reads a frozen snapshot of their own graph memory plus shared
  story canon before rating, and no experiment result is written back until all
  arms have finished.

One listener returns all ratings in one structured inference. That means a
1,000-agent / three-finalist verification is 1,000 agent calls and 4,000
explicit ending evaluations, rather than 4,000 separate calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random
from collections import defaultdict
from collections.abc import Callable

from app.config import settings
from app.engine.audience_agent import _render_memory
from app.engine.cache import Cache
from app.engine.runner import persona_fingerprint, persona_preamble
from app.graph.audience_store import write_cliffhanger_evaluations
from app.llm.base import LLMClient
from app.schemas import (
    CliffhangerAgentVerdict,
    CliffhangerRating,
    Persona,
    Story,
)

logger = logging.getLogger(__name__)


def mean_score(ratings: list[CliffhangerRating]) -> float:
    return (
        round(sum(r.hook_score for r in ratings) / len(ratings), 1) if ratings else 0.0
    )


def ci95(ratings: list[CliffhangerRating]) -> float:
    """Normal-approximation 95% interval half-width for this simulated panel."""
    n = len(ratings)
    if n < 2:
        return 0.0
    values = [float(r.hook_score) for r in ratings]
    mean = sum(values) / n
    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    return round(1.96 * math.sqrt(variance / n), 1)


def stratified_sample(members: list[Persona], n: int) -> list[Persona]:
    """Stable round-robin sample across audience segments."""
    if n >= len(members):
        return list(members)
    groups: dict[str, list[Persona]] = defaultdict(list)
    for member in sorted(members, key=lambda item: item.id):
        groups[member.segment or "General"].append(member)
    ordered_groups = [groups[key] for key in sorted(groups)]
    out: list[Persona] = []
    offset = 0
    while len(out) < n:
        advanced = False
        for group in ordered_groups:
            if offset < len(group):
                out.append(group[offset])
                advanced = True
                if len(out) >= n:
                    break
        if not advanced:
            break
        offset += 1
    return out


def _memory_fingerprint(memory: list[dict]) -> str:
    raw = "::".join(
        f"{item.get('post')}|{item.get('sentiment')}|{item.get('engagement')}|{item.get('comment')}"
        for item in memory
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12] if raw else "nomem"


def _alternatives_fingerprint(alternatives: list[tuple[str, str]]) -> str:
    raw = "::".join(f"{candidate_id}|{text}" for candidate_id, text in alternatives)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_cliffhanger_prompt(
    persona: Persona,
    story: Story,
    weak_excerpt: str,
    alternatives: list[tuple[str, str]],
    canon: str,
    memory: list[dict],
) -> tuple[str, str]:
    """Build one paired-comparison prompt for a persistent listener-agent."""
    ids = ", ".join(candidate_id for candidate_id, _ in alternatives)
    system = (
        persona_preamble(persona)
        + persona.system_prompt
        + " You are evaluating endings as this exact listener, not as a writing critic. "
        "Your identity and preferences remain stable across every option. Rate whether "
        "the complete episode plus each ending makes you immediately start the next "
        "episode. Use the full 0-100 hook scale consistently. Return exactly one rating "
        f"for every candidate id, and no other ids. Required ids: {ids}."
    )
    episode_context = (
        story.text.replace(weak_excerpt, "[ENDING OPTION INSERTED HERE]")
        if weak_excerpt and weak_excerpt in story.text
        else story.text
    )
    parts = [
        f"SHOW: {story.title}",
        f"EPISODE: {story.episode or 'Unspecified'}",
        "COMPLETE EPISODE CONTEXT:",
        episode_context,
        "BLINDED ENDING OPTIONS:",
    ]
    for candidate_id, text in alternatives:
        parts.append(f"\n[{candidate_id}]\n{text}")
    rendered_memory = _render_memory(memory, scope="show")
    if rendered_memory:
        parts.extend(["", rendered_memory])
    if canon:
        parts.extend(["", "SHARED STORY CANON:", canon])
    parts.extend(
        [
            "",
            (
                "For each required id, return hook_score (0-100), will_continue, and one "
                "short listener-level reason. Score the ending in the context of the full episode."
            ),
        ]
    )
    return system, "\n".join(parts)


async def _one_verdict(
    *,
    member: Persona,
    story: Story,
    weak_excerpt: str,
    alternatives: list[tuple[str, str]],
    canon: str,
    memory: list[dict],
    llm: LLMClient,
    cache: Cache,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[CliffhangerAgentVerdict, bool]:
    expected_real = {candidate_id for candidate_id, _ in alternatives}
    seed_raw = f"{member.id}|{_alternatives_fingerprint(alternatives)}"
    seed = int(hashlib.sha256(seed_raw.encode("utf-8")).hexdigest()[:16], 16)
    blinded = list(alternatives)
    random.Random(seed).shuffle(blinded)
    alias_to_candidate = {
        f"arm_{index + 1}": candidate_id
        for index, (candidate_id, _) in enumerate(blinded)
    }
    blinded_alternatives = [
        (alias, text)
        for alias, (_, text) in zip(alias_to_candidate, blinded, strict=True)
    ]
    expected = set(alias_to_candidate)
    cache_key = cache.make_key(
        llm.name,
        model,
        "cliffhanger-swarm-v1",
        member.id,
        persona_fingerprint(member),
        story.title,
        story.episode or "",
        hashlib.sha256(story.text.encode("utf-8")).hexdigest()[:16],
        hashlib.sha256(weak_excerpt.encode("utf-8")).hexdigest()[:12],
        _alternatives_fingerprint(blinded_alternatives),
        _memory_fingerprint(memory),
        hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12] if canon else "nocanon",
    )
    cached = cache.get(cache_key)
    if cached is not None:
        try:
            verdict = CliffhangerAgentVerdict.model_validate(cached)
            if {rating.candidate_id for rating in verdict.ratings} == expected_real:
                return verdict, True
        except Exception as exc:  # noqa: BLE001 - stale/corrupt cache is a miss
            logger.debug("Ignoring invalid cliffhanger cache entry: %s", exc)

    system, prompt = build_cliffhanger_prompt(
        member, story, weak_excerpt, blinded_alternatives, canon, memory
    )
    last_error: Exception | None = None
    for attempt in range(settings.sim_max_retries + 1):
        try:
            async with semaphore:
                verdict = await llm.structured(
                    system=system,
                    prompt=prompt,
                    schema=CliffhangerAgentVerdict,
                    temperature=member.temperature,
                    model=model,
                )
            actual = {rating.candidate_id for rating in verdict.ratings}
            if actual != expected or len(verdict.ratings) != len(expected):
                raise ValueError(
                    f"agent returned candidate ids {sorted(actual)}; expected {sorted(expected)}"
                )
            verdict = CliffhangerAgentVerdict(
                ratings=[
                    rating.model_copy(
                        update={"candidate_id": alias_to_candidate[rating.candidate_id]}
                    )
                    for rating in verdict.ratings
                ]
            )
            cache.set(cache_key, verdict.model_dump())
            return verdict, False
        except Exception as exc:  # noqa: BLE001 - retry provider/shape failures
            last_error = exc
            if attempt >= settings.sim_max_retries:
                break
            delay = 0.5 * (2**attempt)
            await asyncio.sleep(delay + random.random() * delay)
    assert last_error is not None
    raise last_error


async def run_cliffhanger_panel(
    *,
    members: list[Persona],
    story: Story,
    weak_excerpt: str,
    alternatives: list[tuple[str, str]],
    canon: str,
    memories: dict[str, list[dict]],
    llm: LLMClient,
    cache: Cache,
    model: str,
    phase: str,
    emit: Callable[[dict], None],
) -> tuple[dict[str, list[tuple[Persona, CliffhangerRating]]], int, int]:
    """Rate every alternative with every member and stream honest progress."""
    semaphore = asyncio.Semaphore(settings.sim_concurrency)
    total = len(members)
    ratings: dict[str, list[tuple[Persona, CliffhangerRating]]] = {
        candidate_id: [] for candidate_id, _ in alternatives
    }

    async def _run_member(
        member: Persona,
    ) -> tuple[Persona, CliffhangerAgentVerdict, bool]:
        verdict, cached = await _one_verdict(
            member=member,
            story=story,
            weak_excerpt=weak_excerpt,
            alternatives=alternatives,
            canon=canon,
            memory=memories.get(member.id, []),
            llm=llm,
            cache=cache,
            model=model,
            semaphore=semaphore,
        )
        return member, verdict, cached

    tasks = [asyncio.ensure_future(_run_member(member)) for member in members]
    completed = 0
    dropped = 0
    cached_agents = 0
    try:
        for future in asyncio.as_completed(tasks):
            try:
                member, verdict, cached = await future
            except Exception as exc:  # noqa: BLE001 - visible partial failure
                dropped += 1
                logger.warning(
                    "Cliffhanger listener-agent failed after retries: %s", exc
                )
                emit(
                    {
                        "type": "agent_error",
                        "phase": phase,
                        "completed": completed,
                        "dropped": dropped,
                        "total": total,
                        "error": str(exc),
                    }
                )
                continue
            if cached:
                cached_agents += 1
            completed += 1
            for rating in verdict.ratings:
                ratings[rating.candidate_id].append((member, rating))
            running_scores = {
                candidate_id: mean_score([rating for _, rating in pairs])
                for candidate_id, pairs in ratings.items()
            }
            emit(
                {
                    "type": "agent_scored",
                    "phase": phase,
                    "completed": completed,
                    "dropped": dropped,
                    "total": total,
                    "persona": {
                        "id": member.id,
                        "name": member.name,
                        "segment": member.segment or "General",
                    },
                    "memory_items_loaded": len(memories.get(member.id, [])),
                    "cached": cached,
                    "running_scores": running_scores,
                }
            )
    finally:
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return ratings, dropped, cached_agents


async def persist_experiment_memory(
    story: Story,
    winner_text: str,
    weak_excerpt: str,
    original_pairs: list[tuple[Persona, CliffhangerRating]],
    winner_pairs: list[tuple[Persona, CliffhangerRating]],
) -> bool:
    """Archive a test result without pretending the unpublished arm was heard.

    Experiment edges are intentionally excluded from ``REACTED_TO`` recall.
    They remain queryable in the graph and can be promoted only after a real
    publish/apply action exists.
    """
    written = await write_cliffhanger_evaluations(
        story=story,
        original_text=weak_excerpt,
        winner_text=winner_text,
        original_pairs=original_pairs,
        winner_pairs=winner_pairs,
        source="Cliffhanger Planner",
    )
    return written == len(winner_pairs) and written > 0
