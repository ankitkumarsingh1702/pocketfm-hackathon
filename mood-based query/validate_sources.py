"""
Mood-First Search — source file validator.

Run this BEFORE ingest, every time the data changes:

    python3 validate_sources.py --catalog catalog.json \\
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

# `source` values that mean "a model wrote this". Fingerprinting model-written
# synopses makes the system grade its own homework: the fingerprint says
# "rain-soaked" because the generator wrote it that way, retrieval matches
# rainy queries to it, and every eval number becomes decorative. The failure is
# invisible — the metrics go UP.
SYNTHETIC_SOURCES = {"synthetic", "llm", "generated", "fixture", "gpt", "claude"}

MIN_SYNOPSIS_CHARS = 120
MIN_EPISODES_FOR_ARCS = 6

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
        for key in ("series", "profiles", "personas", "episodes"):
            if key in blob:
                return blob[key]
        return list(blob.values())
    return blob


# --------------------------------------------------------------------------


def validate_catalog(records: list[dict], rep: Report) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    arc_ids: Counter[str] = Counter()

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
            rep.warn(
                f"{where}: source='{source}' is model-written. Fine as padding, "
                f"must be excluded from the eval set."
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

        by_id[sid] = rec

    for aid, count in arc_ids.items():
        if count > 1:
            rep.error(f"arc_id {aid} used {count} times — must be globally unique")

    rep.note(f"catalog: {len(by_id)} series, {sum(arc_ids.values())} arcs")
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
            continue  # stubs will be derived; not an error
        for arc in rec.get("arcs") or []:
            start = arc.get("start_episode")
            if isinstance(start, int) and start not in have:
                rep.error(
                    f"series {sid}: arc {arc.get('arc_id')} sends listeners to "
                    f"ep {start}, which does not exist in the episode file. "
                    f"This 404s in the player."
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
