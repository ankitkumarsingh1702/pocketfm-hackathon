"""HTTP service around the pipeline.

A conversion takes five to eight minutes — one model call per scene, plus three
alignment votes — which is far too long to hold a request open. So work runs as
a job: POST returns an id immediately, and the client polls until it is done.

The pipeline modules are used exactly as the CLI uses them. Nothing in
extract/transform/verify is reimplemented here, so changes there arrive in the
service without touching this file.

    POST /api/extract        {"text": "..."}                 -> job
    POST /api/extract/file   multipart: file                 -> job
    POST /api/convert        {"text": "...", "genre": "..."} -> job
    POST /api/convert/file   multipart: file, genre          -> job
    GET  /api/jobs/{id}                                      -> status / result
    GET  /api/genres                                         -> the five packs
    GET  /health
"""

import hashlib
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cache import cached_skeleton, cached_text
from extract import extract_clean, lint_skeleton
from genre_pack import available_packs, load_pack
from models import StorySkeleton
from transform import plan_scenes, transform
from verify import ALIGN_VOTES, verify_prose

# A story has to be long enough to have a plot and short enough to finish. The
# ceiling is not a model limit — it is a reminder that this pipeline is built for
# short fiction; see LONGFORM.md for what novel length would require.
MIN_CHARS = 400
MAX_CHARS = int(os.environ.get("MAX_CHARS", "60000"))

# Two at a time. Each job is mostly waiting on Vertex, but every extra concurrent
# job multiplies quota pressure and memory for no wall-clock gain to the user.
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))

# Jobs live in memory, so the service must run as a single instance. Firestore
# would be the fix if this ever needs to scale out; see the deploy script.
MAX_JOBS_RETAINED = 200

# A real run emits roughly twenty events — three or four per stage, three per
# scene. This is a runaway guard, not a budget: the oldest are dropped so the
# tail the client is actually reading always survives.
MAX_EVENTS_RETAINED = 200

app = FastAPI(
    title="Story genre converter",
    description="Rewrite a story in another genre, and score how much of the plot survived.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(os.environ.get("CORS_ORIGINS") or "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="job")
_jobs: Dict[str, "Job"] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class Job(BaseModel):
    """The unit the client polls.

    The progress fields exist so a caller can render a real progress bar rather
    than a spinner. A conversion is five to eight minutes, which is long enough
    that "working…" reads as "hung": `stage` says which phase, `step`/`steps`
    say where inside it, and `percent` blends the two into one number across the
    whole job. All three are advisory — `status` is the only field to branch on.

    `events` and `partial` exist for the same reason taken further. A bar that
    moves proves the job is alive but says nothing about what it is doing, and
    the interesting artifacts — the plot skeleton, each scene as it is written —
    are finished minutes before the job is. So they are published the moment
    they exist rather than held back for the final payload:

        events   append-only log of what happened, in order, with timings
        partial  the result so far — skeleton, scene plan, scenes with prose

    Anything in `partial` is final for that piece: a scene already written is
    not rewritten later. `result` still carries the authoritative whole at the
    end, so a client that ignores both fields behaves exactly as before.
    """

    id: str
    kind: str = Field(description="extract | convert")
    status: str = Field(description="queued | running | done | error")
    genre: Optional[str] = None
    stage: Optional[str] = Field(None, description="extract | transform | verify")
    progress: Optional[str] = Field(None, description="Human-readable detail, e.g. 'scene 4/7'.")
    step: Optional[int] = Field(None, description="Units finished within the current stage.")
    steps: Optional[int] = Field(None, description="Units the current stage will take, when known.")
    percent: Optional[int] = Field(None, description="Whole-job progress, 0-100.")
    events: List[dict] = Field(
        default_factory=list,
        description="Append-only log: {seq, at, stage, note, detail}. Newest last.",
    )
    partial: dict = Field(
        default_factory=dict,
        description="Result pieces published as they finish: skeleton, scene_plan, scenes.",
    )
    created_at: float
    updated_at: float
    result: Optional[dict] = None
    error: Optional[str] = None


class TextIn(BaseModel):
    text: str = Field(description="The story, as plain text.")


