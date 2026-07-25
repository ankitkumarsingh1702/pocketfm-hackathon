"""The whole loop: story -> skeleton -> rewrite -> skeleton -> fidelity.

This is the thing the other four modules were built for. It closes the circle
the README draws: extract the plot, rewrite it somewhere else entirely, extract
the plot back out of the rewrite, and score how much of it survived the trip.

    python pipeline.py stories/reveal.txt --genre horror
    python pipeline.py stories/reveal.txt --all-genres
    python pipeline.py stories/reveal.txt --genre horror --no-cache

Everything lands in .cache/ under readable names, so a demo re-run is instant.
Read the numbers against the calibration band, not against 100% — calibrate.py
tells you how much of any gap is the extractor rather than the rewrite.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

from cache import cached_skeleton, cached_text
from extract import extract_clean
from genre_pack import available_packs, load_pack
from transform import transform
from verify import print_report, verify_prose


def convert(story_path: Path, genre: str, use_cache: bool = True) -> Dict[str, object]:
    """One story, one genre, all three stages. Returns the fidelity detail."""
    stem = story_path.stem
    pack = load_pack(genre)

    started = time.time()
    source = cached_skeleton(
        stem, lambda: extract_clean(story_path.read_text())[0], use_cache
    )
    print(
        f"  source skeleton   {len(source.beats)} beats, "
        f"{len(source.load_bearing_ids)} load-bearing, {len(source.causal_edges)} edges",
        file=sys.stderr,
    )

    rewritten = cached_text(
        f"{stem}__{genre}",
        lambda: transform(source, pack, verbose=True),
        use_cache,
    )
    print(f"  rewrite           {len(rewritten.split())} words", file=sys.stderr)

    # Scored against the prose, not against a skeleton re-extracted from it.
    # The round trip through a second extraction was losing exactly the nuance
    # the comparison depends on — see verify.score_prose.
    print("  verifying         checking beats against the page", file=sys.stderr)
    result = verify_prose(source, rewritten)
    result["genre"] = genre
    result["story"] = stem
    result["words"] = len(rewritten.split())
    result["seconds"] = round(time.time() - started, 1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite a story in another genre and score the plot.")
    parser.add_argument("story", help="path to a story .txt")
    parser.add_argument("--genre", help=f"one of: {', '.join(available_packs())}")
    parser.add_argument("--all-genres", action="store_true", help="run every pack")
    parser.add_argument("--no-cache", action="store_true", help="recompute everything")
    parser.add_argument("--show", action="store_true", help="print the rewritten prose too")
    args = parser.parse_args()

    story_path = Path(args.story)
    if not story_path.exists():
        print(f"no such story: {story_path}", file=sys.stderr)
        return 2

    genres = available_packs() if args.all_genres else [args.genre]
    if not args.all_genres and not args.genre:
        parser.error("give --genre or --all-genres")

    use_cache = not args.no_cache
    results: List[Dict[str, object]] = []

    for genre in genres:
        print("=" * 68)
        print(f"{story_path.stem.upper()}  ->  {genre.upper()}")
        print("=" * 68)
        result = convert(story_path, genre, use_cache)
        results.append(result)
        print()
        print_report(result, f"{story_path.stem} as {genre}")
        print(f"  {result['words']} words in {result['seconds']}s")
        if args.show:
            print()
            print((Path(__file__).parent / ".cache" / f"{story_path.stem}__{genre}.txt").read_text())
        print()

    if len(results) > 1:
        print("=" * 68)
        print("SUMMARY")
        print("=" * 68)
        for r in sorted(results, key=lambda x: -x["fidelity"]):
            print(
                f"  {r['genre']:<10} fidelity {r['fidelity']:>7.2%}   "
                f"load-bearing {r['load_bearing_recall_counts']:<7} "
                f"edges {r['edge_recall_counts']:<7} {r['words']:>5}w"
            )
        best = max(results, key=lambda x: x["fidelity"])
        worst = min(results, key=lambda x: x["fidelity"])
        print()
        print(f"  best  {best['genre']} at {best['fidelity']:.2%}")
        print(f"  worst {worst['genre']} at {worst['fidelity']:.2%}")
        print()
        print("  Compare against calibrate.py's ceiling, not against 100% — the gap")
        print("  below the ceiling is extractor noise, not plot damage.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
