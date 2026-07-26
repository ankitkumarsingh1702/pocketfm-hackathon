# Mood-First Search (`app.mood`)

Feel-based discovery: search audio fiction by *how you want it to feel* —
"something that feels like a rainy Sunday after heartbreak" — instead of picking
a genre. Indexes **felt experience** at **arc** granularity and returns a
**doorway** ("Start at Ep 34"), not a 200-episode series title.

This package is the standalone hackathon build wired into the Simulated Studio
service. The full product rationale lives in the original design docs
(`mood-first-search-prd.md` and the feature `CLAUDE.md` in the `mood-based query/`
drop at the repo root).

## How it plugs into the studio

- **Routes** are mounted under `/api/mood/*` by `app/main.py`
  (`app.include_router(mood_router, prefix="/api/mood")`). The mount is
  best-effort: if the package fails to import, `main.py` logs it and leaves the
  studio lenses running rather than crashing the whole API.
- **LLM** — `llm_client.py` reuses `app.config.settings` (project, region,
  provider, model) and the same ADC auth as every other lens. It exposes a
  synchronous `complete(system, user) -> str` (Gemini via `google-genai` or
  Claude via `anthropic`, per `settings.llm_provider`) because the parser,
  reranker and judge parse JSON themselves. Every LLM path degrades to a
  deterministic heuristic — a missing model lowers quality, never takes the
  service down.
- **Index** — built once at import from in-memory fixtures
  (`seed_catalog.build_seed_catalog`) unless `MOOD_INDEX` / `MOOD_EPISODES` /
  `DEMO_PANEL` point at real data. Retrieval is pure NumPy; there is no vector DB
  to run. Embeddings fall back to the offline `HashingEmbedder` when
  `sentence-transformers` is absent, so startup never downloads a model.

## Endpoints (all under `/api/mood`)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | index size, tier-A count, active parser/embedder/reranker |
| GET  | `/starters` | 8 empty-state queries (we show queries, not shows) |
| GET  | `/sliders` | refine controls (`heavier`, `faster`, `warmer`, `stranger`) |
| GET  | `/profiles` | 10 curated demo listeners for the persona picker |
| POST | `/search` | `{text, profile_id?}` → `SearchResponse` (`shelves`\|`clarify`\|`safety`) |
| POST | `/clarify` | `{query_id, option_id?}` → resolves the one question |
| POST | `/refine` | `{query_id, shelf_id, current_axes, slider_deltas}` → one re-ranked shelf (no LLM) |
| GET  | `/episodes/{series_id}?start=&limit=` | the doorway window, defaulting to the entry point |
| POST | `/baseline` | genre/keyword search over the same catalog (Lab only) |
| GET  | `/debug/{query_id}` | retrieval trace: blocked items, pool sizes, latency (Lab only) |

## Frontend

The **Mood Search** studio tab (`frontend/src/components/tabs/MoodSearchTab.jsx`
+ `controllers/useMoodSearch.js` + `components/mood/*`) renders the one surface
with four modes off `SearchResponse.mode`. It is built on the studio's light
design tokens; the genre baseline lives behind the `?dev` Lab, never in the
primary flow.

## What gets queried, and from where

Three independent sources meet at scoring time. Keeping them separate is the
design — conflating history into the mood signal is the failure this product
exists to avoid.

| # | Source | Where it lives | Provenance today |
|---|---|---|---|
| 1 | **Content index** — one row per *arc*: 9 mood axes, `vibe_sentence` embedding, `sensory_tags`, `contraindicated_for` codes, `entry_episode`, `duration_min` | `MoodStore` (NumPy, in-process) | ⚠️ **100% synthetic** — `seed_catalog.build_seed_catalog()`, 145 arcs / 51 series incl. 3 deliberate traps |
| 2 | **Mood query** — the free-text feeling → `MoodQuery` | `parser.py` (LLM + heuristic floor) | Real, per request |
| 3 | **User history** — completed/liked series → taste centroid, liked tags, slot, finished set | `persona.ListenerProfile` → `AffinityScorer` | ⚠️ **Synthetic demo personas** (`api.py` builds 10 from `synthetic_personas`) |

**Intended (not yet wired) content sources**, in priority order:

1. **Pocket FM catalog** — production answer. Every arc fingerprinted from real
   content; `audio_verified` becomes meaningful.
2. **`sources.py --local catalog.json`** — hand-curated real series with
   hand-marked arc boundaries. This is the highest-value manual work: arc
   boundaries are what make "Ep 34" *true* rather than approximate.
3. **`sources.py --librivox N`** — LibriVox adapter, written and quality-gated
   (rejects `sections < 6`, synopsis `< 120` chars, runtime `< 1800s`) but
   **never run**. Gives density, not fidelity.

Point the service at real fingerprints with `MOOD_INDEX=<dir>`; `MoodStore.load`
re-embeds automatically if the saved vectors came from a different embedder.

### How the three combine

```
              mood query ─────┐
                              ├─► hard filters   language, avoid_tags, session length
   user history ──────────────┤       ↓
   (finished series)          └─► HARD MASK      finished series dropped, not penalised
                                      ↓
                                  SAFETY        contraindication codes  +  axis despair rule
                                      ↓         (both BEFORE scoring, never after)
                                  fused score   axis 0.45 · semantic 0.30 · tags 0.20
                                      ↓         · affinity ≤0.22 (scaled by query sparsity)
                                  MMR           relevance vs mood-diversity, λ=0.72
                                      ↓
                                  rerank        LLM judge (search) / heuristic (refine)
                                      ↓
                                  entry point   arc → "Start at Ep 34"
```

The ordering is the load-bearing part: **cheap exact rules first, expensive
fuzzy judgement last.** A contraindicated arc is masked before it is ever
scored, so no persuasive `vibe_sentence` can talk it back in.

History only ever **breaks ties** (ceiling 0.22 against axis 0.45, scaled by how
little the query said) and applies **one hard rule** — never re-serve a finished
series. It stores *taste*, never mood: "this person finishes warm, slow things"
is stable; "this person is sad" is not, and tonight is why they opened the app.

## Tests

```bash
uv run pytest tests/ -k mood
```

`test_mood_contract.py` (frozen contract), `test_mood_retrieval.py` (retrieval,
traps, sliders, latency), `test_mood_logic.py` (the safety gate, target
calibration, MMR, refine invariants). `conftest.py` pins the offline embedder so
no test depends on a model version or makes a network call.
