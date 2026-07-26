# Design: genre conversion at novel length

Target: 200–250 pages, ~70,000 words. The current pipeline is built for ~1,000
words and does not extend by turning the dial up. This document says why, and
what to build instead.

This design is now implemented — `segment.py`, `bible.py`, `casting.py`, and
`longform.py` — and wired into the HTTP service: a convert past `MAX_CHARS`
runs this pipeline as the job's `longform` lane (see `api.py`). The rest of
this document is the original design rationale.

---

## 1. Why the current design does not scale

Four failures, in order of severity.

### 1.1 The rolling summary is a recursive compression chain

This is the one that matters and the one that is invisible until it is bad.

`transform.py` carries continuity forward by having each scene write two or three
sentences for the next. At six scenes that works — the current corpus runs at 5–7
scenes and the seams hold. At three hundred scenes, scene 200 is reading a summary
of a summary of a summary, two hundred rounds deep. Everything from the first
third of the book is gone except whatever survived being re-compressed a hundred
and fifty times.

**Lossy compression applied recursively converges on noise.** A larger context
window does not help, because the information was discarded by the pipeline, not
by the model.

The fix is not a longer summary. It is to stop summarising and start retrieving.

### 1.2 Extraction is a single call over the whole text

70,000 words is roughly 95,000 tokens. It fits in the window; that is not the
same as being read. Recall degrades sharply for material in the middle of very
long inputs, and `llm.structured` caps output at 16,000 tokens, which bounds how
large a skeleton can even be returned.

The practical result would be about fifteen beats for an entire novel — a blurb,
not a decomposition.

### 1.3 Alignment is quadratic and single-shot

`verify.align` renders both skeletons into one prompt and asks for a match per
source beat. At novel scale that is 800 source beats against 800 candidate beats
in a single call. There is no version of that prompt that works.

### 1.4 Granularity is length-blind

`models.py` asks for "8 to 15 beats for a short story". There is no correct flat
number for a novel. A novel is not a longer list of beats; it is a *tree* —
book, parts, chapters, scenes — and each level needs its own resolution.

### 1.5 A visible warning already

`plan_scenes` sweeps trailing non-load-bearing beats into the final scene. In the
current corpus run that produced a closing scene carrying four beats where every
other scene carried one or two. At novel scale this becomes systemic: the end of
every chapter gets overloaded and compressed. The bug is small today and
structural at length.

---

## 2. Principles

1. **Retrieval over recompression.** State is stored once and read from, never
   iteratively rewritten.
2. **Hierarchy over flat lists.** Every artifact has levels: book → act →
   chapter → beat.
3. **Decide once, reuse forever.** Names, places, and physical facts are fixed by
   one deliberate call, not re-invented per scene.
4. **Bounded prompts everywhere.** No prompt grows with the length of the novel.
5. **Verify locally, aggregate globally.** Score chapters; combine into a book
   number that can be traced back to the chapter that lost something.

---

## 3. Data structures

### 3.1 `StoryBible` — replaces the rolling summary

The single most important change in this document, so it is worth explaining
before defining.

**What it is, in one line:** a fact sheet about the story so far that gets added
to and never rewritten. The name comes from television — a "show bible" is the
document a writers' room keeps so the writer of episode 40 does not contradict
episode 3.

**What it replaces.** Today each scene hands the next one two or three sentences.
Scene 5 of the horror rewrite receives roughly:

> *Leo has confronted Ollerman in the archive. Ollerman admitted the forgeries
> and offered him the directorship. Leo is shaken.*

That is everything scene 5 knows about the preceding two thousand words. If scene
2 established that Ollerman moves stiffly, that the brass key sits in a
particular drawer, or that Leo makes himself smaller when nervous — gone, unless
it happened to be re-selected in four consecutive summaries. And each summary is
written from the previous summary, so the loss compounds rather than levelling
off.

**What it looks like instead:**

```
CHARACTERS
  protagonist   Leo Farrow, junior archivist, 29. Squeaking shoes.
                Makes himself smaller when nervous.
  gatekeeper    Mr Ollerman, Head Curator. Immaculate grey suit.
                Descends stairs with a stiff, jointed motion.

PLACES
  institution   The Palliative Wing. Leaded windows, water-stained
                ceiling, smells of old paper and dried herbs.

FACTS
  #4   Something drags itself across the floor above.      (scene 1)
  #9   The provenance records were forged by Ollerman.     (scene 2)
  #17  A small brass key sits on the director's desk.      (scene 6)
```

