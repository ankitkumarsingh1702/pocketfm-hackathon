"""Calibrate the verifier BEFORE building the transform.

A fidelity number you haven't calibrated is unfalsifiable. Two checks make it
trustworthy:

  CEILING  extract the same story twice, independently, and score one against
           the other. The plot is identical, so anything below ~0.90 is the
           extractor being noisy, not the rewrite being bad.

  FLOOR    score two genuinely different stories against each other. Anything
           above ~0.30 means the aligner is matching on generic story shape
           ("someone wants something, someone refuses") rather than on content.

Only once the ceiling is high and the floor is low does a mid-range score for a
real rewrite mean anything.

    python calibrate.py                 # uses stories/*.txt
    python calibrate.py --no-cache      # ignore cached skeletons
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

from cache import cached_skeleton
from extract import extract_clean, extract_skeleton, lint_skeleton
from models import StorySkeleton
from verify import align, print_report, score

STORIES_DIR = Path(__file__).parent / "stories"

CEILING_TARGET = 0.90
FLOOR_TARGET = 0.30


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true", help="re-extract everything")
    args = parser.parse_args()
    use_cache = not args.no_cache

    story_paths = sorted(STORIES_DIR.glob("*.txt"))
    if len(story_paths) < 2:
        print(f"need at least 2 stories in {STORIES_DIR}", file=sys.stderr)
        return 2

    print("=" * 68)
    print("EXTRACTION")
    print("=" * 68)

    skeletons: Dict[str, StorySkeleton] = {}
    dirty: List[str] = []

    for path in story_paths:
        name = path.stem
        words = len(path.read_text().split())
        started = time.time()
        skeleton = cached_skeleton(name, lambda p=path: extract_clean(p.read_text())[0], use_cache)
        # Re-lint rather than reusing extract_clean's verdict, so cached runs report too.
        remaining = lint_skeleton(skeleton)
        skeletons[name] = skeleton

        status = "clean" if not remaining else f"{len(remaining)} lint issue(s)"
        print(
            f"{name:<12} {words:>5}w  ->  {len(skeleton.beats):>2} beats, "
            f"{len(skeleton.load_bearing_ids):>2} load-bearing, "
            f"{len(skeleton.causal_edges):>2} edges   [{status}]  {time.time() - started:.1f}s"
        )
        if remaining:
            dirty.append(name)
            for c in remaining:
                print(f"             - {c}")

    print()
    print("=" * 68)
    print("CEILING CHECK  (same story, extracted twice -- want >= %.2f)" % CEILING_TARGET)
    print("=" * 68)

    ceiling_name = story_paths[0].stem
    source = skeletons[ceiling_name]
    second = cached_skeleton(
        f"{ceiling_name}__second_pass",
        lambda: extract_skeleton(STORIES_DIR.joinpath(f"{ceiling_name}.txt").read_text()),
        use_cache,
    )
    ceiling = score(source, second, align(source, second))
    print_report(ceiling, f"{ceiling_name} vs itself")
    ceiling_value = ceiling["fidelity"]

    print()
    print("=" * 68)
    print("FLOOR CHECK  (two different stories -- want <= %.2f)" % FLOOR_TARGET)
    print("=" * 68)

    a, b = story_paths[0].stem, story_paths[1].stem
    floor = score(skeletons[a], skeletons[b], align(skeletons[a], skeletons[b]))
    print_report(floor, f"{a} vs {b}")
    floor_value = floor["fidelity"]

    print()
    print("=" * 68)
    print("VERDICT")
    print("=" * 68)

    ok = True

    if ceiling_value >= CEILING_TARGET:
        print(f"  PASS  ceiling {ceiling_value:.2%} >= {CEILING_TARGET:.0%}")
    else:
        ok = False
        print(f"  FAIL  ceiling {ceiling_value:.2%} < {CEILING_TARGET:.0%}")
        print("        The extractor is not stable across runs, so the fidelity score")
        print("        measures extractor noise as much as it measures plot drift.")
        print("        Fix: look at which beats failed to align. Usually the two passes")
        print("        chose different granularity -- one merged two beats the other")
        print("        split. Tighten the `beats` Field description in models.py with an")
        print("        explicit rule for when to split (e.g. one beat per change of")
        print("        who-holds-the-advantage), not the system prompt.")

    if floor_value <= FLOOR_TARGET:
        print(f"  PASS  floor   {floor_value:.2%} <= {FLOOR_TARGET:.0%}")
    else:
        ok = False
        print(f"  FAIL  floor   {floor_value:.2%} > {FLOOR_TARGET:.0%}")
        print("        The aligner is matching generic story shape rather than content.")
        print("        Fix: the abstraction level is too high -- beats like 'the")
        print("        protagonist encounters an obstacle' match anything. Push the")
        print("        `action` Field description toward naming the specific thing")
        print("        transacted (information, permission, an object, a promise) while")
        print("        still avoiding proper nouns. Strengthen the strictness paragraph")
        print("        in ALIGN_SYSTEM if that alone doesn't separate them.")

    if dirty:
        ok = False
        print(f"  FAIL  lint    {', '.join(dirty)} still leaking after one retry")
        print("        A flavoured skeleton limits how far the transform can move.")
        print("        Fix: add the offending words to GENRE_WORDS and sharpen the")
        print("        good/bad examples in the Beat.action Field description.")

    print()
    if ok:
        margin = ceiling_value - floor_value
        print(f"  Metric is trustworthy. Separation: {margin:.2%}.")
        print("  Go build the transform stage.")
    else:
        print("  Do NOT start the transform stage yet. Fix the above first --")
        print("  everything downstream inherits this measurement error.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
