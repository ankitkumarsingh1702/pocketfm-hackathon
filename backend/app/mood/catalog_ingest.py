"""
Mood-First Search — metadata-only catalog ingest.

Replaces the offline audio pipeline (ASR -> prosody -> CLAP -> fusion) with a
single step: curated metadata JSON -> MoodFingerprint. Everything downstream is
unchanged, because retrieval only ever spoke MoodFingerprint and never cared
where one came from.

THE ONE RULE THAT MAKES THIS VALID
----------------------------------
`source` must not be a language model.

If an LLM writes the synopsis AND an LLM derives the fingerprint from it, the
system is grading its own homework. The fingerprint reads "slow, rain-soaked"
because the generator wrote it that way, retrieval then matches rainy queries
to it, and the eval reports excellent numbers that measure nothing except one
model's self-consistency. Every metric in evaluate.py becomes decorative, and
the failure is invisible -- the numbers look better, not worse.

Grounding it in real synopses (scraped, hand-collected, partner-supplied) makes
the fingerprinter perform actual inference over text someone else wrote. That
is a real capability and it is defensible in a demo. `SYNTHETIC_SOURCES` is
rejected by default for exactly this reason; pass allow_synthetic=True only for
padding the long tail, and never let padded items reach the eval set.

WHAT THIS COSTS
---------------
The claim "mood comes from the voice, not the tags" is not available any more.
It was the strongest differentiator in the PRD and it is now roadmap. Say so
plainly in the demo rather than implying an audio pipeline that isn't there --
that specific overclaim is the one a judge is most likely to probe.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from app.mood.llm_client import LLMClient
from app.mood.schemas import MoodAxes, MoodFingerprint

# Values of `source` that mean "a model wrote this". Kept in lockstep with
# validate_sources.SYNTHETIC_SOURCES -- they disagreed once, and the disagreement
# pointed the wrong way: the validator warned about "gpt"/"claude" while ingest,
# not recognising them, accepted those series as REAL and let them into the eval
# set. A denylist that the checker and the loader disagree about is worse than
# none, because it reports safety it is not providing.
SYNTHETIC_SOURCES = frozenset({
    "synthetic", "llm", "generated", "fixture",
    "gpt", "claude", "gemini", "openai", "model",
})

# Fallback per-episode runtime when nothing better is known. Only used to size an
# arc; see `_arc_duration_min`.
DEFAULT_EPISODE_SEC = 1200

SYSTEM = """\
You read a description of one arc of an audio-fiction series and describe how \
LISTENING to it feels. You are not summarising the plot.

Return ONLY a JSON object, no prose, no fences:
{
  "valence": -1.0..1.0, "arousal": 0..1, "tension": 0..1, "warmth": 0..1,
  "pace": 0..1, "catharsis": 0..1, "hope": 0..1, "companionship": 0..1,
  "weight": 0..1,
  "sensory_tags": [str], "vibe_sentence": str,
  "good_for": [str], "contraindicated_for": [str], "confidence": 0..1
}

Axis meanings: valence bleak->uplifting. arousal still->frantic. tension \
safe->dread. warmth clinical->held. pace slow-burn->propulsive. catharsis \
numb->tear-releasing. hope hopeless->redemptive. companionship watching a \
world->being spoken to. weight frothy->heavy.

