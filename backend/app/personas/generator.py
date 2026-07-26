"""LLM-driven synthesis of a diverse audience of listener-agents.

``fan_out_audience`` only clones a handful of archetypes with a small age jitter,
so a "1000-listener panel" is really 5-7 near-duplicates. This module asks the
LLM to invent *genuinely distinct* audience members — varied age, gender, city,
genre taste, habits and voice — so the simulator runs thousands of different
agents, not copies. Batches are generated concurrently for speed and diversity.

Best-effort: if the LLM is unavailable, it falls back to archetype fan-out so a
run never dies for lack of a roster.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.config import settings
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import Persona, SynthBatch

logger = logging.getLogger(__name__)

_BATCH = 20  # members generated per LLM call (keeps each response within budget)

_SYS = (
    "You are a casting director assembling a realistic, diverse audience panel "
    "for an Indian audio-drama app (PocketFM-style). Invent distinct listeners: "
    "vary age (teens to 60s), gender, city (mix metros like Mumbai/Delhi/"
    "Bengaluru with smaller towns), genre taste, listening habits, patience and "
    "personality. Each must feel like one specific real person, never a "
    "stereotype, and no two alike. Write each system_prompt in the second person "
    "('You are ...'), 2-3 vivid sentences, capturing exactly what earns THIS "
    "listener's next tap and what makes them bail."
)


def _ask(n: int, brief: str | None, seeds: list[str] | None, batch_idx: int) -> str:
    ask = f"Create {n} distinct audience members (batch {batch_idx})."
    if brief:
        ask += f" Target audience: {brief}."
    if seeds:
        ask += " Diversify around and beyond these archetypes: " + ", ".join(seeds) + "."
    ask += " Spread ages, genders, cities and genres widely. No duplicates or near-copies."
    return ask


async def generate_personas(
    n: int,
    brief: str | None = None,
    seed_segments: list[str] | None = None,
) -> list[Persona]:
    """Generate ``n`` genuinely distinct audience personas via the LLM.

    Returns Persona objects (kind='audience') with unique ids and a spread of
    per-agent temperatures for extra behavioural variety. Falls back to
    archetype fan-out if generation yields nothing.
    """
    n = max(1, min(n, settings.sim_panel_max))
    if seed_segments is None:
        seed_segments = [p.segment for p in load_personas("audience") if p.segment][:8]

    llm = get_llm()
    model = settings.model_for("sim")
    num_batches = (n + _BATCH - 1) // _BATCH
    sizes = [min(_BATCH, n - i * _BATCH) for i in range(num_batches)]
    sem = asyncio.Semaphore(settings.sim_synthesis_concurrency)

    async def _one_batch(bi: int, take: int) -> list:
        try:
            async with sem:
                batch = await llm.structured(
                    system=_SYS,
                    prompt=_ask(take, brief, seed_segments, bi),
                    schema=SynthBatch,
                    temperature=1.0,
                    model=model,
                )
            return list(batch.personas)
        except Exception as exc:  # noqa: BLE001 - one flaky batch shouldn't sink the run
            logger.warning("Persona synthesis batch %s failed: %s", bi, exc)
            return []

    results = await asyncio.gather(*(_one_batch(i, s) for i, s in enumerate(sizes)))

    out: list[Persona] = []
    seen: set[tuple[str, str, str]] = set()
    for sp in (p for batch in results for p in batch):
        signature = (sp.name.strip().lower(), sp.city.strip().lower(), sp.system_prompt.strip().lower())
        if signature in seen:
            continue
        seen.add(signature)
        idx = len(out)
        out.append(
            Persona(
                id=f"aud-gen-{uuid4().hex}",
                name=sp.name,
                kind="audience",
                segment=sp.segment,
                age=sp.age,
                gender=sp.gender,
                city=sp.city,
                genres=list(sp.genres),
                traits=list(sp.traits),
                # Spread temperatures 0.7..1.2 so even same-segment members vary.
                temperature=round(0.7 + (idx % 6) * 0.1, 2),
                system_prompt=sp.system_prompt,
            )
        )
        if len(out) >= n:
            break

    if len(out) < n:
        missing = n - len(out)
        logger.warning(
            "Persona synthesis returned %s/%s unique members — filling %s from archetypes",
            len(out),
            n,
            missing,
        )
        fallback = fan_out_audience(load_personas("audience"), missing)
        for p in fallback:
            out.append(p.model_copy(update={"id": f"aud-fallback-{uuid4().hex}"}))
    return out[:n]
