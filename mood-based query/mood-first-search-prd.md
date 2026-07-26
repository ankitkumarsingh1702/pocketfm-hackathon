# Mood-First Search — PRD & Execution Flow

**Problem statement:** Entertainment Discovery (P5) — users want to say *"I want something that feels like a rainy Sunday after heartbreak"* instead of picking a genre.

**Working name options:** `Saundh` (from *saundhi khushbu* — the smell of first rain on earth; ties directly to the hero query) · `Mann` · `Petrichor`

---

## 1. The bet in one paragraph

Genre is a **library taxonomy**, not a **desire taxonomy**. Nobody wakes up wanting "Romance / Thriller / Urban Fantasy." They want a *felt experience* — to be held, to be distracted, to be allowed to cry, to be pulled somewhere far away. Every discovery surface in audio today forces people to translate a feeling into a shelf label, and the translation is lossy in both directions. We're building a search layer where the query is the feeling itself, and the index is not plot metadata but an **affective fingerprint of the content**.

---

## 2. Why the obvious solution fails (this is the whole design)

The naive version: embed the query, embed the show synopsis, cosine similarity. **It does not work**, and understanding why is the entire product.

Synopses describe **plot**. Queries describe **experience**. These live in different semantic spaces.

| Query | Synopsis it should match | Lexical/semantic overlap |
|---|---|---|
| "rainy Sunday after heartbreak" | "A widowed baker in Lucknow reopens her mother's shop and slowly learns to want things again." | ~zero |
| "rainy Sunday after heartbreak" | "A rainy season romance where two lovers are torn apart." | high — **and it's the wrong answer** (this will retraumatise, not soothe) |

Second failure: **mood is not a property of a series.** A 200-episode Pocket FM show swings from cosy to brutal to triumphant. Fingerprinting a whole series averages it into mush. Mood lives at the **arc/episode** level.

Third failure: **audio carries mood that text does not.** Voice tremor, pacing, silence ratio, score presence, breath. A transcript-only pipeline throws away the majority of the affective signal in an audio-first catalog. This is the thing a Netflix/Spotify text-metadata approach structurally cannot do, and it's our moat for an *audio* company.

**So the three moves that make this 0→1:**
1. Index **felt experience**, extracted from content (text + audio), not from metadata.
2. Index at **arc granularity**, and return an *entry point*, not just a title.
3. Treat the query as **under-specified and emotionally loaded** — resolve intent, don't guess it.

---

## 3. The intent problem (the second insight)

"After heartbreak" is genuinely ambiguous. The same eight words map to at least three incompatible desires:

- **Sit in it** — I want permission to feel this. Give me something sad and beautiful. Let me cry.
- **Be kept company** — Don't fix me, just don't leave me alone. Warm, low-stakes, intimate voice.
- **Get me out of here** — Take me somewhere so absorbing I forget. High immersion, different world entirely.

A single ranked list is the wrong output shape. Guessing wrong is worse than asking — but asking a grieving person a survey is worse than both.

**Solution: three shelves, one screen.** We return all three interpretations side by side, each labelled in human language, each with a one-line reason. The user's *click* is the disambiguation. Zero friction, and the shelf structure itself demonstrates that the system understood the ambiguity — which is what makes it feel intelligent rather than lucky.

---

## 4. Cold start — the empty box

### 4.1 There is no such thing as a user mood fingerprint

Mood is a **state**, not a **trait**. A fingerprint is a property of *content*. Storing a per-user mood vector and feeding it into retrieval means tonight's heartbreak query gets polluted by last Tuesday's commute boredom. Onboarding mood questionnaires fail for the same reason twice over: nobody fills a form at 10:40pm while sad, and whatever they do fill is stale in 72 hours.

### 4.2 Three different cold starts — do not conflate them

| Type | Status in this design |
|---|---|
| **User cold start** — no listening history | **Already solved.** The query carries all the signal. This is mood search's structural advantage, not a gap. |
| **Item cold start** — new title, zero listens | **Already solved.** Fingerprints come from content, not behaviour. A show is discoverable on day one. |
| **Blank-box cold start** — user doesn't know they can type a feeling | 🔴 **The real problem.** |

Only the third one needs building.

### 4.3 Empty state: show queries, not shows

