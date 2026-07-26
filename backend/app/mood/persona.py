"""
Mood-First Search — listener profiles and affinity. Replaces the dead
`ScoringWeights.tier` (audio-verified bonus) now that the catalog is
metadata-only.

WHAT AFFINITY IS ALLOWED TO DO
------------------------------
Break ties. That is it.

The temptation with a 43-field persona and a watch history is to let it drive
ranking. Do that and the mood query becomes decoration on a collaborative
filter -- the demo still works, and the thing being demonstrated is no longer
the thing in the PRD. So affinity is capped at a weight (0.12) that cannot
outrank the mood-axis term (0.45): it reorders results that were already
comparable, and it never promotes something the query didn't ask for.

The asymmetry is deliberate and worth stating out loud when a judge asks why
personalization is weighted so low: the query is evidence about tonight, the
history is evidence about the last six months, and tonight is why they opened
the app.

THREE THINGS AFFINITY MAY NEVER DO
----------------------------------
1. Reinstate a contraindicated item. Someone who has historically loved sad
   breakup dramas is still in a fresh breakup tonight. Contraindications are
   filtered in `Retriever.retrieve` BEFORE scoring, so affinity never sees
   those rows -- keep it that way.
2. Re-surface something already finished. That is a hard mask, not a penalty.
3. Encode mood. Mood is state, not trait. What is stored here is TASTE (what
   they finish, what they abandon, when they listen) -- never "this user is a
   sad person".
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from app.mood.schemas import AXIS_NAMES, MoodAxes
from app.mood.store import MoodStore, axes_to_row


@dataclass(slots=True)
class WatchRecord:
    """One thing a listener has watched.

    `completed` is the only field that changes retrieval: it feeds the taste
    centroid and hard-masks the series from results. `episodes_listened` and
    `dropped_at_episode` are carried for display and are genuinely optional --
    they used to be required positionally, which meant a history entry authored
    from the documented table raised a TypeError at import time and took the
    whole /api/mood surface down with it.
    """

    series_id: str
    completed: bool = False
    episodes_listened: int = 0
    liked: Optional[bool] = None       # explicit signal, usually absent
    dropped_at_episode: Optional[int] = None


@dataclass(slots=True)
class ListenerProfile:
    """One selectable demo listener. `attrs` is the 43-field panel record."""

    persona_id: str
    display_name: str
    attrs: dict = field(default_factory=dict)
    history: list[WatchRecord] = field(default_factory=list)

    # -- derived signals -------------------------------------------------

    @property
    def completion_rate(self) -> float:
        if self.history:
            return sum(h.completed for h in self.history) / len(self.history)
        return float(self.attrs.get("series_completion_rate", 0.5))

    @property
    def slot(self) -> str:
        return str(self.attrs.get("listening_time_slot", "unknown"))

    @property
    def language(self) -> str:
        return str(self.attrs.get("primary_language", "en"))

    def watched_series(self) -> frozenset[str]:
        return frozenset(h.series_id for h in self.history)

    def finished_series(self) -> frozenset[str]:
        """Hard-masked from results. Finishing is not a request for more of it."""
        return frozenset(h.series_id for h in self.history
                         if h.completed or h.liked is False)

    def to_json(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "display_name": self.display_name,
            "attrs": self.attrs,
            "history": [asdict(h) for h in self.history],
        }


def load_profiles(path: str | Path) -> list[ListenerProfile]:
    """Read the demo listener panel.

    Accepts the aliases and wrappers a real panel export actually arrives with,
    and drops unknown history keys instead of raising. A panel record carries
    dozens of fields; `attrs` keeps all of them, but `history` rows are a fixed
    shape, and one extra column used to be a TypeError at import time -- which
    unmounted the whole feature rather than ignoring a field nobody reads.
    """
    blob = json.loads(Path(path).read_text())
    if isinstance(blob, dict):
        for key in ("profiles", "personas"):
            if key in blob:
                blob = blob[key]
                break
        else:
            blob = list(blob.values())

    known = {f.name for f in fields(WatchRecord)}

    def record(h: dict) -> WatchRecord:
        return WatchRecord(**{k: v for k, v in h.items() if k in known})

    out: list[ListenerProfile] = []
    for r in blob:
        pid = r.get("persona_id") or r.get("id")
        if not pid:
            continue  # nothing to key a listener on; skip rather than crash
        out.append(
            ListenerProfile(
                persona_id=str(pid),
                display_name=r.get("display_name") or str(pid),
                attrs=r.get("attrs") or {},
                history=[record(h) for h in (r.get("history") or [])],
            )
        )
    return out


def save_profiles(profiles: Sequence[ListenerProfile], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps([p.to_json() for p in profiles], indent=2, ensure_ascii=False)
    )


# --------------------------------------------------------------------------
# Slot -> sensory tag expectations. Used for the "does this suit when they
# actually listen" term.
# --------------------------------------------------------------------------

_SLOT_TAGS: dict[str, frozenset[str]] = {
    "late_night": frozenset({"night", "small-room", "rain"}),
    "bedtime": frozenset({"night", "winter-quilt", "small-room"}),
    "commute": frozenset({"crowd", "open-road", "morning"}),
    "chores": frozenset({"small-room", "morning", "evening"}),
    "work_break": frozenset({"evening", "crowd"}),
}


class AffinityScorer:
    """Per-row affinity in [0,1] for one listener. Built once per request.

    Four components, each bounded, each cheap:
      taste       0.40  do they finish arcs that feel like this one
      tags        0.25  do the sensory tags match what they finish
      commitment  0.20  is this entry point realistic for their drop-off habit
      slot        0.15  does it suit when they actually listen

    `taste` reads the mood axes of arcs they COMPLETED. That is a taste signal,
    not a mood signal -- it captures "this person finishes warm, slow things",
    which is stable, rather than "this person is sad", which is not.
    """

    W_TASTE, W_TAGS, W_COMMIT, W_SLOT = 0.40, 0.25, 0.20, 0.15

    def __init__(self, store: MoodStore, profile: ListenerProfile) -> None:
        self.store = store
        self.profile = profile

        rows_by_series: dict[str, list[int]] = {}
        for row, fp in enumerate(store.fingerprints):
            rows_by_series.setdefault(fp.series_id, []).append(row)

        positive_rows: list[int] = []
        liked_tags: set[str] = set()
        for record in profile.history:
            if record.liked is False:
                continue
            if not (record.completed or record.liked is True):
                continue
            for row in rows_by_series.get(record.series_id, []):
                positive_rows.append(row)
                liked_tags.update(
                    t.lower() for t in store.fingerprints[row].sensory_tags
                )

        self._centroid: Optional[np.ndarray] = (
            store._axes[positive_rows].mean(axis=0) if positive_rows else None
        )
        self._liked_tags = frozenset(liked_tags)
        self._slot_tags = _SLOT_TAGS.get(profile.slot, frozenset())
        self._finished = profile.finished_series()

    # -- masking ---------------------------------------------------------

    def exclusion_mask(self) -> np.ndarray:
        """False for series they already finished. Hard, not a penalty."""
        return np.array(
            [fp.series_id not in self._finished for fp in self.store.fingerprints],
            dtype=bool,
        )

    # -- scoring ---------------------------------------------------------

    def scores(self) -> np.ndarray:
        n = len(self.store)
        if n == 0:
            return np.zeros(0, dtype=np.float32)

        # taste
        if self._centroid is None:
            # Cold listener: no history, so no opinion. Returning a flat 0.5
            # rather than 0 keeps the term from silently penalising every row
            # for a new user.
            taste = np.full(n, 0.5, dtype=np.float32)
        else:
            diff = self.store._axes - self._centroid[None, :]
            dist = np.sqrt((diff ** 2).mean(axis=1))
            taste = np.clip(1.0 - dist / 0.6, 0.0, 1.0).astype(np.float32)

        # tags
        if self._liked_tags:
            tags = np.array(
                [len(t & self._liked_tags) / len(self._liked_tags)
                 for t in self.store._tags],
                dtype=np.float32,
            )
        else:
            tags = np.full(n, 0.5, dtype=np.float32)

        # commitment: a listener who abandons series at episode 12 should not
        # be handed a doorway at episode 140, however well it matches.
        rate = self.profile.completion_rate
        typical_dropoff = float(self.profile.attrs.get("typical_dropoff_episode", 25))
        tolerance = max(8.0, typical_dropoff * (0.5 + rate))
        entries = np.array(
            [fp.entry_episode for fp in self.store.fingerprints], dtype=np.float32
        )
        commit = np.clip(1.0 - np.maximum(0.0, entries - tolerance) / 120.0, 0.0, 1.0)

        # slot
        if self._slot_tags:
            slot = np.array(
                [min(1.0, len(t & self._slot_tags) / 2.0) for t in self.store._tags],
                dtype=np.float32,
            )
        else:
            slot = np.full(n, 0.5, dtype=np.float32)

        return (
            self.W_TASTE * taste
            + self.W_TAGS * tags
            + self.W_COMMIT * commit
            + self.W_SLOT * slot
        ).astype(np.float32)

    def explain(self, row: int) -> dict:
        """Per-row breakdown. Debug/Lab surface only — never shown to a listener."""
        fp = self.store.fingerprints[row]
        return {
            "content_id": fp.content_id,
            "affinity": round(float(self.scores()[row]), 3),
            "entry_episode": fp.entry_episode,
            "commitment_tolerance": round(
                max(8.0, float(self.profile.attrs.get("typical_dropoff_episode", 25))
                    * (0.5 + self.profile.completion_rate)), 1),
            "tag_overlap": sorted(self.store._tags[row] & self._liked_tags),
            "slot": self.profile.slot,
        }


# --------------------------------------------------------------------------
# Demo panel
# --------------------------------------------------------------------------


def build_demo_panel(
    panel: Sequence, store: MoodStore, n: int = 10, seed: int = 11
) -> list[ListenerProfile]:
    """Pick n personas from the real panel and give them contrasting history.

    Chosen for CONTRAST, not representativeness. The demo beat is "same query,
    different listener, different shelf" -- and a panel of ten people with
    randomly-drawn history produces ten near-identical taste centroids, which
    makes affinity look broken when it is merely being appropriately quiet.

    So history is drawn per-listener from ONE mood neighbourhood rather than
    uniformly. That is also more realistic: real listening histories are
    lopsided. People have a lane.

    The temptation when the difference looks too subtle is to raise the
    affinity weight. Don't -- that makes personalization outrank the query,
    which is the exact failure this module's docstring is about. Make the
    listeners genuinely different instead; then a small weight is enough.

    The history is synthesised and that is a real limitation to state if
    asked -- generated to be consistent with each persona's completion rate and
    slot, not observed. Hand-edit the JSON for the two or three listeners you
    will actually demo.
    """
    rng = random.Random(seed)
    if len(store) == 0:
        return []

    # Cluster the catalog by mood neighbourhood, one per destination.
    from app.mood.mood_config import DESTINATION_TARGETS

    dest_names = list(DESTINATION_TARGETS)
    centroids = np.vstack([axes_to_row(DESTINATION_TARGETS[d]) for d in dest_names])
    lanes: dict[str, list[str]] = {d: [] for d in dest_names}
    for row, fp in enumerate(store.fingerprints):
        nearest = int(np.argmin(np.linalg.norm(centroids - store._axes[row], axis=1)))
        sid = fp.series_id
        if sid not in lanes[dest_names[nearest]]:
            lanes[dest_names[nearest]].append(sid)

    # Spread the chosen personas across listening slots too, so the slot term
    # has something to contribute alongside taste.
    wanted_slots = ["late_night", "commute", "bedtime", "chores", "work_break"]
    chosen: list = []
    for slot in wanted_slots:
        matches = [p for p in panel
                   if str(getattr(p, "attrs", {}).get("listening_time_slot")) == slot]
        chosen.extend(matches[: max(1, n // len(wanted_slots))])
    for p in panel:
        if len(chosen) >= n:
            break
        if p not in chosen:
            chosen.append(p)
    chosen = chosen[:n]

    profiles: list[ListenerProfile] = []
    for i, p in enumerate(chosen):
        attrs = dict(getattr(p, "attrs", {}) or {})
        rate = float(attrs.get("series_completion_rate", rng.uniform(0.2, 0.8)))
        dropoff = int(attrs.get("typical_dropoff_episode", rng.randint(8, 60)))

        # This listener's lane. Cycling rather than sampling guarantees the
        # panel spans the space even at n=10.
        lane = dest_names[i % len(dest_names)]
        pool = lanes[lane] or [fp.series_id for fp in store.fingerprints]
        others = [s for s in {fp.series_id for fp in store.fingerprints} if s not in pool]

        picks = rng.sample(pool, k=min(len(pool), rng.randint(3, 5)))
        if others and rng.random() < 0.6:
            picks.append(rng.choice(others))  # nobody is purely one lane

        history = []
        for sid in picks:
            in_lane = sid in pool
            # They finish what's in their lane and abandon what isn't. That is
            # what makes the taste centroid mean something.
            completed = rng.random() < (rate + 0.25 if in_lane else rate - 0.35)
            history.append(WatchRecord(
                series_id=sid,
                episodes_listened=rng.randint(dropoff, dropoff + 40) if completed
                else rng.randint(2, max(3, dropoff)),
                completed=completed,
                liked=True if completed and in_lane else (False if not in_lane and not completed else None),
                dropped_at_episode=None if completed else rng.randint(2, max(3, dropoff)),
            ))

        attrs.setdefault("demo_lane", lane)
        profiles.append(ListenerProfile(
            persona_id=str(getattr(p, "id", f"demo{i}")),
            display_name=attrs.get("display_name") or f"Listener {i + 1}",
            attrs=attrs,
            history=history,
        ))
    return profiles
