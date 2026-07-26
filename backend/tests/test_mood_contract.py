"""Mood-First Search — frozen-contract checks.

Ported from the feature's standalone ``test_contract.py``; the assertions are
unchanged, wrapped in a pytest test so the studio suite runs them. Run with
``uv run pytest tests/test_mood_contract.py -s`` for the printed trace.
"""

import time

from app.mood.mock_api import fake_parse, respond
from app.mood.mood_config import (
    DESTINATION_TARGETS,
    MOOD_STARTERS,
    build_clarifying_question,
    heuristic_sparsity,
    rank_destinations,
    slider_deltas_to_axis_deltas,
)
from app.mood.schemas import MoodAxes, MoodFingerprint


def _check(label, cond):
    assert cond, f"FAILED: {label}"
    print(f"  ok  {label}")


def test_mood_contract():
    hero = "something that feels like a rainy Sunday after heartbreak"
    sparse = "bore ho raha hoon"

    print("\n1. sparsity heuristic")
    _check("rich query scores low", heuristic_sparsity(hero) < 0.6)
    _check("sparse query scores high", heuristic_sparsity(sparse) >= 0.6)

    print("\n2. three modes")
    for text, expected in [
        (hero, "shelves"),
        (sparse, "clarify"),
        ("main jeene ka mann nahi karta", "safety"),
    ]:
        r = respond(fake_parse(text), "t", time.time())
        _check(f"'{text[:30]}' -> {expected}", r.mode == expected)

    print("\n3. hero query never asks a question")
    _check("no clarify on rich query", build_clarifying_question(fake_parse(hero)) is None)

    print("\n4. shelves for the hero query")
    r = respond(fake_parse(hero), "t", time.time())
    _check("exactly 3 shelves", len(r.shelves) == 3)
    _check("heartbreak leads with sit_with", r.shelves[0].destination == "sit_with")

    print("\n5. explicit destination skips the question")
    q = fake_parse("kuch aisa jo sona aasan kar de")
    _check("sleep detected", q.destination == "sleep")
    _check("no clarify when destination known", not q.needs_clarification)

    print("\n6. slider math")
    base = DESTINATION_TARGETS["sit_with"]
    heavier = base.nudge(slider_deltas_to_axis_deltas({"heavier": 1.0}))
    _check("heavier raises weight", heavier.weight > base.weight)
    _check("heavier lowers valence", heavier.valence < base.valence)
    _check(
        "clamped in range",
        -1.0 <= heavier.valence <= 1.0 and 0.0 <= heavier.weight <= 1.0,
    )

    print("\n7. distance is sane")
    d_self = base.distance(base)
    d_far = DESTINATION_TARGETS["sit_with"].distance(DESTINATION_TARGETS["escape"])
    d_near = DESTINATION_TARGETS["sit_with"].distance(DESTINATION_TARGETS["make_sense_of"])
    _check("self distance is 0", d_self < 1e-9)
    _check("sit_with is nearer make_sense_of than escape", d_near < d_far)

    print("\n8. destination_prior reorders but never overrides")
    q = fake_parse(hero).model_copy(update={"destination_prior": "escape"})
    _check("prior moves escape to front", rank_destinations(q)[0] == "escape")
    q2 = fake_parse(hero).model_copy(
        update={"destination": "sit_with", "destination_prior": "escape"}
    )
    _check("explicit destination beats prior", rank_destinations(q2)[0] == "sit_with")

    print("\n9. fingerprint validation")
    fp = MoodFingerprint(
        content_id="c1", series_id="s1", series_title="mock", arc_label="the monsoon arc",
        entry_episode=34, episode_span=(30, 41), axes=MoodAxes(valence=-0.5, catharsis=0.9),
        vibe_sentence="Slow, rain-soaked, and it does not rush you.",
        contraindicated_for=["someone who wants cheering up"], duration_min=22,
    )
    _check("valid fingerprint accepted", fp.entry_episode == 34)
    try:
        MoodFingerprint.model_validate(fp.model_dump() | {"entry_episode": 99})
        raise AssertionError("should have rejected out-of-span entry_episode")
    except Exception as e:  # noqa: BLE001 - we assert on the message
        _check("entry_episode outside span rejected", "episode_span" in str(e))

    print("\n10. starters")
    _check("8 starters", len(MOOD_STARTERS) == 8)
    _check("hero query is a starter", any(s.id == "post_breakup" for s in MOOD_STARTERS))

    print("\nall contract tests passed\n")
