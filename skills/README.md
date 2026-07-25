# skills/ — the persona library

Every file in this directory is **one agent**. Simulated Studio is a single
persona-simulation engine viewed through many *lenses* (Audience Simulator,
Writers' Room, Cliffhanger Optimizer). All lenses draw from the **same** pool of
personas defined here — you author a persona once, and it powers every lens it is
eligible for.

The loader (`backend/app/personas/loader.py`) walks this folder recursively,
reads every `.yaml` / `.yml` file with PyYAML, and turns each into a
`Persona` (see `backend/app/schemas.py`). **One YAML = one persona = one agent.**

## The audience-vs-expert split

Personas come in two kinds, and the **folder name sets the kind**:

| Folder          | `kind`     | Used by                                           |
| --------------- | ---------- | ------------------------------------------------- |
| `audience/`     | `audience` | Audience Simulator + Cliffhanger before/after panels |
| `experts/`      | `expert`   | Writers' Room panel                               |

- An **audience** persona is a *listener* — a synthetic member of the crowd. It
  reacts emotionally to an episode and answers: would I keep listening, how
  gripped was I, and where did I check out? These are fanned out (cloned with
  light age/city variation) into a representative panel of hundreds.
- An **expert** persona is a *craftsperson* — a director, editor, critic, etc. It
  critiques the writing itself and returns a structured craft verdict.

`kind` may be written explicitly in the file (recommended, and it is here), but if
it is omitted the loader infers it from the parent folder: `audience/` →
`audience`, `experts/` → `expert`.

## Schema

Shared shape (`Persona` in `schemas.py`):

```
id            str        unique slug, also the YAML filename stem
name          str        the persona's display name
kind          str        "audience" | "expert" (or inferred from folder)
segment       str?       audience only — short archetype label (e.g. "Metro Binge-Watcher")
role          str?       expert only   — job title (e.g. "Director")
age           int?       audience flavour
city          str?       audience flavour (Indian context)
genres        [str]      genres this persona gravitates to
traits        [str]      a few defining characteristics
system_prompt str        the instruction that makes this agent behave distinctively
```

### Audience persona keys

`id, name, kind, segment, age, city, genres, traits, system_prompt`

### Expert persona keys

`id, name, kind, role, traits, system_prompt`

`segment` / `role` are the meaningful discriminators: `segment` labels an audience
archetype (and is what the aggregator groups retention stats by), while `role`
names an expert's craft seat on the Writers' Room panel.

## Writing a good `system_prompt`

The `system_prompt` is the persona. It becomes the LLM `system` instruction for
that agent (the engine appends a short task line — e.g. "Answer strictly as this
listener reacting to one audio-drama episode."). Aim for **3–5 sentences**:

- **Audience:** first person. Give the listener a listening context, clear likes
  and dislikes, and a decision rule for when they drop off. Distinctive taste
  produces a distinctive retention signal.
- **Expert:** role-defined. State the lens the expert reads through, what they
  praise, what they flag, and end by asking for a concrete, actionable critique.

Distinct personas are the whole point: they should *disagree*. A metro
binge-watcher and a mythology traditionalist reacting to the same episode is the
signal the studio exists to surface.

## Adding a persona

1. Drop a new `.yaml` into `audience/` or `experts/`.
2. Match the schema above; keep `id` equal to the filename stem.
3. That's it — no code change. The loader picks it up on the next run, and it
   immediately participates in every lens for its `kind`.

> If this folder is ever empty, the loader falls back to a small built-in set so
> the app still boots — but these files are the real library.

## What's here now

**Audience (6 archetypes):** Metro Binge-Watcher, Small-Town Commuter, Gen-Z
Thriller Fan, Romance Devotee, Mythology Traditionalist, True-Crime Skeptic.

**Experts (6 seats):** Director, Script Editor, Sound Designer, Audience
Psychologist, Story Critic, Showrunner / Producer.
