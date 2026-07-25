# How it works

A plain-English walkthrough. No prior knowledge assumed.

---

## What this thing does

You give it a story. You pick a genre. It gives you back the same story rewritten
in that genre — and a number saying how much of the original plot survived.

Take the story in `stories/reveal.txt`: a young archivist named Priya discovers
her mentor forged the paperwork behind the museum's collection, confronts him, is
offered his job in exchange for silence, refuses, reports him — and then ends up
taking the job anyway once she sees the confiscated artifacts rotting in storage.

Ask for horror, and you get a different story on every surface. The archivist is
now a man called Leo. The museum is a decaying "Palliative Wing" with water stains
on the ceiling and something dragging itself across the floor above. It ends with
him alone in his new office, hearing a dry scratching from a locked drawer.

Different names, different place, different mood, genuinely frightening. But the
plot underneath is beat for beat the same: someone discovers a fraud, confronts
the person responsible, is offered their position as a bribe, refuses, reports
them, and inherits the mess anyway.

---

## The problem worth solving

Modern AI already writes good horror. That is not the hard part.

The hard part is that when you ask a model to "rewrite this story as horror", it
drifts. It gets absorbed in writing atmospheric prose and quietly loses things.
A subplot vanishes. The person who betrays the hero changes. The ending becomes a
different ending. The output *reads* well, which is exactly what makes it
dangerous — nothing looks wrong unless you sit down and compare the two stories
carefully, and nobody does that at scale.

So the interesting problem is not "can it write horror". It is **"can you prove
it did not wreck the story"**. That is why the checker was built before the
rewriter.

---

## The core idea: separate the plot from everything else

Think of an X-ray. It throws away skin, hair, and clothing, and keeps the
skeleton. Two very different-looking people can have the same bone structure.

This tool does that to stories. It produces a **skeleton**: a stripped-down
description of what happens, with every trace of style, setting, and personality
removed.

The skeleton keeps:

- **The beats** — the individual events, in order.
- **Who does what** — but described by their *role*, not their name. Not "Priya"
  but "the protagonist". Not "Devraj" but "the person guarding the secret".
- **What each event causes** — event 3 happens *because* event 2 did.
- **Which events are essential** — delete this one and the ending stops making
  sense.

The skeleton deliberately throws away:

- Names, places, time period
- Weather, rooms, objects, what anything looks like
- Mood, imagery, dialogue, sentence rhythm
- What the danger physically *is*

Here is the same event in both forms:

> **Story:** *"Priya's hands went cold as she read the dealer's letter. The
> signature at the bottom was not one she recognised."*
>
> **Skeleton:** *"the protagonist discovers a discrepancy in an object's records"*

The skeleton version is deliberately flat and boring. That is the point. It reads
like a line from a court transcript rather than from a novel.

**Why this matters:** because "someone hides a secret; another person finds it;
their relationship breaks" works equally well as a ghost story or as a romance
that falls apart. Once you have the plot in that neutral form, the genre is free
to reinvent every single surface detail without touching the story underneath.

---

## The three steps

The whole system is one loop, run in order:

**Step 1 — Read the story and write down its skeleton.**
**Step 2 — Write a brand-new story from that skeleton, in the target genre.**
**Step 3 — Read the *new* story, write down *its* skeleton, and compare the two.**

Step 3 is the clever bit and gets its own section below.

---

## Step 1 — Extracting the skeleton

The AI reads the story and returns the beats, the roles, the causal links, and
which beats are essential.

Then something cheap and non-AI checks the result. This checker costs nothing to
run — it is ordinary code, not another AI call — and it looks for two mistakes:

1. **A name leaked through.** If the skeleton says "Priya" anywhere, it failed.
   Names are supposed to be gone.
2. **Genre words leaked through.** If the skeleton says "dread", "haunting",
   "tender", or "hilarious", it failed. The skeleton is supposed to be
   genre-neutral, and if it already leans horror, the romance version will come
   out subtly haunted.

If either happens, the tool goes back to the AI once, quotes the exact problem,
and asks for a corrected version. Then it moves on regardless — a slightly
imperfect skeleton is still usable, and you are told what was wrong.

**Why bother:** whatever ends up in the skeleton is something the rewrite is
locked into. Flavour in the skeleton is flavour the new genre cannot escape.

