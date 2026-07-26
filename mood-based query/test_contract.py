"""Run this before you build on the contract. python3 test_contract.py"""

from mood_config import (
    DESTINATION_TARGETS, MOOD_STARTERS, build_clarifying_question,
    heuristic_sparsity, rank_destinations, slider_deltas_to_axis_deltas,
)
from mock_api import fake_parse, respond
from schemas import MoodAxes, MoodFingerprint

import time

ok = lambda label: print(f"  ok  {label}")


def check(label, cond):
    assert cond, f"FAILED: {label}"
    ok(label)


print("\n1. sparsity heuristic")
hero = "something that feels like a rainy Sunday after heartbreak"
sparse = "bore ho raha hoon"
print(f"     hero   {heuristic_sparsity(hero):.2f}  '{hero[:38]}...'")
print(f"     sparse {heuristic_sparsity(sparse):.2f}  '{sparse}'")
check("rich query scores low", heuristic_sparsity(hero) < 0.6)
check("sparse query scores high", heuristic_sparsity(sparse) >= 0.6)

print("\n2. three modes")
for text, expected in [
    (hero, "shelves"),
    (sparse, "clarify"),
    ("main jeene ka mann nahi karta", "safety"),
]:
    r = respond(fake_parse(text), "t", time.time())
    check(f"'{text[:30]}' -> {expected}", r.mode == expected)

print("\n3. hero query never asks a question")
check("no clarify on rich query", build_clarifying_question(fake_parse(hero)) is None)

print("\n4. shelves for the hero query")
r = respond(fake_parse(hero), "t", time.time())
check("exactly 3 shelves", len(r.shelves) == 3)
for s in r.shelves:
    print(f"     {s.label:<18} {s.destination}")
check("heartbreak leads with sit_with", r.shelves[0].destination == "sit_with")

print("\n5. explicit destination skips the question")
q = fake_parse("kuch aisa jo sona aasan kar de")
check("sleep detected", q.destination == "sleep")
check("no clarify when destination known", not q.needs_clarification)

print("\n6. slider math")
base = DESTINATION_TARGETS["sit_with"]
heavier = base.nudge(slider_deltas_to_axis_deltas({"heavier": 1.0}))
check("heavier raises weight", heavier.weight > base.weight)
check("heavier lowers valence", heavier.valence < base.valence)
check("clamped in range", -1.0 <= heavier.valence <= 1.0 and 0.0 <= heavier.weight <= 1.0)
print(f"     weight {base.weight:.2f} -> {heavier.weight:.2f} | "
      f"valence {base.valence:.2f} -> {heavier.valence:.2f}")

print("\n7. distance is sane")
d_self = base.distance(base)
d_far = DESTINATION_TARGETS["sit_with"].distance(DESTINATION_TARGETS["escape"])
d_near = DESTINATION_TARGETS["sit_with"].distance(DESTINATION_TARGETS["make_sense_of"])
check("self distance is 0", d_self < 1e-9)
check("sit_with is nearer make_sense_of than escape", d_near < d_far)
print(f"     sit_with->make_sense_of {d_near:.3f} | sit_with->escape {d_far:.3f}")

print("\n8. destination_prior reorders but never overrides")
q = fake_parse(hero).model_copy(update={"destination_prior": "escape"})
check("prior moves escape to front", rank_destinations(q)[0] == "escape")
q2 = fake_parse(hero).model_copy(
    update={"destination": "sit_with", "destination_prior": "escape"}
)
check("explicit destination beats prior", rank_destinations(q2)[0] == "sit_with")

print("\n9. fingerprint validation")
fp = MoodFingerprint(
    content_id="c1", series_id="s1", series_title="mock", arc_label="the monsoon arc",
    entry_episode=34, episode_span=(30, 41), axes=MoodAxes(valence=-0.5, catharsis=0.9),
    vibe_sentence="Slow, rain-soaked, and it does not rush you.",
    contraindicated_for=["someone who wants cheering up"], duration_min=22,
)
check("valid fingerprint accepted", fp.entry_episode == 34)
try:
    fp.model_copy(update={"entry_episode": 99}).model_validate(
        fp.model_dump() | {"entry_episode": 99}
    )
    raise AssertionError("should have rejected out-of-span entry_episode")
except Exception as e:
    check("entry_episode outside span rejected", "episode_span" in str(e))

print("\n10. starters")
check("8 starters", len(MOOD_STARTERS) == 8)
check("hero query is a starter", any(s.id == "post_breakup" for s in MOOD_STARTERS))

print("\nall contract tests passed\n")
