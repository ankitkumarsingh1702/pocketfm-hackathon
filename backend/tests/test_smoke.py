"""Offline smoke tests — no network, no LLM calls.

Verifies the pure-function aggregation math and that the persona loader returns
non-empty audience and expert rosters.
"""

from __future__ import annotations

from app.engine.aggregate import aggregate_audience
from app.personas.loader import load_personas
from app.schemas import DROP_STAGES, Persona, PersonaReaction


def _persona(i: int, segment: str) -> Persona:
    return Persona(
        id=f"t{i}",
        name=f"Test {i}",
        kind="audience",
        segment=segment,
        system_prompt="React as this listener.",
    )


def _reaction(
    will_continue: bool,
    hook: int,
    drop_point: str,
    reason: str = "reason",
    emotion: str = "curious",
) -> PersonaReaction:
    return PersonaReaction(
        will_continue=will_continue,
        hook_score=hook,
        drop_point=drop_point,
        reason=reason,
        emotion=emotion,
    )


def test_aggregate_binge_pct_and_monotonic_curve():
    pairs: list[tuple[Persona, PersonaReaction]] = [
        (_persona(0, "Metro"), _reaction(True, 90, "finished")),
        (_persona(1, "Metro"), _reaction(True, 70, "cliffhanger")),
        (_persona(2, "Town"), _reaction(False, 40, "middle")),
        (_persona(3, "Town"), _reaction(False, 20, "hook")),
    ]

    result = aggregate_audience(pairs, sample_size=2)

    assert result.total == 4
    # 2 of 4 listeners continue -> 50%
    assert result.binge_pct == 50.0
    # mean of 90, 70, 40, 20 == 55
    assert abs(result.avg_hook_score - 55.0) < 1.0

    curve = result.drop_off_curve
    assert len(curve) == len(DROP_STAGES)
    # Everyone survives the very first stage (index 0), so retention starts at 1.0
    assert curve[0] == 1.0
    # Retention must be monotonically non-increasing across stages
    for earlier, later in zip(curve, curve[1:]):
        assert later <= earlier

    assert len(result.sample_reactions) == 2


def test_aggregate_empty_is_safe():
    result = aggregate_audience([])
    assert result.total == 0
    assert result.binge_pct == 0
    assert result.avg_hook_score == 0
    assert all(v == 0 for v in result.drop_off_curve)


def test_load_personas_non_empty():
    audience = load_personas("audience")
    experts = load_personas("expert")
    assert isinstance(audience, list) and len(audience) > 0
    assert isinstance(experts, list) and len(experts) > 0


def test_audience_verdict_math_offline():
    """The Writers' Room audience-voice helper is a pure, network-free function."""
    from app.lenses.writers_room import _audience_verdict

    pairs: list[tuple[Persona, PersonaReaction]] = [
        (_persona(0, "Metro"), _reaction(True, 90, "finished", reason="loved the ending")),
        (_persona(1, "Metro"), _reaction(True, 60, "climax", reason="the twist got me")),
        (_persona(2, "Town"), _reaction(False, 40, "middle", reason="lost me in the middle")),
        (_persona(3, "Town"), _reaction(False, 20, "hook", reason="slow open, tuned out")),
    ]

    verdict = _audience_verdict(pairs)

    # 2 of 4 listeners continue -> 50%; mean of 90/60/40/20 == 52.5
    assert verdict.following_pct == 50.0
    assert verdict.avg_engagement == 52.5
    # 50% following -> partial-comprehension band
    assert "partially following" in verdict.comprehension

    # Confusion points come only from pre-climax droppers (middle + hook here).
    assert isinstance(verdict.confusion_points, list)
    assert "lost me in the middle" in verdict.confusion_points
    assert "slow open, tuned out" in verdict.confusion_points
    assert len(verdict.confusion_points) <= 5

    # Representative quotes mix continuers and droppers, up to 4 distinct.
    assert isinstance(verdict.representative_quotes, list)
    assert 0 < len(verdict.representative_quotes) <= 4


def test_audience_verdict_empty_is_safe():
    """No reactions -> zeros and empty lists, never a divide-by-zero."""
    from app.lenses.writers_room import _audience_verdict

    verdict = _audience_verdict([])
    assert verdict.following_pct == 0.0
    assert verdict.avg_engagement == 0.0
    assert verdict.confusion_points == []
    assert verdict.representative_quotes == []
    assert isinstance(verdict.comprehension, str) and verdict.comprehension
