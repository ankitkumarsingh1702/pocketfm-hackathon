/**
 * Mood-First Search — the walkthrough content.
 *
 * Diagrams, speaker notes and the tuned numbers, kept out of the components so
 * the copy can be corrected without touching rendering code.
 *
 * THESE DESCRIBE THE CODE, NOT THE PITCH. Every node was traced out of
 * `backend/app/mood/` and then adversarially re-checked against the source, so
 * where the honest answer is "this is a static table, not a model", the diagram
 * says so. That constraint is the whole value of showing it: the audience may go
 * on to read the source, and an aspirational box would be worse than no box.
 *
 * The class names carry the meaning — `llm` is a model call, `det` is
 * deterministic, `safe` is a safety gate, `out` is something the listener sees.
 * Most boxes are `det`, which is the point: this is mostly ordinary, testable
 * code with a few model calls in it.
 *
 * Colours are literal rather than `var(--token)` because mermaid resolves them
 * itself, and because it keeps the source portable — pasting a diagram into a
 * deck or a README carries its styling with it. They mirror the design tokens.
 */

const LLM = 'fill:#fdecec,stroke:#f4b8b8,color:#111111'
const DET = 'fill:#f6f6f6,stroke:#e6e6e6,color:#111111'
const SAFE = 'fill:#ffffff,stroke:#a93636,stroke-width:2px,color:#111111'
const OUT = 'fill:#ffffff,stroke:#111111,stroke-width:1.5px,color:#111111'

const PALETTE = `  classDef llm ${LLM}
  classDef det ${DET}
  classDef safe ${SAFE}
  classDef out ${OUT}`

/* ------------------------------------------------------------- at a glance --- */

// The opener: twelve nodes, one story. The detailed view below is the same flow
// with nothing elided — this one exists because a 32-node diagram is a bad first
// thing to put on a projector.
const GLANCE = `flowchart TD
  Q["A listener types a feeling<br/>'something like a rainy Sunday after heartbreak'"]
  P["Read the sentence<br/>one model call, with a keyword floor under it"]
  MODE{"Which answer is honest<br/>for what they actually gave us?"}
  SAFETY["Distress · answer gently<br/>helplines, and no search runs at all"]
  ASK["Almost nothing said · ask ONE thing<br/>the answer moves the target directly"]

  subgraph THREE["A feeling, read three ways at once"]
    T1["Stay with the feeling"]
    T2["Somebody with you"]
    T3["Somewhere else entirely"]
  end

  SHELF["For each reading, in parallel:<br/>narrow → BLOCK WHAT WOULD HARM → score → diversify → judge"]
  DONE["Three shelves, each a doorway<br/>'Start at Ep 34 — the monsoon arc'"]
  PLAY["The episode list opens AT episode 34<br/>not at episode 1"]
  NUDGE["Heavier · slower · warmer<br/>instant, and no model in the path"]

  Q --> P --> MODE
  MODE -->|"distress"| SAFETY
  MODE -->|"too thin to split"| ASK
  MODE -->|"ambiguous"| THREE
  ASK -->|"one tap"| THREE
  T1 --> SHELF
  T2 --> SHELF
  T3 --> SHELF
  SHELF --> DONE --> PLAY
  DONE --> NUDGE
  NUDGE --> SHELF

${PALETTE}
  class P,SHELF llm
  class T1,T2,T3,ASK,NUDGE det
  class MODE,SAFETY safe
  class Q,DONE,PLAY out`

/* --------------------------------------------------------------- end to end --- */

