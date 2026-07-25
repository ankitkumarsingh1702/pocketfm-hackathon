"""Writers' Room lens — an expert panel AND the live audience react to one episode.

Every expert persona (director, editor, sound designer, historian, ...) is asked
for a structured craft critique concurrently. In parallel, a fanned-out audience
panel reacts as listeners, and their collective voice — are they following the
story? — is summarised locally into an ``AudienceVerdict`` (no extra LLM call).
The consensus blends the experts' verdicts with the audience read, also locally.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from itertools import zip_longest

from app.config import settings
from app.db.firestore import save_simulation
from app.engine.cache import Cache
from app.engine.runner import run_reactions
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


async def run_writers_room(story: Story) -> WritersRoomResult:
    """Convene the expert panel + live audience for ``story`` and summarise both."""
    llm = get_llm()
    experts = load_personas("expert")
    expert_prompt = "Critique this audio-drama episode for craft.\n" + _story_text(story)
    expert_model = settings.model_for("experts")

    audience_personas = fan_out_audience(
        load_personas("audience"), min(20, settings.audience_fanout)
    )
    audience_model = settings.model_for("audience")
    cache = Cache(settings.cache_dir)

    # Experts and the audience react concurrently — reuse the one LLM client.
    notes, pairs = await asyncio.gather(
        asyncio.gather(
            *(
                llm.structured(
                    system=e.system_prompt,
                    prompt=expert_prompt,
                    schema=ExpertNote,
                    model=expert_model,
                )
                for e in experts
            ),
            return_exceptions=True,
        ),
        run_reactions(audience_personas, story, llm, cache, model=audience_model),
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
    return result