---

## Step 2 — Transforming into the new genre

Two rules make this work, and both are counter-intuitive.

### Rule 1: The rewriter never sees the original story

It only ever sees the skeleton. This seems like throwing away useful information.
It is deliberate. If the original prose were in front of it, the model would
borrow phrases, keep the same setting, and produce a lightly repainted version of
what it was given. Starving it of the original forces genuine reinvention.

### Rule 2: Write one scene at a time, never the whole story at once

Asking for a whole story in one request is exactly how beats go missing — the
model runs long, starts rushing, and compresses the last third.

Instead the skeleton is chopped into scenes of one to three beats. Each request
gets:

- **only the handful of beats that scene is responsible for** — a short list is
  hard to lose things from
- **the genre pack** (below)
- **a short summary of the story so far**, written by the previous scene, so
  names and setting stay consistent

Each scene also reports which beats it believes it delivered. If it skipped an
essential one, the tool asks again, quoting the missed beat. Then it moves on.

The scenes are split so that no single scene contains two major turning points.
A scene asked to carry two big moments will always short-change one of them.

### The genre packs

Each genre is a small file — `genres/horror.json`, `genres/romance.json`, and so
on — describing what that genre is allowed to do:

- **Premise** — the genre's core assumption. Horror: *the world was never safe;
  the protagonist has only just noticed.*
- **Expected moves** — things readers of that genre want. Horror: *an early
  wrongness the protagonist explains away.*
- **Sensory palette** — what to notice. Horror: *sound in rooms that should be
  empty; cold that arrives before its cause.*
- **Pacing, point of view, dialogue style.**
- **Forbidden moves** — and this is the important one.

The forbidden list is what keeps genres distinct. Telling a model to "write
dread" produces competent prose in every genre, because competent prose is what
it does by default. Telling it *"never explain how the thing works"* and *"never
release the tension with a joke"* is what actually stops horror from sliding into
a thriller.

Adding a sixth genre — noir, western, whatever — means writing one more small
file. No code changes.

---

## Step 3 — Verifying the plot survived

Here is the trick that makes the whole thing work.

**Run the rewritten story back through Step 1.** Extract a skeleton from the
horror version exactly the way one was extracted from the original. Now you have
two skeletons: one from the story you started with, one from the story you
produced.

They should describe the same plot. If the rewrite lost a subplot, that subplot
cannot possibly show up in the second skeleton — you cannot extract something
that is not there.

So the comparison is skeleton against skeleton, never prose against prose. All
the surface differences — different names, different century, different
threat — are already gone by the time the comparison happens. Only structure is
left to compare.

### How the comparison works

The AI is asked exactly one question, once per beat: *does the new story contain
an event doing the same job as this one?*

It is told to judge **function, not appearance**. A betrayal by a business
partner and a betrayal by a ghost are the same beat. A locked door and a sealed
spell are the same obstacle. It is also told to be harsh — if it finds itself
constructing an argument for why two events are "sort of" similar, they are not.
A wrong match is far more damaging than a missed one, because a wrong match makes
a broken rewrite look fine.

### How the score is calculated

Once the matching is done, the AI is finished. The rest is plain arithmetic, so
the same two skeletons always produce the same number and anyone can check it by
hand.

Three things are measured:

| Measured | Weight | Why |
|---|---|---|
| Did the **essential** beats survive? | 60% | This is the actual promise being made. |
| Did **all** beats survive? | 20% | Stops a rewrite scoring well by keeping the spine and shredding everything else. |
| Did the **causal links** survive? | 20% | Catches a chain with a hole in it. |

That third one deserves a note. It is not enough for two events to both be
present — the *link between them* has to survive too. If the original said "she
finds the document, **which lets her** stop him", and the rewrite has both events
but no longer connects them, that link is counted as broken. This is what catches
a rewrite that keeps all the pieces but loses the reason they happen.

---

## What the score actually means

A score by itself is meaningless without knowing what a good one looks like. So
the tool measures its own two boundaries — this is what `calibrate.py` does.

**The ceiling: how high can a *perfect* result score?**

Extract a skeleton from the same story twice, and compare the two. Nothing was
rewritten at all, so this should score 100%. It does not — and the gap is the
tool's own margin of error.

