"""A2A Word-of-Mouth cascade engine — genuine agent-to-agent communication.

The Audience Simulator fans a post out to N agents that each react INDEPENDENTLY
(no agent ever sees another's output). This engine adds the missing horizontal
arrow: when an agent SHARES/SUBSCRIBES, its *actual comment* is injected into the
prompt of the peers who follow it, and the post propagates round by round through
a homophily social graph — an independent-cascade diffusion.

Loop per round:
  1. the current frontier of agents reacts (one structured ``SocialReaction``
     each), with any upstream peers' comments carried in their ``inbox``;
  2. agents whose action is ``share``/``subscribe`` are spreaders — their
     un-exposed neighbours become the next round's frontier, each carrying the
     spreader's comment as an inbox message (the A2A message);
  3. stop when no new spreaders, ``max_rounds`` is hit, or the total-reach cap
     bounds cost.

Everything is bounded (seed/rounds/per-round/total caps) and reuses the existing
reaction machinery (``_react_with_retry``, ``story_images``, ``reaction_view``,
the disk cache). Nothing here touches the Audience Simulator's own code paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable

from app.config import settings
from app.engine.aggregate import reaction_view
from app.engine.audience_agent import _react_with_retry, _render_memory
from app.engine.cache import Cache
from app.engine.runner import (
    _story_hash,
    persona_fingerprint,
    persona_preamble,
    story_images,
)
from app.graph.audience_store import recall_member_memory
from app.llm.base import LLMClient
from app.schemas import (
    A2ACascadeResult,
    CascadeEdge,
    CascadeNode,
    CascadeReactionView,
    CascadeSpreader,
    Persona,
    SocialReaction,
    Story,
)

logger = logging.getLogger(__name__)

# --- tunables (kept here so config.py stays untouched; all cost-bounding) ----
A2A_SEED_DEFAULT = 24          # agents in round 0
A2A_MAX_ROUNDS = 4            # hops to propagate
A2A_AVG_DEGREE = 8           # homophily out-degree per agent
A2A_PER_ROUND_CAP = 48       # max new agents added to any single round
A2A_TOTAL_CAP = 200          # hard ceiling on total agents that react (bounds LLM calls)
A2A_POPULATION_CAP = 400     # size of the network the post can spread through
A2A_MESSAGE_EMIT_CAP = 90    # cap A->B "message" events streamed to the UI

# The actions that put the post into a follower's feed (word of mouth): a public
# comment, a share, or a subscribe all surface to the peers who follow the agent.
SPREAD_ACTIONS = {"comment", "share", "subscribe"}


def _inbox_fp(inbox: list[dict]) -> str:
    """Digest of the peer messages an agent saw, folded into the cache key so an
    influenced reaction never replays an organic (no-inbox) one."""
    if not inbox:
        return "noinbox"
    raw = "::".join(f"{m.get('from_id')}|{m.get('comment')}" for m in inbox)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _rotate_start(seed: str, n: int) -> int:
    """Stable index in [0, n) from a seed string (deterministic, no RNG)."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % n


