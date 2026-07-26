"""
Mood-First Search — source file validator.

Run this BEFORE ingest, every time the data changes. From `backend/`:

    python -m app.mood.validate_sources --catalog catalog.json \\
        --episodes episodes.json --profiles profiles.json

Field lists are the easy part. What actually costs you a demo is a
CROSS-FILE break — an arc pointing at episode 190 of a series that only has
180, a persona whose history references a series you deleted. Nothing in the
type system catches those, because they live in three separately-authored
files, and the symptom is a 404 in front of a judge rather than an exception at
build time.

Errors block ingest. Warnings mean the data will load and the results will be
worse than they look, which is the more dangerous of the two.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# IMPORTED, not redeclared. This list had drifted from the loader's copy, and the
# drift pointed the wrong way: the validator warned about "gpt"/"claude" while
# ingest, not recognising those values, accepted the series as REAL and let them
# into the eval set. A checker that disagrees with the loader reports safety it is
# not providing, so there is now one definition of the set.
#
# The fallback exists because this script must stay runnable by whoever is doing
# the data entry, from a bare checkout with no backend dependencies installed —
# importing the loader drags in pydantic-settings and the whole app config. If
# that import fails we still validate, but we say so, rather than quietly
# checking against a copy that may have drifted.
try:
    from app.mood.catalog_ingest import SYNTHETIC_SOURCES

    _SOURCES_FROM_LOADER = True
except Exception:  # pragma: no cover - standalone use
    SYNTHETIC_SOURCES = frozenset({
        "synthetic", "llm", "generated", "fixture",
        "gpt", "claude", "gemini", "openai", "model",
    })
    _SOURCES_FROM_LOADER = False

MIN_SYNOPSIS_CHARS = 120
MIN_EPISODES_FOR_ARCS = 6

# `language` is matched by EXACT STRING EQUALITY against the parsed query, inside
# the un-relaxable base mask. A query only carries a language when the listener
# asked for one, so a catalog tagged with a language nobody requests is simply
# never filtered on — but a MIXED catalog is a live hazard: the moment one query
# does specify a language, every arc tagged differently disappears from it.
KNOWN_LANGUAGES = {"en", "hi", "ta", "te", "mr", "bn", "gu", "kn", "ml", "pa", "ur"}

# Fields persona.py and evaluate.py actually read. Everything else in a panel
# record is carried along untouched — do not spend curation time on it.
LOAD_BEARING_ATTRS = {
    "listening_time_slot",      # slot fit term + demo contrast
    "primary_language",         # language filter
    "series_completion_rate",   # commitment fit
    "typical_dropoff_episode",  # commitment fit
    "tolerance_for_heaviness",  # ProxyJudge
}

VALID_SLOTS = {"late_night", "bedtime", "commute", "chores", "work_break"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def render(self) -> str:
        out = []
        for msg in self.notes:
            out.append(f"  ·  {msg}")
        for msg in self.warnings:
            out.append(f"  !  {msg}")
        for msg in self.errors:
            out.append(f"  X  {msg}")
        out.append("")
        out.append(
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
            + ("  — ready to ingest" if not self.errors else "  — fix errors first")
        )
        return "\n".join(out)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(path: str | Path, rep: "Report") -> Any:
    """Read a source file, reporting problems instead of raising.

    Whoever authors the catalog is doing data entry, not Python. A stack trace
    tells them nothing; `line 7, column 96` tells them where the comma is.
    """
    p = Path(path)
    if not p.exists():
        rep.error(f"{p}: file not found")
        return []
    try:
        blob = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        rep.error(
            f"{p}: not valid JSON — {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}"
        )
        return []
    except UnicodeDecodeError:
        rep.error(f"{p}: not valid UTF-8 — re-save the file as UTF-8")
        return []
    if not isinstance(blob, (list, dict)):
        rep.error(f"{p}: expected a list of records, got {type(blob).__name__}")
        return []
    if isinstance(blob, dict):
        for key in ("series", "profiles", "personas", "episodes", "catalog"):
            if key in blob:
                blob = blob[key]
                break
        else:
            blob = list(blob.values())

    # A wrapper key holding a nested list (`{"catalog": [[...]]}`) or a dict of
    # dicts used to reach the field loops and crash on `.get` of a list. Say so
    # instead: whoever authored this is doing data entry, not debugging Python.
    if not isinstance(blob, list) or any(not isinstance(r, dict) for r in blob):
        rep.error(
            f"{p}: expected a flat list of records; got "
            f"{type(blob).__name__} containing "
            f"{sorted({type(r).__name__ for r in blob}) if isinstance(blob, list) else '?'}"
        )
        return []
    return blob


# --------------------------------------------------------------------------


def validate_catalog(records: list[dict], rep: Report) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    arc_ids: Counter[str] = Counter()
    languages: Counter[str] = Counter()

    for i, rec in enumerate(records):
        where = f"catalog[{i}]"
        sid = rec.get("series_id")
        if not sid:
            rep.error(f"{where}: missing series_id")
            continue
        where = f"series {sid}"
        if sid in by_id:
            rep.error(f"{where}: duplicate series_id")
            continue

        if not rec.get("title"):
            rep.error(f"{where}: missing title")

        synopsis = (rec.get("synopsis") or "").strip()
        if len(synopsis) < MIN_SYNOPSIS_CHARS:
            rep.warn(
                f"{where}: synopsis is {len(synopsis)} chars "
                f"(< {MIN_SYNOPSIS_CHARS}). Thin synopses produce vague "
                f"fingerprints that match everything weakly."
            )

        source = str(rec.get("source", "")).lower()
        if not source:
            rep.error(f"{where}: missing `source` — required to keep the eval honest")
        elif source in SYNTHETIC_SOURCES:
            # Deliberately an ERROR, not a warning. `ingest` skips these series
            # WHOLE unless allow_synthetic=True, so calling it a warning meant a
            # clean-looking run producing a catalog a fraction of its expected
            # size — indistinguishable from having authored fewer series.
            rep.error(
                f"{where}: source='{source}' is model-written, and ingest skips "
                f"such series entirely by default. Pass --allow-synthetic to keep "
                f"them as long-tail padding, and never point the eval at that index."
            )

        total = rec.get("total_episodes")
        if not isinstance(total, int) or total < 1:
            rep.error(f"{where}: total_episodes must be a positive int, got {total!r}")
            total = 0

        arcs = rec.get("arcs") or []
        if not arcs:
            if total >= MIN_EPISODES_FOR_ARCS:
                rep.warn(
                    f"{where}: no arcs — even splits will be synthesised. "
                    f"Hand-marked arc boundaries are worth more curation effort "
                    f"than a better synopsis; they are what makes the entry "
                    f"point true rather than approximate."
                )
        else:
            spans: list[tuple[int, int, str]] = []
            for j, arc in enumerate(arcs):
                aid = arc.get("arc_id") or f"{sid}_a{j}"
                arc_ids[aid] += 1
                start, end = arc.get("start_episode"), arc.get("end_episode")
                if not isinstance(start, int) or not isinstance(end, int):
                    rep.error(f"{where} arc {aid}: start/end_episode must be ints")
                    continue
                if start < 1:
                    # MoodFingerprint.entry_episode is ge=1, so this raises during
                    # ingest — where the exception is swallowed into a failures
                    # list that only prints its first few entries. The arc simply
                    # goes missing from the index with a clean validator run.
                    rep.error(
                        f"{where} arc {aid}: start_episode is {start}; episodes are "
                        f"1-based, and ingest drops the arc silently if it is not"
                    )
                if start > end:
                    rep.error(f"{where} arc {aid}: start {start} > end {end}")
                if total and end > total:
                    rep.error(
                        f"{where} arc {aid}: ends at ep {end} but series has "
                        f"{total} episodes"
                    )
                if not arc.get("label"):
                    rep.warn(
                        f"{where} arc {aid}: no label — it is shown to the "
                        f"listener as 'Start at Ep {start} — <label>'"
                    )
                spans.append((start, end, aid))

            spans.sort()
            for (s1, e1, a1), (s2, _, a2) in zip(spans, spans[1:]):
                if s2 <= e1:
                    rep.warn(
                        f"{where}: arcs {a1} and {a2} overlap ({s1}-{e1} / "
                        f"{s2}-). Retrieval may return the same stretch twice."
                    )

        lang = rec.get("language")
        if lang is not None:
            if not isinstance(lang, str) or lang != lang.strip().lower():
                rep.error(
                    f"{where}: language={lang!r} must be a lowercase, untrimmed-free "
                    f"string — it is matched by exact equality, so 'HI' and 'hi ' "
                    f"are different languages as far as retrieval is concerned"
                )
            elif lang not in KNOWN_LANGUAGES:
                rep.warn(
                    f"{where}: language='{lang}' is not one of "
                    f"{sorted(KNOWN_LANGUAGES)}. Typos here are invisible: the arc "
                    f"just never matches a query that asks for a language."
                )
            languages[lang] += 1

        by_id[sid] = rec

    for aid, count in arc_ids.items():
        if count > 1:
            rep.error(f"arc_id {aid} used {count} times — must be globally unique")

    rep.note(f"catalog: {len(by_id)} series, {sum(arc_ids.values())} arcs")
    if len(languages) > 1:
        rep.warn(
            f"catalog mixes languages {dict(languages)}. Language is an exact-match "
            f"hard filter, so any query that names one of these silently drops every "
            f"arc in the others. Keep one language per index unless that is intended."
        )
    real = sum(1 for r in by_id.values()
               if str(r.get("source", "")).lower() not in SYNTHETIC_SOURCES)
    rep.note(f"catalog: {real} from real sources, {len(by_id) - real} model-written")
    return by_id


def validate_episodes(
    records: list[dict], catalog: dict[str, dict], rep: Report
) -> dict[str, set[int]]:
    by_series: dict[str, set[int]] = {}

    for i, rec in enumerate(records):
        if "episodes" in rec:
            sid = rec.get("series_id")
            eps = rec["episodes"]
        else:
            sid = rec.get("series_id")
            eps = [rec]
        if not sid:
            rep.error(f"episodes[{i}]: missing series_id")
            continue
        if catalog and sid not in catalog:
            rep.error(f"episodes: series_id {sid} is not in the catalog")
            continue

        numbers = by_series.setdefault(sid, set())
        for ep in eps:
            n = ep.get("number")
            if not isinstance(n, int) or n < 1:
                rep.error(f"series {sid}: episode number must be a positive int, got {n!r}")
                continue
            if n in numbers:
                rep.error(f"series {sid}: duplicate episode {n}")
            numbers.add(n)
            if not ep.get("title"):
                rep.warn(f"series {sid} ep {n}: no title")
            dur = ep.get("duration_sec")
            if dur is not None and (not isinstance(dur, int) or dur < 0):
                rep.error(f"series {sid} ep {n}: duration_sec must be a non-negative int")

    # THE CROSS-CHECK THIS FILE EXISTS FOR.
    for sid, rec in catalog.items():
        have = by_series.get(sid)
        if have is None:
            continue  # stubs will be derived for the whole series; not an error

        arcs = rec.get("arcs") or []
        if arcs:
            starts = [
                (a.get("arc_id"), a.get("start_episode")) for a in arcs
            ]
        else:
            # No arcs authored -> ingest calls synthesize_arcs, which invents even
            # splits. Those invented entry points are what listeners get sent to,
            # so they need the same check. This is the gap the recommended workflow
            # walks straight into: "hand-mark arcs for the ~15 series you demo, let
            # the rest split evenly" plus "author episodes only for what you demo"
            # means the split series have entry points at ep 71 and 141 and an
            # episode file that stops at 3.
            total = rec.get("total_episodes")
            if not isinstance(total, int) or total < 1:
                continue
            n = max(1, min(3, total))
            size = max(1, total // n)
            starts = [(f"{sid}_a{i} (synthesised)", i * size + 1) for i in range(n)]

        for aid, start in starts:
            if isinstance(start, int) and start not in have:
                rep.error(
                    f"series {sid}: arc {aid} sends listeners to ep {start}, which "
                    f"does not exist in the episode file. This 404s in the player."
                )

    if by_series:
        total = sum(len(v) for v in by_series.values())
        rep.note(f"episodes: {total} authored across {len(by_series)} series")
    return by_series


def validate_profiles(
    records: list[dict], catalog: dict[str, dict], rep: Report
) -> None:
    seen: set[str] = set()
    slots: Counter[str] = Counter()

    for i, rec in enumerate(records):
        pid = rec.get("persona_id") or rec.get("id")
        where = f"profiles[{i}]" if not pid else f"persona {pid}"
        if not pid:
            rep.error(f"{where}: missing persona_id")
            continue
        if pid in seen:
            rep.error(f"{where}: duplicate persona_id")
        seen.add(pid)

        if not rec.get("display_name"):
            rep.warn(f"{where}: no display_name — the picker will show the raw id")

        attrs = rec.get("attrs") or {}
        missing = LOAD_BEARING_ATTRS - set(attrs)
        if missing:
            rep.warn(
                f"{where}: missing load-bearing attrs {sorted(missing)} — "
                f"these fall back to defaults and weaken the affinity signal"
            )
        slot = attrs.get("listening_time_slot")
        if slot:
            slots[slot] += 1
            if slot not in VALID_SLOTS:
                rep.warn(
                    f"{where}: listening_time_slot='{slot}' is not one of "
                    f"{sorted(VALID_SLOTS)} — the slot term will contribute nothing"
                )

        history = rec.get("history") or []
        if not history:
            rep.warn(f"{where}: no history — affinity has no opinion for this listener")
        for h in history:
            hsid = h.get("series_id")
            if catalog and hsid not in catalog:
                rep.error(f"{where}: history references unknown series {hsid}")
            if not isinstance(h.get("completed"), bool):
                rep.error(f"{where}: history entry for {hsid} needs a boolean `completed`")

    rep.note(f"profiles: {len(seen)} listeners, slots {dict(slots)}")
    if len(slots) < 3 and len(seen) >= 5:
        rep.warn(
            "profiles: listeners cluster into fewer than 3 listening slots. "
            "The demo beat is 'same query, different listener, different shelf' "
            "— similar listeners make affinity look broken rather than subtle."
        )


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--episodes")
    ap.add_argument("--profiles")
    args = ap.parse_args()

    rep = Report()
    if not _SOURCES_FROM_LOADER:
        rep.warn(
            "could not import the ingest module, so the model-written `source` "
            "list is a local copy and may have drifted. Run from backend/ with "
            "the backend dependencies installed to check against the real one."
        )
    catalog = validate_catalog(_load(args.catalog, rep), rep)
    if args.episodes:
        validate_episodes(_load(args.episodes, rep), catalog, rep)
    else:
        rep.note("no --episodes: stubs will be derived from total_episodes")
    if args.profiles:
        validate_profiles(_load(args.profiles, rep), catalog, rep)

    print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