Why isn't it 100%? Because writing a skeleton involves judgement, and the AI
makes that judgement fresh each time. Asked twice about the same story, it once
produced 14 beats and once produced 8 — splitting a confrontation into three
events one time, folding it into one the other. Neither is wrong. But the
comparison counts one event against one event, so a story cut into 8 pieces can
never fully match the same story cut into 14.

**The floor: how high does an *unrelated* story score?**

Compare two completely different stories. This should score near zero. If it
scores high, the matcher is being fooled by generic story shape — "someone wants
something, someone refuses" describes almost every story ever written.

**A score only means something in the band between those two numbers.**

Where things currently stand:

- **Floor: passing.** Unrelated stories score 0–25%. The matcher is not being
  fooled by generic shape.
- **Ceiling: not passing.** It should be 90% or better. It was 48.72%, rose to
  76.04% once a bug in the name checker was fixed, and has not been re-measured
  since the most recent change.

So today: a rewrite scoring well above ~76% is genuinely good. A rewrite scoring
below ~60% is genuinely broken. Anything in between cannot yet be told apart from
the tool's own noise. Closing that gap is the next job.

---

## A real run, start to finish

`reveal.txt` (1,227 words) converted to horror:

| Stage | What happened |
|---|---|
| Extract | 12 beats, 6 of them essential, 11 causal links |
| Plan | Split into 6 scenes |
| Rewrite | 6 requests, one per scene → 3,428 words of horror |
| Re-extract | 12 beats, 6 essential, 11 links |
| Compare | **67.73% fidelity** |

Nine AI calls, about six and a half minutes. Everything is saved to disk, so
running it again is instant — which matters, because you never want to demo this
live from a cold start.

The comparison flagged two beats as lost. Reading them by hand:

- One was a **false alarm**. The original had "the board offers her the job, which
  she accepts" as a single beat. The horror version splits that across two
  scenes — offered, then accepted. Since the scoring matches one event to one
  event, a split beat can only ever half-match. Nothing was actually lost.
- One was **real**. In the original, a colleague advises her to confront the
  mentor before going to the board. In the horror version, the colleague instead
  warns that the mentor answers to hidden powers. Similar shape, genuinely
  different job in the plot. The checker was right to flag it.

Worth knowing: the rewriter *claimed* it had covered both beats. Its own
self-report was too optimistic, which is precisely why the independent check
exists rather than trusting the model's word.

---

## Known weaknesses

Stated plainly, because a tool that measures things should be honest about its
own measurement:

- **The ceiling is too low.** Until it clears 90%, mid-range scores cannot be
  trusted. This is the biggest open item.
- **The skeleton has no opinion about gender.** In the horror version, Priya
  became Leo. Names and identity are treated as surface detail the genre may
  reinvent. That may or may not be what you want.
- **"Essential" is over-applied.** The AI is asked to be strict about which beats
  are load-bearing and still flags most of them. Since that measure is 60% of the
  score, over-flagging makes the number less discriminating than it should be.
- **The rewrite runs long.** 1,227 words in, 3,428 out. Faithful, but not the same
  size.

---

## The files

| File | What it is |
|---|---|
| `models.py` | The definition of a skeleton. The contract everything else depends on. |
| `extract.py` | Step 1 — story into skeleton, plus the free non-AI checker. |
| `transform.py` | Step 2 — skeleton into a new story, scene by scene. |
| `verify.py` | Step 3 — compare two skeletons, calculate the score. |
| `pipeline.py` | Runs all three steps in order. This is the one to run. |
| `calibrate.py` | Measures the ceiling and the floor, so the score means something. |
| `genre_pack.py` | Loads the genre files. |
| `genres/*.json` | One file per genre. Add a file, get a genre. |
| `llm.py` | The single place the AI is called. |
| `cache.py` | Saves results to disk so nothing is ever paid for twice. |

Two files carry most of the weight. `llm.py` is the only place the AI is
contacted, so the model choice, the login method, and the error messages are all
set in one place. And `models.py` is where the skeleton's rules are written —
including the instructions the AI actually follows most closely. Counter-intuitively,
those instructions matter more than the main prompt, because the system feeds them
directly into the format the AI is required to fill in. When a skeleton comes out
wrong, that is the first file to edit.