def build_adjacency(members: list[Persona], degree: int = A2A_AVG_DEGREE) -> dict[str, list[str]]:
    """Deterministic homophily social graph: each agent follows peers who share
    its segment, city, or a genre. Tops up from the wider population so every
    agent has ~``degree`` links even when a homophily cohort is tiny (e.g. a
    freshly generated set), which keeps the cascade alive. No randomness (stable
    across re-runs). Returns ``{member_id: [neighbour_id, ...]}`` — out-edges are
    the peers who see this agent's activity.
    """
    ids = [m.id for m in members]
    seg_buckets: dict[str, list[str]] = defaultdict(list)
    city_buckets: dict[str, list[str]] = defaultdict(list)
    genre_buckets: dict[str, list[str]] = defaultdict(list)
    for m in members:
        seg_buckets[(m.segment or "general").strip().lower()].append(m.id)
        if m.city and m.city.strip():
            city_buckets[m.city.strip().lower()].append(m.id)
        for g in m.genres or []:
            if g and g.strip():
                genre_buckets[g.strip().lower()].append(m.id)

    adjacency: dict[str, list[str]] = {}
    for m in members:
        candidates: list[str] = []
        candidates.extend(x for x in seg_buckets[(m.segment or "general").strip().lower()] if x != m.id)
        if m.city and m.city.strip():
            candidates.extend(x for x in city_buckets[m.city.strip().lower()] if x != m.id)
        for g in m.genres or []:
            if g and g.strip():
                candidates.extend(x for x in genre_buckets[g.strip().lower()] if x != m.id)

        # dedupe, preserve order
        seen: set[str] = {m.id}
        uniq: list[str] = []
        for x in candidates:
            if x not in seen:
                seen.add(x)
                uniq.append(x)

        picked: list[str] = []
        if uniq:
            # rotate the start so the graph isn't hub-and-spoke onto the first few.
            start = _rotate_start(m.id, len(uniq))
            picked = [uniq[(start + i) % len(uniq)] for i in range(min(degree, len(uniq)))]

        # Top up from the wider population so the network stays connected.
        if len(picked) < degree and len(ids) > 1:
            chosen = set(picked)
            chosen.add(m.id)
            start = _rotate_start(m.id + "|fill", len(ids))
            i = 0
            while len(picked) < degree and i < len(ids):
                cand = ids[(start + i) % len(ids)]
                if cand not in chosen:
                    picked.append(cand)
                    chosen.add(cand)
                i += 1

        adjacency[m.id] = picked
    return adjacency


def build_cascade_prompt(
    persona: Persona,
    story: Story,
    canon: str | None,
    memory: list[dict] | None,
    inbox: list[dict] | None,
) -> tuple[str, str]:
    """``(system, user)`` for one agent — with any upstream peers' comments
    injected as the A2A message (``inbox``)."""
    preamble = persona_preamble(persona)
    social = " — and people you follow are already reacting to it" if inbox else ""
    system = (
        preamble
        + persona.system_prompt
        + f" You are scrolling PocketFM and THIS exact post appears in your feed{social}. "
        "React ONLY as this specific listener — your age, city, taste and mood drive everything. "
        "Choose the ONE action you'd truly take right now (scroll_past, like, comment, share, save, "
        "subscribe, or binge). React honestly as yourself: a dull or not-for-you post earns a scroll or "
        "a quiet like, but a post that genuinely grips you earns a COMMENT (say what you'd actually "
        "type), a SHARE, or a SUBSCRIBE. Those three surface to the peers who follow you and pass the "
        "post onward; a plain like or scroll does not. If people you follow are already reacting to it, "
        "that social proof makes you more likely to comment or share it on — though hype does not move "
        "everyone. Set hook_score 0-100 for how gripping THIS post is FOR "
        "YOU. 'comment' = the exact words you'd type, in your own voice (empty if you wouldn't). "
        "'reasoning' = your candid private why. 'memory_note' = how prior context shaped this."
    )
    parts = [f"POST TITLE: {story.title}"]
    if story.episode:
        parts.append(f"EPISODE: {story.episode}")
    parts.append("POST TEXT:\n" + story.text)
    user = "\n".join(parts)
    if story.image_base64:
        user += "\n\n(An image is attached to this post — LOOK at it and react to what you SEE too.)"
    if inbox:
        lines: list[str] = []
        for m in inbox[:6]:
            who = m.get("from_name") or "Someone you follow"
            seg = f", {m['from_segment']}" if m.get("from_segment") else ""
            comment = (m.get("comment") or "").strip() or "shared this with you"
            lines.append(f'- {who}{seg}: "{comment}"')
        user += (
            "\n\nPEOPLE YOU FOLLOW ARE ALREADY TALKING ABOUT THIS POST:\n"
            + "\n".join(lines)
            + "\n(Their word-of-mouth may or may not pull you in — decide honestly, as yourself.)"
        )
    mem = _render_memory(memory or [])
    if mem:
        user += "\n\n" + mem
    if canon:
        user += "\n\nWHAT YOU REMEMBER OF THE STORY SO FAR:\n" + canon
    user += "\n\nReact now."
    return system, user


