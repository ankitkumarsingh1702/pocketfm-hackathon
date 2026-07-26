"""
Mood-First Search — MOCK API (H0 deliverable)

Returns real contract shapes with fake data. Frontend builds against this from
H1 and never waits for the pipeline. Ankit swaps the internals at H8; the
response shapes do not move.

    uvicorn mock_api:app --reload --port 8000

Endpoints
    GET  /starters          -> empty state
    POST /search            -> shelves | clarify | safety
    POST /clarify           -> shelves (after the one question)
    POST /refine            -> shelves (slider drag, no LLM)
    GET  /sliders           -> slider config for the refine UI
"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI

from mood_config import (
    DESTINATION_TARGETS,
    MOOD_STARTERS,
    SHELF_COPY,
    SLIDER_LABELS,
    build_clarifying_question,
    heuristic_sparsity,
    rank_destinations,
    slider_deltas_to_axis_deltas,
)
from schemas import (
    ClarifyAnswerRequest,
    MoodAxes,
    MoodQuery,
    RefineRequest,
    ResultCard,
    SearchResponse,
    Shelf,
    Situation,
)

app = FastAPI(title="Mood-First Search (mock)")

_SESSIONS: dict[str, MoodQuery] = {}

_DISTRESS = ("kill myself", "end it all", "want to die", "self harm",
             "marna hai", "jeene ka mann nahi", "stop feeling anything")

from mood_config import SUPPORT_RESOURCES as SUPPORT


# --------------------------------------------------------------------------
# Fake parser. Ankit replaces this with LLM + Instructor at H1-H4.
# Signature and return type stay identical.
# --------------------------------------------------------------------------

def fake_parse(text: str) -> MoodQuery:
    low = text.lower()
    felt: list[str] = []
    for w in ("heartbreak", "lonely", "sad", "tired", "akela", "udaas", "bore"):
        if w in low:
            felt.append(w)

    return MoodQuery(
        raw_text=text,
        situation=Situation(
            weather="rain" if ("rain" in low or "baarish" in low) else None,
            time_of_day="night" if ("night" in low or "raat" in low) else None,
            solitude="alone" if ("alone" in low or "akela" in low) else "unknown",
        ),
        felt_state=felt,
        intensity=0.7 if felt else 0.3,
        destination="sleep" if ("sona" in low or "neend" in low or "sleep" in low) else None,
        sparsity_score=heuristic_sparsity(text),
        distress_flag=any(p in low for p in _DISTRESS),
    )


def fake_results(destination: str, target: MoodAxes) -> list[ResultCard]:
    """Placeholder cards. Sahil's retriever replaces this at H8."""
    label, _ = SHELF_COPY[destination]
    return [
        ResultCard(
            content_id=f"{destination}_{i}",
            series_id=f"mock_s{i}",
            series_title=f"[mock series {i}]",
            arc_label="the monsoon arc",
            entry_episode=34 + i,
            entry_label=f"Start at Ep {34 + i} — the monsoon arc",
            explanation="Because you didn't ask to feel better — you asked to feel it properly.",
            vibe_sentence="Slow, rain-soaked, and it does not rush you.",
            duration_min=22,
            audio_verified=(i == 0),
            score=round(0.92 - i * 0.07, 2),
        )
        for i in range(3)
    ]


def build_shelves(query: MoodQuery) -> list[Shelf]:
    shelves = []
    for dest in rank_destinations(query):
        label, subtitle = SHELF_COPY[dest]
        target = DESTINATION_TARGETS[dest]
        shelves.append(
            Shelf(
                id=f"shelf_{dest}",
                label=label,
                subtitle=subtitle,
                destination=dest,
                target_axes=target,
                results=fake_results(dest, target),
            )
        )
    return shelves


def respond(query: MoodQuery, query_id: str, t0: float) -> SearchResponse:
    ms = int((time.time() - t0) * 1000)

    if query.distress_flag:
        return SearchResponse(
            query_id=query_id, mode="safety", parsed=query,
            safety_message=(
                "Yeh sunna bhaari lagta hai, aur main isse kisi kahani se replace "
                "nahi karna chahta. Agar abhi kisi se baat kar sako toh behtar hoga."
            ),
            support_resources=SUPPORT,
            latency_ms=ms,
        )

    question = build_clarifying_question(query)
    if question is not None:
        return SearchResponse(
            query_id=query_id, mode="clarify", parsed=query,
            clarifying_question=question, latency_ms=ms,
        )

    return SearchResponse(
        query_id=query_id, mode="shelves", parsed=query,
        shelves=build_shelves(query), latency_ms=ms,
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/starters")
def starters():
    return {"starters": [s.model_dump() for s in MOOD_STARTERS]}


@app.get("/sliders")
def sliders():
    return {
        "sliders": [
            {"id": k, "left": v[0], "right": v[1]} for k, v in SLIDER_LABELS.items()
        ]
    }


@app.post("/search")
def search(body: dict):
    t0 = time.time()
    query = fake_parse(body.get("text", ""))
    query_id = str(uuid.uuid4())[:8]
    _SESSIONS[query_id] = query
    return respond(query, query_id, t0)


@app.post("/clarify")
def clarify(req: ClarifyAnswerRequest):
    t0 = time.time()
    query = _SESSIONS.get(req.query_id)
    if query is None:
        return {"error": "unknown query_id"}

    if req.option_id:
        from mood_config import DEFAULT_CLARIFY, SESSION_CLARIFY
        for q in (DEFAULT_CLARIFY, SESSION_CLARIFY):
            for opt in q.options:
                if opt.id == req.option_id and opt.resolves_destination:
                    query = query.model_copy(
                        update={"destination": opt.resolves_destination}
                    )

    # Skipped or unresolved: drop sparsity so we answer with shelves rather
    # than asking again. We never ask twice.
    query = query.model_copy(update={"sparsity_score": 0.0})
    _SESSIONS[req.query_id] = query
    return respond(query, req.query_id, t0)


@app.post("/refine")
def refine(req: RefineRequest):
    """Pure vector math. No LLM. This is the sub-200ms path."""
    t0 = time.time()
    deltas = slider_deltas_to_axis_deltas(req.slider_deltas)
    new_axes = req.current_axes.nudge(deltas)
    query = _SESSIONS.get(req.query_id) or fake_parse("")
    dest = req.shelf_id.replace("shelf_", "")
    label, subtitle = SHELF_COPY[dest]

    shelf = Shelf(
        id=req.shelf_id, label=label, subtitle=subtitle, destination=dest,
        target_axes=new_axes, results=fake_results(dest, new_axes),
    )
    return SearchResponse(
        query_id=req.query_id, mode="shelves", parsed=query,
        shelves=[shelf], latency_ms=int((time.time() - t0) * 1000),
    )
