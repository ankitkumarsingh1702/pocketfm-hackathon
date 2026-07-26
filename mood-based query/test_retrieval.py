"""Retrieval layer tests. python3 test_retrieval.py"""

import time

import numpy as np

from contraindications import derive_content_codes, derive_listener_codes
from embeddings import HashingEmbedder
from entrypoint import resolve_entry
from parser import heuristic_parse as fake_parse
from mood_config import DESTINATION_TARGETS
from retrieval import Retriever, situation_tags
from schemas import MoodAxes, MoodQuery, Situation
from search import MoodSearchEngine
from seed_catalog import build_seed_catalog
from store import MoodStore

HERO = "something that feels like a rainy Sunday after heartbreak"


def check(label, cond):
    assert cond, f"FAILED: {label}"
    print(f"  ok  {label}")


print("\nbuilding index")
t0 = time.time()
store = MoodStore(HashingEmbedder())
store.add(build_seed_catalog())
engine = MoodSearchEngine(store)
print(f"     {len(store)} arcs, {len({f.series_id for f in store.fingerprints})} series, "
      f"{int((time.time() - t0) * 1000)}ms")

print("\n1. axis distance matches the schema method exactly")
target = DESTINATION_TARGETS["sit_with"]
vec = store.axis_distances(target)
manual = np.array([fp.axes.distance(target) for fp in store.fingerprints])
check("vectorised == MoodAxes.distance", np.allclose(vec, manual, atol=1e-6))

print("\n2. hard filters actually bind")
mask = store.axis_mask({"arousal": (0.0, 0.25)})
arousals = [fp.axes.arousal for fp, m in zip(store.fingerprints, mask) if m]
check("every survivor respects the bound", all(a <= 0.25 + 1e-6 for a in arousals))
check("filter is not a no-op", int(mask.sum()) < len(store))

print("\n3. contraindication codes derive correctly")
check("breakup phrase -> code",
      "breakup" in derive_content_codes(["someone going through a breakup"]))
check("cheering phrase -> code",
      "wants_cheering" in derive_content_codes(["someone who wants cheering up"]))
q = fake_parse(HERO)
check("hero query flags listener as breakup", "breakup" in derive_listener_codes(q))

print("\n4. TRAP AVOIDANCE — the one that matters")
retr = Retriever(store)
blocked = dict(retr.debug_blocked(q))
trap_ids = {f"trap_{i}" for i in range(3)}
check("all 3 traps blocked", trap_ids <= set(blocked))
for tid in sorted(trap_ids):
    print(f"     {tid} blocked ({blocked[tid]})")

shelves = engine.search(q)
surfaced = {c.content_id for s in shelves for c in s.results}
check("no trap reaches any shelf", not (surfaced & trap_ids))

print("\n5. traps DO surface when they are not contraindicated")
neutral = MoodQuery(raw_text="something rainy and slow", felt_state=[], intensity=0.3)
check("neutral listener has no block codes", not derive_listener_codes(neutral))
check("traps not blocked for a neutral listener",
      not (trap_ids & set(dict(Retriever(store).debug_blocked(neutral)))))
print("     -> the block is state-dependent, not a blacklist")

print("\n6. shelves for the hero query")
check("3 shelves", len(shelves) == 3)
for s in shelves:
    ids = [c.series_title[:26] for c in s.results]
    print(f"     {s.label:<14} {s.destination:<14} {len(s.results)} results  {ids[0]}")
check("every shelf full", all(len(s.results) == 3 for s in shelves))
check("no empty shelf shipped", all(s.results for s in shelves))

print("\n7. one arc per series inside a shelf")
for s in shelves:
    titles = [c.series_title for c in s.results]
    check(f"{s.destination}: no duplicate series", len(titles) == len(set(titles)))