async def _react(
    persona: Persona,
    story: Story,
    canon: str | None,
    canon_fp: str | None,
    inbox: list[dict],
    llm: LLMClient,
    cache: Cache | None,
    model: str | None,
    images,
    story_hash: str,
    sem: asyncio.Semaphore,
    kg_sem: asyncio.Semaphore,
) -> tuple[Persona, SocialReaction]:
    """One agent's turn: recall own memory, read its inbox, decide (cached)."""
    memory: list[dict] = []
    if settings.sim_agentic:
        async with kg_sem:
            memory = await recall_member_memory(persona.id)
    system, user = build_cascade_prompt(persona, story, canon, memory, inbox)

    key = None
    if cache is not None:
        key = cache.make_key(
            llm.name,
            model or "default",
            persona.id,
            persona_fingerprint(persona),
            story_hash,
            canon_fp or "nocanon",
            _inbox_fp(inbox),
            "a2a",
        )
        cached = cache.get(key)
        if cached is not None:
            try:
                return persona, SocialReaction.model_validate(cached)
            except Exception:  # noqa: BLE001 - stale entry, regenerate
                logger.debug("Ignoring stale a2a cache entry for %s", persona.id)

    async with sem:
        reaction = await _react_with_retry(llm, system, user, model, persona.temperature, images)
    if cache is not None and key is not None:
        cache.set(key, reaction.model_dump())
    return persona, reaction


