# Mood-First Search — running it on real data

How the source files become a live index, what has to be set, and how to tell
whether what you are looking at is real. Companion to
[SOURCE_SCHEMA.md](SOURCE_SCHEMA.md), which covers how to author the files.

---

## 1. The pipeline, end to end

```
catalog.json  episodes.json  profiles.json     ← you author these
      │             │              │
      ▼             ▼              │
  validate_sources.py  ────────────┤            ← blocks on cross-file breaks
      │                            │
      ▼                            │
  app.mood.sources  (one LLM call per arc)      ← the only expensive step
      │                            │
      ├── moodstore/               │            → MOOD_INDEX
      │     vectors.npz            │
      │     fingerprints.jsonl     │
      └── moodstore.episodes.jsonl │            → MOOD_EPISODES
                                   └──────────  → DEMO_PANEL
```

Three commands:

```bash
cd backend
python -m app.mood.validate_sources --catalog catalog.json --episodes episodes.json --profiles profiles.json
python -m app.mood.sources --local catalog.json --episodes episodes.json --out ./moodstore
MOOD_INDEX=./moodstore MOOD_EPISODES=./moodstore.episodes.jsonl DEMO_PANEL=./profiles.json \
  uvicorn app.main:app --port 8000
```

Ingest is the only step that costs money or time: one LLM call per **arc**, so
~600 series × 3 arcs ≈ 1,800 calls. Episodes are never fingerprinted — at ~150
episodes each that would be ~90,000 calls for a signal that already exists at the
right granularity.

**Re-run ingest after any change to `catalog.json` or `episodes.json`.** The
service reads the built stores, not your source files. `profiles.json` is the
exception: `DEMO_PANEL` is read directly, so a restart is enough.

---

## 2. Configuration

### Environment variables

| Variable | Default | Unset means | Set it to |
|---|---|---|---|
| `MOOD_INDEX` | `/tmp/moodstore` | **Synthetic seed fixture** — 48 invented series, results that look real and are not | The directory `--out` wrote |
| `MOOD_EPISODES` | `/tmp/moodepisodes.jsonl` | Numbered stubs, Play disabled on every episode | The `.episodes.jsonl` the same run wrote |
| `DEMO_PANEL` | `/tmp/demo_panel.json` | Ten synthesised listeners with invented histories | Your `profiles.json` |
| `MOOD_EMBEDDER` | *(auto)* | Vertex → sentence-transformers → hashing | Leave unset. `hashing` reduces the semantic term to character-trigram overlap |
| `MOOD_EMBED_MODEL` | `text-embedding-005` | — | Leave unless the region lacks it. Read at import, so it must be set before start |
| `PERSONA_PANEL` | *(none)* | `evaluate.py` uses 200 synthetic stand-ins | Your real panel, for the eval harness only. The API never reads this |

The `/tmp` defaults are not viable in production: on Cloud Run `/tmp` is a
per-instance tmpfs, so it is empty on every cold start. Bake the stores into the
image or mount them.

### Settings (from `app/config.py`, overridable by env or `backend/.env`)

`google_cloud_project`, `vertex_location`, `llm_provider` (`gemini`),
`gemini_model`, and `cors_origins` — which must include the real frontend origin.
Mood does not read the Firestore, Neo4j, or per-lens model settings.

### Not yet wired into deployment

No workflow or deploy script sets `MOOD_INDEX`, `MOOD_EPISODES`, or `DEMO_PANEL`.
**A deploy today serves the synthetic fixture**, and the only place that admits it
is `/api/mood/health`. Wiring those three into the Cloud Run service — and getting
the store files into the image — is the remaining step before this is genuinely
live.

---

## 3. The failure mode that matters: everything degrades silently

Every expensive dependency has a fallback, which is correct for demo day and
means **nothing ever errors**. Without Application Default Credentials:

- the embedder falls back to lexical hashing — synonymy stops working, so the
  0.30 semantic term stops doing its job;
- the parser, reranker, and persona judge all fall back to heuristics.

No exception, no log line, no visible change. The one signal is:

```bash
curl -s localhost:8000/api/mood/health | python -m json.tool
```

Read four fields before trusting anything on screen:

| Field | Real | Fixture / degraded |
|---|---|---|
| `arcs` / `series` | your counts | `145` / `51` = the seed fixture |
| `semantic` | `true` | `false` = lexical hashing, not embeddings |
| `parser` | `"llm"` | `"heuristic"` = no LLM resolved |
| `reranker` | `"LLMReranker"` | `"HeuristicReranker"` = template explanations |

`flagged_audio` is a catalog flag, **not** evidence of an audio pipeline. There
isn't one in this build; the field is deliberately not surfaced in the UI.

To check credentials directly, one real round trip:

```bash
python -m app.mood.llm_client
```

### One hard failure worth knowing

The index, episode store, and panel are all built at **import** time. A malformed
file raises there, and the guard in `app/main.py` catches it and leaves
`/api/mood` unmounted — the rest of the studio keeps working, but every mood
route, including `/api/mood/health`, returns 404 with a single line in the logs.
If the lens is entirely absent, read the startup log before anything else. This is
what `validate_sources.py` exists to prevent.

---

## 4. What to curate, in priority order

1. **Arc boundaries** for the ~15 series that will actually appear. They are what
   makes "Start at Ep 34" true rather than approximate, and they matter more than
   a better synopsis.
2. **Episode records** for those same series, with real `duration_sec` — that is
   what gives arcs distinct durations and makes the session-length filter mean
   something.
3. **Listener contrast** across `listening_time_slot` and
   `typical_dropoff_episode`. Ten similar histories produce ten similar centroids
   and make affinity look broken when it is being appropriately quiet.
4. Synopses. Real ones, ≥ 120 chars, and not model-written.

Everything else in a panel record is carried along untouched.

---

## 5. Known gaps

- **No audio pipeline.** Fingerprints come from text. "Mood comes from the voice"
  is not a claim this build can make.
- **`contraindicated_for` is entirely LLM-written** at ingest and cannot be
  supplied from `catalog.json`. It is capped at four entries and reduced to a
  seven-code closed vocabulary, so phrases outside that vocabulary match nothing.
  The structural despair rule in `retrieval.py` is the backstop.
- **`series_completion_rate`, `primary_language`, `episodes_listened`, and
  `dropped_at_episode` do not affect retrieval.** See SOURCE_SCHEMA.md.
- **The eval judge is geometric**, thresholding the same axis distance retrieval
  maximises. Numbers from `evaluate.py` measure self-consistency until
  `PERSONA_PANEL` points at a real panel and the LLM judge is wired in.
