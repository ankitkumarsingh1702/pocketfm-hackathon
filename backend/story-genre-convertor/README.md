# Story genre converter

Rewrite a story as horror / romance / comedy / thriller / anime while keeping the
plot intact — and prove the plot survived.

The hard part is not generating the horror version. Frontier models already
write good horror. The hard part is that one-shot rewrites drift: a subplot
disappears, the betrayer changes, the ending quietly becomes a different ending.
So the verifier, not the generator, is the thing worth building first.

```
story ──[extract]──▶ StorySkeleton ──[transform]──▶ rewritten story
                            │          scene by scene,        │
                            │          skeleton pinned        │
                            │                                 │
                            └────────[verify]◀────────────────┘
                              re-extract, align, score
```

**[ARCHITECTURE.md](ARCHITECTURE.md)** explains the whole thing in plain English,
no prior knowledge assumed — what the skeleton is, why the rewriter never sees
the original, how the verification works, and what the score does and doesn't
mean. Start there if you're new to this.

**[LONGFORM.md](LONGFORM.md)** is the design for novel length (200–250 pages).
This pipeline is built for ~1,000 words and does not extend by turning the dial
up; that document says why and what to build instead.

## What's here

All three stages.

| File | Stage |
|---|---|
| `models.py` | The `StorySkeleton` IR — `Beat`, `Role`, `StorySkeleton` |
| `llm.py` | The only place the Gemini API is touched |
| `extract.py` | Stage 1: story → skeleton, plus a zero-token lint and one self-correcting retry |
| `transform.py` | Stage 2: skeleton + genre pack → rewritten story, scene by scene |
| `genre_pack.py` | Loads `genres/*.json` and renders a pack into a prompt brief |
| `verify.py` | Stage 3: align two skeletons, score fidelity deterministically |
| `pipeline.py` | All three stages end to end, with the fidelity report |
| `calibrate.py` | The harness that makes the fidelity number trustworthy |
| `cache.py` | Disk cache for skeletons and rewrites — never demo a cold run |
| `genres/` | One JSON per genre: horror, romance, comedy, thriller, anime |
| `stories/` | Three source stories with deliberately different plot shapes |

## Setup

Runs on Gemini via the `google-genai` SDK in Vertex AI mode — the same auth path
as the rest of this backend (`../app/llm/gemini_vertex.py`). There is no API key:
access comes from Application Default Credentials.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login    # once per machine
```

If Vertex AI isn't enabled on the project yet, `../../scripts/gcp_setup.sh` turns
on the services and grants the roles.

Defaults (project `pocketfm-hackathon`, region `us-central1`) are baked into
`llm.py`, so nothing else is required. To override, put values in `.env`
(gitignored — see `.env.example`) and load them into the shell; env vars don't
persist across shells:

```bash
set -a && . ./.env && set +a
```

Model defaults to `gemini-2.5-pro` — extraction and alignment are reasoning tasks
(decomposing causality, judging structural equivalence) where a flash-tier model
gets sloppy about causal edges. Override without touching code:

```bash
export GEMINI_MODEL=gemini-2.5-flash    # cheaper; re-run calibrate.py after switching
export VERTEX_LOCATION=us-east5         # if a region runs short on quota
```

**Two temperatures, on purpose.** Extraction and alignment run at
`SKELETON_TEMPERATURE` (default 0): the same story must decompose the same way
twice, or `calibrate.py`'s ceiling check measures sampling luck instead of
extractor quality. The transform is creative writing and runs at
`TRANSFORM_TEMPERATURE` (default 0.9). Neither is called `TEMPERATURE`, because
the app's own `.env` one directory up sets that to 0.9 and sourcing it must not
silently loosen extraction.

Use Python 3.11+ if you can. 3.9 works, but `google-auth` prints an
end-of-life warning on every import.

## Run

```bash
python verify.py --selftest             # scoring math, no credentials needed
python transform.py --selftest          # scene planning, no credentials needed
python extract.py stories/reveal.txt    # eyeball one skeleton
python calibrate.py                     # is the fidelity number trustworthy?

python pipeline.py stories/reveal.txt --genre horror    # the whole loop
python pipeline.py stories/reveal.txt --all-genres      # all five, ranked
```

`pipeline.py` runs extract → transform → re-extract → verify and prints the
fidelity breakdown. Read it against `calibrate.py`'s ceiling rather than against
100%: the gap below the ceiling is extractor noise, not plot damage.

`calibrate.py` makes 6 model calls on a cold run — 3 extractions, a second pass
over one story for the ceiling, and 2 alignments — plus up to one extra retry
per extraction if the lint fires. Results cache to `.cache/`.

`calibrate.py` caches skeletons in `.cache/`; pass `--no-cache` to re-extract.

## The design in one page

**The skeleton holds invariants only.** Causal chain of beats, character
functions, who wants what, who gets it, outcomes and reversals, order of
reveals. Setting, names, imagery, pacing, dialogue register, and the literal
nature of the threat are free variables the genre owns. "A hides a secret from
B; B discovers it; the relationship breaks" works as a haunting or as a
meet-cute gone wrong — that neutrality is the whole thesis.

**Beats are written abstractly on purpose.** `the confidant reveals the withheld
information`, never `Priya reads the dealer's letter`. If the skeleton is
already flavoured, the transform can't move far. `extract.py` enforces this with
a regex lint that costs zero tokens and, on failure, re-asks once with the
specific complaint fed back.

