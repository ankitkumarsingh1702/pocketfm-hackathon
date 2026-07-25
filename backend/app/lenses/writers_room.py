"""Writers' Room lens — an expert panel AND the live audience react to one episode.

Every expert persona (director, editor, sound designer, historian, ...) is asked
for a structured craft critique concurrently. In parallel, a fanned-out audience
panel reacts as listeners, and their collective voice — are they following the
story? — is summarised locally into an ``AudienceVerdict`` (no extra LLM call).
The consensus blends the experts' verdicts with the audience read, also locally.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from itertools import zip_longest

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.cache import Cache
from app.engine.runner import (
    _story_hash,
    build_reaction_prompt,
    persona_fingerprint,
    run_reactions,
)
from app.graph.store import (
    canon_fingerprint,
    fetch_canon_subgraph,
    render_canon_memory,
    write_audience_verdict,
)
from app.llm.factory import get_llm
from app.personas.loader import fan_out_audience, load_personas
from app.schemas import (
    AudienceVerdict,
    ExpertFeedback,
    ExpertNote,
    Persona,
    PersonaReaction,
    Story,
    WritersRoomResult,
)

# Stages that count as "disengaged before the climax" — a listener who dropped
# here never reached the payoff, so their reason is a genuine confusion point.
_EARLY_DROP: set[str] = {"hook", "early", "middle"}


def _story_text(story: Story) -> str:
    """Render a story into a compact prompt-friendly block."""
    episode = story.episode or "-"
    return f"TITLE: {story.title} EPISODE: {episode} SCRIPT:\n{story.text}"


def _mean(values: list[float]) -> float:
    """Mean of ``values``, or ``0.0`` for an empty sequence."""
    return sum(values) / len(values) if values else 0.0


def _comprehension(following_pct: float) -> str:
    """Plain-language read on whether the audience is following the story."""
    if following_pct >= 70:
        return "The audience is following the story and staying engaged."
    if following_pct >= 45:
        return "The audience is partially following — engagement dips in the middle."
    return "The audience is losing the thread — many disengage early."


def _audience_verdict(pairs: list[tuple[Persona, PersonaReaction]]) -> AudienceVerdict:
    """Summarise the audience panel's collective voice — locally, no LLM call.

    Pure function over ``(persona, reaction)`` pairs so it can be unit-tested
    offline. All means are guarded against empty input.
    """
    reactions = [reaction for _, reaction in pairs]
    if not reactions:
        return AudienceVerdict(
            following_pct=0.0,
            avg_engagement=0.0,
            comprehension=_comprehension(0.0),
            confusion_points=[],
            representative_quotes=[],
        )

    following_pct = round(100 * _mean([1.0 if r.will_continue else 0.0 for r in reactions]), 1)
    avg_engagement = round(_mean([float(r.hook_score) for r in reactions]), 1)

    # Confusion points: distinct reasons from listeners who dropped before the climax.
    confusion_points: list[str] = []
    seen: set[str] = set()
    for r in reactions:
        if r.drop_point not in _EARLY_DROP:
            continue
        reason = r.reason.strip()
        if reason and reason.lower() not in seen:
            seen.add(reason.lower())
            confusion_points.append(reason)
        if len(confusion_points) >= 5:
            break

    # Representative quotes: a mix of continuers and droppers, up to 4 distinct.
    continuers = [r.reason.strip() for r in reactions if r.will_continue and r.reason.strip()]
    droppers = [r.reason.strip() for r in reactions if not r.will_continue and r.reason.strip()]
    quotes: list[str] = []
    seen_q: set[str] = set()
    for pair in zip_longest(continuers, droppers):
        for reason in pair:
            if reason and reason.lower() not in seen_q:
                seen_q.add(reason.lower())
                quotes.append(reason)
            if len(quotes) >= 4:
                break
        if len(quotes) >= 4:
            break

    return AudienceVerdict(
        following_pct=following_pct,
        avg_engagement=avg_engagement,
        comprehension=_comprehension(following_pct),
        confusion_points=confusion_points,
        representative_quotes=quotes,
    )


def _consensus(panel: list[ExpertFeedback], verdict: AudienceVerdict | None) -> str:
    """Blend the expert panel and audience read into one or two sentences (local)."""
    if panel:
        n = len(panel)
        verdicts = Counter(fb.note.verdict for fb in panel)
        verdict_parts = ", ".join(f"{count} {verdict_}" for verdict_, count in verdicts.most_common())
        avg_score = sum(fb.note.score for fb in panel) / n
        expert_part = f"Expert panel of {n}: {verdict_parts}; average score {avg_score:.0f}/100."
    else:
        expert_part = "No expert feedback was available for this episode."

    if verdict is None:
        return expert_part

    if verdict.following_pct >= 70:
        follow = "and are following it"
    elif verdict.following_pct >= 45:
        follow = "but are only partially following it"
    else:
        follow = "and are losing the thread"
    audience_part = (
        f" Audience voice: {verdict.following_pct:.0f}% are staying with the story {follow}."
    )
    return expert_part + audience_part


async def run_writers_room(
    story: Story,
    experts: list[Persona] | None = None,
    audience: list[Persona] | None = None,
) -> WritersRoomResult:
    """Convene the expert panel + live audience for ``story`` and summarise both.

    When ``experts``/``audience`` are supplied (the UI's edited rosters) they are
    used verbatim; otherwise the default personas from ``skills/*.yaml`` load.
    """
    llm = get_llm()
    experts = experts if experts is not None else load_personas("expert")
    expert_model = settings.model_for("experts")

    audience_base = audience if audience is not None else load_personas("audience")
    audience_personas = fan_out_audience(audience_base, min(20, settings.audience_fanout))
    audience_model = settings.model_for("audience")
    cache = Cache(settings.cache_dir)

    # Ground both panels in the story canon (knowledge-graph memory) when present.
    canon = render_canon_memory(await fetch_canon_subgraph(story))
    canon_fp = canon_fingerprint(canon)
    expert_prompt = "Critique this audio-drama episode for craft.\n" + _story_text(story)
    if canon:
        expert_prompt += "\n\nSTORY SO FAR (canon you can assume the audience knows):\n" + canon

    # Experts and the audience react concurrently — reuse the one LLM client.
    notes, pairs = await asyncio.gather(
        asyncio.gather(
            *(
                llm.structured(
                    system=e.system_prompt,
                    prompt=expert_prompt,
                    schema=ExpertNote,
                    temperature=e.temperature,
                    model=expert_model,
                )
                for e in experts
            ),
            return_exceptions=True,
        ),
        run_reactions(
            audience_personas,
            story,
            llm,
            cache,
            model=audience_model,
            canon=canon,
            canon_fp=canon_fp,
        ),
    )

    panel: list[ExpertFeedback] = []
    for expert, note in zip(experts, notes):
        if isinstance(note, Exception):
            continue  # drop experts whose call failed
        panel.append(ExpertFeedback(persona=expert.name, role=expert.role or "Expert", note=note))

    verdict = _audience_verdict(pairs)
    result = WritersRoomResult(
        panel=panel, audience=verdict, consensus=_consensus(panel, verdict)
    )
    save_simulation("writers_room", story, result.model_dump())
    if verdict is not None:
        await write_audience_verdict(
            story,
            [{
                "segment": "All listeners",
                "following_pct": verdict.following_pct,
                "avg_hook": verdict.avg_engagement,
            }],
        )
    return result


async def stream_writers_room(
    story: Story,
    experts: list[Persona] | None = None,
    audience: list[Persona] | None = None,
):
    """Stream the Writers' Room simulation as NDJSON-friendly event dicts.

    Yields one event dict per the streaming protocol as each agent finishes:
    ``run_started`` first, then ``expert_done``/``audience_done``/``*_error``
    interleaved as agents complete (fast audience models tend to land before
    the stronger expert models), then a single ``orchestrator`` summary, then
    ``done`` carrying the full persisted result. One agent's failure never
    aborts the stream — it yields an ``*_error`` event and the run continues.

    When ``experts``/``audience`` are supplied (the UI's edited rosters) they are
    used verbatim; otherwise the default personas from ``skills/*.yaml`` load.
    """
    experts = experts if experts is not None else load_personas("expert")
    audience_base = audience if audience is not None else load_personas("audience")
    audience = fan_out_audience(audience_base, min(20, settings.audience_fanout))
    llm = get_llm()
    cache = Cache(settings.cache_dir)
    expert_model = settings.model_for("experts")
    audience_model = settings.model_for("audience")

    # Ground both panels in the story canon (knowledge-graph memory) when present.
    canon = render_canon_memory(await fetch_canon_subgraph(story))
    canon_key = canon_fingerprint(canon)
    expert_prompt = "Critique this audio-drama episode for craft.\n" + _story_text(story)
    if canon:
        expert_prompt += "\n\nSTORY SO FAR (canon you can assume the audience knows):\n" + canon

    t0 = time.monotonic()

    # 1) run_started — the roster the frontend renders placeholders for.
    yield {
        "type": "run_started",
        "experts": [
            {"id": e.id, "name": e.name, "role": e.role or "Expert"} for e in experts
        ],
        "audience_count": len(audience),
        "story": {"title": story.title, "episode": story.episode},
    }

    sem = asyncio.Semaphore(settings.concurrency)
    story_hash = _story_hash(story)

    async def _expert_event(e: Persona) -> dict:
        """Return this expert's finished event dict (done or error)."""
        start = time.monotonic()
        try:
            note = await llm.structured(
                system=e.system_prompt,
                prompt=expert_prompt,
                schema=ExpertNote,
                temperature=e.temperature,
                model=expert_model,
            )
        except Exception as exc:  # noqa: BLE001 - report as an event, never abort
            return {
                "type": "expert_error",
                "id": e.id,
                "name": e.name,
                "role": e.role or "Expert",
                "error": str(exc),
            }
        return {
            "type": "expert_done",
            "id": e.id,
            "name": e.name,
            "role": e.role or "Expert",
            "note": note.model_dump(),
            "elapsed_ms": int((time.monotonic() - start) * 1000),
        }

    async def _audience_event(p: Persona) -> dict:
        """Return this listener's finished event dict (done or error), cached."""
        try:
            system, user = build_reaction_prompt(p, story, canon)
            key = cache.make_key(
                llm.name,
                audience_model or "default",
                p.id,
                persona_fingerprint(p),
                story_hash,
                canon_key,
                "reaction",
            )
            reaction: PersonaReaction | None = None
            cached = cache.get(key)
            if cached is not None:
                try:
                    reaction = PersonaReaction.model_validate(cached)
                except Exception:
                    reaction = None  # corrupt/stale entry — regenerate below
            if reaction is None:
                async with sem:
                    reaction = await llm.structured(
                        system, user, PersonaReaction, temperature=p.temperature, model=audience_model
                    )
                cache.set(key, reaction.model_dump())
        except Exception as exc:  # noqa: BLE001 - report as an event, never abort
            return {"type": "audience_error", "id": p.id, "error": str(exc)}
        return {
            "type": "audience_done",
            "id": p.id,
            "name": p.name,
            "segment": p.segment,
            "reaction": reaction.model_dump(),
        }

    # One task per agent; audience + experts race together.
    tasks = [asyncio.ensure_future(_expert_event(e)) for e in experts]
    tasks += [asyncio.ensure_future(_audience_event(p)) for p in audience]

    audience_by_id = {p.id: p for p in audience}
    expert_notes: dict[str, ExpertNote] = {}
    pairs: list[tuple[Persona, PersonaReaction]] = []

    # 2) Interleave per-agent events as each finishes; accumulate for the summary.
    for fut in asyncio.as_completed(tasks):
        event = await fut
        etype = event.get("type")
        if etype == "expert_done":
            try:
                expert_notes[event["id"]] = ExpertNote.model_validate(event["note"])
            except Exception:
                pass
        elif etype == "audience_done":
            persona = audience_by_id.get(event["id"])
            if persona is not None:
                try:
                    pairs.append(
                        (persona, PersonaReaction.model_validate(event["reaction"]))
                    )
                except Exception:
                    pass
        yield event

    # 3) orchestrator — aggregated audience voice + expert panel summary.
    verdict = _audience_verdict(pairs)
    # Panel ordered by the original experts order for stable rendering.
    panel = [
        ExpertFeedback(persona=e.name, role=e.role or "Expert", note=expert_notes[e.id])
        for e in experts
        if e.id in expert_notes
    ]
    consensus = _consensus(panel, verdict)
    verdict_counts = Counter(fb.note.verdict for fb in panel)
    avg_score = sum(fb.note.score for fb in panel) / len(panel) if panel else 0.0
    yield {
        "type": "orchestrator",
        "audience": verdict.model_dump(),
        "consensus": consensus,
        "expert_summary": {
            "count": len(panel),
            "avg_score": round(avg_score, 1),
            "verdicts": {
                "strong": verdict_counts.get("strong", 0),
                "mixed": verdict_counts.get("mixed", 0),
                "weak": verdict_counts.get("weak", 0),
            },
        },
    }

    # 4) done — the full persisted result, matching the non-streaming route.
    result = WritersRoomResult(panel=panel, audience=verdict, consensus=consensus)
    save_simulation("writers_room", story, result.model_dump())
    await write_audience_verdict(
        story,
        [{
            "segment": "All listeners",
            "following_pct": verdict.following_pct,
            "avg_hook": verdict.avg_engagement,
        }],
    )
    yield {
        "type": "done",
        "result": result.model_dump(),
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
    }