A grid of available shows on first open quietly reinstates the browse experience this product exists to replace — and a judge will spot it in two seconds. Instead we show 8 **mood starters**: pre-written queries in the listener's own register.

> *"Baarish ho rahi hai aur kisi se baat nahi karni"*
> *"Long drive hai, jagaye rakhna hai"*
> *"Kuch aisa jo sona aasan kar de"*
> *"Abhi ek series khatam ki, us jaisa feel chahiye"*

They teach the interaction model in one glance. They span the destination space, so whoever opens the app finds one that is nearly true. And one of them is the hero query, which means the demo can start with a tap instead of typing.

If shows must appear on the home surface, they appear under **mood shelves** (`Sone se pehle` / `Raat 2 baje wala` / `Rone ke liye`) — never genre rails. Even the browse path teaches the model.

### 4.4 Sparsity-triggered single question

Sometimes a question genuinely beats shelves — but only in two cases:

1. **The query is too thin to split.** *"Bore ho raha hoon"* has no emotional content; three distinct hypotheses cannot be generated from it honestly.
2. **The ambiguity is on a constraint, not an intent.** Session length, listening context. Showing these as parallel shelves explodes the grid.

So the parser emits a `sparsity_score`. Above `SPARSITY_THRESHOLD = 0.60` we ask **exactly one** question; below it we go straight to shelves.

**The rules, in order:**
- Distress flag → never ask, go to the safety path.
- Explicit destination present → never ask about intent; they already told us.
- Sparse → ask the one intent question.
- Otherwise → three shelves.
- **Never ask twice.** A skip drops sparsity to zero and we answer with what we have.

The critical design detail: **every answer option resolves directly into mood space** (a `Destination` or a set of axis deltas). The answer moves the target vector with no second LLM call — the same path the sliders use. Question and slider are the same mechanism wearing different clothes.

### 4.5 What actually persists: MoodProfile

Not a mood. A **calibration** — the lens we read this listener's words through:

- **Vocabulary** — do they say *halka* or *light*
- **Scale calibration** — one person's "heavy" is another's "medium"
- **Hard contraindications** — *"never anything with a parent dying"* (safety-relevant, permanent)
- **Destination prior** — 🔑 the valuable one: when this listener is sad, do they historically tap *escape* or *sit with*

And it costs nothing to collect. **Every three-shelf result is a labelled datapoint** — they chose `escape` over `sit_with` on a heartbreak query. Zero extra UI, zero friction. The disambiguation screen we already built *is* the profile-building mechanism.

Guardrail: `destination_prior` only **reorders shelves and breaks ties**. It never filters, and it never beats an explicitly stated destination. Otherwise we are back to last week's mood polluting tonight.

**Hackathon scope:** starters and the sparsity question ship. `MoodProfile` is defined in the contract but roadmap-only — history cannot accumulate inside a demo, so there is nothing to show.

---

## 5. Product principles

1. **The query is the feeling.** No filters, no chips, no "select a genre" fallback anywhere in the primary flow.
2. **Always explain.** A mood recommendation without a reason feels random. One line, in the user's emotional register, never in metadata-speak. *"Because you didn't ask to feel better — you asked to feel it properly."*
3. **Return a doorway, not a title.** "Start at Episode 34" beats "here's a 200-episode series."
4. **Refine in mood space.** Follow-up is *heavier / lighter / slower / warmer*, never re-typing the query.
5. **Never make it worse.** Emotional queries carry real distress. Safety is a first-class path, not an afterthought.

---

## 6. Users & jobs

**Primary persona — the evening drifter.** 22-34, tier-1/2 India, opens the app at 10:40pm with a feeling and no title in mind. Currently scrolls home feed for 4 minutes and either replays something known or closes the app. **JTBD:** *"Help me find something that matches what I'm feeling right now, without making me name it."*

**Secondary — the cold-start user.** No history, so the recommender has nothing. Mood-first search is the only surface that works on day zero, because the query carries all the signal.

**Tertiary — the returning binger between series.** Just finished a show, in a specific afterglow, wants "something that felt like *that*." Query becomes "more of how X made me feel" — same pipeline, fingerprint of X as the query vector.

---

## 7. The mood ontology