const MAIN = `flowchart TD
  IN["Free text feeling<br/>'aaj bahut akela lag raha hai'"]

  subgraph S1["1 · Understand the sentence"]
    DISP{"Parser dispatch"}
    LLMP["LLM parse · 1 call<br/>9 axes + destination + intensity"]
    HEUR["Keyword floor · no model<br/>18 mood words, if/elif chain"]
    FLOOR["distress = regex OR model<br/>named loss floors intensity 0.75"]
    SANE["Sanity floor<br/>drop a destination the text cannot support"]
    DISP -->|"client resolved"| LLMP
    DISP -->|"no credentials"| HEUR
    LLMP -->|"any exception"| HEUR
    LLMP --> FLOOR
    FLOOR --> SANE
  end

  IN --> DISP

  subgraph S2["2 · Two gates before any search"]
    GS{"distress flag set?"}
    GC{"too little signal?<br/>sparsity 0.60 or above"}
    GS -->|"no"| GC
  end

  SANE --> GS
  HEUR -->|"skips the sanity floor"| GS

  SAFETY["mode = safety<br/>fixed Hinglish message<br/>Tele-MANAS 14416 · KIRAN 1800-599-0019"]
  CLARIFY["mode = clarify<br/>one question · options · skip"]
  DEST["rank_destinations · static table<br/>exactly 3 readings of the feeling"]

  GS -->|"yes · returns before retrieval"| SAFETY
  GC -->|"ask one question"| CLARIFY
  CLARIFY -->|"answer sets sparsity to 0.0"| DEST
  GC -->|"enough signal"| DEST

  subgraph S3["3 · Three shelves, three threads"]
    FAN["ThreadPoolExecutor · 3 workers"]
    TGT["resolve_target<br/>destination centroid nudged for this listener"]
    FAN --> TGT
  end

  DEST --> FAN

  subgraph S4["4 · Filters and safety masks · BEFORE any scoring"]
    M1["Base mask · never relaxes<br/>language · avoid tags · session length"]
    M2["Destination axis bounds<br/>relax 0 · 0.10 · 0.22 · 0.40 until 12 rows"]
    M3["Exclude series the listener finished"]
    M4["Contraindication codes<br/>set intersection · row switched off"]
    M5["Despair shape<br/>hopeless AND bleak AND heavy"]
    TGT --> M1 --> M2 --> M3 --> M4 --> M5
  end

  subgraph S5["5 · Only now do we score"]
    EMB["Embed the query text · cached by exact string"]
    SC["Fused score<br/>axis 0.45 · semantic 0.30 · tags 0.20 · affinity 0.12"]
    DD["One arc per series"]
    MMR["MMR to 8 · relevance 0.72 vs feel distance 0.28"]
    EMB --> SC --> DD --> MMR
  end

  NOSHELF["No shelf returned"]

  M5 -->|"blocked rows can never reach the judge"| EMB
  M5 -->|"mask empty · nothing left to score"| NOSHELF

  subgraph S6["6 · Judge, then doorway"]
    RR["Reranker · 1 LLM call per shelf<br/>score 0-10 + one quoted line + harmful flag"]
    HR["Heuristic judge · deterministic<br/>retrieval score + good_for bonus"]
    CUT["Drop flagged · keep top 3"]
    ENT["resolve_entry<br/>'Start at Ep 34' or swap to an earlier arc"]
    RR --> CUT
    HR --> CUT
    CUT --> ENT
  end

  MMR -->|"8 candidates"| RR
  RR -->|"call fails"| HR

  ENT --> ASM["Assemble shelf · 3 cards + label + target axes"]
  ASM -->|"zero cards survived"| NOSHELF
  ASM --> RESP["mode = shelves · 1 to 3 shelves"]
  NOSHELF -->|"all three empty · re-ask"| CLARIFY

  RESP --> UI["Three readings on screen<br/>the listener's click is the disambiguation"]
  UI --> DOOR["Card tap · doorway<br/>episode list from the entry point · no model call"]
  UI --> NUDGE["Nudge chip · refine<br/>one shelf swapped in place"]
  NUDGE --> UI

${PALETTE}
  class LLMP,RR,EMB llm
  class DISP,HEUR,SANE,DEST,FAN,TGT,M1,M2,M3,SC,DD,MMR,HR,CUT,ENT,ASM det
  class FLOOR,GS,GC,SAFETY,M4,M5 safe
  class IN,CLARIFY,RESP,UI,DOOR,NUDGE,NOSHELF out`

/* ------------------------------------------------------------ inside a shelf --- */