class ConvertIn(TextIn):
    genre: str = Field(description="One of the available genre packs.")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _key(text: str, suffix: str = "") -> str:
    """Content-addressed cache key, so the same story is never paid for twice."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"api_{digest}{suffix}"


def _clean_text(raw: str, source: str) -> str:
    text = (raw or "").replace("\r\n", "\n").strip()
    if len(text) < MIN_CHARS:
        raise HTTPException(
            422,
            f"{source} is too short to have a plot ({len(text)} characters, "
            f"minimum {MIN_CHARS}). Paste a full short story.",
        )
    if len(text) > MAX_CHARS:
        raise HTTPException(
            413,
            f"{source} is {len(text)} characters; this service handles up to "
            f"{MAX_CHARS}. Novel-length input needs a different pipeline.",
        )
    return text


async def _read_upload(file: UploadFile) -> str:
    """Pull plain text out of an uploaded file."""
    name = (file.filename or "").lower()
    if not name.endswith((".txt", ".md", ".text")):
        raise HTTPException(415, f"Unsupported file type {name!r}. Upload a .txt file.")
    raw = await file.read()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return _clean_text(raw.decode(encoding), "The uploaded file")
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "Could not decode the file as text. Save it as UTF-8 .txt.")


def _check_genre(genre: str) -> str:
    if genre not in available_packs():
        raise HTTPException(
            422, f"Unknown genre {genre!r}. Available: {', '.join(available_packs())}."
        )
    return genre


# Where each stage starts and ends on a 0-1 whole-job scale. The spans are wall
# clock, not call count: transform is one model call per scene and dominates,
# extract is a single call, and verify is ALIGN_VOTES * 2 calls at the end.
# Deliberately not measured — an honest estimate that moves steadily beats a
# precise one that jumps.
_CONVERT_SPANS = {"extract": (0.00, 0.10), "transform": (0.10, 0.80), "verify": (0.80, 1.00)}
_EXTRACT_SPANS = {"extract": (0.00, 1.00)}


def _percent(kind: str, stage: str, step: int, steps: Optional[int]) -> int:
    """Blend stage position and within-stage position into one 0-100 number."""
    spans = _EXTRACT_SPANS if kind == "extract" else _CONVERT_SPANS
    start, end = spans.get(stage, (0.0, 1.0))
    fraction = (step / steps) if steps else 0.0
    return max(0, min(100, round((start + (end - start) * fraction) * 100)))


def _touch(job: Job, **fields) -> None:
    with _lock:
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = time.time()


def _submit(kind: str, text: str, genre: Optional[str] = None) -> Job:
    job = Job(
        id=uuid.uuid4().hex[:12],
        kind=kind,
        status="queued",
        genre=genre,
        created_at=time.time(),
        updated_at=time.time(),
    )
    with _lock:
        _jobs[job.id] = job
        if len(_jobs) > MAX_JOBS_RETAINED:  # drop the oldest, keep memory bounded
            for stale in sorted(_jobs.values(), key=lambda j: j.created_at)[:-MAX_JOBS_RETAINED]:
                _jobs.pop(stale.id, None)
    _pool.submit(_run, job, text, genre)
    return job


def _skeleton_payload(skeleton: StorySkeleton) -> dict:
    return {
        "logline": skeleton.logline,
        "roles": [r.model_dump() for r in skeleton.roles],
        "beats": [b.model_dump() for b in skeleton.beats],
        "counts": {
            "beats": len(skeleton.beats),
            "load_bearing": len(skeleton.load_bearing_ids),
            "edges": len(skeleton.causal_edges),
        },
    }


def _run(job: Job, text: str, genre: Optional[str]) -> None:
    """The whole job, on a worker thread. Mirrors pipeline.convert."""
    started = time.time()

    # Built here and republished as fresh copies rather than mutated in place.
    # get_job serialises the job outside the lock, on the request thread, and a
    # list being appended to while it is iterated is exactly the kind of race
    # that only ever shows up in front of an audience.
    events: List[dict] = []
    scenes: List[dict] = []
    partial: Dict[str, object] = {}

    # verify.verify_prose runs its ballots on a pool, so `advance` is called
    # from several threads at once during that stage. Without this, two ballots
    # landing together read the same len(events) and mint the same `seq` — which
    # a client keying a list by it renders as one row instead of two. Held
    # across the _touch as well, so the published snapshot is never a stale one
    # overwriting a newer one. Nothing else takes this lock, so nesting the
    # module `_lock` inside it cannot deadlock.
    progress_lock = threading.Lock()

    def advance(
        stage: str,
        note: str,
        step: int = 0,
        steps: Optional[int] = None,
        detail: Optional[dict] = None,
    ) -> None:
        """Publish one progress update, including the whole-job percentage.

        Also clears `queued`: anything calling this is, by definition, running.
        Keeping the two in one place is what stops a client from being told
        "waiting for a worker" while a model call is already in flight.
        """
        with progress_lock:
            events.append(
                {
                    "seq": len(events) + 1,
                    "at": round(time.time() - started, 1),
                    "stage": stage,
                    "note": note,
                    "detail": detail or {},
                }
            )
            del events[:-MAX_EVENTS_RETAINED]
            _touch(
                job,
                status="running",
                stage=stage,
                progress=note,
                step=step,
                steps=steps,
                percent=_percent(job.kind, stage, step, steps),
                events=list(events),
            )

    def publish(**pieces: object) -> None:
        """Make a finished piece of the result visible before the job ends."""
        with progress_lock:
            partial.update(pieces)
            _touch(job, partial=dict(partial))

    try:
        # ---------------------------------------------------------- extract --
        extracted_live = False

        def on_extract(done: int, total: int, note: str, detail: Optional[dict] = None) -> None:
            nonlocal extracted_live
            extracted_live = True
            advance("extract", note, done, total, detail)

        # No opening event of its own: extract_clean's first report is "reading
        # the story for its plot", which fires before the model call and says
        # the same thing. A cache hit skips it and is announced below instead.
        source = cached_skeleton(
            _key(text), lambda: extract_clean(text, on_progress=on_extract)[0]
        )
        if not extracted_live:
            advance("extract", "reused the skeleton from an earlier run", 2, 2, {"cached": True})

        lint = lint_skeleton(source)
        skeleton = _skeleton_payload(source)
        # The skeleton is the whole answer for an extract job and the first real
        # artifact of a convert one. Published now either way, so a convert can
        # show the plot it is about to rewrite instead of five more minutes of bar.
        publish(skeleton=skeleton, lint=lint)
        advance(
            "extract",
            f"plot skeleton ready — {len(source.beats)} beats, "
            f"{len(source.load_bearing_ids)} load-bearing",
            2,
            2,
            {"beats": len(source.beats), "load_bearing": len(source.load_bearing_ids)},
        )

        if job.kind == "extract":
            _touch(
                job,
                status="done",
                stage=None,
                progress=None,
                step=None,
                steps=None,
                percent=100,
                result={
                    "skeleton": skeleton,
                    "lint": lint,
                    "seconds": round(time.time() - started, 1),
                },
            )
            return

        # -------------------------------------------------------- transform --
        pack = load_pack(genre)
        # plan_scenes is deterministic and free, so the scene count — and with it
        # a real denominator for the progress bar — is known before the first
        # model call rather than discovered on the way through.
        planned = plan_scenes(source)
        plan = [
            {
                "scene": index + 1,
                "beat_ids": [b.id for b in group],
                "load_bearing": [b.id for b in group if b.load_bearing],
            }
            for index, group in enumerate(planned)
        ]
        publish(scene_plan=plan, scenes=[])
        advance(
            "transform",
            f"planned {len(planned)} scenes from {len(source.beats)} beats",
            0,
            len(planned),
            {"scenes": len(planned), "plan": plan},
        )

        transformed_live = False

        def on_scene(done: int, total: int, note: str, detail: Optional[dict] = None) -> None:
            nonlocal transformed_live
            transformed_live = True
            info = dict(detail or {})
            prose = info.pop("prose", None)  # travels in `partial`, not in every event
            if info.get("phase") == "written" and prose is not None:
                scenes.append({**info, "prose": prose})
                publish(scenes=list(scenes), words=sum(s.get("words", 0) for s in scenes))
            advance("transform", note, done, total, info)

        rewritten = cached_text(
            _key(text, f"__{genre}"),
            lambda: transform(source, pack, on_progress=on_scene),
        )
        if not transformed_live:
            # A cache hit skips every scene callback, so the prose would
            # otherwise never reach `partial` at all.
            publish(prose=rewritten, words=len(rewritten.split()))
            advance(
                "transform",
                "reused the rewrite from an earlier run",
                1,
                1,
                {"cached": True, "words": len(rewritten.split())},
            )

        # ----------------------------------------------------------- verify --
        # Scored against the prose rather than a skeleton re-extracted from it:
        # the round trip through a second extraction loses the nuance the
        # comparison depends on. See verify.score_prose.
        def on_check(done: int, total: int, note: str, detail: Optional[dict] = None) -> None:
            advance("verify", note, done, total, detail)

        advance(
            "verify",
            f"checking all {len(source.beats)} beats against the rewrite",
            0,
            ALIGN_VOTES * 2,
            {"votes": ALIGN_VOTES, "beats": len(source.beats), "edges": len(source.causal_edges)},
        )
        detail = verify_prose(source, rewritten, on_progress=on_check)

        advance(
            "verify",
            f"fidelity {detail['fidelity']:.0%}",
            ALIGN_VOTES * 2,
            ALIGN_VOTES * 2,
            {"fidelity": detail["fidelity"]},
        )

        _touch(
            job,
            status="done",
            stage=None,
            progress=None,
            step=None,
            steps=None,
            percent=100,
            result={
                "genre": genre,
                "rewritten": rewritten,
                "words": len(rewritten.split()),
                "fidelity": detail["fidelity"],
                "detail": detail,
                "source_skeleton": skeleton,
                "seconds": round(time.time() - started, 1),
            },
        )
    except Exception as exc:  # surfaced to the caller rather than swallowed
        # The events and partials stay: what did finish is exactly what makes an
        # error legible, and throwing it away leaves the user with a bare string.
        _touch(job, status="error", stage=None, progress=None, step=None, steps=None, error=str(exc))


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Liveness. Deliberately touches nothing that needs credentials."""
    with _lock:
        running = sum(1 for j in _jobs.values() if j.status == "running")
    return {
        "status": "ok",
        "genres": available_packs(),
        "jobs": {"tracked": len(_jobs), "running": running},
    }