Hybrid: **interpretable axes** (for retrieval, filtering, and the refine sliders) + **free-text vibe** (for reranking and explanation). Axes alone are too coarse; free text alone can't be steered.

### 7.1 `MoodFingerprint` — per arc

```python
class MoodFingerprint(BaseModel):
    # continuous axes, 0..1 unless noted
    valence: float          # -1..1  bleak → uplifting
    arousal: float          # still → frantic
    tension: float          # safe → dread
    warmth: float           # cold/clinical → intimate, held
    pace: float             # slow-burn → propulsive
    catharsis: float        # numb → tear-releasing
    hope: float             # hopeless → redemptive
    companionship: float    # observing a world → being spoken to
    weight: float           # frothy → heavy

    sensory_tags: list[str]      # rain, night, small-room, monsoon, open-road, winter-quilt, crowd
    vibe_sentence: str           # one line, listener language, no plot spoilers
    good_for: list[str]          # "crying it out", "falling asleep", "long commute"
    contraindicated_for: list[str]  # "someone who wants cheering up", "active grief"
    confidence: float
```

The `contraindicated_for` field is doing more work than it looks like — it's what prevents the "rainy season romance where lovers are torn apart" failure above.

### 7.2 `MoodQuery` — parsed from free text

```python
class MoodQuery(BaseModel):
    situation: dict          # {time, weather, solitude, activity, place}
    felt_state: list[str]    # ["heartbreak", "listlessness"]
    intensity: float
    desired_destination: Literal[
        "sit_with", "lift_gently", "company", "escape", "make_sense_of", "sleep"
    ] | None                 # None = ambiguous → generate shelves
    intensity_tolerance: float
    session_length_min: int | None
    hard_filters: dict       # language, avoid_tags
    distress_flag: bool
```

---

## 8. System design

### 8.1 Offline — the indexing pipeline

```
audio file
   │
   ├─► [ASR]  faster-whisper ──► transcript + word timings
   │
   ├─► [Prosody]  librosa ──► per-30s window:
   │                            RMS energy, tempo, pitch mean/variance,
   │                            speech rate, silence ratio, spectral centroid,
   │                            music-vs-speech ratio
   │
   └─► [Audio-text embedding]  CLAP ──► audio embedding in a shared
                                        language-audio space
   │
   ▼
[Segmenter] → scene/arc chunks (3-8 min, boundary on silence + topic shift)
   │
   ▼
[Fingerprinter]  LLM + Instructor/Pydantic
   inputs: chunk transcript + prosody summary + neighbouring context
   output: MoodFingerprint (structured, validated)
   │
   ▼
[Fusion]  text-derived axes  ⊕  prosody-derived arousal/tension/pace
          (prosody overrides text on arousal & pace — it's the ground truth
           for "how does this *sound*", text wins on valence & hope)
   │
   ▼
[Aggregation]  chunk → arc → series
   KEEP VARIANCE. Store per-arc fingerprints AND series-level
   mean + std. High std = "this show has range" (useful signal, not noise).
   │
   ▼
[Index]  LanceDB / Qdrant
   vector: embed(vibe_sentence + sensory_tags) ⊕ axis vector ⊕ CLAP audio vec
   payload: all axes as filterable scalars, entry-point episode number
```

**Why fuse rather than pick one:** text-only misreads a calm-sounding scene as calm when the delivery is tight with dread; audio-only can't tell hopeful-sad from hopeless-sad. Each covers the other's blind spot.

### 8.2 Online — the query pipeline

```
"something that feels like a rainy Sunday after heartbreak"
   │
   ▼
[1. Parse]  LLM + Instructor → MoodQuery
            └─ if distress_flag → SAFETY BRANCH (§8), exit
   │
   ▼
[2. Hypothesise]  if desired_destination is None:
                  generate 3 intent hypotheses
                  → 3 target fingerprints (not 3 text queries —
                    3 *points in mood space*)
   │
   ▼
[3. Retrieve]  per hypothesis, hybrid:
               • vector kNN on fused mood embedding      (top 50)
               • structured filter on axes               (hard bounds,
                 e.g. sit_with ⇒ catharsis > .6, arousal < .4)
               • hard filters: language, avoid_tags
   │
   ▼
[4. Rerank]  LLM judge, batched:
             "Given this listener's state and destination, does this arc
              deliver the experience? Score 0-10. Flag contraindications."
             → drops the 'rainy romance about lovers torn apart' trap
   │
   ▼
[5. Entry point]  pick the arc with the best score → resolve to episode number
                  → "Start at Ep 34 — the monsoon arc"
   │
   ▼
[6. Explain]  one line per result, emotional register, spoiler-free
   │
   ▼
[7. Present]  3 labelled shelves × 3-4 results
   │
   ▼
[8. Refine]  sliders (heavier↔lighter, slower↔faster, alone↔company,
             familiar↔strange) → nudge the target vector, re-retrieve.
             NO re-parse, NO LLM call. Sub-200ms. This is the demo moment.
```

