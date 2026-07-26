# The Genre Convertor, in simple words

**The big idea:** take a story, strip it down to just its plot (no names, no
style, no genre flavor), rewrite that bare plot in a new genre, then check how
much of the original plot survived.

For the full technical walkthrough see [HOW-IT-WORKS.md](HOW-IT-WORKS.md); this
page is the two-minute version.

## Step 0 — You paste a story

You pick a target genre (anime, comedy, horror, romance, or thriller) and hit
**Convert**. The service does a quick free check first — the story must be at
least 400 characters. Up to 60,000 characters it runs the scene-by-scene
pipeline below; past that (up to ~400,000) it switches to the **long-form
lane**, which splits the story into chapters, fixes the cast up front, writes
against a shared story bible, and verifies chapter by chapter. Either way it
starts a background job and the browser keeps polling it, so you watch progress
live instead of staring at a spinner. If this exact short story was converted
before, it reuses the saved work and finishes in seconds.

## Step 1 — Extract the skeleton

One Gemini call reads your story and boils it down to a **plot skeleton**: one
logline, the characters reduced to their *roles* (protagonist, betrayer,
gatekeeper…), and 8–15 **beats** — the key things that happen and what causes
what. The important beats (the ones the ending depends on) get marked
**load-bearing**.

The rules are strict: no character names, no genre words, no descriptions —
just the bare plot moves. Example: *"Sunita hides her brother's confession
letter in the attic"* becomes *"the confidant conceals withheld information."*

A free code check (no AI) then scans for leaked names or genre words, and if it
finds any, asks the extractor once to reword.

## Step 2 — Rewrite it, scene by scene

Simple math (no AI) groups the beats into scenes — max 3 beats per scene, and
every important beat ends its scene. Then one Gemini call writes each scene.
Each call only gets three things:

1. the **genre pack** — a brief describing the target genre's rules, mood, and
   forbidden moves;
2. **this scene's beats** only;
3. a short **summary from the previous scene**, for continuity.

The writer **never sees your original story** — only the skeleton. That's the
trick: with nothing to copy, it must genuinely retell, not find-and-replace.

Each scene also reports which beats it actually delivered — if an important one
is missing, that scene gets one rewrite.

## Step 3 — Judge the result

The finished rewrite is compared against your original story's skeleton by AI
judges. Two questions, each asked 3 separate times:

- does each beat *actually happen on the page*?
- do things still happen *because of* other things?

Then a simple majority vote — 2 out of 3 judges must agree. (Three votes
because a single judge is inconsistent.) The judges are strict: a character
*remembering* an event doesn't count, and a flipped outcome definitely doesn't.

## Step 4 — The score

Pure arithmetic:

| What | Weight |
| --- | --- |
| Did the crucial (load-bearing) beats survive? | 60% |
| Did all beats survive? | 20% |
| Do the cause-and-effect links still hold? | 20% |

You get the number plus a list of exactly which beats got lost and why.
Everything is saved to History.

## Why it takes a few minutes

Roughly: 1 call to extract, 1 call per scene (usually 4–7), and 6 concurrent
calls to judge. The scene-writing dominates. The same walkthrough is in the app
itself — the **"How it works"** button on the Story Rewrite Engine tab shows it
as an interactive flowchart.