const RETRIEVAL = `flowchart TD
  Q["MoodQuery + one destination<br/>one of the three shelf threads"]
  T["resolve_target<br/>destination centroid nudged for this listener"]
  B["Base mask · never relaxes<br/>language · avoid tags"]
  D{"does session length leave 12 rows?"}
  DA["apply the duration mask"]
  DB["drop the duration constraint silently"]
  R{"Destination axis bounds<br/>relax 0 · 0.10 · 0.22 · 0.40"}
  X["Exclude series the listener finished · hard mask"]
  C["Contraindication codes<br/>listener codes intersect authored codes"]
  DS["Despair shape<br/>hope low AND valence low AND weight high<br/>armed for fresh grief and breakup only"]
  NONE["Return no shelf rather than an empty one"]
  E["Embed raw_text · cached by exact string"]
  F["score = 0.45 axis + 0.30 semantic + 0.20 tags + 0.12 affinity<br/>divided by 1.07 · masked rows set to minus infinity"]
  P40["Keep the best 40"]
  U["One arc per series · no back fill from rank 41"]
  M["MMR to 8<br/>0.72 relevance minus 0.28 redundancy, in axis space"]
  J{"Which judge?"}
  JL["LLM · one batched call<br/>score 0-10, harmful flag, 120-char reason"]
  JH["Heuristic · retrieval score + 0.12 good_for<br/>re-runs the codes and the despair rule itself"]
  K["Drop flagged · sort by judge score · keep 3"]
  EN{"entry episode past 12?"}
  SW["Swap the doorway to an earlier sibling arc"]
  LB["Render 'Start at Ep N — arc label'"]
  CARD["3 ResultCards + the shelf's target_axes"]

  Q --> T --> B --> D
  D -->|"yes"| DA
  D -->|"no"| DB
  DA --> R
  DB --> R
  R -->|"under 12 rows · widen one rung"| R
  R -->|"12 rows survive"| X
  R -->|"all four rungs fail · bounds abandoned"| X
  X --> C --> DS
  DS -->|"mask empty"| NONE
  DS -->|"safe pool only"| E
  E --> F --> P40 --> U --> M
  M --> J
  J -->|"credentials resolved"| JL
  J -->|"no credentials, or the call throws"| JH
  JL --> K
  JH --> K
  K --> EN
  EN -->|"yes · sibling 35% earlier, within 0.015 of the match"| SW
  EN -->|"no"| LB
  SW --> LB
  LB --> CARD

${PALETTE}
  class E,JL llm
  class T,B,D,DA,DB,R,X,F,P40,U,M,J,JH,K,EN,SW,LB det
  class C,DS safe
  class Q,NONE,CARD out`

/* ------------------------------------------------------ offline index build --- */

const OFFLINE = `flowchart TD
  A["catalog.json<br/>series · arcs · synopsis · source"]
  B["episodes.json<br/>playable units + duration_sec"]
  C["profiles.json<br/>demo listeners"]
  V["validate_sources CLI · run by hand<br/>exit 1 on errors · nothing imports it"]
  L["load_source to SourceSeries<br/>language defaults en · source defaults unknown"]
  LV["optional LibriVox pad<br/>live HTTP · rejects thin records"]
  MG["merge · curated first · dedupe · cap 600"]
  SG{"source looks model written?"}
  DROP["whole series dropped, every arc with it"]
  AR{"arcs authored?"}
  SY["synthesize up to 3 even arcs<br/>every summary becomes the whole synopsis"]
  DM["episode_seconds map<br/>first read · silent no-op if the path is missing"]
  FP["fingerprint_arc<br/>ONE LLM call per ARC · text in, text out<br/>9 axes + tags + vibe line + good_for + wrong_for"]
  NOAUD["No audio · no ASR · no prosody · no CLAP<br/>every number is one text model reading someone's prose"]
  PA["parse + clamp<br/>missing axis becomes 0.5<br/>unparseable valence drops the whole arc"]
  EM["embed vibe_sentence + sensory_tags<br/>Vertex, else local model, else 256-dim hashing"]
  SV["moodstore/vectors.npz + fingerprints.jsonl<br/>no manifest, no embedder identity recorded"]
  ES["build_episode_store · second read<br/>authored episodes win · stubs fill 'Episode N' at 1200s"]
  SE["moodstore.episodes.jsonl · sibling path, not inside the dir"]
  CHK["entry_episode membership check<br/>prints the first 10 problems · exit code unchanged"]
  E1["MOOD_INDEX"]
  E2["MOOD_EPISODES"]
  E3["DEMO_PANEL · bypasses ingest entirely"]
  RUN["FastAPI reads all three once, at import"]
  SEED["build_seed_catalog<br/>48 invented series + 3 trap arcs · what a deploy serves today"]

  A --> V
  B --> V
  V -->|"advisory only"| L
  A --> L
  L --> LV --> MG --> SG
  SG -->|"yes and the flag is not set"| DROP
  SG -->|"no · 'unknown' passes the denylist"| AR
  AR -->|"yes"| FP
  AR -->|"no"| SY
  SY --> FP
  B -->|"first read"| DM
  DM --> FP
  FP -.- NOAUD
  FP --> PA --> EM --> SV
  B -->|"second read"| ES
  ES --> SE
  SV --> CHK
  SE --> CHK
  SV --> E1
  SE --> E2
  C --> E3
  E1 --> RUN
  E2 --> RUN
  E3 --> RUN
  RUN -->|"index path missing"| SEED

${PALETTE}
  class FP,EM llm
  class A,B,C,V,L,LV,MG,SG,AR,SY,DM,PA,ES,CHK det
  class NOAUD,DROP safe
  class SV,SE,E1,E2,E3,RUN,SEED out`