- "vibe_sentence": one line, the way a listener would describe the feeling to \
a friend. No plot, no spoilers, no genre words, no "fans of".
- "sensory_tags": from rain, monsoon, night, evening, morning, summer, winter, \
small-room, open-road, crowd, winter-quilt. Only what the arc actually evokes.
- "contraindicated_for": listener states this would make WORSE. Be concrete \
and be willing to leave it empty. A sad story about a breakup is usually wrong \
for someone in a fresh breakup even though it matches on topic — that is \
exactly the kind of entry that belongs here.\
"""


@dataclass(slots=True)
class SourceArc:
    arc_id: str
    label: str
    start_episode: int
    end_episode: int
    summary: str


@dataclass(slots=True)
class SourceSeries:
    series_id: str
    title: str
    synopsis: str
    total_episodes: int
    source: str
    language: str = "en"
    arcs: list[SourceArc] = None  # type: ignore[assignment]

    @property
    def is_synthetic(self) -> bool:
        return self.source.lower() in SYNTHETIC_SOURCES


def load_source(path: str | Path) -> list[SourceSeries]:
    """Read the curated catalog JSON.

    Expected shape per record:
      {"series_id","title","synopsis","total_episodes","source","language",
       "arcs":[{"arc_id","label","start_episode","end_episode","summary"}]}

    `arcs` may be omitted -- see `synthesize_arcs`.
    """
    blob = json.loads(Path(path).read_text())
    if isinstance(blob, dict):
        blob = blob.get("series", list(blob.values()))

    out: list[SourceSeries] = []
    for rec in blob:
        arcs = [
            SourceArc(
                arc_id=str(a.get("arc_id") or f"{rec['series_id']}_a{i}"),
                label=a.get("label") or "the opening arc",
                start_episode=int(a.get("start_episode", 1)),
                end_episode=int(a.get("end_episode", rec.get("total_episodes", 1))),
                summary=a.get("summary") or "",
            )
            for i, a in enumerate(rec.get("arcs") or [])
        ]
        out.append(
            SourceSeries(
                series_id=str(rec["series_id"]),
                title=rec["title"],
                synopsis=rec.get("synopsis", ""),
                total_episodes=int(rec.get("total_episodes", 1)),
                source=str(rec.get("source", "unknown")),
                language=rec.get("language", "en"),
                arcs=arcs,
            )
        )
    return out


def synthesize_arcs(series: SourceSeries, target_arcs: int = 3) -> list[SourceArc]:
    """Split a series into even arcs when the source gives no arc structure.

    This is a real compromise and worth naming: even splits are not where the
    emotional turns actually are, so entry points land near the right episode
    rather than on it. Arc boundaries in the metadata are the single highest
    value field to curate by hand -- more valuable than a better synopsis,
    because they are what makes "start at Ep 34" true rather than approximate.
    """
    n = max(1, min(target_arcs, series.total_episodes))
    size = max(1, series.total_episodes // n)
    labels = ["the opening arc", "the turn", "the last stretch",
              "the quiet arc", "the monsoon arc"]
    arcs = []
    for i in range(n):
        start = i * size + 1
        end = series.total_episodes if i == n - 1 else (i + 1) * size
        arcs.append(SourceArc(
            arc_id=f"{series.series_id}_a{i}",
            label=labels[i % len(labels)],
            start_episode=start,
            end_episode=end,
            summary=series.synopsis,
        ))
    return arcs


def _extract_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    a, b = raw.find("{"), raw.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("no JSON object in fingerprinter output")
    return json.loads(raw[a:b + 1])


def _axes(payload: dict) -> MoodAxes:
    def g(name, lo=0.0):
        try:
            return max(lo, min(1.0, float(payload.get(name, 0.5))))
        except (TypeError, ValueError):
            return 0.5
    return MoodAxes(
        valence=max(-1.0, min(1.0, float(payload.get("valence", 0.0) or 0.0))),
        arousal=g("arousal"), tension=g("tension"), warmth=g("warmth"),
        pace=g("pace"), catharsis=g("catharsis"), hope=g("hope"),
        companionship=g("companionship"), weight=g("weight"),
    )


def _arc_duration_min(
    arc: SourceArc, episode_seconds: Optional[dict[int, int]] = None
) -> int:
    """How long ONE sitting in this arc is, in minutes.

    This used to be the constant 22 for every arc in every catalog, which broke
    two things quietly. Every result card in the UI read "22 min", and
    `session_length_min` became a no-op: `store.duration_mask` compares against
    this value, so a uniform catalog is either entirely inside the bound or
    entirely outside it, and the entirely-outside case is then discarded by the
    starvation guard in `Retriever._base_mask`. A filter that cannot discriminate
    is indistinguishable from one that is not wired up.

    Prefers real authored durations, falls back to a per-episode default. Reports
    a typical EPISODE length rather than the whole arc's runtime, because that is
    what "kitna time hai?" is asking and what the card claims.
    """
    if episode_seconds:
        known = [
            episode_seconds[n]
            for n in range(arc.start_episode, arc.end_episode + 1)
            if episode_seconds.get(n)
        ]
        if known:
            return max(1, round(sum(known) / len(known) / 60))
    return max(1, round(DEFAULT_EPISODE_SEC / 60))


def fingerprint_arc(
    client: LLMClient,
    series: SourceSeries,
    arc: SourceArc,
    episode_seconds: Optional[dict[int, int]] = None,
) -> MoodFingerprint:
    user = "\n".join([
        f"Series: {series.title}",
        f"Series description: {series.synopsis}",
        f"Arc: {arc.label} (episodes {arc.start_episode}-{arc.end_episode} "
        f"of {series.total_episodes})",
        f"Arc description: {arc.summary or series.synopsis}",
    ])
    payload = _extract_json(client.complete(SYSTEM, user))

    return MoodFingerprint(
        content_id=arc.arc_id,
        series_id=series.series_id,
        series_title=series.title,
        arc_label=arc.label,
        entry_episode=arc.start_episode,
        episode_span=(arc.start_episode, arc.end_episode),
        axes=_axes(payload),
        sensory_tags=[str(t) for t in (payload.get("sensory_tags") or [])][:6],
        vibe_sentence=str(payload.get("vibe_sentence") or "").strip()[:200]
        or f"An arc of {series.title}.",
        good_for=[str(t) for t in (payload.get("good_for") or [])][:4],
        contraindicated_for=[str(t) for t in (payload.get("contraindicated_for") or [])][:4],
        duration_min=_arc_duration_min(arc, episode_seconds),
        language=series.language,
        # Metadata-only: nothing here has been near an audio decoder. Leaving
        # this False everywhere is the honest state, and it is what keeps the
        # tier bonus in ScoringWeights from silently meaning nothing --
        # see the note in the module docstring about the moat claim.
        audio_verified=False,
        axes_variance=0.0,
        confidence=min(1.0, float(payload.get("confidence", 0.6) or 0.6)),
    )


def ingest(
    client: LLMClient,
    source: Iterable[SourceSeries],
    allow_synthetic: bool = False,
    on_error: Optional[callable] = None,
    episode_seconds: Optional[dict[str, dict[int, int]]] = None,
) -> tuple[list[MoodFingerprint], list[tuple[str, str]]]:
    """Fingerprint a whole catalog. Returns (fingerprints, failures).

    Failures are returned rather than raised: one bad record in six hundred must
    not abort a run that takes real wall-clock time. Callers MUST surface the
    count -- a rejected series is a silently missing series, and the only signal
    is this list.

    `episode_seconds` maps series_id -> {episode number: duration_sec}, used to
    give each arc a real duration instead of a constant. Pass the authored
    episode data if you have it.
    """
    out: list[MoodFingerprint] = []
    failures: list[tuple[str, str]] = []

    for series in source:
        if series.is_synthetic and not allow_synthetic:
            # Whole series dropped, every arc with it. Named explicitly because
            # the docs describe model-written padding as "allowed": it is, but
            # only with allow_synthetic=True, and forgetting that flag looks
            # exactly like the catalog being smaller than you thought.
            failures.append((
                series.series_id,
                f"source='{series.source}' is model-written and "
                f"allow_synthetic=False — series skipped entirely",
            ))
            continue
        arcs = series.arcs or synthesize_arcs(series)
        per_series = (episode_seconds or {}).get(series.series_id)
        for arc in arcs:
            try:
                out.append(fingerprint_arc(client, series, arc, per_series))
            except Exception as exc:
                failures.append((arc.arc_id, f"{type(exc).__name__}: {exc}"))
                if on_error:
                    on_error(arc.arc_id, exc)
    return out, failures


TEMPLATE = [
    {
        "series_id": "pf_001",
        "title": "<real series title>",
        "synopsis": "<real synopsis — copied, not written by a model>",
        "total_episodes": 212,
        "language": "hi",
        "source": "pocketfm_web",
        "arcs": [
            {"arc_id": "pf_001_a0", "label": "the opening arc",
             "start_episode": 1, "end_episode": 33,
             "summary": "<what happens, in the source's own words>"},
            {"arc_id": "pf_001_a1", "label": "the monsoon arc",
             "start_episode": 34, "end_episode": 78, "summary": "..."}
        ],
    }
]


if __name__ == "__main__":
    print(json.dumps(TEMPLATE, indent=2, ensure_ascii=False))