**Tune the `Field` descriptions, not the system instruction.** Gemini's
structured-output mode compiles the Pydantic models into the response schema it
is constrained by, descriptions included — so the good/bad examples on
`Beat.action` sit closer to the generation than anything in `EXTRACT_SYSTEM`
does. When a skeleton comes out at the wrong granularity or the wrong
abstraction level, that is the first thing to edit.

**Scoring is deterministic.** One LLM call aligns source beats to candidate
beats on causal function; the number is then pure Python — 60% load-bearing
recall, 20% all-beat recall, 20% causal-edge recall. An edge survives only if
both endpoints matched *and* the candidate has that edge between the matched
pair, which is what catches a chain with a hole in it.

**Genre packs are data, not prompt strings.** One JSON per genre in `genres/`:
premise, obligatory beats, pacing curve, sensory palette, POV distance, dialogue
register, taboo moves. Adding a sixth genre costs a file, not a refactor — and a
judge will ask whether it can do noir. `taboo_moves` is the field that earns its
keep: positive instructions ("write dread") produce competent prose in every
genre, and the prohibitions are what stop horror drifting into thriller.

**The transform never sees the source story.** Only the skeleton. If the prose
were in the prompt, the model would borrow its surface and the genre distance
would collapse — so scene calls get the beats they own, the pack, and a rolling
summary the previous scene wrote for them. Nothing else.

**One scene at a time, cut at the pivots.** `plan_scenes` is deterministic and
costs zero tokens: it groups consecutive beats and always ends a scene on a
load-bearing one, so no scene carries two turning points. A scene with two turns
short-changes one of them, and that is the one the verifier reports missing.

## Build order

1. ~~**Extract only.**~~ Done. Lint clean on all three stories.
2. **Verify, before transform.** `calibrate.py`. Ceiling (same story extracted
   twice) should be ≥ 0.90; floor (two different stories) ≤ 0.30. Floor passes
   comfortably (0–25% across all three pairs). **The ceiling does not yet** — it
   was 48.72%, then 76.04% after a lint bug was fixed, and has not been
   re-measured since the granularity fix. Treat ~76% as a noise floor: a rewrite
   well above it is real signal, one inside the band is not yet distinguishable
   from extractor drift.
3. ~~**Transform.**~~ Done, all five genres. Scene by scene, each call getting
   the beats it must hit, the genre pack, and a rolling summary for continuity.
   Never one giant call.
4. ~~**Add comedy / thriller / anime as data.**~~ Done — they cost a JSON file each.
5. **UI.** Paste story → pick genre → side-by-side with beat-by-beat markers,
   plus the Plot Fidelity × Genre Distance scatter. High fidelity + high genre
   distance is the money quadrant, and that chart is the demo.

Two things that will bite: retry once on a low-fidelity scene with the missed
beat quoted explicitly, then move on; and cache aggressively, pre-computing one
flagship story across all five genres before presenting. Never let a judge watch
a cold run.

## Why not fine-tune

Considered and rejected. Teaching genre isn't the bottleneck — models already
know horror. And the supervision you'd need is *paired* data (the same story in
two genres), which doesn't exist; genre-labelled corpora are unpaired, and
learning "which parts to hold fixed" from unpaired data is a research problem,
not an 18-hour build. A fine-tuned model would also still be sampling, so the
verifier is mandatory either way.

The instinct behind it is right, though, and the delivery mechanism is retrieval
rather than weights: a **craft exemplar bank** of 15–20 annotated passages per
genre, each tagged with the beat type it demonstrates (reveal, confrontation,
first meeting), retrieved at transform time and injected into the scene prompt.
Same benefit, about an hour, and inspectable when a genre comes out weak.

Fine-tuning stays on the roadmap slide as rejection-sampling distillation: run
the prompt pipeline at volume, keep only the pairs clearing the fidelity
threshold, and you have a quality-gated parallel corpus that didn't exist
before. The verifier isn't just a demo feature — it's the data engine.

## Notes on the source stories

`reveal.txt`, `bargain.txt`, and `return.txt` are ~1000 words each and have
deliberately different skeletons — a discovery-and-refusal, a bargain-and-
reversal, and a return-and-relinquish. The first two are what `calibrate.py`
uses for the floor check, so they need to stay structurally distinct.
