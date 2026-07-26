"""
Mood-First Search — dependency-light heuristic engine (Python port of the Node
`mood-based query/local_mood_server.mjs`).

WHY THIS EXISTS
---------------
The default engine (`app.mood.api`) ranks an LLM-fingerprinted ``MoodStore`` that
an offline Vertex ingest must build first — so a catalog is invisible until it
has been ingested. This module is the shortcut that makes a hand-curated catalog
serve DIRECTLY: it reads ``data/catalog.json`` + ``data/episodes.json`` +
``data/profiles.json``, scores them against hand-authored mood axes with a small
keyword parser, and speaks the exact same ``/api/mood/*`` contract the frontend
already uses. No ``MoodStore``, no Vertex, no LLM — so real songs show up in
prod without an ingest step.

It is OPT-IN: ``main.py`` mounts this router instead of the LLM one only when
``MOOD_SIMPLE`` is set. With the flag unset nothing here runs.

The retrieval is deliberately simple (keyword→intent, euclidean distance in
axis space); it is not the LLM pipeline and does not pretend to be. The one
thing it does keep is the safety gate: ``detect_distress`` and the real
``SUPPORT_RESOURCES`` are reused verbatim so a distress query still returns
helplines rather than a shelf of songs.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from pathlib import Path

from fastapi import APIRouter

from app.mood.mood_config import SUPPORT_RESOURCES
from app.mood.parser import detect_distress

_DATA = Path(__file__).parent / "data"


def _load(name: str):
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


CATALOG = _load("catalog.json")
EPISODES = _load("episodes.json")
PROFILES = _load("profiles.json")

AXIS_KEYS = [
    "valence", "arousal", "tension", "warmth", "pace",
    "catharsis", "hope", "companionship", "weight",
]

# Hand-authored axes per collection (the seed_catalog move: known mood -> axes,
# no model). valence is -1..1, the rest 0..1.
AXES: dict[str, dict[str, float]] = {
    "pf_after_ending":     {"valence": -0.7, "arousal": 0.25, "tension": 0.35, "warmth": 0.60, "pace": 0.25, "catharsis": 0.85, "hope": 0.30, "companionship": 0.50, "weight": 0.85},
    "pf_three_am_clarity": {"valence": -0.1, "arousal": 0.35, "tension": 0.35, "warmth": 0.55, "pace": 0.35, "catharsis": 0.55, "hope": 0.55, "companionship": 0.55, "weight": 0.60},
    "pf_soft_morning":     {"valence": 0.50, "arousal": 0.40, "tension": 0.15, "warmth": 0.75, "pace": 0.40, "catharsis": 0.30, "hope": 0.80, "companionship": 0.55, "weight": 0.30},
    "pf_held":             {"valence": 0.55, "arousal": 0.35, "tension": 0.15, "warmth": 0.90, "pace": 0.35, "catharsis": 0.40, "hope": 0.70, "companionship": 0.85, "weight": 0.35},
    "pf_windows_down":     {"valence": 0.35, "arousal": 0.75, "tension": 0.45, "warmth": 0.40, "pace": 0.85, "catharsis": 0.30, "hope": 0.60, "companionship": 0.30, "weight": 0.40},
    "pf_hands_up":         {"valence": 0.75, "arousal": 0.90, "tension": 0.20, "warmth": 0.55, "pace": 0.90, "catharsis": 0.35, "hope": 0.75, "companionship": 0.50, "weight": 0.20},
    "pf_neon_shadow":      {"valence": -0.2, "arousal": 0.60, "tension": 0.60, "warmth": 0.35, "pace": 0.60, "catharsis": 0.30, "hope": 0.35, "companionship": 0.35, "weight": 0.55},
    "pf_static_starlight": {"valence": 0.10, "arousal": 0.10, "tension": 0.10, "warmth": 0.60, "pace": 0.15, "catharsis": 0.15, "hope": 0.50, "companionship": 0.50, "weight": 0.25},
}

VIBE: dict[str, str] = {
    "pf_after_ending": "Quiet and low — it sits in the ache with you instead of rushing you out of it.",
    "pf_three_am_clarity": "Clear-eyed and reflective — it puts a shape around the thing you can't name.",
    "pf_soft_morning": "Warm and easy — it opens the curtains and ends better than it starts.",
    "pf_held": "Tender and close to the mic — the sound of being wholly wanted.",
    "pf_windows_down": "Propulsive and wide-screen — built for motion and an empty road.",
    "pf_hands_up": "Pure euphoria — the hooks everyone knows and every hand in the air.",
    "pf_neon_shadow": "Sleek, brooding and a little dangerous — after-midnight cool.",
    "pf_static_starlight": "Slow and weightless — made to be half-heard on the way to sleep.",
}

INTENTS = [
    {"key": "sit_with", "label": "Sit in it", "subtitle": "Stays low and doesn't rush you out of it.", "ref": "pf_after_ending",
     "kw": ["sad", "heartbreak", "heartbroken", "cry", "crying", "breakup", "broke up", "alone", "lonely", "miss", "grief", "hurt", "tears", "down", "blue", "sob"]},
    {"key": "reflect", "label": "Help me think", "subtitle": "Clear-eyed and reflective.", "ref": "pf_three_am_clarity",
     "kw": ["think", "thinking", "reflect", "reflective", "nostalgia", "nostalgic", "memories", "introspect", "process", "ponder", "clarity"]},
    {"key": "lift", "label": "Lift me out of it", "subtitle": "Warm and hopeful — ends better than it starts.", "ref": "pf_soft_morning",
     "kw": ["happy", "cheer", "lift", "hopeful", "hope", "sunshine", "better", "uplift", "bright", "morning", "good mood", "smile", "sunny"]},
    {"key": "company", "label": "Keep me company", "subtitle": "Close and warm, someone right there.", "ref": "pf_held",
     "kw": ["cozy", "cosy", "warm", "company", "comfort", "love", "romantic", "romance", "together", "hold", "tender", "sweet", "cuddle", "in love"]},
    {"key": "escape", "label": "Take me somewhere", "subtitle": "Propulsive and wide-screen, full of motion.", "ref": "pf_windows_down",
     "kw": ["drive", "driving", "road", "motion", "adventure", "escape", "energy", "energetic", "workout", "run", "running", "gym", "fast", "highway"]},
    {"key": "party", "label": "Turn it up", "subtitle": "Pure euphoria — hands in the air.", "ref": "pf_hands_up",
     "kw": ["party", "dance", "dancing", "hype", "club", "turn up", "celebrate", "banger", "upbeat", "fun", "pump", "hyped"]},
    {"key": "wind_down", "label": "Wind down", "subtitle": "Slow and weightless, for the drift to sleep.", "ref": "pf_static_starlight",
     "kw": ["sleep", "sleepy", "calm", "relax", "wind down", "chill", "ambient", "quiet", "bedtime", "unwind", "peaceful", "study", "focus", "soothe"]},
    {"key": "neon", "label": "Something with an edge", "subtitle": "Sleek, brooding, after-midnight.", "ref": "pf_neon_shadow",
     "kw": ["dark", "moody", "edgy", "midnight", "brooding", "cool", "sleek", "intense", "night", "neon"]},
]

DEFAULT_READINGS = ["sit_with", "company", "lift"]

STARTERS = [
    {"id": f"s{i}", "text": t}
    for i, t in enumerate([
        "something that feels like a rainy Sunday after heartbreak",
        "I want to feel hopeful again",
        "songs to cry to, alone at night",
        "keep me company while I cook",
        "a long night drive with the windows down",
        "turn it up — I want to dance",
        "help me wind down for sleep",
        "something with a dark edge after midnight",
    ])
]

SLIDERS = [
    {"id": "weight", "left": "Lighter", "right": "Heavier"},
    {"id": "pace", "left": "Slower", "right": "Faster"},
    {"id": "warmth", "left": "Cooler", "right": "Warmer"},
    {"id": "arousal", "left": "Calmer", "right": "More intense"},
    {"id": "hope", "left": "Bleaker", "right": "More hopeful"},
]

SAFETY_MESSAGE = (
    "Yeh sunna bhaari lagta hai, aur main isse kisi gaane se replace nahi karna "
    "chahta. Agar abhi kisi se baat kar sako toh behtar hoga."
)


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


# Episodes indexed by series, sorted by number.
EPS_BY_SERIES: dict[str, list[dict]] = {}
for _block in EPISODES:
    EPS_BY_SERIES[_block["series_id"]] = sorted(_block.get("episodes", []), key=lambda e: e["number"])


def _build_candidates() -> list[dict]:
    """One candidate per arc, with a small per-arc drift so deeper arcs differ
    (which lets an entry point land on 'track 16' rather than always track 1)."""
    out: list[dict] = []
    for series in CATALOG:
        base = AXES.get(series["series_id"])
        if not base:
            continue
        eps = EPS_BY_SERIES.get(series["series_id"], [])
        for j, arc in enumerate(series.get("arcs") or []):
            axes = dict(base)
            axes["weight"] = _clamp(axes["weight"] + j * 0.05, 0.0, 1.0)
            axes["pace"] = _clamp(axes["pace"] - j * 0.04, 0.0, 1.0)
            axes["hope"] = _clamp(axes["hope"] + j * 0.05, -1.0, 1.0)
            span = [e for e in eps if arc["start_episode"] <= e["number"] <= arc["end_episode"]]
            avg_sec = (sum(e.get("duration_sec") or 0 for e in span) / len(span)) if span else 240
            out.append({
                "content_id": arc["arc_id"],
                "series_id": series["series_id"],
                "series_title": series["title"],
                "entry_episode": arc["start_episode"],
                "arc_label": arc["label"],
                "axes": axes,
                "explanation": f"{VIBE.get(series['series_id'], '')} — {arc.get('summary', '')}",
                "duration_min": max(1, round(avg_sec / 60)),
            })
    return out


CANDIDATES = _build_candidates()


def _dist(a: dict, b: dict) -> float:
    return math.sqrt(sum((a.get(k, 0.5) - b.get(k, 0.5)) ** 2 for k in AXIS_KEYS))


def _pick_readings(text: str) -> list[dict]:
    q = (text or "").lower()
    scored = sorted(
        ({"it": it, "score": sum(1 for w in it["kw"] if w in q)} for it in INTENTS),
        key=lambda s: -s["score"],
    )
    chosen = [s["it"]["key"] for s in scored if s["score"] > 0]
    for k in DEFAULT_READINGS:
        if len(chosen) < 3 and k not in chosen:
            chosen.append(k)
    for it in INTENTS:
        if len(chosen) < 3 and it["key"] not in chosen:
            chosen.append(it["key"])
    chosen = chosen[:3]
    return [next(i for i in INTENTS if i["key"] == k) for k in chosen]


def _shelf_for(intent: dict, target: dict, finished: set[str]) -> dict:
    seen: set[str] = set()
    ranked = sorted(
        (c for c in CANDIDATES if c["series_id"] not in finished),
        key=lambda c: _dist(c["axes"], target),
    )
    results: list[dict] = []
    for c in ranked:
        if c["series_id"] in seen:
            continue
        seen.add(c["series_id"])
        entry_ep = next(
            (e for e in EPS_BY_SERIES.get(c["series_id"], []) if e["number"] == c["entry_episode"]),
            None,
        )
        results.append({
            "content_id": c["content_id"],
            "series_id": c["series_id"],
            "series_title": c["series_title"],
            "entry_episode": c["entry_episode"],
            "entry_label": (
                "Start from the beginning" if c["entry_episode"] <= 1
                else f"Start at track {c['entry_episode']} — {c['arc_label']}"
            ),
            "entry_title": entry_ep.get("title") if entry_ep else None,
            "entry_artist": entry_ep.get("synopsis") if entry_ep else None,
            "entry_audio_url": entry_ep.get("audio_url") if entry_ep else None,
            "explanation": c["explanation"],
            "duration_min": c["duration_min"],
        })
        if len(results) >= 4:
            break
    return {
        "id": f"shelf_{intent['key']}",
        "label": intent["label"],
        "subtitle": intent["subtitle"],
        "target_axes": target,
        "results": results,
    }


def _profile_view(p: dict) -> dict:
    hist = p.get("history") or []
    completed = sum(1 for h in hist if h.get("completed"))
    finished = [h["series_id"] for h in hist if h.get("completed") or h.get("liked") is False]
    attrs = p.get("attrs") or {}
    return {
        "persona_id": p["persona_id"],
        "display_name": p.get("display_name"),
        "slot": attrs.get("listening_time_slot"),
        "language": attrs.get("primary_language"),
        "completion_rate": round(completed / len(hist), 2) if hist else attrs.get("series_completion_rate"),
        "typical_dropoff_episode": attrs.get("typical_dropoff_episode"),
        "tolerance_for_heaviness": attrs.get("tolerance_for_heaviness"),
        "history_count": len(hist),
        "finished": sorted(set(finished))[:5],
    }


def _finished_set(profile_id) -> set[str]:
    p = next((x for x in PROFILES if x["persona_id"] == profile_id), None)
    if not p:
        return set()
    return {h["series_id"] for h in (p.get("history") or []) if h.get("completed") or h.get("liked") is False}


_SESSIONS: dict[str, dict] = {}


def _search(text: str, profile_id) -> dict:
    query_id = uuid.uuid4().hex[:8]
    _SESSIONS[query_id] = {"text": text, "profile_id": profile_id}

    # Safety gate — reuse the real distress detection, never a shelf of songs.
    if detect_distress(text or ""):
        return {
            "query_id": query_id,
            "mode": "safety",
            "safety_message": SAFETY_MESSAGE,
            "support_resources": SUPPORT_RESOURCES,
            "latency_ms": 1,
        }

    finished = _finished_set(profile_id)
    readings = _pick_readings(text)
    shelves = [_shelf_for(it, AXES[it["ref"]], finished) for it in readings]
    return {
        "query_id": query_id,
        "mode": "shelves",
        "parsed": {"text": text, "destination": readings[0]["key"], "sparsity_score": 0},
        "shelves": shelves,
        "latency_ms": 3,
    }


# --------------------------------------------------------------------------
# Lexical baseline — the genre/keyword search we argue against
# --------------------------------------------------------------------------
# Pure term overlap over song title + artist. NO mood axes, so it ranks the
# lexically-strongest match — which is how it surfaces the emotionally-wrong
# song for a feeling query. is_trap marks a hit whose collection mood is far
# from what the query PRIMARILY wants: lexically perfect, emotionally wrong.

_STOP = frozenset(
    "a an the and or of to in on at for with without from by is are was were be been "
    "i me my you your it its this that these those something anything some any like "
    "feels feel felt want wanted need needed after before".split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1 and t not in _STOP]


# Flat song list (title + artist) — the documents the baseline ranks over.
_ALL_SONGS: list[dict] = []
for _series in CATALOG:
    for _ep in EPS_BY_SERIES.get(_series["series_id"], []):
        _m = re.search(r"[?&]v=([^&]+)", _ep.get("audio_url") or "")
        _ALL_SONGS.append({
            "content_id": _m.group(1) if _m else f"{_series['series_id']}-{_ep['number']}",
            "title": _ep.get("title") or "",
            "artist": _ep.get("synopsis") or "",
            "series_id": _series["series_id"],
        })
_SONG_DOCS = [_tokenize(f"{s['title']} {s['artist']}") for s in _ALL_SONGS]
_DF: Counter = Counter()
for _doc in _SONG_DOCS:
    _DF.update(set(_doc))
_NDOCS = max(1, len(_SONG_DOCS))


def _idf(term: str) -> float:
    return math.log(1 + _NDOCS / (1 + _DF.get(term, 0)))


def _baseline_search(text: str, k: int) -> list[dict]:
    terms = list(dict.fromkeys(_tokenize(text)))
    if not terms:
        return []
    targets = [AXES[it["ref"]] for it in _pick_readings(text) if it["ref"] in AXES]
    scored: list[tuple[float, int, list[str]]] = []
    for i, doc in enumerate(_SONG_DOCS):
        if not doc:
            continue
        counts = Counter(doc)
        score = 0.0
        matched: list[str] = []
        for t in terms:
            if counts[t]:
                score += (1 + math.log(counts[t])) * _idf(t)
                matched.append(t)
        if score > 0:
            scored.append((score / math.sqrt(len(doc)), i, matched))
    scored.sort(key=lambda x: -x[0])
    out: list[dict] = []
    for _score, i, matched in scored[:k]:
        song = _ALL_SONGS[i]
        # Trap = lexically matched but far from what the query PRIMARILY wants.
        primary_dist = _dist(AXES.get(song["series_id"], {}), targets[0]) if targets else 0.0
        out.append({
            "content_id": song["content_id"],
            "series_title": song["title"],
            "snippet": f'{song["artist"]} · matched "{", ".join(matched[:3])}" — ranked on the words, not on how it feels.',
            "is_trap": primary_dist > 1.0,
        })
    return out


# --------------------------------------------------------------------------
# Router — same paths and shapes as app.mood.api
# --------------------------------------------------------------------------

router = APIRouter()


@router.get("/health")
def health():
    return {
        "arcs": len(CANDIDATES),
        "series": len(CATALOG),
        "episodes": sum(len(v) for v in EPS_BY_SERIES.values()),
        "reranker": "HeuristicSimple",
        "parser": "keyword",
        "engine": "simple",
        "source": "curated-music-catalog",
    }


@router.get("/starters")
def starters():
    return {"starters": STARTERS}


@router.get("/sliders")
def sliders():
    return {"sliders": SLIDERS}


@router.get("/profiles")
def profiles():
    return {"profiles": [_profile_view(p) for p in PROFILES]}


@router.post("/search")
def search(body: dict):
    return _search(body.get("text") or "", body.get("profile_id"))


@router.post("/clarify")
def clarify(body: dict):
    # This engine never asks a clarifying question; a skip just re-runs the query.
    prev = _SESSIONS.get(body.get("query_id"), {})
    return _search(prev.get("text") or "", prev.get("profile_id"))


@router.post("/refine")
def refine(body: dict):
    prev = _SESSIONS.get(body.get("query_id"), {})
    intent_key = str(body.get("shelf_id") or "").replace("shelf_", "")
    intent = next((i for i in INTENTS if i["key"] == intent_key), INTENTS[0])
    target = dict(body.get("current_axes") or AXES[intent["ref"]])
    for ax, delta in (body.get("slider_deltas") or {}).items():
        lo = -1.0 if ax == "valence" else 0.0
        try:
            target[ax] = _clamp(target.get(ax, 0.5) + float(delta) * 0.2, lo, 1.0)
        except (TypeError, ValueError):
            continue
    shelf = _shelf_for(intent, target, _finished_set(prev.get("profile_id")))
    shelf["id"] = body.get("shelf_id")  # preserve so the client replaces in place
    return {"query_id": body.get("query_id"), "mode": "shelves", "shelves": [shelf], "latency_ms": 2}


@router.get("/episodes/{series_id}")
def episodes(series_id: str, start: int = 1, limit: int = 12):
    eps = EPS_BY_SERIES.get(series_id)
    if not eps:
        return {"error": "unknown series", "series_id": series_id}
    start = max(1, start)
    chosen = [e for e in eps if e["number"] >= start][:limit]
    title = next((c["title"] for c in CATALOG if c["series_id"] == series_id), series_id)
    last = eps[-1]["number"]
    return {
        "series_id": series_id,
        "series_title": title,
        "start": start,
        "total": len(eps),
        "has_more": bool(chosen) and chosen[-1]["number"] < last,
        "episodes": chosen,
    }


@router.post("/baseline")
def baseline(body: dict):
    return {"results": _baseline_search(body.get("text") or "", int(body.get("k") or 3))}


@router.get("/debug/{query_id}")
def debug(query_id: str):
    return {"engine": "simple", "note": "heuristic engine — no retrieval trace"}