**Latency budget:** parse 600ms · hypothesise 800ms (parallel) · retrieve 80ms · rerank 1.2s (batched, parallel across shelves) · **total ~2.5s cold, <200ms on every refine.** Stream shelves as they resolve so the first one paints at ~1.5s.

---

## 9. Safety path

Mood queries will surface genuine distress — this is not hypothetical, it's the second-most-likely thing a "how are you feeling" input box receives.

- **Detect:** the parser sets `distress_flag` on explicit self-harm ideation, hopelessness with no exit, or "I want to stop feeling anything."
- **Do not serve deeper.** Never return high-despair, low-hope content into an active-crisis query. The `contraindicated_for` field enforces this at retrieval, not just at the LLM layer.
- **Respond, don't deflect.** Acknowledge warmly, offer content that is *steady and warm* rather than either bleak or aggressively cheerful, and surface a support resource (in India: Tele-MANAS 14416, KIRAN 1800-599-0019) without making it feel like a shutdown.
- Log the flag rate as a product metric — it tells you something real about when people open the app.

Judges will ask about this. Having it built rather than mentioned is a differentiator.

---

## 10. Evaluation — the hard part, and your unfair advantage

**The core problem: there is no ground truth for "does this match a mood."** No labelled dataset exists. Most teams will hand-wave this with vibes and three cherry-picked queries.

**You already have the answer: the 1,000-persona Indian listener panel.** Repurpose it as an offline eval harness.

```
for persona in panel.sample(200):
    for scenario in mood_scenarios:          # 20 scripted emotional states
        query   = persona.phrase(scenario)   # in their own voice/language mix
        results = mood_search(query)
        verdict = persona.judge(results)     # would I tap? would I finish?
                                             # did this understand me?
```

**Metrics that come out of this:**

| Metric | Definition | Demo target |
|---|---|---|
| **Mood Match Rate** | % results a persona judges as "yes, that's what I meant" | > 70% |
| **Lift vs genre baseline** | MMR of mood-search vs genre-keyword search, same queries | **2×+** |
| **Intent coverage** | % ambiguous queries where ≥1 of 3 shelves is judged right | > 90% |
| **Trap avoidance** | % where a lexically-similar-but-emotionally-wrong item is excluded | > 85% |
| **Shelf diversity** | mean pairwise mood distance within a shelf (not-too-samey) | monitored |
| **Cold coverage** | % catalog reachable by ≥1 mood query (vs. long tail dead in genre nav) | > 60% |

The **genre baseline side-by-side** is your money slide. Same query, two panels, one obviously broken.

---

## 11. Catalog strategy (the hackathon's real constraint)

No Pocket FM catalog access. Do **not** fully synthesise — judges smell it instantly and it invalidates the audio pipeline claim.

**Two-tier, and be transparent about the seam:**

- **Tier A — 40 real audio items, full pipeline.** LibriVox / public-domain audio fiction + open podcast RSS. These go through ASR → prosody → CLAP → fingerprint end-to-end. This *proves the technology works on real audio.* Pick for emotional range, not fame.
- **Tier B — ~600 items, metadata-derived fingerprints.** Real synopses from public sources, fingerprinted text-only. This gives the search *density* so results don't look thin. Marked internally with `audio_verified: false`.

In the demo, say this out loud: *"40 titles went through the full audio pipeline. 600 more are text-fingerprinted so the catalog feels real. On Pocket FM's actual library, every title is Tier A."* Honesty here reads as competence, and it pre-empts the question.

---

