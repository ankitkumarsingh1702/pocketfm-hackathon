"""Mood-First Search — retrieval-layer checks.

Ported from the feature's standalone ``test_retrieval.py``; assertions are
unchanged. The one edit is persistence, which now round-trips through a temp
directory instead of a hardcoded ``/tmp`` path so it runs on any OS.
"""

import os
import tempfile
import time

import numpy as np

from app.mood.contraindications import derive_content_codes, derive_listener_codes
from app.mood.embeddings import HashingEmbedder
from app.mood.entrypoint import resolve_entry
from app.mood.mood_config import DESTINATION_TARGETS, SLIDER_AXIS_MAP
from app.mood.parser import heuristic_parse as fake_parse
from app.mood.retrieval import Retriever, situation_tags
from app.mood.schemas import MoodAxes, MoodQuery, Situation
from app.mood.search import MoodSearchEngine
from app.mood.seed_catalog import build_seed_catalog
from app.mood.store import MoodStore

HERO = "something that feels like a rainy Sunday after heartbreak"


def _check(label, cond):
    assert cond, f"FAILED: {label}"
    print(f"  ok  {label}")


def test_mood_retrieval():
    print("\nbuilding index")
    store = MoodStore(HashingEmbedder())
    store.add(build_seed_catalog())
    engine = MoodSearchEngine(store)

    print("\n1. axis distance matches the schema method exactly")
    target = DESTINATION_TARGETS["sit_with"]
    vec = store.axis_distances(target)
    manual = np.array([fp.axes.distance(target) for fp in store.fingerprints])
    _check("vectorised == MoodAxes.distance", np.allclose(vec, manual, atol=1e-6))

    print("\n2. hard filters actually bind")
    mask = store.axis_mask({"arousal": (0.0, 0.25)})
    arousals = [fp.axes.arousal for fp, m in zip(store.fingerprints, mask) if m]
    _check("every survivor respects the bound", all(a <= 0.25 + 1e-6 for a in arousals))
    _check("filter is not a no-op", int(mask.sum()) < len(store))

    print("\n3. contraindication codes derive correctly")
    _check(
        "breakup phrase -> code",
        "breakup" in derive_content_codes(["someone going through a breakup"]),
    )
    _check(
        "cheering phrase -> code",
        "wants_cheering" in derive_content_codes(["someone who wants cheering up"]),
    )
    q = fake_parse(HERO)
    _check("hero query flags listener as breakup", "breakup" in derive_listener_codes(q))

    print("\n4. TRAP AVOIDANCE — the one that matters")
    retr = Retriever(store)
    blocked = dict(retr.debug_blocked(q))
    trap_ids = {f"trap_{i}" for i in range(3)}
    _check("all 3 traps blocked", trap_ids <= set(blocked))

    shelves = engine.search(q)
    surfaced = {c.content_id for s in shelves for c in s.results}
    _check("no trap reaches any shelf", not (surfaced & trap_ids))

    print("\n5. traps DO surface when they are not contraindicated")
    neutral = MoodQuery(raw_text="something rainy and slow", felt_state=[], intensity=0.3)
    _check("neutral listener has no block codes", not derive_listener_codes(neutral))
    _check(
        "traps not blocked for a neutral listener",
        not (trap_ids & set(dict(Retriever(store).debug_blocked(neutral)))),
    )

    print("\n6. shelves for the hero query")
    _check("3 shelves", len(shelves) == 3)
    _check("every shelf full", all(len(s.results) == 3 for s in shelves))
    _check("no empty shelf shipped", all(s.results for s in shelves))

    print("\n7. one arc per series inside a shelf")
    for s in shelves:
        titles = [c.series_title for c in s.results]
        _check(f"{s.destination}: no duplicate series", len(titles) == len(set(titles)))

    print("\n8. diversity — results are not near-identical")
    for s in shelves:
        rows = [
            i for i, fp in enumerate(store.fingerprints)
            if fp.content_id in {c.content_id for c in s.results}
        ]
        pairs = [
            float(np.linalg.norm(store._axes[a] - store._axes[b]))
            for i, a in enumerate(rows) for b in rows[i + 1:]
        ]
        _check(f"{s.destination}: mean pairwise spread > 0.05", np.mean(pairs) > 0.05)

    print("\n9. destination filters shape the shelves")
    sleep_q = fake_parse("kuch aisa jo sona aasan kar de")
    sleep_shelf, _ = engine.build_shelf(sleep_q, "sleep")
    rows = [
        fp for fp in store.fingerprints
        if fp.content_id in {c.content_id for c in sleep_shelf.results}
    ]
    _check("sleep shelf is all low-arousal", all(fp.axes.arousal <= 0.25 for fp in rows))

    print("\n10. situation tags extracted")
    tags = situation_tags(
        MoodQuery(
            raw_text="x",
            situation=Situation(weather="rain", time_of_day="night", solitude="alone"),
        )
    )
    _check("rain + night + small-room", {"rain", "night", "small-room"} <= set(tags))

    print("\n11. entry points — must be VARIED, not all episode 1")
    eps = []
    for s in shelves:
        for c in s.results:
            eps.append(c.entry_episode)
    _check("not everything collapsed to ep 1", len(set(eps)) > 1)
    _check("at least one genuinely deep entry", max(eps) > 12)

    cand = retr.retrieve(q, "sit_with", DESTINATION_TARGETS["sit_with"], k=3)
    _check(
        "labels are human",
        all(
            resolve_entry(c, store, DESTINATION_TARGETS["sit_with"]).label.startswith(
                ("Start at track", "Start from")
            )
            for c in cand
        ),
    )
    swaps = sum(
        resolve_entry(c, store, DESTINATION_TARGETS["sit_with"]).swapped_for_earlier
        for c in cand
    )
    _check("swap is selective, not universal", swaps < len(cand))

    print("\n12. refine — EVERY slider must visibly move results")
    base = shelves[0]
    base_ids = {c.content_id for c in base.results}
    for name in SLIDER_AXIS_MAP:
        for v in (1.0, -1.0):
            refined = engine.refine(q, base.destination, base.target_axes, {name: v})
            check_ids = {c.content_id for c in refined.results}
            churn = len(check_ids - base_ids)
            _check(f"{name} {v:+.0f} changes the shelf ({churn}/3 new)", churn > 0)
            assert refined.destination == base.destination, "slider must not change intent"

    print("\n13. latency")
    t = time.time()
    for _ in range(20):
        engine.search(q)
    per = (time.time() - t) / 20 * 1000
    _check(f"full 3-shelf search {per:.1f}ms < 150ms (heuristic reranker)", per < 150)

    print("\n14. persistence round-trips")
    path = os.path.join(tempfile.mkdtemp(), "moodstore")
    store.save(path)
    loaded = MoodStore.load(path, HashingEmbedder())
    _check("same length", len(loaded) == len(store))
    _check("same vectors", np.allclose(loaded._axes, store._axes))
    _check("codes rebuilt", loaded.codes == store.codes)

    print("\n15. degrades instead of failing")
    empty = MoodStore(HashingEmbedder())
    _check("empty store returns no shelves", MoodSearchEngine(empty).search(q) == [])
    impossible = MoodQuery(raw_text="x", language="xx")
    _check(
        "impossible filter returns nothing, no crash",
        Retriever(store).retrieve(impossible, "sit_with") == [],
    )

    print("\nall retrieval tests passed\n")