Scene 40 reads the same words scene 2 wrote — the entry itself, not a paraphrase
of a paraphrase of it. The facts do not degrade with distance.

**Why append-only.** A summary is rewritten every scene, so a detail survives
only by being re-selected three hundred times in a row. A bible entry is written
once and stays; nothing has to survive anything. When something genuinely changes
— a character dies, a secret breaks — the old fact is marked revoked rather than
deleted, so the history of when a thing became true is preserved.

**Why only a slice is sent.** By chapter 40 the bible is large, and sending all of
it would reintroduce the problem it solves. Each scene receives only the rows its
beats touch: the entities acting, the places named, the facts those beats depend
on. Ten rows, not four hundred. This is what keeps prompt size constant at any
book length.

**Where entries come from.** Casting fills it in up front — names, descriptions,
relationships, decided once before any prose exists. Then each scene *proposes*
new facts as it writes ("I established that the key opens the top drawer"), and
those are merged with a note recording which scene added them. That record is
also what makes drift debuggable: when chapter 30 contradicts chapter 4, you can
find the scene that introduced the contradiction. Today that is unrecoverable,
because the summaries are never written to disk at all.

#### The structure

```
Entity
  slug            role slug from the skeleton, or a new one for genre-invented cast
  name            the name used in the rewrite
  description     physical and manner, fixed at casting
  relationships   {other_slug: "what they are to each other"}
  established     [Fact]        # things now true and unrevisable

Place
  slug, name, description, first_seen_chapter

Fact
  text            "the letter is hidden in the workshop bench"
  chapter         where it became true
  beats           which beat ids established it
  status          established | revoked   # revoked keeps history rather than deleting

StoryBible
  entities: {slug: Entity}
  places:   {slug: Place}
  facts:    [Fact]
  revisions: [BibleRevision]     # every write, with the scene that made it
```

A scene reads **only the slice relevant to its beats** — the entities acting in
those beats, the places named, the facts those beats depend on. Prompt size stays
constant whether it is chapter 2 or chapter 40.

Writes are proposals: a scene returns *facts it established*, and those are merged
after the scene is accepted, with the revision log recording who wrote what. This
is the audit trail that makes drift debuggable.

### 3.2 `Casting` — decide the cast once

```
Casting
  genre
  entities: {role_slug: Entity}     # name, description, relationships
  places:   {place_slug: Place}
  register_notes: str               # naming conventions, era, honorifics
```

One call, before any prose. Today "Leo" is invented inside scene 1 and carried
onward by summary; across 300 scenes names, ages, and relationships will drift.
Fixing the cast up front is cheap and removes an entire class of failure.

### 3.3 `HierarchicalSkeleton`

```
BookSkeleton
  logline
  roles: [Role]
  acts: [ActSkeleton]

ActSkeleton
  id, summary, function          # what this act does to the whole
  chapters: [ChapterSkeleton]

ChapterSkeleton
  id, source_span                # which chunk of the source it came from
  summary
  beats: [Beat]                  # the existing Beat model, unchanged
```

The existing `Beat` and `Role` models carry over untouched. `causes` edges stay
within a chapter where possible, with cross-chapter edges recorded at act level.

---

## 4. Pipeline

### Stage 0 — Segment (deterministic, zero tokens)

Split the source on chapter markers where they exist; fall back to windowing on
blank-line runs at ~2,500 words with 200-word overlap. Emit a manifest of chunks
with character offsets. No model involved, so it is testable offline and the same
input always segments the same way.

### Stage 1 — Extract, bottom-up

1. **Per chunk, in parallel:** extract a `ChapterSkeleton`. Same prompt as today,
   same lint. Bounded input, bounded output, embarrassingly parallel.
2. **Reduce to acts:** feed chapter *summaries plus load-bearing beats only* into
   one call per act. Never the full beat list.
3. **Reduce to a book spine:** act summaries into 10–20 beats describing the whole
   arc.

Each level is separately lintable and separately cacheable. A change in chapter 12
re-extracts one chunk, not the book.

### Stage 2 — Cast and outline

1. **Casting call** — roles and places into concrete genre identities.
2. **Outline call per act** — the genre-concrete chapter plan: for each chapter,
   which beats it must deliver, its function, its position in the pacing curve.

The outline is what gives global structure. A purely sequential process can only
produce local continuity, which is why sequential long-form generation always
sags in the middle.

### Stage 3 — Write

Chapter by chapter, scene by scene within a chapter. Each scene call receives:

- the beats it owns (unchanged from today)
- the genre pack (unchanged)
- **the bible slice** for those beats — not a summary
- **the chapter's outline entry** — its job in the larger structure
- **the last ~200 words of the previous scene, verbatim** — for voice and seam
  continuity, which a summary handles badly
- the act-level summary for orientation

It returns prose, claimed beat coverage, and **proposed bible facts**.

Chapters whose bible dependencies are already satisfied can be generated in
parallel — which is the real payoff of casting and outlining first.

### Stage 4 — Verify hierarchically

1. **Chapter alignment:** match source chapters to rewritten chapters using
   chapter summaries. ~40 against ~40, one call, majority-voted as today.
2. **Beat alignment within matched pairs:** ~15 against ~15 per pair. Bounded,
   parallel, and reuses `verify.align` unchanged.
3. **Aggregate:** chapter fidelity, act fidelity, book fidelity — weighted by
   load-bearing beat count so a chapter that carries a pivot counts for more.

Quadratic becomes linear. And the output is *diagnostic*: "act 2 lost the
subplot" instead of "71%".

### Stage 5 — Continuity checks (deterministic, zero tokens)

Cheap checks over the bible that fidelity scoring cannot see:

- **Entity consistency** — one name per slug throughout; no name reused across slugs.
- **Timeline monotonicity** — no beat resolving before the beat it depends on.
- **Fact contradiction** — a fact established and later contradicted without a
  revocation.
- **Introduced and unused** — an entity or object established with weight and
  never paid off.

These run in ordinary Python and catch the failures readers actually notice.

---

## 5. Cost

For one 70,000-word novel into one genre, assuming ~40 chapters and ~120 scenes:

| Stage | Calls |
|---|---:|
| Chapter extraction | ~40 |
| Act + book reduction | ~8 |
| Casting + outline | ~6 |
| Scene writing | ~120 (+ retries) |
| Re-extraction of the rewrite | ~40 |
| Chapter alignment | 3 (voted) |
| Beat alignment | ~40 × 3 = 120 |
| **Total** | **~330–400** |

Parallelism matters more than raw count: stage 1 and stage 4 are fully parallel,
and stage 3 is parallel per chapter once the bible is fixed. Wall clock is bounded
by the longest chapter chain, not the sum.

Caching must be per chapter, not per book, so a failure at chapter 31 costs
thirty seconds rather than an hour.

---

## 6. Build order

1. **`StoryBible` + casting.** Biggest win per unit of work, and it improves
   quality at *any* length — worth doing even for the short-form pipeline.
2. **Persist everything.** Today only prose is cached; summaries and claimed beat
   coverage are thrown away. Drift you did not log is drift you cannot debug.
   This is a prerequisite for the rest, not a nicety.
3. **Segmentation + chapter-level extraction.** Deterministic, offline-testable.
4. **Hierarchical reduction to acts and book.**
5. **Outline-then-prose.**
6. **Hierarchical verification.**
7. **Continuity checks.**

Steps 1–2 are small and immediately useful. Steps 3–4 are the real work.

---

## 7. Risks and open questions

- **Bible conflicts.** Two scenes generated in parallel may each establish an
  incompatible fact. Needs either a merge policy or a serialisation point per
  chapter. Leaning toward: parallel within a chapter is forbidden, parallel
  across chapters is allowed only after the outline fixes what each chapter owns.
- **Chapter boundary detection** on sources without clean markers. The fallback
  windowing will sometimes cut mid-scene, which produces a bad chapter skeleton.
- **What "load-bearing" means at book scale.** A beat can be essential to its
  chapter and irrelevant to the novel. The flag probably needs to become a level,
  not a boolean.
- **Retrieval granularity.** Too narrow a bible slice and a scene contradicts
  something it never saw; too wide and the prompt grows with the book.
- **The ceiling problem does not go away.** It gets worse: extraction variance
  compounds across 40 chapters. The perturbed-input ceiling described in the
  README needs solving before any of these numbers can be trusted at length.
- **Length fidelity.** The short pipeline already expands 750 words into ~3,000.
  Unmanaged, a 70,000-word novel becomes 280,000. Target length has to be a
  constraint carried in the outline, not an emergent property.

---

## 8. What carries over unchanged

The skeleton IR, the genre packs, the zero-token lint, the deterministic scoring
maths, majority-voted alignment, and the central idea — extract, rewrite,
re-extract, compare. The verification thesis is length-independent.

What has to be rebuilt is how state is carried between calls. That is the whole
of the problem.
