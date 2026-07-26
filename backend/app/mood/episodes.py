"""
Mood-First Search — the episode layer.

Three tiers, and keeping them apart is the whole point of this file:

    Series          catalog record        (title, synopsis, total_episodes)
      └─ Arc        MOOD INDEX            (fingerprinted, ranked by retrieval)
           └─ Episode  PLAYABLE UNIT      (what the player actually opens)

WHY EPISODES ARE NOT FINGERPRINTED
----------------------------------
The obvious move is to fingerprint every episode and index those. Don't:

  * Cost. 600 series x ~150 episodes is ~90,000 LLM calls against ~1,800 at
    arc level. Two orders of magnitude for a signal you already have.
  * It is the wrong granularity anyway. A single 20-minute episode does not
    have a stable felt quality distinct from the arc around it; "the monsoon
    arc feels like this" is a real claim, "episode 37 feels like this" is
    mostly noise from wherever the scene break landed.
  * Churn. Episode titles and durations change when a series is re-cut.
    Fingerprints are expensive and should not be invalidated by a metadata
    edit.

So episodes are a cheap flat lookup keyed by (series_id, number). No vectors,
no LLM, no axes. Retrieval never touches this file — it is read only after a
listener taps a card.

THE INTEGRATION RISK WORTH NAMING
---------------------------------
`MoodFingerprint.entry_episode` is a promise that an episode with that number
exists. Nothing enforces that across two separately-built files: if the catalog
says 212 episodes and the episode data only has 180, the shelf cheerfully says
"Start at Ep 190" and the player 404s in front of a judge. `validate_against`
catches exactly that, and it belongs in the ingest run, not in a test nobody
runs on demo day.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from pydantic import BaseModel, Field

from app.mood.catalog_ingest import SourceSeries


class Episode(BaseModel):
    """One playable unit. Numbers are 1-based and must match entry_episode."""

    series_id: str
    number: int = Field(ge=1)
    # `title` and `duration_sec` are defaulted, not required. They used to be
    # mandatory, which meant a hand-authored `{"number": 34}` -- the exact shape
    # the source docs invite -- raised a ValidationError at import time and, via
    # the guard in app/main.py, took the whole /api/mood surface offline. A
    # missing title is a cosmetic gap; it must not be a fatal one. The fallback
    # matches what derive_stub_episodes has always produced.
    title: str = ""
    duration_sec: int = Field(0, ge=0)
    synopsis: Optional[str] = None
    audio_url: Optional[str] = Field(
        None,
        description=(
            "Absent for a metadata-only catalog. The player shows the episode "
            "and disables play rather than hiding it -- a missing file is a "
            "content gap, not a reason to pretend the episode does not exist."
        ),
    )
    is_arc_start: bool = False


@dataclass(slots=True)
class EpisodeWindow:
    """What the player asks for: a slice starting at the doorway, not the top."""

    series_id: str
    series_title: str
    start: int
    total: int
    episodes: list[Episode]
    has_more: bool


class EpisodeStore:
    def __init__(self) -> None:
        self._by_series: dict[str, list[Episode]] = {}

    def add(self, episodes: Iterable[Episode]) -> None:
        for ep in episodes:
            self._by_series.setdefault(ep.series_id, []).append(ep)
        for eps in self._by_series.values():
            eps.sort(key=lambda e: e.number)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_series.values())

    def series_ids(self) -> list[str]:
        return sorted(self._by_series)

    def total_for(self, series_id: str) -> int:
        return len(self._by_series.get(series_id, []))

    def get(self, series_id: str, number: int) -> Optional[Episode]:
        for ep in self._by_series.get(series_id, []):
            if ep.number == number:
                return ep
        return None

    def window(
        self,
        series_id: str,
        series_title: str = "",
        start: int = 1,
        limit: int = 12,
    ) -> EpisodeWindow:
        """The doorway fetch.

        Defaults to `start` rather than 1 on purpose. A listener sent to
        episode 34 does not want to scroll past 33 episodes they were never
        told to play; the entry point is the top of the list, and everything
        before it is history they can go back to if they want.
        """
        eps = self._by_series.get(series_id, [])
        chosen = [e for e in eps if e.number >= start][:limit]
        return EpisodeWindow(
            series_id=series_id,
            series_title=series_title,
            start=start,
            total=len(eps),
            episodes=chosen,
            has_more=bool(eps) and chosen and chosen[-1].number < eps[-1].number,
        )

    # -- persistence ------------------------------------------------------

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            "\n".join(
                ep.model_dump_json()
                for eps in self._by_series.values()
                for ep in eps
            )
        )

    @classmethod
    def load(cls, path: str | Path) -> "EpisodeStore":
        store = cls()
        store.add(
            Episode(**json.loads(line))
            for line in Path(path).read_text().splitlines()
            if line.strip()
        )
        return store

    # -- validation -------------------------------------------------------

    def validate_against(self, fingerprints: Sequence) -> list[str]:
        """Every entry_episode must resolve. Run this at ingest time.

        Returns human-readable problems rather than raising: one broken series
        should not abort a catalog build, but you must be told before the demo
        rather than by a 404 during it.
        """
        problems: list[str] = []
        for fp in fingerprints:
            total = self.total_for(fp.series_id)
            if total == 0:
                problems.append(
                    f"{fp.series_id} ({fp.series_title}): no episodes at all, "
                    f"but arc {fp.content_id} points at ep {fp.entry_episode}"
                )
                continue
            # MEMBERSHIP, not a count. Comparing entry_episode against the number
            # of records assumes episodes are a contiguous 1..N run, which is
            # exactly what partial authoring breaks: author eps 1 and 34 for the
            # series you plan to demo and `total` is 2, so a perfectly valid
            # "Start at Ep 34" gets reported as broken while the real 404 -- an
            # entry point that has no record at all -- goes unnoticed.
            if self.get(fp.series_id, fp.entry_episode) is None:
                have = sorted(e.number for e in self._by_series[fp.series_id])
                shown = have[:8] + (["…"] if len(have) > 8 else [])
                problems.append(
                    f"{fp.series_id}: arc {fp.content_id} sends listeners to ep "
                    f"{fp.entry_episode}, which has no episode record. This 404s "
                    f"in the player. Episodes present: {shown}"
                )
        return problems


# --------------------------------------------------------------------------
# Building episodes
# --------------------------------------------------------------------------


def derive_stub_episodes(
    series: SourceSeries, default_duration_sec: int = 1200
) -> list[Episode]:
    """Numbered placeholders for sources that publish a count but no per-episode data.

    LibriVox gives `num_sections` and a total runtime, not a chapter list; a
    hand-collected Pocket FM sheet usually gives episode titles. This fills the
    first case so the player has something coherent to render.

    These are STUBS and the titles say so. Resist the urge to have a model
    invent episode titles -- they would read plausibly, be wrong, and be
    indistinguishable from real ones in the UI, which is the worst of the three
    options.
    """
    arc_starts = {a.start_episode for a in (series.arcs or [])}
    return [
        Episode(
            series_id=series.series_id,
            number=n,
            title=f"Episode {n}",
            duration_sec=default_duration_sec,
            synopsis=None,
            audio_url=None,
            is_arc_start=n in arc_starts,
        )
        for n in range(1, max(1, series.total_episodes) + 1)
    ]


def load_authored_episodes(path: str | Path) -> list[Episode]:
    """Read hand-authored episode data.

    Expected shape -- a list of series blocks:

        [
          {"series_id": "pf_001",
           "episodes": [
             {"number": 1, "title": "Jo Reh Gaya", "duration_sec": 1180,
              "synopsis": "...", "audio_url": "https://..."},
             ...
           ]}
        ]

    Flat records ({"series_id": ..., "number": ...}) are accepted too, so a
    spreadsheet export works without reshaping.

    Deliberately forgiving about the shapes a human actually produces:
      * a nested episode row may repeat `series_id` (a spreadsheet export will)
        without colliding with the block's own,
      * unknown keys are dropped rather than raising, so an extra spreadsheet
        column is not a fatal error,
      * a top-level `{"episodes": [...]}` wrapper is unwrapped, matching the key
        the validator already accepts.

    All of these used to raise, and because this runs at import time the failure
    unmounted the entire /api/mood surface for one stray column.
    """
    blob = json.loads(Path(path).read_text())
    if isinstance(blob, dict):
        for key in ("series", "episodes"):
            if key in blob:
                blob = blob[key]
                break
        else:
            blob = list(blob.values())

    known = set(Episode.model_fields)

    def build(row: dict, series_id: str | None = None) -> Episode:
        data = {k: v for k, v in row.items() if k in known}
        if series_id is not None:
            data["series_id"] = series_id
        if not data.get("title"):
            data["title"] = f"Episode {data.get('number')}"
        return Episode(**data)

    out: list[Episode] = []
    for rec in blob:
        if "episodes" in rec:
            sid = str(rec["series_id"])
            out.extend(build(ep, sid) for ep in rec["episodes"])
        else:
            out.append(build(rec))
    return out


def build_episode_store(
    catalog: Sequence[SourceSeries], authored_path: Optional[str | Path] = None
) -> EpisodeStore:
    """Authored data wins; stubs fill the gaps.

    Precedence matters: a series you took the trouble to write real episode
    titles for is almost certainly one you plan to demo, and a stub silently
    overwriting it would be a quiet downgrade of exactly the thing you cared
    about most.

    The merge is PER EPISODE, not per series. Skipping a whole series once any of
    it was authored punished the recommended workflow -- "author the episodes for
    the series you demo" usually means the two or three the entry points land on,
    and that left a 212-episode show with three playable episodes and no way to
    scroll. Authored numbers win; every other number still gets its stub.
    """
    store = EpisodeStore()
    authored_by_series: dict[str, dict[int, Episode]] = {}

    if authored_path and Path(authored_path).exists():
        for ep in load_authored_episodes(authored_path):
            authored_by_series.setdefault(ep.series_id, {})[ep.number] = ep

    for series in catalog:
        authored = authored_by_series.pop(series.series_id, {})
        stubs = [
            ep for ep in derive_stub_episodes(series) if ep.number not in authored
        ]
        store.add(list(authored.values()) + stubs)

    # Authored episodes for a series that is not in the catalog. Keep them rather
    # than dropping silently -- the validator reports this as an error, and losing
    # the data here would make that report look like a false positive.
    for leftover in authored_by_series.values():
        store.add(list(leftover.values()))

    return store


AUTHORED_TEMPLATE = [
    {
        "series_id": "pf_001",
        "episodes": [
            {"number": 1, "title": "<real episode title>", "duration_sec": 1180,
             "synopsis": "<one line, optional>", "audio_url": None},
            {"number": 34, "title": "<the arc-start episode>", "duration_sec": 1240,
             "synopsis": None, "audio_url": None},
        ],
    }
]


if __name__ == "__main__":
    print(json.dumps(AUTHORED_TEMPLATE, indent=2, ensure_ascii=False))