## 12. Scope

**In (must demo):**
- Full audio→fingerprint pipeline on Tier A
- Query decomposition + 3 intent shelves
- Hybrid retrieve + LLM rerank with contraindication filtering
- Arc-level entry points ("start at Ep 34")
- Per-result explanation line
- Mood sliders, instant refine
- Genre-search baseline panel, side by side
- One eval number from the persona panel
- Safety branch
- **Mood starters empty state** (8 pre-written queries)
- **Sparsity-triggered single question** (`sparsity_score >= 0.60`)

**Out (name them as roadmap, don't build):**
- `MoodProfile` learning — schema is frozen, but nothing to demo without history
- Personalisation / listening history
- Multilingual query handling (English + Hinglish input only)
- Real-time / live ASR
- Mobile app (web demo only)
- Auth, accounts, persistence
- Catalog > 1000 items

---

## 13. 18-hour execution flow

Three people. **Parallelise on day one, integrate at H8, freeze at H16.** The single biggest risk is a late integration — a contract-first split prevents it.

**H0 — H0:45 · All three, together. Do not skip this.** ✅ **Done — see `/code`.**
`schemas.py` is frozen: `MoodAxes`, `MoodFingerprint`, `MoodQuery`, `ClarifyingQuestion`, `MoodProfile`, `SearchResponse`. `mood_config.py` holds starters, slider map, destination targets/filters, sparsity heuristic. `mock_api.py` serves all five endpoints with real shapes and fake data — frontend starts at H1 and never waits on the pipeline. `test_contract.py` passes.

Two design decisions are baked into the contract and should not be relitigated mid-build: `SearchResponse.mode` is the discriminator (`shelves` / `clarify` / `safety`) — the frontend renders one of exactly three screens; and `MoodAxes.nudge()` is the **only** way the target vector moves after parse, which is what keeps refinement LLM-free and under 200ms.

| Block | Ankit — query + frontend | Ritik — indexing | Sahil — retrieval + eval |
|---|---|---|---|
| **H1–4** | Query parser (LLM+Instructor) — must emit `sparsity_score`. 3-hypothesis generator. Swap `fake_parse()` in place. | ASR + prosody on **5** items. Get one fingerprint that looks right by eye. Iterate the prompt here — this is where quality is won. | Stand up LanceDB. Ingest mock fingerprints. Hybrid retrieve + axis filters working against fakes. Port the persona panel loader. |
| **H4–8** | Next.js: **starters empty state**, 3-shelf layout, result card, explanation line, **clarify screen**. Wire to real API. | Scale to 40 Tier A. Kick off Tier B text-only batch in background. Arc segmentation + aggregation. | LLM reranker with contraindication check. Entry-point resolver. Genre baseline search (deliberately dumb — keyword on genre tags). |
| **H8** | **🔴 INTEGRATION CHECKPOINT.** One real query, end to end, ugly but working. If this slips past H9, cut Tier B entirely and demo on 40 items. | | |
| **H8–12** | Mood sliders + instant re-retrieve (no LLM in this path). Side-by-side baseline panel. | Tier B ingest complete. Fix fingerprint quality on the 15 worst items by hand — curation is legitimate at this scale. | Persona eval harness runs. First MMR + lift numbers. Tune retrieval bounds per destination. |
| **H12–14** | Safety branch UI. Explanation prompt polish — this line is what people quote. | Sensory-tag cleanup. Build the 5 demo-query golden path and verify each returns something genuinely good. | Full eval run, 200 personas × 20 scenarios. Lock the numbers for the deck. |
| **H14–16** | Visual polish. Loading states that stream shelves in. Empty/error states. | Backup: cache all demo-query responses to disk. **Demo must run with zero network.** | Metrics slide. Architecture diagram. |
| **H16** | **🔴 FEATURE FREEZE.** No new code. Anything broken gets removed, not fixed. | | |
| **H16–17:15** | Full demo rehearsal ×3, out loud, timed. Rehearse the failure recovery. | | |
| **H17:15–18** | Buffer. Do not fill it. | | |

**Stack:** faster-whisper (ASR) · librosa (prosody) · CLAP (audio-text embeddings) · Claude/GPT + Instructor + Pydantic (structured fingerprints & rerank) · LanceDB (embedded, no server to babysit) · FastAPI · Next.js + Tailwind. No GPU required if Tier A stays at 40 items and you pre-transcribe overnight.

---

## 14. Demo script — 3 minutes

1. **(0:00)** Empty state — eight mood starters, no shows, no genres. **"There's no browse grid here. We don't show you a catalog, we show you feelings."** Tap the hero starter: *"something that feels like a rainy Sunday after heartbreak."*
2. **(0:20)** Three shelves resolve. Read the shelf labels aloud — *Sit in it · Somebody with you · Somewhere else entirely.* Land the point: **"We didn't guess. We noticed the query was ambiguous and answered all three ways."**
3. **(0:50)** Point at one explanation line. *"Because you didn't ask to feel better — you asked to feel it properly."*
4. **(1:10)** Point at the entry point. **"It's not sending you to a 200-episode series. It's sending you to Episode 34, because that's the arc that feels like this."**
5. **(1:30)** Drag the *heavier → lighter* slider. Results re-rank instantly. **"Refinement happens in mood space, not by re-typing."**
6. **(1:50)** Fresh search, type *"bore ho raha hoon."* One question appears, four taps. **"When the query is too thin to split three ways, we ask once — never a form, never twice."** Tap an answer, shelves resolve instantly.
7. **(2:15)** Flip to the baseline panel. Same query, genre search. It returns thrillers because of the word "heartbreak." **"This is what discovery looks like today."**
8. **(2:30)** Metrics slide. Mood Match Rate, 2× lift, method: 200 simulated Indian listeners × 20 emotional scenarios. **"We didn't just build it, we measured it — against a listener panel, not against our own taste."**
9. **(2:50)** Close on the audio pipeline diagram: **"The mood signal comes from the voice, not the tags. That's something only an audio company can build."**

Rehearse the recovery line for a live failure: *"cached run"* — and have it ready on a second tab.

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Fingerprint quality is mediocre → results feel random | Spend H1–4 on prompt iteration with a human in the loop. Hand-curate the worst 15. At 640 items, curation is honest. |
| Live API latency kills the demo | Pre-cache all demo queries. Demo must run offline. |
| Integration slips past H8 | Contract-first schemas at H0. Hard cut of Tier B if H9 passes. |
| Judges see "it's just RAG on synopses" | Lead with the audio pipeline and the prosody fusion. Show a case where text-only gets it wrong and audio fixes it. Have that example ready. |
| 3-shelf output reads as "couldn't decide" | Frame it explicitly as intent disambiguation *before* they can form that thought. It's in the script for a reason. |

---

## 16. Beyond the hackathon

- **Mood → completion loop.** Log which mood queries produce full-arc completion. That is a training signal nobody else has, and it turns the fingerprint index into a learned one.
- **Ambient mood.** Time of day, weather API, day of week as query priors. "Rainy Sunday" is *literally inferable* on a rainy Sunday.
- **Mood-as-a-shelf on home.** Once fingerprints exist, the whole home feed can be reorganised by felt experience rather than genre rails.
- **Creator side.** Same index tells writers what emotional territory is underserved. "Nobody in the catalog delivers *warm + low-stakes + 20-minute*." That's a commissioning brief.
- **Multilingual mood.** Emotional vocabulary is language-specific — *saundhi*, *udaas*, *sukoon* don't have clean English mappings. Native-language mood queries are a genuine Bharat moat.

---

## Appendix — H0 code artifacts

| File | Owner after freeze | What it is |
|---|---|---|
| `schemas.py` | all three (frozen) | The contract. Nobody edits alone. |
| `mood_config.py` | Sahil | Starters, slider map, `DESTINATION_TARGETS` / `DESTINATION_FILTERS`, sparsity heuristic, clarify builder. Tuning lives here so nobody touches `schemas.py`. |
| `mock_api.py` | Ankit | Five endpoints, real shapes, fake data. Replace `fake_parse()` at H1 and `fake_results()` at H8 — signatures stay. |
| `test_contract.py` | Sahil | Run before building. Covers all three modes, slider clamping, distance sanity, prior-override rules. |

```bash
pip install pydantic fastapi uvicorn
python3 test_contract.py
uvicorn mock_api:app --reload --port 8000
```