@app.get("/")
def root() -> dict:
    return {
        "service": "story genre converter",
        "docs": "/docs",
        "endpoints": [
            "POST /api/extract",
            "POST /api/extract/file",
            "POST /api/convert",
            "POST /api/convert/file",
            "GET /api/jobs/{id}",
            "GET /api/genres",
        ],
    }


@app.get("/api/genres")
def genres() -> List[dict]:
    """The packs, so a client can build a picker without hardcoding names."""
    return [
        {
            "name": name,
            "premise": pack.premise,
            "pacing": pack.pacing_curve,
            "taboo_moves": pack.taboo_moves,
        }
        for name, pack in ((n, load_pack(n)) for n in available_packs())
    ]


@app.post("/api/extract", response_model=Job)
def extract_text(body: TextIn = Body(...)) -> Job:
    return _submit("extract", _clean_text(body.text, "The pasted text"))


@app.post("/api/extract/file", response_model=Job)
async def extract_file(file: UploadFile = File(...)) -> Job:
    return _submit("extract", await _read_upload(file))


@app.post("/api/convert", response_model=Job)
def convert_text(body: ConvertIn = Body(...)) -> Job:
    return _submit("convert", _clean_text(body.text, "The pasted text"), _check_genre(body.genre))


@app.post("/api/convert/file", response_model=Job)
async def convert_file(file: UploadFile = File(...), genre: str = Form(...)) -> Job:
    return _submit("convert", await _read_upload(file), _check_genre(genre))


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"No job {job_id!r}. Jobs are held in memory and lost on restart.")
    return job


@app.get("/api/jobs", response_model=List[Job])
def list_jobs(limit: int = 25) -> List[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: -j.created_at)[:limit]
