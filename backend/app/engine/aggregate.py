"""Turn raw persona reactions into an ``AudienceResult``.

Pure, synchronous number-crunching: retention curve, binge rate, average hook
score, per-segment breakdown, top churn reasons and a few raw samples for the
UI. Handles the empty-input case by returning an all-zeros result.
"""

from __future__ import annotations

from app.schemas import (
    DROP_STAGES,
    SIM_ENGAGEMENTS,
    SIM_SENTIMENTS,
    AudienceReactionView,
    AudienceResult,
    AudienceSimResult,
    EngagementStat,
    Persona,
    PersonaReaction,
    SegmentStat,
    SentimentStat,
    SimSegmentStat,
    SocialReaction,
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_audience(
    pairs: list[tuple[Persona, PersonaReaction]],
    sample_size: int = 6,
) -> AudienceResult:
    """Aggregate ``(persona, reaction)`` pairs into an ``AudienceResult``."""
    total = len(pairs)
    stages = list(DROP_STAGES)

    if total == 0:
        return AudienceResult(
            total=0,
            binge_pct=0.0,
            avg_hook_score=0.0,
            drop_off_curve=[0.0] * len(stages),
            stages=stages,
            segments=[],
            top_churn_reasons=[],
            sample_reactions=[],
        )

    reactions = [r for _, r in pairs]

    binge_pct = round(100.0 * _mean([1.0 if r.will_continue else 0.0 for r in reactions]), 1)
    avg_hook_score = round(_mean([float(r.hook_score) for r in reactions]), 1)

    # Retention at each stage: fraction of listeners whose drop_point reaches
    # at least that stage. Index 0 ('hook') is always 1.0.
    drop_indices = [DROP_STAGES.index(r.drop_point) for r in reactions]
    drop_off_curve = [
        round(sum(1 for di in drop_indices if di >= i) / total, 3)
        for i in range(len(stages))
    ]

    # Per-segment breakdown.
    grouped: dict[str, list[PersonaReaction]] = {}
    for persona, reaction in pairs:
        seg = persona.segment or "General"
        grouped.setdefault(seg, []).append(reaction)
    segments = [
        SegmentStat(
            segment=seg,
            count=len(rs),
            binge_pct=round(100.0 * _mean([1.0 if r.will_continue else 0.0 for r in rs]), 1),
            avg_hook=round(_mean([float(r.hook_score) for r in rs]), 1),
        )
        for seg, rs in grouped.items()
    ]

    # Up to 5 distinct reasons from listeners who won't continue.
    top_churn_reasons: list[str] = []
    for r in reactions:
        if not r.will_continue and r.reason and r.reason not in top_churn_reasons:
            top_churn_reasons.append(r.reason)
            if len(top_churn_reasons) >= 5:
                break

    sample_reactions = [
        {
            "persona": persona.name,
            "segment": persona.segment,
            "reaction": reaction.model_dump(),
        }
        for persona, reaction in pairs[:sample_size]
    ]

    return AudienceResult(
        total=total,
        binge_pct=binge_pct,
        avg_hook_score=avg_hook_score,
        drop_off_curve=drop_off_curve,
        stages=stages,
        segments=segments,
        top_churn_reasons=top_churn_reasons,
        sample_reactions=sample_reactions,
    )


# ---------------------------------------------------------------------------
# Audience Simulator ("Living Audience") aggregation
# ---------------------------------------------------------------------------

# How much each engagement action amplifies a post — the basis of the virality
# score (0 = invisible, 100 = maximum reach/commitment).
_ENGAGEMENT_WEIGHT: dict[str, int] = {
    "scroll_past": 0,
    "like": 25,
    "comment": 45,
    "save": 55,
    "share": 80,
    "subscribe": 90,
    "binge": 100,
}


def reaction_view(persona: Persona, reaction: SocialReaction) -> AudienceReactionView:
    """Join a persona with its social reaction for the UI feed."""
    return AudienceReactionView(
        persona_id=persona.id,
        name=persona.name,
        segment=persona.segment,
        age=persona.age,
        city=persona.city,
        will_listen=reaction.will_listen,
        hook_score=int(reaction.hook_score),
        sentiment=reaction.sentiment,
        engagement=reaction.engagement,
        emotion=reaction.emotion,
        comment=reaction.comment,
        reasoning=reaction.reasoning,
        memory_note=reaction.memory_note,
    )


def aggregate_sim(
    pairs: list[tuple[Persona, SocialReaction]],
    dropped: int = 0,
    sample_size: int = 80,
) -> AudienceSimResult:
    """Fold ``(persona, SocialReaction)`` pairs into an ``AudienceSimResult``."""
    total = len(pairs)
    if total == 0:
        return AudienceSimResult(
            total=0, listen_pct=0.0, avg_hook_score=0.0, virality=0.0, dropped=dropped
        )

    reactions = [r for _, r in pairs]
    listen_pct = round(100.0 * _mean([1.0 if r.will_listen else 0.0 for r in reactions]), 1)
    avg_hook_score = round(_mean([float(r.hook_score) for r in reactions]), 1)
    virality = round(
        _mean([float(_ENGAGEMENT_WEIGHT.get(r.engagement, 0)) for r in reactions]), 1
    )

    # Sentiment distribution (kept in the canonical order for stable UI bars).
    sent_counts = {s: 0 for s in SIM_SENTIMENTS}
    for r in reactions:
        sent_counts[r.sentiment] = sent_counts.get(r.sentiment, 0) + 1
    sentiment_breakdown = [
        SentimentStat(sentiment=s, count=c, pct=round(100.0 * c / total, 1))
        for s, c in sent_counts.items()
    ]

    # Engagement funnel (strongest action each listener takes).
    eng_counts = {e: 0 for e in SIM_ENGAGEMENTS}
    for r in reactions:
        eng_counts[r.engagement] = eng_counts.get(r.engagement, 0) + 1
    engagement_funnel = [
        EngagementStat(action=e, count=c, pct=round(100.0 * c / total, 1))
        for e, c in eng_counts.items()
    ]

    # Per-segment breakdown, biggest cohorts first.
    grouped: dict[str, list[SocialReaction]] = {}
    for persona, reaction in pairs:
        grouped.setdefault(persona.segment or "General", []).append(reaction)
    segments = [
        SimSegmentStat(
            segment=seg,
            count=len(rs),
            avg_hook=round(_mean([float(r.hook_score) for r in rs]), 1),
            positive_pct=round(
                100.0 * _mean([1.0 if r.sentiment in ("love", "like") else 0.0 for r in rs]), 1
            ),
            listen_pct=round(100.0 * _mean([1.0 if r.will_listen else 0.0 for r in rs]), 1),
        )
        for seg, rs in grouped.items()
    ]
    segments.sort(key=lambda s: s.count, reverse=True)

    # Standout comments: highest hook_score among those who actually commented.
    commented = [(p, r) for p, r in pairs if (r.comment or "").strip()]
    commented.sort(key=lambda pr: pr[1].hook_score, reverse=True)
    top_comments = [reaction_view(p, r) for p, r in commented[:6]]

    # A capped sample of raw reactions for the feed (the UI has no virtualization).
    reactions_view = [reaction_view(p, r) for p, r in pairs[:sample_size]]

    return AudienceSimResult(
        total=total,
        listen_pct=listen_pct,
        avg_hook_score=avg_hook_score,
        virality=virality,
        sentiment_breakdown=sentiment_breakdown,
        engagement_funnel=engagement_funnel,
        segments=segments,
        top_comments=top_comments,
        reactions=reactions_view,
        dropped=dropped,
    )