/* ---------------------------------------------------------------- refine loop --- */

const REFINE = `flowchart TD
  T["Nudge chip<br/>warmer · heavier · faster · stranger<br/>always exactly +1 or -1, one control per tap"]
  P["POST /api/mood/refine<br/>query_id + shelf_id + the shelf's own target_axes + raw delta"]
  S["Session lookup in process<br/>same query, same listener · finished-series mask survives"]
  N["Fold one control into up to 4 axis deltas<br/>nudge and clamp · pure arithmetic"]
  SL["Per-axis slack · min of 0.40 and delta x 1.8<br/>only on bounds this destination declares"]
  W["Refine weights<br/>axis 0.78 · semantic 0.10 · tags 0.07 · affinity 0.05"]
  R["retrieve · same masks, same two safety layers<br/>embed is a cache hit, the text has not changed"]
  H["HeuristicReranker · hard wired on this path<br/>retrieval score + 0.12 good_for + template reason"]
  NL["No LLM anywhere on this path · that is the latency contract"]
  O["One shelf back, carrying its new target_axes"]
  U["Client swaps only the shelf whose id matches<br/>the other two keep their data, so drags compound"]

  T --> P --> S --> N --> SL --> W --> R --> H --> O --> U
  H -.- NL
  U -->|"next nudge starts from the moved point"| T

${PALETTE}
  class S,N,SL,W,R,H det
  class NL safe
  class T,P,O,U out`

/* -------------------------------------------------------------------------------- */

export const MOOD_FLOW_VIEWS = [
  {
    id: 'glance',
    label: 'At a glance',
    caption:
      'One sentence in, three shelves and a doorway out. The three branches are the whole product argument: an ambiguous feeling is answered three ways rather than guessed at, a thin one gets exactly one question, and genuine distress never reaches retrieval at all.',
    definition: GLANCE,
  },
  {
    id: 'main',
    label: 'End to end',
    caption:
      'The same flow with nothing left out, including every fallback. Pink is a model call; white with a red edge is a safety gate. Notice how few boxes are models — most of this is deterministic, which is what makes it explainable and testable.',
    definition: MAIN,
  },
  {
    id: 'retrieval',
    label: 'Inside one shelf',
    caption:
      'How a shelf is actually built. The ordering is the point: both safety layers finish while we are still doing boolean masks, so a blocked arc is never scored, never ranked and never seen by the judge — it cannot lose narrowly and slip through.',
    definition: RETRIEVAL,
  },
  {
    id: 'offline',
    label: 'How the index is built',
    caption:
      'The offline half, one model call per arc. Two things worth saying out loud: arc boundaries are the highest-value thing a human curates, and there is no audio stage anywhere in this build.',
    definition: OFFLINE,
  },
  {
    id: 'refine',
    label: 'The refine loop',
    caption:
      'Refinement happens in mood space, not by re-typing. Nothing in this path calls a model or the network — which is what keeps a nudge instant, and why the axis weight rises to 0.78: a deliberate drag is stronger evidence than the original sentence.',
    definition: REFINE,
  },
]

