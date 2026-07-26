"""
Mood-First Search — real service.

Same endpoints and the same frozen contract as the H0 mock, with the real
retrieval stack behind them. Frontend needs no change: point it here.

STILL FAKE: `fake_parse`. The parser is Ankit's H1-4 block and is the one
remaining seam. Everything downstream of MoodQuery is real.

    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from dataclasses import asdict

from fastapi import FastAPI

from embeddings import default_embedder
from episodes import EpisodeStore, derive_stub_episodes
from baseline import GenreBaseline
from parser import default_parser
from persona import build_demo_panel, load_profiles
from mood_config import (
    MOOD_STARTERS, SLIDER_LABELS, SUPPORT_RESOURCES, build_clarifying_question,
)
from rerank import default_reranker
from schemas import ClarifyAnswerRequest, MoodQuery, RefineRequest, SearchResponse
from search import MoodSearchEngine
from seed_catalog import build_seed_catalog
from store import MoodStore

INDEX_PATH = os.environ.get("MOOD_INDEX", "/tmp/moodstore")

app = FastAPI(title="Mood-First Search")
_SESSIONS: dict[str, MoodQuery] = {}


def _build_engine() -> MoodSearchEngine:
    embedder = default_embedder()
    if Path(INDEX_PATH).exists():
        store = MoodStore.load(INDEX_PATH, embedder)
    else:
        # Fixture fallback so the service always boots. Ritik's real
        # fingerprints land at INDEX_PATH and this branch stops firing.
        store = MoodStore(embedder)
        store.add(build_seed_catalog())
    return MoodSearchEngine(store, reranker=default_reranker())


engine = _build_engine()
parser = default_parser()
baseline = GenreBaseline(engine.store)

EPISODES_PATH = os.environ.get("MOOD_EPISODES", "/tmp/moodepisodes.jsonl")
if Path(EPISODES_PATH).exists():
    EPISODES = EpisodeStore.load(EPISODES_PATH)
else:
    # Derive stubs straight from the index so /playing is never empty. Real
    # episode data replaces this via MOOD_EPISODES.
    from catalog_ingest import SourceArc, SourceSeries

    EPISODES = EpisodeStore()
    _seen: set[str] = set()
    for _fp in engine.store.fingerprints:
        if _fp.series_id in _seen:
            continue
        _seen.add(_fp.series_id)
        _arcs = [
            SourceArc(arc_id=f.content_id, label=f.arc_label,
                      start_episode=f.entry_episode, end_episode=f.episode_span[1],
                      summary="")
            for f in engine.store.fingerprints if f.series_id == _fp.series_id
        ]
        EPISODES.add(derive_stub_episodes(SourceSeries(
            series_id=_fp.series_id, title=_fp.series_title, synopsis="",
            total_episodes=max(f.episode_span[1] for f in engine.store.fingerprints
                               if f.series_id == _fp.series_id),
            source="derived", language=_fp.language, arcs=_arcs,
        )))

PANEL_PATH = os.environ.get("DEMO_PANEL", "/tmp/demo_panel.json")
if Path(PANEL_PATH).exists():
    PROFILES = {p.persona_id: p for p in load_profiles(PANEL_PATH)}
else:
    from evaluate import synthetic_personas
    PROFILES = {p.persona_id: p for p in
                build_demo_panel(synthetic_personas(150), engine.store, n=10)}


def _respond(query: MoodQuery, query_id: str, t0: float, profile=None) -> SearchResponse:
    ms = lambda: int((time.time() - t0) * 1000)

    if query.distress_flag:
        return SearchResponse(
            query_id=query_id, mode="safety", parsed=query,
            safety_message=(
                "Yeh sunna bhaari lagta hai, aur main isse kisi kahani se "
                "replace nahi karna chahta. Agar abhi kisi se baat kar sako toh "
                "behtar hoga."
            ),
            support_resources=SUPPORT_RESOURCES, latency_ms=ms(),
        )

    question = build_clarifying_question(query)
    if question is not None:
        return SearchResponse(
            query_id=query_id, mode="clarify", parsed=query,
            clarifying_question=question, latency_ms=ms(),
        )

    shelves = engine.search(query, profile=profile)
    if not shelves:
        # Every shelf came back empty. Ask rather than show a blank screen --
        # a question is recoverable, an empty result is a dead end.
        return SearchResponse(
            query_id=query_id, mode="clarify", parsed=query,
            clarifying_question=build_clarifying_question(
                query.model_copy(update={"destination": None, "sparsity_score": 1.0})
            ),
            latency_ms=ms(),
        )

    return SearchResponse(
        query_id=query_id, mode="shelves", parsed=query,
        shelves=shelves, latency_ms=ms(),
    )


@app.get("/health")
def health():
    return {
        "arcs": len(engine.store),
        "series": len({f.series_id for f in engine.store.fingerprints}),
        "tier_a": sum(f.audio_verified for f in engine.store.fingerprints),
        "episodes": len(EPISODES),
        "reranker": type(engine.reranker).__name__,
        "parser": "llm" if parser.client else "heuristic",
        "embedder": type(engine.store.embedder).__name__,
    }


@app.get("/starters")
def starters():
    return {"starters": [s.model_dump() for s in MOOD_STARTERS]}


@app.get("/sliders")
def sliders():
    return {"sliders": [{"id": k, "left": v[0], "right": v[1]}
                        for k, v in SLIDER_LABELS.items()]}


@app.post("/search")
def search(body: dict):
    t0 = time.time()
    query = parser.parse(body.get("text", ""))
    query_id = str(uuid.uuid4())[:8]
    profile = PROFILES.get(body.get("profile_id"))
    _SESSIONS[query_id] = (query, profile)
    return _respond(query, query_id, t0, profile)


@app.post("/clarify")
def clarify(req: ClarifyAnswerRequest):
    t0 = time.time()
    entry = _SESSIONS.get(req.query_id)
    if entry is None:
        return {"error": "unknown query_id"}
    query, profile = entry

    if req.option_id:
        from mood_config import DEFAULT_CLARIFY, SESSION_CLARIFY
        for q in (DEFAULT_CLARIFY, SESSION_CLARIFY):
            for opt in q.options:
                if opt.id == req.option_id and opt.resolves_destination:
                    query = query.model_copy(
                        update={"destination": opt.resolves_destination}
                    )

    query = query.model_copy(update={"sparsity_score": 0.0})
    _SESSIONS[req.query_id] = (query, profile)
    return _respond(query, req.query_id, t0, profile)


@app.post("/refine")
def refine(req: RefineRequest):
    t0 = time.time()
    query = (_SESSIONS.get(req.query_id) or (parser.parse(""), None))[0]
    destination = req.shelf_id.replace("shelf_", "")
    shelf = engine.refine(query, destination, req.current_axes, req.slider_deltas)
    if shelf is None:
        return {"error": "no results after refine", "shelf_id": req.shelf_id}
    return SearchResponse(
        query_id=req.query_id, mode="shelves", parsed=query,
        shelves=[shelf], latency_ms=int((time.time() - t0) * 1000),
    )


@app.get("/debug/{query_id}")
def debug(query_id: str):
    """What retrieval did. Not user-facing -- this is the shelf-came-back-thin tool."""
    entry = _SESSIONS.get(query_id)
    if entry is None:
        return {"error": "unknown query_id"}
    query, profile = entry
    return {
        "parsed": query.model_dump(),
        "profile": profile.persona_id if profile else None,
        "blocked": engine.retriever.debug_blocked(query),
        "shelves": [asdict(d) for d in engine.last_debug],
    }


@app.post("/baseline")
def baseline_search(body: dict):
    """Genre/keyword search over the same catalog. Lab tab only.

    Shipped as an endpoint rather than a hardcoded screenshot so the comparison
    is live and runs on whatever the judge types.
    """
    hits = baseline.search(body.get("text", ""), k=int(body.get("k", 3)))
    return {"results": [asdict(h) for h in hits]}


@app.get("/profiles")
def profiles():
    """The 10 curated demo listeners. Mood-query tab reads this for the picker."""
    return {"profiles": [
        {
            "persona_id": p.persona_id,
            "display_name": p.display_name,
            "slot": p.slot,
            "language": p.language,
            "completion_rate": round(p.completion_rate, 2),
            "history_count": len(p.history),
            "finished": sorted(p.finished_series())[:5],
        }
        for p in PROFILES.values()
    ]}


@app.get("/episodes/{series_id}")
def episodes(series_id: str, start: int = 1, limit: int = 12):
    """The doorway fetch. Defaults to `start`, not episode 1.

    A listener sent to episode 34 should not have to scroll past 33 episodes
    nobody told them to play. Everything before the entry point is still
    reachable — `start=1` returns it — it just isn't the default.
    """
    title = next(
        (fp.series_title for fp in engine.store.fingerprints
         if fp.series_id == series_id),
        series_id,
    )
    window = EPISODES.window(series_id, title, start=max(1, start), limit=limit)
    if not window.episodes and window.total == 0:
        return {"error": "unknown series", "series_id": series_id}
    return {
        "series_id": window.series_id,
        "series_title": window.series_title,
        "start": window.start,
        "total": window.total,
        "has_more": window.has_more,
        "episodes": [e.model_dump() for e in window.episodes],
    }
