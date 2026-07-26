# Source file schemas

Three files. Author them, then run the validator before every ingest:

```bash
python3 validate_sources.py --catalog catalog.json \
    --episodes episodes.json --profiles profiles.json
```

Errors block ingest. Warnings mean it will load and the results will be worse
than they look — which is the more dangerous of the two.

---

## 1. `catalog.json` — series and arcs

The one that matters most. This is what gets fingerprinted.

```json
[
  {
    "series_id": "pf_001",
    "title": "Adhoora Raag",
    "synopsis": "A widowed music teacher in Lucknow reopens her late mother's academy and slowly relearns how to want things again, one student at a time.",
    "total_episodes": 120,
    "language": "hi",
    "source": "pocketfm_web",
    "arcs": [
      { "arc_id": "pf_001_a0", "label": "the opening arc",
        "start_episode": 1,  "end_episode": 33, "summary": "..." },
      { "arc_id": "pf_001_a1", "label": "the monsoon arc",
        "start_episode": 34, "end_episode": 78, "summary": "..." }
    ]
  }
]
```

| Field | Required | Notes |
|---|---|---|
| `series_id` | yes | Unique, stable. Referenced by both other files. |
| `title` | yes | Shown on the result card. |
| `synopsis` | yes | **≥ 120 chars.** The entire fingerprint is derived from this. |
| `total_episodes` | yes | Positive int. Arc ends must fall inside it. |
| `language` | no | Defaults `en`. **Exact-match hard filter — see below.** |
| `source` | yes | Provenance. See the rule below. |
| `arcs` | no | Omitted → even splits are synthesised. |
| `arcs[].arc_id` | yes* | **Globally unique**, not just per series. |
| `arcs[].label` | yes* | Shown as "Start at Ep 34 — *the monsoon arc*". |
| `arcs[].start_episode` / `end_episode` | yes* | Must exist in the episode file. |
| `arcs[].summary` | no | Falls back to the series synopsis. |

\* if `arcs` is present.

### The `source` rule

`source` must not be a language model. The rejected set lives in one place —
`catalog_ingest.SYNTHETIC_SOURCES`, which the validator imports rather than
copying — and currently holds `synthetic`, `llm`, `generated`, `fixture`, `gpt`,
`claude`, `gemini`, `openai`, `model`.

If a model writes the synopsis and a model derives the fingerprint from it, the
system grades its own homework: the fingerprint says "rain-soaked" because the
generator wrote it that way, retrieval matches rainy queries to it, and every
eval number becomes decorative.

**The failure is invisible — the metrics go up, not down.**

Model-written padding is allowed, **but only with `--allow-synthetic`.** Without
that flag ingest skips such series *whole*, every arc with them. That is why the
validator treats a model-written `source` as an error rather than a warning: the
run otherwise looks clean and quietly produces a fraction of the catalog you
authored. Never point the eval at an index built with the flag on.

Omitting `source` is not a way around this — it defaults to `"unknown"`, which is
not on the list, so the series is ingested as though it were real. The validator
errors on a missing `source` for exactly that reason.

### The `language` rule

`language` is compared by **exact string equality** against the parsed query,
inside the base mask that filter-relaxation never widens. If a query carries a
language no arc is tagged with, retrieval returns nothing at all — no error, no
empty-shelf warning, just a clarifying question on every single search.

This bit once, and the trap was in the documentation: the example above is tagged
`"hi"`, while the query parser defaulted every query to `"en"`. Any catalog
authored exactly as documented returned zero results.

Two rules keep it safe:

- **A query only carries a language when the listener asked for one.**
  `MoodQuery.language` defaults to `None` — no preference, no filter. Typing in
  Hinglish is not a language request; it is how people talk.
- **Keep one language per index.** Mixing them is legal but means the first query
  that does name a language drops every arc in the others. The validator warns.

Use lowercase ISO-ish codes (`en`, `hi`, `ta`). `"HI"` and `"hi "` are different
languages as far as an equality check is concerned.

### Spend your curation time on arc boundaries, not synopses

A good synopsis with even-split arcs gives approximate entry points. A mediocre
synopsis with hand-marked boundaries gives true ones — and "Start at Ep 34" is
the signature moment of the demo. Mark arcs by hand for the ~15 series that
will actually appear on screen; let the rest split evenly.

---

## 2. `episodes.json` — playable units

```json
[
  { "series_id": "pf_001",
    "episodes": [
      { "number": 1,  "title": "Jo Reh Gaya", "duration_sec": 1180,
        "synopsis": null, "audio_url": null },
      { "number": 34, "title": "Barsaat",     "duration_sec": 1240,
        "synopsis": null, "audio_url": "https://..." }
    ]
  }
]
```

Flat records (`{"series_id": ..., "number": ...}`) work too, so a spreadsheet
export needs no reshaping — including one that repeats `series_id` on every row.
Unknown columns are ignored rather than rejected.