export const MOOD_FLOW_NARRATION = [
  {
    beat: 'The ask',
    say: 'A listener does not know what they want to hear. They know how they feel. So the only input is one sentence in their own words — Hinglish, English, whatever comes out. No genre, no filters, no dropdowns. Everything from here down is machinery for turning that one sentence into three shelves and a first episode to press play on.',
    point_at: 'At a glance · the input at the top',
  },
  {
    beat: 'One model call to read it, and a floor under that',
    say: 'One call turns the sentence into structure: nine mood axes, a guess at what they want from us, and how intense the feeling is. If the model is unavailable, or the call throws, or the JSON is wrong, we fall through to a deterministic keyword floor. The product still works with zero model calls — it just works less well, and we can tell you exactly which half degrades.',
    point_at: 'End to end · LLMP, and the fallback edge into HEUR',
  },
  {
    beat: 'Safety is a gate, not a ranking signal',
    say: 'Before anything is searched, the distress check runs. It is regex-first and the model is OR-ed in, so the model can only ever raise the flag, never clear it. If it fires we return two helplines and stop. No retrieval runs, no shelves are built. Those numbers are string constants, because a model must never paraphrase a phone number.',
    point_at: 'End to end · GS and SAFETY',
  },
  {
    beat: 'Too thin to split? Ask once instead of guessing three times',
    say: '"bore ho raha hoon" is four words and carries almost no signal. Rather than confidently invent three shelves out of nothing, we ask exactly one question — and never a second. There is a guard on our own model here too: if it returns a confident intent on text our heuristic reads as empty, we throw the intent away and ask anyway.',
    point_at: 'End to end · GC and CLARIFY',
  },
  {
    beat: 'Three readings, not one ranked list',
    say: '"I feel alone" has at least three honest answers: sit in it with me, keep me company, or take me somewhere else. We do not pick. We build all three concurrently in three threads and let the click be the disambiguation. That is one round trip, not three.',
    point_at: 'End to end · the S3 block, node FAN',
  },
  {
    beat: 'The load-bearing ordering: blocking happens before scoring',
    say: 'This is the part I most want you to notice. Everything that could hurt someone is removed while we are still doing boolean masks over the catalog — the written contraindications, then a structural despair rule that catches stories nobody thought to tag. Only after those masks settle do we embed the query and score anything. A blocked arc is never scored, never ranked, never seen by the judge. It cannot lose narrowly and slip through.',
    point_at: 'End to end · M4 and M5, and the edge labelled "blocked rows can never reach the judge"',
  },
  {
    beat: 'How ranking actually works',
    say: 'The score is a fusion, and axis distance is deliberately the biggest term at 0.45 — bigger than the embedding at 0.30. That is a choice, not a fit: if embeddings outvoted the mood axes, dragging "heavier" would not get heavier and the controls would be theatre. Listening history is in there too, capped under the axis term, so this stays mood search and does not quietly become collaborative filtering.',
    point_at: 'Inside one shelf · F, the fused score',
  },
  {
    beat: 'One act of judgement produces both the score and the sentence',
    say: 'Eight candidates go to the judge in a single call, and it returns a score and the one line the listener reads, together. The explanation is not written afterwards to justify a number — it is the same judgement. If that call fails we degrade to a deterministic reranker that re-runs the safety checks itself. Being honest: the model judge does not re-run them, it trusts its own harmful flag, so that second deterministic layer only exists on the degraded path.',
    point_at: 'End to end · RR and the fallback edge to HR',
  },
  {
    beat: 'The doorway, and the nudge',
    say: 'A mood match on episode 140 of a 200-episode show is useless, so the last deterministic step picks the doorway — "start at Ep 34" — and will swap to an earlier arc of the same series if that saves you a third of the episodes for almost no loss in match quality. Tapping a card makes no model call. And if a shelf is close but not right, a nudge re-enters the same retriever with no model in the path at all, and swaps just that one shelf.',
    point_at: 'End to end · ENT, then DOOR and NUDGE; then The refine loop · NL',
  },
]

