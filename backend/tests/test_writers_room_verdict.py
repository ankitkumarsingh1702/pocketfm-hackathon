"""Writers Room audience verdict aggregation.

`_audience_verdict` turns per-listener reactions into the collective "Still
following" read shown on the Writers Room card. It must never collapse to a
hard 0% when the panel is genuinely (if faintly) engaged — a raw will_continue
tally does exactly that, which is the bug these tests pin down. Pure functions
over synthetic reactions, so no Neo4j and no LLM call.
"""

from __future__ import annotations

from app.lenses.writers_room import _audience_verdict, _retention_score
from app.schemas import Persona, PersonaReaction


def _persona(i: int) -> Persona:
    return Persona(
        id=f"a{i}",
        name=f"Listener {i}",
        kind="audience",
        segment="Test Segment",
        system_prompt="You are a PocketFM listener.",
    )


def _reaction(
    *,
    will_continue: bool,
    hook: int,
    drop_point: str = "middle",
    reason: str = "reason",
) -> PersonaReaction:
    return PersonaReaction(
        will_continue=will_continue,
        hook_score=hook,
        drop_point=drop_point,
        reason=reason,
        emotion="curious",
    )


def _pairs(reactions: list[PersonaReaction]):
    return [(_persona(i), r) for i, r in enumerate(reactions)]


def test_empty_panel_is_all_zero() -> None:
    v = _audience_verdict([])
    assert v.following_pct == 0.0
    assert v.avg_engagement == 0.0
    assert v.respondent_count == 0
    assert v.returning_count == 0
    assert "losing the thread" in v.comprehension


def test_unanimous_drop_still_reflects_engagement() -> None:
    """The regression: everyone says "no" but there is a real hook pulse.

    A raw will_continue tally returns a flat, broken-looking 0%. The graded
    blend must surface the engagement instead — non-zero, and equal to the
    documented 0.7*intent + 0.3*(hook/100) formula.
    """
    v = _audience_verdict(_pairs([_reaction(will_continue=False, hook=40) for _ in range(10)]))
    assert v.following_pct == 12.0  # 0.3 * 0.40 * 100
    assert v.following_pct > 0
    assert v.avg_engagement == 40.0
    assert v.returning_count == 0
    assert v.respondent_count == 10


def test_strong_episode_reads_high() -> None:
    v = _audience_verdict(_pairs([_reaction(will_continue=True, hook=80) for _ in range(8)]))
    assert v.following_pct == 94.0  # (0.7 + 0.3 * 0.80) * 100
    assert v.returning_count == 8
    assert v.respondent_count == 8
    assert "following the story" in v.comprehension


def test_following_pct_is_monotonic_in_hook() -> None:
    weak = _audience_verdict(_pairs([_reaction(will_continue=False, hook=10) for _ in range(5)]))
    strong = _audience_verdict(_pairs([_reaction(will_continue=False, hook=60) for _ in range(5)]))
    assert strong.following_pct > weak.following_pct


def test_retention_score_bounds_and_weights() -> None:
    # Continue + max hook saturates at 1.0; drop + zero hook floors at 0.0.
    assert _retention_score(_reaction(will_continue=True, hook=100)) == 1.0
    assert _retention_score(_reaction(will_continue=False, hook=0)) == 0.0
    # Intent alone contributes exactly its weight.
    assert _retention_score(_reaction(will_continue=True, hook=0)) == 0.7


def test_returning_count_counts_only_intent() -> None:
    reactions = [
        _reaction(will_continue=True, hook=70),
        _reaction(will_continue=False, hook=20),
        _reaction(will_continue=True, hook=55),
    ]
    v = _audience_verdict(_pairs(reactions))
    assert v.returning_count == 2
    assert v.respondent_count == 3
    assert v.representative_quotes  # a mix of continuers and droppers is surfaced