print("\n8. diversity — results are not near-identical")
for s in shelves:
    rows = [i for i, fp in enumerate(store.fingerprints)
            if fp.content_id in {c.content_id for c in s.results}]
    pairs = [float(np.linalg.norm(store._axes[a] - store._axes[b]))
             for i, a in enumerate(rows) for b in rows[i + 1:]]
    check(f"{s.destination}: mean pairwise spread {np.mean(pairs):.3f} > 0.05",
          np.mean(pairs) > 0.05)

print("\n9. destination filters shape the shelves")
sleep_q = fake_parse("kuch aisa jo sona aasan kar de")
sleep_shelf, _ = engine.build_shelf(sleep_q, "sleep")
rows = [fp for fp in store.fingerprints
        if fp.content_id in {c.content_id for c in sleep_shelf.results}]
check("sleep shelf is all low-arousal", all(fp.axes.arousal <= 0.25 for fp in rows))
print(f"     arousals: {[round(fp.axes.arousal, 2) for fp in rows]}")

print("\n10. situation tags extracted")
tags = situation_tags(MoodQuery(
    raw_text="x", situation=Situation(weather="rain", time_of_day="night", solitude="alone")))
check("rain + night + small-room", {"rain", "night", "small-room"} <= set(tags))

print("\n11. entry points — must be VARIED, not all episode 1")
eps = []
for s in shelves:
    for c in s.results:
        eps.append(c.entry_episode)
        print(f"     {c.entry_label}")
check("not everything collapsed to ep 1", len(set(eps)) > 1)
check("at least one genuinely deep entry", max(eps) > 12)
print(f"     episodes: {sorted(eps)}")

cand = retr.retrieve(q, "sit_with", DESTINATION_TARGETS["sit_with"], k=3)
check("labels are human", all(
    resolve_entry(c, store, DESTINATION_TARGETS["sit_with"]).label.startswith(("Start at Ep", "Start from"))
    for c in cand))
swaps = sum(resolve_entry(c, store, DESTINATION_TARGETS["sit_with"]).swapped_for_earlier
            for c in cand)
check("swap is selective, not universal", swaps < len(cand))
print(f"     earlier-arc swaps: {swaps}/{len(cand)}")

print("\n12. refine — EVERY slider must visibly move results")
from mood_config import SLIDER_AXIS_MAP
base = shelves[0]
base_ids = {c.content_id for c in base.results}
churn_total = 0
for name in SLIDER_AXIS_MAP:
    for v in (1.0, -1.0):
        refined = engine.refine(q, base.destination, base.target_axes, {name: v})
        check_ids = {c.content_id for c in refined.results}
        churn = len(check_ids - base_ids)
        churn_total += churn
        check(f"{name} {v:+.0f} changes the shelf ({churn}/3 new)", churn > 0)
        assert refined.destination == base.destination, "slider must not change intent"
print(f"     mean churn per full drag: {churn_total / 8:.2f}/3")
check("intent never changes under refine", True)

print("\n13. latency")
t = time.time()
for _ in range(20):
    engine.search(q)
per = (time.time() - t) / 20 * 1000
check(f"full 3-shelf search {per:.1f}ms < 150ms (heuristic reranker)", per < 150)

t = time.time()
for _ in range(50):
    store.axis_distances(target)
print(f"     raw axis scan over {len(store)} arcs: "
      f"{(time.time() - t) / 50 * 1e6:.0f}us  <- why no vector DB")

print("\n14. persistence round-trips")
store.save("/tmp/moodstore")
loaded = MoodStore.load("/tmp/moodstore", HashingEmbedder())
check("same length", len(loaded) == len(store))
check("same vectors", np.allclose(loaded._axes, store._axes))
check("codes rebuilt", loaded.codes == store.codes)

print("\n15. degrades instead of failing")
empty = MoodStore(HashingEmbedder())
check("empty store returns no shelves", MoodSearchEngine(empty).search(q) == [])
impossible = MoodQuery(raw_text="x", language="xx")
check("impossible filter returns nothing, no crash",
      Retriever(store).retrieve(impossible, "sit_with") == [])

print("\nall retrieval tests passed\n")