export const MOOD_FLOW_QA = [
  {
    question:
      'There is no audio anywhere in this. You call it mood search but never listen to the audio — so "mood comes from the voice, not the tags" is a claim you cannot make.',
    answer:
      'Correct, and we should say it before you find it. There is no audio, no ASR, no prosody model and no CLAP in this build. Every number in every fingerprint is one text model\'s inference over a synopsis and an arc summary — the ingest module says so in its own docstring. Two honest consequences we have not hidden: audio_verified is hardcoded False by ingest, and axes_variance is hardcoded 0.0. The defensible part of the claim is architectural, not empirical: the fingerprint is a nine-axis felt-quality vector with authored contraindications, and that vector is the durable artifact on disk. Swapping the text fingerprinter for an audio one changes exactly one function and nothing downstream of it. What we have proven is the retrieval, safety and doorway machinery around that vector — not that we derived it from a voice.',
  },
  {
    question: 'Is the catalog real, or did you generate it?',
    answer:
      'What a deploy serves right now is a synthetic fixture: 48 invented series with two to four arcs each, plus three deliberate trap arcs, under a fixed seed — 145 arcs across 51 series. No workflow sets MOOD_INDEX, so the service falls back to that fixture, and /api/mood/health is the surface that admits it. The ingest path for real data is fully implemented and runnable, but the three authored source files are not in this repo, so it has never been run on real catalog data here. There is one deliberate defence against self-dealing: any series whose source field names a model is dropped whole from ingest unless you explicitly pass --allow-synthetic. It is a denylist though, not an allowlist, so an omitted source defaults to "unknown" and passes. There is also a LibriVox adapter that ingests real public-domain human prose, which proves the fingerprinter works on writing nobody here produced — but it returns Victorian literature, the wrong register for Pocket FM, so it pads the index and must never reach the eval set.',
  },
  {
    question:
      'Is the evaluation not circular? You wrote the catalog, you wrote the mood labels, and you wrote the queries.',
    answer:
      'On the synthetic fixture, yes — measuring retrieval quality against labels generated by the same family of model tells you the pipeline is self-consistent and nothing more. We are not claiming a quality number from it. What the fixture is genuinely good for is the parts that are not circular: the three trap arcs exist so that a grieving listener\'s query has something that should be blocked, and the despair mask either catches them or it does not — that is a pass/fail behavioural test, not a preference judgement. The relax ladder, the one-arc-per-series rule, the entry-point swap and the mode branching are all deterministic and testable without circularity. What we cannot honestly evaluate yet is whether the mood axes match how human listeners feel about real Pocket FM content. That needs real catalog data and real listeners, and the correct answer is that it is the top of the post-hackathon list, not something we have solved.',
  },
  {
    question: 'Strip away the framing — is this not just RAG over synopses with a nice UI?',
    answer:
      'The embedding is 0.30 of the score, deliberately the smaller of the two main terms. The 0.45 term is weighted euclidean distance in a nine-axis felt-quality space — catharsis, warmth, hope, weight, tension and so on, each with its own weight in the metric — and that is what makes the controls work: a nudge toward "heavier" moves the centroid and the results actually change, which pure semantic search cannot do because the query text never changed. Three things here are not RAG at all. First, a closed-vocabulary safety layer removes content before anything is scored, plus a structural axis rule that catches despair-shaped stories whose prose never named a contraindication. Second, the output is three competing interpretations of one ambiguous feeling, not one ranked list. Third, the answer to "where do I start" is a deterministic doorway calculation over sibling arcs, not a retrieval result. And the Lab panel runs a keyword baseline beside the mood shelves precisely so you can look at the difference yourself rather than take our word for it.',
  },
  {
    question: 'How many model calls does one search cost, and what is the latency story?',
    answer:
      'Best case on the shelves path: one parser call, one embedding call inside retrieval, and three reranker calls — one per shelf, fired concurrently in three threads, so you pay the reranker wait once rather than three times. The safety and clarify paths make no retrieval calls at all, which also means the latency those paths report is milliseconds of regex and dict lookups and is not comparable to the shelves number — we should not let that read as a speed claim. The refine loop is the deliberately fast path: hard-wired to a heuristic reranker, never a model, and the embedding is a cache hit because the raw text has not changed, so a nudge is arithmetic plus numpy. One caveat we know about: on a cold process, or if the in-process session is lost, refine re-parses empty text and pays a real embed round trip, so sub-200ms is a warm-path figure.',
  },
  {
    question: 'What happens when the model is down or the credentials are missing?',
    answer:
      'Everything online degrades rather than fails, and everything offline refuses to run — that asymmetry is intentional. Online: the parser falls back to a keyword floor, the reranker to a heuristic reusing the retrieval score, and the embedder through a local model down to 256-dimension character hashing. You get worse shelves, not an error page. We should be precise about what is lost, though: intensity_tolerance is only ever set by the model, so on the keyword floor half of the centroid personalisation silently does nothing; the parser\'s sanity floor is model-path only; and all twelve distress patterns are latin-script, so Devanagari self-harm text is undetected without a live model. Offline, ingest does the opposite and exits rather than fingerprint a catalog with a heuristic — a bad index is permanent, a bad response is one request.',
  },
  {
    question: 'Where are the real holes in the safety story? Do not tell me it is airtight.',
    answer:
      'It is not airtight, and here are the ones we know. First and worst: the distress gate lives inside the search response function, not on the router, so /refine bypasses it — a distress query_id plus any shelf_id will run full retrieval and return shelves. Second: the entry-point swap runs after all masking and consults only series_id, so it can land the doorway on a sibling arc that was contraindication-blocked or language-filtered. That is the one place the "blocked content never reaches the listener" claim actually has a hole. Third: the structural despair mask is armed only for fresh grief and breakup, and a low intensity score can strip those codes from mood-only evidence, so a mildly-scored "dil toot gaya" can lose both layers at once. Fourth: the model judge does not re-run the deterministic contraindication check — it trusts its own harmful flag — so the deterministic second layer exists only on the heuristic path, which is the wrong way round. Separately, the crisis text is sent to the model before any safety decision exists; what we actually guarantee is monotonicity, not ordering.',
  },
  {
    question: 'How are the three shelves chosen? Is a model deciding what I need?',
    answer:
      'No, and I want to be exact because the function name oversells it. rank_destinations is a static table with no model and no scoring. If the parser committed to an explicit intent, that goes first. Then a substring test for negative words over the felt state picks one of exactly two hardcoded three-item pools — sit-with, company, escape if the words look negative, otherwise company, lift-gently, escape — truncated to three. Two consequences we know about: "make sense of" and "sleep" can never appear as shelves unless the parser named one explicitly, and the negativity test is English-only, so the Hinglish words our own keyword floor produces — udaas, tanha, dukhi — do not match it, meaning a Hinglish query on the fallback path gets no sit-with shelf at all. There is also a tie-break on a listening-history prior that is dead code in production. The design intent stands, the implementation is a table, and the Hinglish gap is a real bug.',
  },
  {
    question: 'You show numbers like 0.45 and 0.72 — how were those tuned, or did you just pick them?',
    answer:
      'Some were reasoned, some were fixed after a visible failure, and I can tell you which. The 0.45 axis weight against 0.30 semantic is a design constraint, not a fit: axis has to dominate or the mood controls do not move the results. The refine weights shift to 0.78 axis because under the defaults the semantic and tag terms are constants across a nudge, so a full drag moved only about 22% of the score and two controls were literal no-ops — that one was found by using it. The entry-swap epsilon was 0.04 and fired on essentially every result, collapsing every entry point to episode 1 and deleting the whole "start at Ep 34" proposition; it is now 0.015. The despair thresholds are narrow because in our fixture the traps sit at hope 0.05 to 0.15 while the sit-with neighbourhood is floored at 0.30, so there is real margin — widening it would empty the shelf a grieving listener most wants. And the 1.07 normaliser is honestly a display fix: unnormalised, scores clipped at 1.0 and the top of the ranking lost its ordering.',
  },
  {
    question: 'What breaks first if you put this in front of real traffic tomorrow?',
    answer:
      'Session state. The sessions map is a plain in-process dict with no TTL and no eviction, and it is what /clarify and /refine look up — so under more than one worker, or after any restart, both start returning "unknown query_id". On refine that failure is invisible: the backend answers HTTP 200 with an error body, the client reads shelves[0], finds nothing and returns early, so a failed nudge looks exactly like a nudge that changed nothing. Second: the three shelf threads share one module-level engine whose debug trace is overwritten wholesale per search, and the embedding cache is an unsynchronised dict, so concurrent requests can clobber each other. Third: the parser is instructed to leave language null, but if it ever sets one it becomes an exact-match filter in the mask that never relaxes — every shelf returns zero and the listener sees a clarifying question instead of an error, a silent total failure that looks like a normal product state.',
  },
]

