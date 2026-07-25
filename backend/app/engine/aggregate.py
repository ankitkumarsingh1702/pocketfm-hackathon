"""Turn raw persona reactions into an ``AudienceResult``.

Pure, synchronous number-crunching: retention curve, binge rate, average hook
score, per-segment breakdown, top churn reasons and a few raw samples for the
UI. Handles the empty-input case by returning an all-zeros result.
"""

from __future__ import annotations

from app.schemas import (
    DROP_STAGES,
    AudienceResult,
    Persona,
    PersonaReaction,
    SegmentStat,
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
