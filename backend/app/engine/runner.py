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


# Natural-language wording for the persona's gender in the reaction preamble.
_GENDER_WORDS: dict[str, str] = {
    "female": "woman",
    "male": "man",
    "non-binary": "non-binary person (they/them)",
    "nonbinary": "non-binary person (they/them)",
}


def _gender_word(gender: str | None) -> str:
    """Map a gender value to a natural word ('listener' when unset)."""
    if not gender or not gender.strip():
        return "listener"
    key = gender.strip().lower()
    return _GENDER_WORDS.get(key, gender.strip())


def persona_fingerprint(persona: Persona) -> str:
    """Short (16-hex) hash over a persona's behaviour-affecting fields.

    Folded into cache keys so that editing a persona (age, gender, city,
    genres, segment, system prompt or temperature) never replays a reaction
    cached before the edit — the demographic edit changes the behaviour, so it
    must change the key.
    """
    raw = "::".join(
        [
            str(persona.age),
            str(persona.gender),
            str(persona.city),
            ",".join(sorted(persona.genres)),
            str(persona.segment),
            persona.system_prompt,
            str(persona.temperature),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_reaction_prompt(
    persona: Persona, story: Story, canon: str | None = None
) -> tuple[str, str]:
    """Return the ``(system, user)`` prompt pair for one persona + story.

    A natural demographic preamble built from the persona's own fields is
    prepended to its system prompt so that edits to age/gender/city/genres
    visibly change how the listener reacts. Each fragment is guarded on its
    field, so a sparse persona still yields a clean sentence.

    When ``canon`` is provided (the story-bible memory from the knowledge
    graph), it is appended to the user turn so the listener reacts as someone
    who remembers earlier episodes. Passing ``None`` reproduces the original,
    memory-free prompt byte-for-byte.
    """
    # Identity sentence: "You are <name>, a <age>-year-old <gender> from <city>."
    identity = f"You are {persona.name}"
    descriptor: list[str] = []
    if persona.age is not None:
        descriptor.append(f"{persona.age}-year-old")
    if descriptor or (persona.gender and persona.gender.strip()):
        descriptor.append(_gender_word(persona.gender))
    if descriptor:
        identity += ", a " + " ".join(descriptor)
    if persona.city and persona.city.strip():
        identity += f" from {persona.city.strip()}"
    identity += "."

    preamble = identity + " "
    genres = [g.strip() for g in persona.genres if g and g.strip()]
    if genres:
        preamble += "You mostly enjoy " + ", ".join(genres) + ". "

    system = (
        preamble
        + persona.system_prompt
        + " Answer strictly as this listener reacting to one audio-drama episode."
    )
    episode = story.episode or ""
    user = "TITLE: " + story.title + " EPISODE: " + episode + " SCRIPT:\n" + story.text
    if canon:
        user += "\n\nWHAT YOU REMEMBER SO FAR:\n" + canon
    user += "\n\nReact now."
    return system, user


async def run_reactions(
    personas: list[Persona],
    story: Story,
    llm: LLMClient,
    cache: Cache | None = None,
    model: str | None = None,
    canon: str | None = None,
    canon_fp: str | None = None,
) -> list[tuple[Persona, PersonaReaction]]:
    """Collect one ``PersonaReaction`` per persona, concurrently and cached.

    Cache hits skip the LLM entirely. Misses call ``llm.structured`` under a
    concurrency semaphore and store the result. Exceptions from any single
    persona are swallowed and that persona is dropped from the output.

    ``canon`` (story-bible memory) is injected into every prompt; ``canon_fp``
    is folded into the cache key so injecting or changing memory never replays a
    reaction cached under different canon.
    """
    sem = asyncio.Semaphore(settings.concurrency)
    story_hash = _story_hash(story)
    canon_key = canon_fp or "nocanon"

    async def _one(persona: Persona) -> tuple[Persona, PersonaReaction]:
        system, user = build_reaction_prompt(persona, story, canon)
        key = (
            cache.make_key(
                llm.name,
                model or "default",
                persona.id,
                persona_fingerprint(persona),
                story_hash,
                canon_key,
                "reaction",
            )
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
            reaction = await llm.structured(
                system, user, PersonaReaction, temperature=persona.temperature, model=model
            )

        if cache is not None and key is not None:
            cache.set(key, reaction.model_dump())
        return persona, reaction

    results = await asyncio.gather(
        *(_one(p) for p in personas), return_exceptions=True
    )
    return [r for r in results if not isinstance(r, BaseException)]
