# Mood-First Search

Search audio fiction by how you want it to feel — "something that feels like a
rainy Sunday after heartbreak" — instead of picking a genre. Pocket FM
hackathon build (P5, Entertainment Discovery).

This file is context for Claude Code. It records decisions that are expensive
to re-derive and traps that have already been hit once.

---

## The premise, and why the obvious build fails

Genre is a library taxonomy, not a desire taxonomy. The naive implementation —
embed the query, embed the synopsis, cosine similarity — **does not work**, and
understanding why is the whole design:

- Synopses describe **plot**. Queries describe **experience**. Different
  semantic neighbourhoods. "Rainy Sunday after heartbreak" has near-zero
  overlap with "a widowed baker reopens her mother's shop".
- Worse, it has *high* overlap with "a rainy season romance where lovers are
  torn apart" — which is the single worst thing to serve someone in fresh
  heartbreak. Topical match is actively harmful here.
- Mood is not a property of a series. A 200-episode show swings from cosy to
  brutal. Fingerprinting a whole series averages it into mush.

So: index **felt experience** at **arc** granularity, return an **entry point**,
and treat the query as under-specified rather than guessing intent.

---

## Layers

```
Series      catalog record          title, synopsis, total_episodes
  └─ Arc    MOOD INDEX              fingerprinted; this is what retrieval ranks
       └─ Episode   PLAYABLE        flat lookup; no vectors, no LLM
```

| File | Role |
|---|---|
| `schemas.py` | **Frozen contract.** MoodAxes, MoodFingerprint, MoodQuery, ClarifyingQuestion, MoodProfile, SearchResponse, ResultCard |
| `mood_config.py` | Starters, slider→axis map, DESTINATION_TARGETS/FILTERS, sparsity heuristic, clarify builder |
| `parser.py` | Free text → MoodQuery (LLM + heuristic floor) |
| `store.py` | Numpy index over arcs; axis prefiltering |
| `contraindications.py` | Closed-vocab safety matching |
| `retrieval.py` | Filters → contraindication block → fused score → MMR |
| `rerank.py` | LLM judge; scores AND explains in one call |
| `entrypoint.py` | Arc → doorway ("Start at Ep 34") |
| `search.py` | Orchestrator → `list[Shelf]` |
| `persona.py` | ListenerProfile, watch history, AffinityScorer |
| `episodes.py` | Playable units, windowed fetch, validation |
| `catalog_ingest.py` | Metadata JSON → fingerprints |
| `sources.py` | LibriVox adapter + local hand-collected |
| `baseline.py` | Genre/keyword search — the comparison we argue against |
| `evaluate.py` | Persona-panel harness, all metrics |
| `llm_client.py` | Vertex via ADC → direct key → None |
| `api.py` | FastAPI service |
| `frontend/` | React: `api.js`, `AppShell.jsx`, `EpisodeList.jsx`, `LabPanel.jsx` |

---

## Invariants — do not break these

**Contraindications run BEFORE scoring.** `Retriever.retrieve` masks blocked
rows before anything is ranked. If a contraindicated item can reach the
reranker, a persuasive vibe sentence can talk it back in. Cheap exact rules
first, expensive fuzzy judgement last — never the reverse.

**Affinity may only break ties.** Capped at 0.12 vs axis 0.45, scaled by query
sparsity. The query is evidence about tonight; the history is evidence about
the last six months; tonight is why they opened the app. Push affinity past
~0.25 and this becomes a collaborative filter in a mood-search costume.

**Affinity may never**: reinstate a contraindicated item, resurface a finished
series (hard mask, not a penalty), or store mood. It stores *taste* — what they
finish, when they listen. Never "this user is sad".

**Episodes are not fingerprinted.** ~90k LLM calls vs ~1.8k at arc level, for a
signal you already have at the right granularity. Episode-level mood is mostly
noise from wherever the scene break landed.

**`source` must not be a language model.** If an LLM writes the synopsis and an
LLM derives the fingerprint, the system grades its own homework and every eval
number becomes decorative. `catalog_ingest` rejects synthetic sources by
default. Padding may be synthetic; the eval set may not.

**`SearchResponse.mode` is not navigation.** `empty | clarify | shelves |
safety` are states of one surface. Routing them separately makes back-from-
shelves land on the clarifying question, which reads as the app not listening.

**Never ask twice.** A skipped clarify sets `sparsity_score = 0`.

**No genre fallback in the primary flow.** No browse tab, no category chips.
The baseline search exists only behind the dev-only Lab surface.

---

## Bugs already found — don't reintroduce

**1. Sliders were no-ops at full drag.** Measured: semantic + tags are 50% of
the score and are *constant* during refine (the query embedding never changes,
only the target axes). A full drag moved 22% of what already separated
candidates, so ranking was pinned. Widening filters did not help — the filter
was never the binding constraint. Fix: `ScoringWeights.for_refine()` puts axis
at 0.78. A drag is axis-level evidence the sentence never contained.

**2. Every entry point collapsed to episode 1.** `EARLIER_ARC_EPSILON` was
loose enough to fire on every result, silently deleting the entire "start at
Ep 34" proposition. Tests passed because they asserted "a valid episode was
returned". Fix: swap only when the entry is genuinely deep (>12) and the saving
is material (≥35%).

**3. The seed fixture contradicted the product premise.** All arcs of a series
were drawn from one template, so arcs within a series were mood-identical —
which is exactly the thing arc-level indexing exists to exploit. Fixed with
per-arc drift.

The pattern in all three: **tests asserted the field was populated, not that
the product behaved.** Assert behaviour.

---

## Open seams

- **Persona panel** — `evaluate.py` falls back to synthetic stand-ins. Real
  panel: `PERSONA_PANEL=<path>`. Numbers are not real until this is wired.
- **LLM never verified end-to-end.** Parser, reranker and judge all degrade
  silently to heuristics. Run `python3 llm_client.py` — it makes one real round
  trip and tells the truth.
- **Catalog** — needs 40-60 hand-collected real series with hand-marked arc
  boundaries. Arc boundaries are worth more curation effort than synopses:
  they are what makes "Ep 34" true rather than approximate.
- **Frontend config** — `frontend/api.js` has `BASE = ""`. Set it to match the
  project's convention.
- **Metrics currently missing target**: lift 1.27x (target 2x) because the
  baseline is scored generously on purpose; catalog coverage 34.5% (target 60%)
  because 20 scenarios × 9 slots cannot cover 145 arcs. Neither is a retrieval
  problem — do not tune retrieval to chase them.

---

## Commands

```bash
python3 llm_client.py                      # verify ADC/Vertex before anything
python3 test_contract.py                   # frozen contract
python3 test_retrieval.py                  # retrieval, traps, sliders, latency
python3 evaluate.py                        # metrics (PERSONA_PANEL=<path>)
python3 sources.py --local catalog.json --librivox 200 --out /tmp/moodstore
MOOD_INDEX=/tmp/moodstore uvicorn api:app --reload --port 8000
```

---

## Demo beats

1. Empty state is **queries, not shows** — no browse grid.
2. Three shelves = intent disambiguation, not indecision.
3. Entry point: "Start at Ep 34", not a 200-episode series.
4. Slider refines in mood space, no retyping.
5. Same query, switch listener, ranking moves — visibly more on thin queries.
6. Lab: same query through genre search returns the trap arcs at rank 1 and 2.

**Do not claim mood comes from the voice.** The audio pipeline was cut; the
catalog is metadata-only. That overclaim is the one a judge will probe.
