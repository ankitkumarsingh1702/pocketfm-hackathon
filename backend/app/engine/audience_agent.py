"""The agentic reaction loop for the Audience Simulator ("Living Audience").

Each listener is a genuine, *stateful* agent that runs a real loop:

1. **perceive** — SEES the posted image + reads the text (a multimodal vision call).
2. **recall**   — reads its OWN past reactions from the knowledge graph, so it
   behaves as a returning listener (statefulness across posts), not a blank slate.
3. **deliberate / decide** — one structured vision call yields a
   :class:`SocialReaction` whose ``reasoning`` is the agent's private, glass-box
   rationale and ``engagement`` is the single concrete action it takes.
4. **remember** — the batch's reactions are written back to the graph (by the
   lens), becoming the memory the agent recalls next time.

Fans out across ``settings.sim_concurrency`` agents with retry + jitter on
transient errors, streams each reaction as it lands (via an ``on_event``
callback), and surfaces — never hides — the count of agents that failed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from collections.abc import Callable

from app.config import settings
from app.db.activity import record_activity
from app.engine.aggregate import reaction_view
from app.engine.cache import Cache
from app.engine.runner import _story_hash, persona_fingerprint, persona_preamble, story_images
from app.graph.audience_store import recall_member_memory
from app.llm.base import LLMClient
from app.schemas import Persona, SocialReaction, Story

logger = logging.getLogger(__name__)


def _memory_fp(memory: list[dict]) -> str:
    """Short digest of an agent's recalled memory, folded into the cache key so a
    returning listener with new history doesn't replay a first-time reaction."""
    if not memory:
        return "nomem"
    raw = "::".join(
        f"{m.get('post')}|{m.get('sentiment')}|{m.get('engagement')}" for m in memory
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _render_memory(memory: list[dict]) -> str:
    """Render recalled reactions as a short first-person history block."""
    if not memory:
        return ""
    lines: list[str] = []
    for m in memory[:4]:
        post = m.get("post") or "an earlier post"
        sentiment = m.get("sentiment") or "reacted"
        engagement = m.get("engagement") or ""
        comment = (m.get("comment") or "").strip()
        line = f'- "{post}": you felt {sentiment}'
        if engagement and engagement != "scroll_past":
            line += f", you {engagement}d it"
        if comment:
            line += f' and commented "{comment}"'
        lines.append(line)
    return (
        "YOUR HISTORY WITH THIS CREATOR (react as someone who remembers):\n"
        + "\n".join(lines)
    )


def build_social_prompt(
    persona: Persona,
    story: Story,
    canon: str | None = None,
    memory: list[dict] | None = None,
) -> tuple[str, str]:
    """Return the ``(system, user)`` prompt pair for one listener-agent."""
    preamble = persona_preamble(persona)
    system = (
        preamble
        + persona.system_prompt
        + " You are scrolling PocketFM and this post/teaser appears in your feed. "
        "React honestly AS THIS LISTENER — not as a critic. Think in first person "
        "about whether it grabs you, then decide the ONE action you'd actually "
        "take (scroll past, like, comment, share, save, subscribe, or binge). In "
        "'reasoning' give your candid inner monologue for why; in 'comment' write "
        "the exact words you'd post, in your own voice; in 'memory_note' say how "
        "your past history with this creator (if any) shaped your reaction."
    )
    parts = [f"POST TITLE: {story.title}"]
    if story.episode:
        parts.append(f"EPISODE: {story.episode}")
    parts.append("POST TEXT:\n" + story.text)
    user = "\n".join(parts)
    if story.image_base64:
        user += (
            "\n\n(An image is attached to this post — LOOK at it and react to what "
            "you SEE, not just the text.)"
        )
    mem = _render_memory(memory or [])
    if mem:
        user += "\n\n" + mem
    if canon:
        user += "\n\nWHAT YOU REMEMBER OF THE STORY SO FAR:\n" + canon
    user += "\n\nReact now."
    return system, user


async def _react_with_retry(
    llm: LLMClient,
    system: str,
    user: str,
    model: str | None,
    temperature: float | None,
    images,
) -> SocialReaction:
    """One deliberation call, retried with exponential backoff + jitter.

    Real fan-out at scale hits transient Vertex 429/503s; retrying with jitter
    keeps agents from vanishing silently the way a single unguarded call would.
    """
    last: Exception | None = None
    for attempt in range(settings.sim_max_retries + 1):
        try:
            return await llm.structured(
                system, user, SocialReaction, temperature=temperature, model=model, images=images
            )
        except Exception as exc:  # noqa: BLE001 - retry transient failures, re-raise the last
            last = exc
            if attempt >= settings.sim_max_retries:
                break
            base = 0.5 * (2**attempt)
            await asyncio.sleep(base + random.random() * base)
    assert last is not None
    raise last


async def run_social_reactions(
    personas: list[Persona],
    story: Story,
    llm: LLMClient,
    cache: Cache | None = None,
    model: str | None = None,
    canon: str | None = None,
    canon_fp: str | None = None,
    on_event: Callable[[dict], None] | None = None,
    source: str = "Audience Simulator",
) -> tuple[list[tuple[Persona, SocialReaction]], int]:
    """Run every persona's agent loop concurrently; stream + collect reactions.

    Returns ``(pairs, dropped)`` where ``pairs`` are the successful
    ``(persona, reaction)`` and ``dropped`` is the number of agents that failed
    even after retries. Emits ``reaction`` / ``agent_error`` events as each agent
    lands so the UI can render a live feed.
    """
    sem = asyncio.Semaphore(settings.sim_concurrency)
    kg_sem = asyncio.Semaphore(settings.sim_concurrency)  # bound the recall reads too
    story_hash = _story_hash(story)
    canon_key = canon_fp or "nocanon"
    images = story_images(story)
    total = len(personas)
    # Count agents that recalled real prior history, so we can surface the
    # collective memory read as ONE activity event (per-agent reads would flood
    # the feed at panel scale). This is the visible proof the agents are stateful.
    recalled = 0

    async def _one(persona: Persona) -> tuple[Persona, SocialReaction]:
        nonlocal recalled
        # recall — the agent reads its own memory (bounded, best-effort).
        memory: list[dict] = []
        if settings.sim_agentic:
            async with kg_sem:
                memory = await recall_member_memory(persona.id)
            if memory:
                recalled += 1

        system, user = build_social_prompt(persona, story, canon, memory)

        key = None
        if cache is not None:
            key = cache.make_key(
                llm.name,
                model or "default",
                persona.id,
                persona_fingerprint(persona),
                story_hash,
                canon_key,
                _memory_fp(memory),
                "social",
            )
            cached = cache.get(key)
            if cached is not None:
                try:
                    return persona, SocialReaction.model_validate(cached)
                except Exception:  # noqa: BLE001 - stale/corrupt entry, regenerate
                    pass

        async with sem:
            reaction = await _react_with_retry(
                llm, system, user, model, persona.temperature, images
            )
        if cache is not None and key is not None:
            cache.set(key, reaction.model_dump())
        return persona, reaction

    tasks = [asyncio.ensure_future(_one(p)) for p in personas]
    pairs: list[tuple[Persona, SocialReaction]] = []
    dropped = 0
    done = 0
    for fut in asyncio.as_completed(tasks):
        try:
            persona, reaction = await fut
        except Exception as exc:  # noqa: BLE001 - drop this agent, but COUNT it
            dropped += 1
            logger.warning("Audience agent failed after retries: %s", exc)
            if on_event:
                on_event({"type": "agent_error", "dropped": dropped, "total": total, "error": str(exc)})
            continue
        pairs.append((persona, reaction))
        done += 1
        if on_event:
            on_event(
                {
                    "type": "reaction",
                    "done": done,
                    "dropped": dropped,
                    "total": total,
                    "reaction": reaction_view(persona, reaction).model_dump(),
                }
            )
    # Surface the collective recall as one read: proof the agents remembered
    # their own past reactions before responding (statefulness across posts).
    if settings.sim_agentic and recalled:
        record_activity(
            "read",
            "recall_member_memory",
            source,
            f"{recalled} of {total} agents recalled their prior reactions from shared memory",
            {"agents_recalled": recalled, "panel": total},
        )
    return pairs, dropped