| Field | Required | Notes |
|---|---|---|
| `series_id` | yes | Must exist in the catalog. |
| `number` | yes | 1-based, ≥ 1. **Every arc `start_episode` must appear here.** |
| `title` | no | Falls back to "Episode N". |
| `duration_sec` | no | Shown on the card, and it is what gives each arc a real `duration_min`. Without it every arc gets the same placeholder length, and `session_length_min` cannot discriminate between them. |
| `synopsis` | no | Not fingerprinted — display only. |
| `audio_url` | no | Absent → episode is listed with Play disabled. |

The file is optional entirely: numbered stubs are derived from
`total_episodes`. Author it for the series you demo.

**Partial authoring is safe and expected.** Writing episodes 1 and 34 of a
212-episode series leaves the other 210 as numbered stubs, with the authored ones
winning where they overlap. (Authoring any part of a series used to suppress
stubs for all of it, which turned "author the episodes you demo" into "lose the
rest of the list".)

**This file only reaches the running service through the ingest CLI.** The API
reads a JSONL store, not this JSON, so pass `--episodes episodes.json` to
`python -m app.mood.sources` and it writes both stores. Editing `episodes.json`
alone changes nothing until you re-run ingest.

**Do not have a model invent episode titles.** They will read plausibly, be
wrong, and be indistinguishable from real ones in the UI — the worst of the
three options.

**Episodes are never fingerprinted.** 600 series × ~150 episodes is ~90,000 LLM
calls against ~1,800 at arc level, for a signal you already have at the right
granularity.

---

## 3. `profiles.json` — the 10 demo listeners

```json
[
  { "persona_id": "p_ananya",
    "display_name": "Ananya",
    "attrs": {
      "listening_time_slot": "late_night",
      "primary_language": "hi",
      "series_completion_rate": 0.35,
      "typical_dropoff_episode": 18,
      "tolerance_for_heaviness": 0.7
    },
    "history": [
      { "series_id": "pf_001", "episodes_listened": 42,
        "completed": true, "liked": true, "dropped_at_episode": null }
    ]
  }
]
```

### Only five attrs are load-bearing

Your panel records carry 43 fields. Five are read; the rest are carried along
untouched. Do not spend curation time on the others.

| Attr | What reads it | Affects results? |
|---|---|---|
| `listening_time_slot` | slot-fit term (`W_SLOT = 0.15`) + demo contrast. One of `late_night`, `bedtime`, `commute`, `chores`, `work_break` | **yes** |
| `typical_dropoff_episode` | commitment fit (`W_COMMIT = 0.20`) — stops a deep entry point going to someone who quits at ep 12 | **yes** |
| `series_completion_rate` | commitment fit, but only as a fallback: `ListenerProfile.completion_rate` computes the real rate from `history` and ignores this whenever history is non-empty | only with empty history |
| `primary_language` | display only, in `/profiles`. The language filter reads the **query**, never the listener | no |
| `tolerance_for_heaviness` | `ProxyJudge` in `evaluate.py` | metrics only |

So two attrs move what a listener sees, one is a fallback, and two do not affect
retrieval at all. Curate `listening_time_slot` and `typical_dropoff_episode`.

One exception: `LLMPersonaJudge` serialises the **whole** `attrs` dict into its
prompt, so if you run the eval with an LLM judge every field is in play.

### History

| Field | Required | Notes |
|---|---|---|
| `series_id` | yes | Must exist in the catalog. |
| `completed` | yes | Boolean. Drives the taste centroid **and hard-masks the series from results** — a listener is never re-served a show they finished, on first search or after a slider drag. |
| `liked` | no | `true` counts as positive even if unfinished; `false` excludes. |
| `episodes_listened` | no | Carried, read by nothing today. |
| `dropped_at_episode` | no | Carried, read by nothing today. |

Extra keys on a history row are ignored. The picker's "N watched" is the number of
history entries, not `episodes_listened`.

`profiles.json` is loaded from the path in **`DEMO_PANEL`**, not a fixed filename.
Unset, the service synthesises ten listeners instead — see the runbook.

### Pick listeners for contrast

The demo beat is *same query, different listener, different shelf*. Ten
listeners with similar histories produce ten similar taste centroids, and
affinity looks broken when it is merely being appropriately quiet. Spread them
across listening slots and give each a lopsided history — real people have a
lane.

**Never fix subtle personalization by raising the affinity weight.** `0.12` is
its *base*; the live ceiling is `AFFINITY_CEILING = 0.22` in `retrieval.py`,
scaled up by how little the query said, against `0.45` for the mood axes. That
one file is the authoritative number — treat any figure quoted elsewhere,
including in this document's history, as stale.

The reason for the cap: the query is evidence about tonight, history is evidence
about the last six months, and tonight is why they opened the app. Make the
listeners genuinely different instead.

---

## What the validator catches that nothing else does

The three files are authored separately, so nothing type-checks across them:

- an arc pointing at ep 190 of a series that has 180
- an arc `start_episode` with no matching episode record → **404 in the player**
- a persona whose history references a deleted series
- duplicate `series_id` or `arc_id`
- overlapping arcs (same stretch returned twice)
- listeners clustered into too few slots for the demo to show anything