async def run_cascade(
    population: list[Persona],
    adjacency: dict[str, list[str]],
    seed_ids: list[str],
    story: Story,
    llm: LLMClient,
    cache: Cache | None = None,
    model: str | None = None,
    canon: str | None = None,
    canon_fp: str | None = None,
    max_rounds: int = A2A_MAX_ROUNDS,
    per_round_cap: int = A2A_PER_ROUND_CAP,
    total_cap: int = A2A_TOTAL_CAP,
    on_event: Callable[[dict], None] | None = None,
    source: str = "A2A Word-of-Mouth",
) -> dict:
    """Run the round-by-round cascade; stream events; return outcome.

    Returns ``{"result": A2ACascadeResult, "pairs": [(persona, reaction), ...],
    "influence": [{source_id,target_id,round,comment}, ...]}`` so the caller can
    persist memory + influence edges and hand the public result to the client.
    """
    by_id = {p.id: p for p in population}
    sem = asyncio.Semaphore(settings.sim_concurrency)
    kg_sem = asyncio.Semaphore(settings.sim_concurrency)
    story_hash = _story_hash(story)
    images = story_images(story)

    exposed: set[str] = set(seed_ids)
    frontier: list[str] = [sid for sid in seed_ids if sid in by_id]
    inbox_map: dict[str, list[dict]] = {sid: [] for sid in frontier}

    pairs: list[tuple[Persona, SocialReaction]] = []
    nodes: list[CascadeNode] = []
    edges: list[CascadeEdge] = []
    influence: list[dict] = []
    reactions_view: list[CascadeReactionView] = []
    reach_curve: list[int] = []
    spreader_reach: dict[str, int] = defaultdict(int)
    spreader_meta: dict[str, tuple[str, str | None]] = {}
    total_spreaders = 0
    total_secondary = 0
    dropped = 0
    messages_emitted = 0
    round_index = 0

    while frontier and round_index < max_rounds and len(pairs) < total_cap:
        if on_event:
            on_event({"type": "round_started", "round": round_index, "exposed": len(frontier)})

        tasks = [
            asyncio.ensure_future(
                _react(
                    by_id[i], story, canon, canon_fp, inbox_map.get(i, []),
                    llm, cache, model, images, story_hash, sem, kg_sem,
                )
            )
            for i in frontier
            if i in by_id
        ]
        round_reactions: list[tuple[Persona, SocialReaction]] = []
        for fut in asyncio.as_completed(tasks):
            try:
                persona, reaction = await fut
            except Exception as exc:  # noqa: BLE001 - drop this agent, but COUNT it
                dropped += 1
                logger.warning("A2A agent failed after retries: %s", exc)
                if on_event:
                    on_event({"type": "agent_error", "round": round_index, "dropped": dropped, "error": str(exc)})
                continue
            inbox_msgs = inbox_map.get(persona.id, [])
            influenced_names = [m["from_name"] for m in inbox_msgs if m.get("from_name")]
            pairs.append((persona, reaction))
            round_reactions.append((persona, reaction))
            nodes.append(
                CascadeNode(id=persona.id, name=persona.name, segment=persona.segment,
                            round=round_index, engagement=reaction.engagement)
            )
            view = CascadeReactionView(
                **reaction_view(persona, reaction).model_dump(),
                round=round_index,
                influenced_by=influenced_names,
            )
            reactions_view.append(view)
            if on_event:
                event = view.model_dump()
                event.update({"type": "reaction", "done": len(pairs)})
                on_event(event)
        reach_curve.append(len(round_reactions))

        # Spreaders seed the next round; their comment becomes the peers' inbox.
        spreaders = [(p, r) for (p, r) in round_reactions if r.engagement in SPREAD_ACTIONS]
        total_spreaders += len(spreaders)
        next_inbox: dict[str, list[dict]] = {}
        next_ids: list[str] = []
        stop = False
        for persona, reaction in spreaders:
            spreader_meta[persona.id] = (persona.name, persona.segment)
            for nb in adjacency.get(persona.id, []):
                if nb in exposed or nb not in by_id:
                    continue
                if len(exposed) + len(next_ids) >= total_cap or len(next_ids) >= per_round_cap:
                    stop = True
                    break
                if nb not in next_inbox:
                    next_inbox[nb] = []
                    next_ids.append(nb)
                next_inbox[nb].append(
                    {
                        "from_id": persona.id,
                        "from_name": persona.name,
                        "from_segment": persona.segment,
                        "comment": reaction.comment,
                    }
                )
                edges.append(CascadeEdge(source=persona.id, target=nb, round=round_index + 1))
                influence.append(
                    {"source_id": persona.id, "target_id": nb, "round": round_index + 1, "comment": reaction.comment}
                )
                spreader_reach[persona.id] += 1
                total_secondary += 1
                if on_event and messages_emitted < A2A_MESSAGE_EMIT_CAP:
                    neighbour = by_id[nb]
                    on_event(
                        {
                            "type": "message",
                            "round": round_index + 1,
                            "from": {"id": persona.id, "name": persona.name, "segment": persona.segment},
                            "to": {"id": neighbour.id, "name": neighbour.name, "segment": neighbour.segment},
                            "comment": reaction.comment,
                        }
                    )
                    messages_emitted += 1
            if stop:
                break

        for i in next_ids:
            exposed.add(i)
        if on_event:
            on_event(
                {
                    "type": "round_done",
                    "round": round_index,
                    "new_reach": len(round_reactions),
                    "cumulative_reach": len(pairs),
                    "new_sharers": len(spreaders),
                }
            )
        frontier = next_ids
        inbox_map = next_inbox
        round_index += 1

    coefficient = round(total_secondary / total_spreaders, 2) if total_spreaders else 0.0
    super_spreaders = sorted(
        (
            CascadeSpreader(
                id=pid,
                name=spreader_meta[pid][0],
                segment=spreader_meta[pid][1],
                reached=count,
            )
            for pid, count in spreader_reach.items()
        ),
        key=lambda s: s.reached,
        reverse=True,
    )[:8]

    result = A2ACascadeResult(
        seed_count=len(seed_ids),
        total_reached=len(pairs),
        population=len(population),
        rounds=round_index,
        virality_coefficient=coefficient,
        reach_curve=reach_curve,
        super_spreaders=super_spreaders,
        nodes=nodes,
        edges=edges,
        reactions=reactions_view,
        dropped=dropped,
    )
    return {"result": result, "pairs": pairs, "influence": influence}
