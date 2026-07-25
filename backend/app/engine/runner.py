"""Concurrent persona-reaction runner.

Fans a story out to many personas, calls the LLM once per persona (bounded by
``settings.concurrency``), caches each reaction on disk, and returns the
successful ``(persona, reaction)`` pairs. Failed LLM calls are dropped rather
than aborting the whole batch, so one flaky response never sinks a run.
"""

from __future__ import annotations

import asyncio
import hashlib

from app.config import settings
from app.engine.cache import Cache
from app.llm.base import LLMClient
from app.schemas import Persona, PersonaReaction, Story


def _story_hash(story: Story) -> str:
    """Stable hash of a story's identity for cache keying."""
    raw = story.title + (story.episode or "") + story.text
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_reaction_prompt(persona: Persona, story: Story) -> tuple[str, str]:
    """Return the ``(system, user)`` prompt pair for one persona + story."""
    system = (
        persona.system_prompt
        + " Answer strictly as this listener reacting to one audio-drama episode."
    )
    episode = story.episode or ""
    user = (
        "TITLE: " + story.title + " EPISODE: " + episode + " SCRIPT:\n" + story.text
        + "\n\nReact now."
    )
    return system, user


async def run_reactions(
    personas: list[Persona],
    story: Story,
    llm: LLMClient,
    cache: Cache | None = None,
) -> list[tuple[Persona, PersonaReaction]]:
    """Collect one ``PersonaReaction`` per persona, concurrently and cached.

    Cache hits skip the LLM entirely. Misses call ``llm.structured`` under a
    concurrency semaphore and store the result. Exceptions from any single
    persona are swallowed and that persona is dropped from the output.
    """
    sem = asyncio.Semaphore(settings.concurrency)
    story_hash = _story_hash(story)

    async def _one(persona: Persona) -> tuple[Persona, PersonaReaction]:
        system, user = build_reaction_prompt(persona, story)
        key = (
            cache.make_key(llm.name, persona.id, story_hash, "reaction")
            if cache is not None
            else None
        )

        if cache is not None and key is not None:
            cached = cache.get(key)
            if cached is not None:
                try:
                    return persona, PersonaReaction.model_validate(cached)
                except Exception:
                    # Corrupt/stale cache entry — regenerate below.
                    pass

        async with sem:
            reaction = await llm.structured(system, user, PersonaReaction)

        if cache is not None and key is not None:
            cache.set(key, reaction.model_dump())
        return persona, reaction

    results = await asyncio.gather(
        *(_one(p) for p in personas), return_exceptions=True
    )
    return [r for r in results if not isinstance(r, BaseException)]
