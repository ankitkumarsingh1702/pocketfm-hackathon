"""Offline smoke tests — no network, no LLM calls.

Verifies the pure-function aggregation math and that the persona loader returns
non-empty audience and expert rosters.
"""

from __future__ import annotations

from itertools import pairwise

from app.engine.aggregate import aggregate_audience
from app.personas.loader import load_personas
from app.schemas import DROP_STAGES, Persona, PersonaReaction, Story


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
    for earlier, later in pairwise(curve):
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


def test_fastapi_app_imports_with_all_lenses_registered():
    """Regression guard: private helper refactors must not break server boot."""
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/plan/cliffhanger/stream" in paths
    assert "/api/mdp/optimize/stream" in paths


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

    # Graded retention (0.7*intent + 0.3*hook/100), averaged over the 4 listeners:
    # (0.97 + 0.88 + 0.12 + 0.06) / 4 = 0.5075 -> 50.7%. mean of 90/60/40/20 == 52.5.
    assert verdict.following_pct == 50.7
    assert verdict.avg_engagement == 52.5
    # Raw continue-intent is surfaced alongside the graded read: 2 of 4 would return.
    assert verdict.returning_count == 2
    assert verdict.respondent_count == 4
    # ~51% following -> partial-comprehension band
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


def test_reaction_prompt_demographics_and_fingerprint_offline():
    """Edits to demographics flow into the prompt and change the cache key."""
    from app.engine.runner import build_reaction_prompt, persona_fingerprint

    persona = Persona(
        id="demo",
        name="Asha",
        kind="audience",
        segment="Metro Binge-Watcher",
        age=30,
        gender="Female",
        city="Delhi",
        genres=["thriller", "romance"],
        system_prompt="React as this listener.",
    )
    story = Story(title="Test", episode="1", text="A short script.")

    system, _user = build_reaction_prompt(persona, story)
    # The demographic preamble is prepended, natural-worded, and guarded per field.
    assert system.startswith("You are Asha, a 30-year-old woman from Delhi.")
    assert "You mostly enjoy thriller, romance." in system
    # The persona's own prompt and the fixed tail are preserved.
    assert "React as this listener." in system
    assert system.endswith(
        "Answer strictly as this listener reacting to one audio-drama episode."
    )

    # Fingerprint is a stable 16-hex digest that changes when a field changes.
    fp = persona_fingerprint(persona)
    assert len(fp) == 16
    assert fp == persona_fingerprint(persona)  # deterministic
    assert fp != persona_fingerprint(persona.model_copy(update={"city": "Mumbai"}))