export const MOOD_FLOW_CONSTANTS = [
  {
    name: 'SPARSITY_THRESHOLD',
    value: '0.60',
    why: 'The single dial between "ask" and "answer". Above it the request becomes one clarifying question instead of three guessed shelves — and answering sets sparsity to 0.0, which is what stops a re-ask loop. schemas.py:233',
  },
  {
    name: 'EVENT_INTENSITY_FLOOR',
    value: '0.75 on the model path; the keyword path assigns 0.85 outright',
    why: 'A named death or rupture must not be talked below the contraindication gate by calm wording. The two paths differ: one is a floor, the other a direct assignment. parser.py:147,169',
  },
  {
    name: 'INTENSITY_GATE / GATED_CODES',
    value: '0.45 / {fresh_grief, breakup}',
    why: 'Below 0.45 a mild mood word stops counting as a contraindication — but a named EVENT is exempt, which is why "my mother died" keeps its protection even when phrased flatly. contraindications.py:111-112',
  },
  {
    name: 'Despair-shape rule',
    value: 'hope ≤ 0.20 AND valence ≤ −0.50 AND weight ≥ 0.75',
    why: 'All three must hold. Deliberately narrow: trap arcs sit at hope 0.05–0.15 while the sit_with neighbourhood is floored at 0.30, so it separates with margin instead of emptying the shelf a grieving listener most wants. contraindications.py:137-140',
  },
  {
    name: 'Score weights + normaliser',
    value: 'axis 0.45 · semantic 0.30 · tags 0.20 · affinity 0.12, ÷ 1.07',
    why: 'Axis distance dominates so the mood controls visibly steer results. The ÷1.07 does not change ranking; it keeps scores off the rerankers\' [0,1] clamp so ordering survives display. retrieval.py:63-66,256-258',
  },
  {
    name: 'Refine weights',
    value: 'axis 0.78 · semantic 0.10 · tags 0.07 · affinity 0.05',
    why: 'On a nudge the text is unchanged, so the semantic and tag terms are constants. Under the defaults a full drag moved ~22% of the score and two controls were literal no-ops. retrieval.py:126',
  },
  {
    name: 'AFFINITY_CEILING',
    value: '0.22',
    why: 'History scales up with query sparsity but is capped under the 0.45 axis term. This keeps it mood search rather than collaborative filtering. retrieval.py:43,102-106',
  },
  {
    name: 'relax_steps / min_pool',
    value: '(0.0, 0.10, 0.22, 0.40) / 12',
    why: 'Bounds widen rather than starve a shelf: an approximate shelf reads as "close, let me nudge it", an empty one reads as broken. If all four rungs fail the bounds are abandoned entirely. retrieval.py:71-72,211-223',
  },
  {
    name: 'pool / RETRIEVE_K / RESULTS_PER_SHELF',
    value: '40 / 8 / 3',
    why: '40 scored rows dedupe to one arc per series, MMR picks a spread of 8, the judge\'s top 3 become cards. retrieval.py:339-340, search.py:31-32',
  },
  {
    name: 'mmr_lambda / max_per_series',
    value: '0.72 / 1',
    why: 'Relevance leads, diversity corrects, both measured in the same weighted axis space. One arc per series, so a shelf offers options rather than a table of contents for one show. retrieval.py:68-69',
  },
  {
    name: 'AXIS_WEIGHTS (the distance metric)',
    value:
      'catharsis 1.3 · warmth 1.2 · valence 1.0 · hope 1.0 · tension 0.9 · weight 0.9 · arousal 0.8 · companionship 0.7 · pace 0.6',
    why: 'Reused for both ranking and MMR diversity so the two share one scale. Catharsis and warmth lead because they are what listeners actually notice. schemas.py:41-45',
  },
  {
    name: 'Entry-point swap',
    value: 'deeper than Ep 12 · saves ≥ 35% · costs ≤ 0.015 of match',
    why: 'The epsilon was 0.04, where the swap fired on everything and collapsed every entry point to episode 1 — deleting the "start at Ep 34" proposition while the tests still passed. entrypoint.py:35,40,44',
  },
  {
    name: 'SESSION_SLACK',
    value: '1.5',
    why: 'A stated session length is an estimate, so "15 minutes" still admits a 22-minute arc — and the duration mask is dropped entirely rather than starve the shelf. mood_config.py:209',
  },
  {
    name: 'SUPPORT_RESOURCES',
    value: 'Tele-MANAS 14416 · KIRAN 1800-599-0019',
    why: 'Hardcoded on the safety path, never model-generated. A model must not paraphrase a helpline number. India-only, with no locale switch yet. mood_config.py:25-28',
  },
  {
    name: 'DISTRESS_PATTERNS',
    value: '12 regexes, latin script only',
    why: 'English plus romanised Hinglish. High-precision by choice, not exhaustive — the model can only OR into it, never clear it. Devanagari text matches nothing without a live model. parser.py:40-45',
  },
  {
    name: 'Model calls per arc at ingest',
    value: '1 (~1,800 total vs ~90,000 at episode level)',
    why: '600 series × 3 arcs against 600 × ~150 episodes. A 20-minute episode has no stable felt quality distinct from its arc, so arc is the right unit and two orders of magnitude cheaper. catalog_ingest.py:242',
  },
  {
    name: 'Seed fixture (what a deploy serves today)',
    value: '48 invented series + 3 trap arcs — 145 arcs / 51 series',
    why: 'No workflow sets MOOD_INDEX, so the service builds from build_seed_catalog(). /api/mood/health is the only surface that admits it. seed_catalog.py:22,159-160',
  },
]
