"""
Mood-First Search — catalog sources.

Produces `SourceSeries` for catalog_ingest. Two adapters, and the choice
between them is a real trade you should make deliberately.

LIBRIVOX  (verified against the live API)
    https://librivox.org/api/feed/audiobooks/?format=json&limit=100&offset=N

    + Real human-written summaries (Wikipedia / volunteer prose). Satisfies the
      no-LLM-wrote-this rule, which is the thing that keeps the eval honest.
    + `num_sections` is a real chapter count, so episode spans are real rather
      than invented.
    + Free, public-domain, no scraping, no ToS question, works right now.
    - WRONG REGISTER. It is Victorian and classical literature in English.
      Nobody's "rainy Sunday after heartbreak" is answered by Boethius. It
      proves the fingerprinter works on real text; it does not make a
      convincing Pocket FM catalog.

LOCAL  (hand-collected)
    Whatever you curate into JSON — real Pocket FM listings, Kuku FM, your own
    partner data. Right register, needs an hour of collecting.

RECOMMENDED SPLIT: hand-collect 40-60 for the demo and the eval set; use
LibriVox to pad the long tail so shelves are not thin. Never let padding into
the eval set — the numbers only mean something on the curated half.

Descriptions arrive as HTML with entities and markup; `clean_html` handles it.
Left unstripped, tags leak into `vibe_sentence` and the fingerprinter starts
describing the mood of a `<br />`.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

from app.mood.catalog_ingest import SourceArc, SourceSeries

LIBRIVOX_API = "https://librivox.org/api/feed/audiobooks/"
USER_AGENT = "mood-first-search/0.1 (hackathon; contact via project owner)"


def clean_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", raw or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\(Summary (?:from|by)[^)]*\)", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# LibriVox
# --------------------------------------------------------------------------


def _fetch(offset: int, limit: int, timeout: int = 20) -> list[dict]:
    params = urllib.parse.urlencode(
        {"format": "json", "limit": limit, "offset": offset, "extended": 1}
    )
    req = urllib.request.Request(
        f"{LIBRIVOX_API}?{params}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("books", [])


def librivox_to_series(book: dict, arcs_per_series: int = 3) -> Optional[SourceSeries]:
    """Transform one API record. Returns None for records we should not index.

    Rejections matter more than they look. The feed contains index pages,
    single-poem entries and reference works whose "arcs" would be meaningless,
    and a fingerprint of a dictionary is noise that lands in every shelf.
    """
    try:
        sections = int(book.get("num_sections") or 0)
    except (TypeError, ValueError):
        sections = 0

    synopsis = clean_html(book.get("description", ""))

    # An index page has no sections; a two-minute poem has no arcs. Both
    # produce fingerprints that mean nothing.
    if sections < 6 or len(synopsis) < 120:
        return None

    total_secs = int(book.get("totaltimesecs") or 0)
    if total_secs < 1800:
        return None

    authors = book.get("authors") or []
    author = " ".join(
        filter(None, [authors[0].get("first_name", "").strip(),
                      authors[0].get("last_name", "").strip()])
    ) if authors else ""

    lang = {"English": "en", "German": "de", "French": "fr",
            "Spanish": "es", "Italian": "it"}.get(book.get("language", ""), "en")

    # Real chapter boundaries, split into arcs. Still even splits within the
    # series, but the episode COUNT is real, which is what makes entry points
    # land on numbers that exist.
    n = max(1, min(arcs_per_series, sections // 4 or 1))
    size = max(1, sections // n)
    labels = ["the opening arc", "the turn", "the last stretch"]
    arcs = [
        SourceArc(
            arc_id=f"lv{book['id']}_a{i}",
            label=labels[i % len(labels)],
            start_episode=i * size + 1,
            end_episode=sections if i == n - 1 else (i + 1) * size,
            summary=synopsis,
        )
        for i in range(n)
    ]

    return SourceSeries(
        series_id=f"lv{book['id']}",
        title=book.get("title", "").strip(),
        synopsis=f"{synopsis} (by {author})" if author else synopsis,
        total_episodes=sections,
        source="librivox",
        language=lang,
        arcs=arcs,
    )


def fetch_librivox(
    target: int = 200, page: int = 100, sleep: float = 1.0, max_pages: int = 12
) -> Iterator[SourceSeries]:
    """Page the LibriVox feed until `target` usable series are collected.

    `sleep` is not optional politeness — this is a volunteer-run non-profit
    server. One second between pages costs you twelve seconds total and is the
    difference between using a public API and abusing one.
    """
    seen = 0
    for p in range(max_pages):
        if seen >= target:
            return
        try:
            books = _fetch(p * page, page)
        except Exception as exc:
            print(f"  page {p} failed: {type(exc).__name__}: {exc}")
            break
        if not books:
            return
        for book in books:
            series = librivox_to_series(book)
            if series is None:
                continue
            yield series
            seen += 1
            if seen >= target:
                return
        time.sleep(sleep)


# --------------------------------------------------------------------------
# Local / hand-collected
# --------------------------------------------------------------------------


def fetch_local(path: str | Path) -> list[SourceSeries]:
    """Hand-collected catalog. `catalog_ingest.load_source` does the parsing;
    this exists so both paths have the same call shape."""
    from app.mood.catalog_ingest import load_source

    return load_source(path)


def merge(
    curated: list[SourceSeries], padding: list[SourceSeries], cap: int = 600
) -> list[SourceSeries]:
    """Curated first, padding after, deduped by series_id.

    Order matters for one reason: if you later truncate, you truncate the
    padding. The curated half is the half your eval and your demo depend on.
    """
    out: list[SourceSeries] = []
    seen: set[str] = set()
    for series in list(curated) + list(padding):
        if series.series_id in seen:
            continue
        seen.add(series.series_id)
        out.append(series)
        if len(out) >= cap:
            break
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build a catalog and fingerprint it")
    ap.add_argument("--local", help="hand-collected catalog JSON")
    ap.add_argument("--librivox", type=int, default=0, help="how many to pad with")
    ap.add_argument("--out", default="/tmp/moodstore")
    args = ap.parse_args()

    curated = fetch_local(args.local) if args.local else []
    padding = list(fetch_librivox(args.librivox)) if args.librivox else []
    catalog = merge(curated, padding)
    print(f"catalog: {len(curated)} curated + {len(padding)} padding "
          f"= {len(catalog)} series")

    if not catalog:
        raise SystemExit("nothing to ingest — pass --local and/or --librivox")

    from app.mood.catalog_ingest import ingest
    from app.mood.embeddings import default_embedder
    from app.mood.llm_client import default_client
    from app.mood.store import MoodStore

    client = default_client()
    if client is None:
        raise SystemExit(
            "no LLM client — run `python3 llm_client.py` first to check ADC"
        )

    fingerprints, failures = ingest(client, catalog)
    print(f"fingerprinted {len(fingerprints)} arcs, {len(failures)} failures")
    for cid, why in failures[:5]:
        print(f"  {cid}: {why}")

    store = MoodStore(default_embedder())
    store.add(fingerprints)
    store.save(args.out)
    print(f"saved index to {args.out}  ->  MOOD_INDEX={args.out} uvicorn api:app")
