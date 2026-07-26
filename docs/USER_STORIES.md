# Simulated Studio — User Stories

The single source of truth for **what we're building and who it's for.** Every
feature here is a *lens* over one shared engine, so we stay focused instead of
building six disconnected tools.

- **Live demo:** https://simulated-studio-326507709413.us-central1.run.app
- **One-liner:** *We didn't build six tools — we built a simulated studio of AI
  humans, and every content decision at PocketFM becomes a query against it.*

---

## The unifying model — one engine, many lenses

Every problem below reduces to the same primitive: **AI personas reacting to a
story.** There are only two kinds of persona:

- **Audience personas** — listener archetypes (the audience voice).
- **Expert personas** — director, editor, critic, psychologist, historian,
  producer (the craft voices).

Build the population once, point it at a story artifact, and each tool is just a
different **query/lens** on that population. That's why they share one backend
engine (persona loader → async LLM runner → cache → aggregate → Firestore) on
**Google Vertex AI**.

---

## Personas (who uses this)

| Persona | Role | Core need |
|---|---|---|
| **Writer / Showrunner** | Drafting an episode | "Is it good, and will listeners keep listening — before I publish?" |
| **Content Producer / Editor** | Deciding what ships | "Which episodes are release-ready, and what's the fix for the rest?" |
| **Growth / Marketing** | Positioning a release | "Who is this for and how do we launch it?" |

Today the loop is **publish, then learn from retention charts** — too late.
Simulated Studio moves that learning **before** release.

---

## Status legend

- ✅ **Live** — deployed and demoable (backend + UI)
- 🟡 **Built** — engine + API deployed; dedicated UI tab pending
- ⚪ **Planned** — designed, not yet built

---

## 1. AI Writers Room ✅ Live

> **As a** writer/showrunner, **I want** an expert panel *and* my audience to
> react to an episode at once, **so that** I get craft feedback and know whether
> listeners are actually following the story — before I publish.

- **Problem:** One writer can't hold six professional perspectives *and* predict
  audience reaction at the same time.
- **Flow:** Paste episode → *Convene the Writers Room* → in ~40s get 7 expert
  critiques (verdict, score, strengths, issues, concrete fix) **+ the audience
  voice** (following %, engagement, "are they following?", confusion points,
  quotes) **+ a fused consensus**.
- **Done when:** the panel returns ≥1 expert per role and an audience verdict,
  and the consensus names the top issue and the audience's following rate.
- **Engine mapping:** expert personas (Gemini 3.1 Pro) + audience personas
  (Gemini 3.6 Flash) over the shared runner.
- **API:** `POST /api/lenses/writers-room` → `WritersRoomResult`

## 2. Audience Simulator 🟡 Built (UI tab pending)

> **As a** producer, **I want** a large panel of listener personas to react to a
> story before release, **so that** I can predict binge rate and drop-off and
> pick winners without spending a release slot.

- **Problem:** Retention data only exists *after* you ship.
- **Flow:** Submit a story → fan out to N listener personas → get **binge %**,
  average **hook score**, a stage-by-stage **drop-off curve**, **segment**
  breakdown, and top **churn reasons**.
- **Done when:** results include a binge %, a non-increasing retention curve, and
  per-segment stats for a run of N listeners.
- **Engine mapping:** audience personas fanned out to N (Flash) → aggregate.
- **API:** `POST /api/simulate/audience` → `AudienceResult`

## 3. Cliffhanger Optimizer 🟡 Built (UI tab pending)

> **As a** writer, **I want** a weak ending rewritten into a gripping cliffhanger
> and proven better, **so that** more listeners start the next episode.

- **Problem:** "This ending feels soft" is a hunch with no evidence and no fix.
- **Flow:** Submit story + the weak ending → engine rewrites it → **A/B
  re-simulates** original vs. rewrite on the audience panel → returns the
  **hook-score lift** and the rewrite's rationale.
- **Done when:** the response includes before/after scores, the delta (lift), and
  a usable rewritten ending.
- **Engine mapping:** rewrite (Pro) → two audience runs (Flash) → compare.
- **API:** `POST /api/lenses/cliffhanger` → `CliffhangerResult`

## 4. AI Rewrite Engine ⚪ Planned

> **As a** writer, **I want** to transform a story into another genre (horror,
> romance, comedy, thriller, anime) while keeping the core plot, **so that** I
> can spin one idea into many shows.

- **Flow:** extract plot beats → regenerate in target genre constrained to those
  beats → verify beats preserved → (optional) re-simulate to show it still lands.
- **Done when:** output preserves the extracted beats and names what changed.
- **API (planned):** `POST /api/lenses/rewrite`

## 5. AI Producer ⚪ Planned

> **As a** producer, **I want** an automatic production + marketing plan for an
> episode, **so that** casting, SFX, pacing, and launch are decided fast.

- **Flow:** one Producer agent returns voice-casting briefs, SFX cue list, pacing
  notes, and a marketing brief whose **target segments reuse the Audience
  Simulator's segments**.
- **Done when:** output covers casting, SFX, pacing, and a launch plan tied to
  real audience segments.
- **API (planned):** `POST /api/lenses/producer`

## 6. Plot Hole Hunter ⚪ Planned

> **As a** showrunner, **I want** contradictions found across a whole season
> before publication, **so that** continuity errors never reach listeners.

- **Flow:** build a "canon ledger" (characters, timeline, rules) from the
  episodes, then flag contradictions with locations, severity, and a fix.
  v1 uses Gemini 3.1 Pro long context; v2 map-reduces thousands of pages.
- **Done when:** returns severity-ranked issues with locations and suggested fixes.
- **API (planned):** `POST /api/lenses/plot-holes`

---

## Out of scope (roadmap only)

Discovery-style ideas — mood search, concierge recommendations, cross-media,
festivals — are a **different product** (recommendation over a content catalog we
don't have). They stay on the roadmap slide, not in the build.

---

## Status at a glance

| # | Tool | User need | Status | Endpoint |
|---|---|---|---|---|
| 1 | AI Writers Room | Is it good + are they following? | ✅ Live | `/api/lenses/writers-room` |
| 2 | Audience Simulator | Will they binge? | 🟡 Built | `/api/simulate/audience` |
| 3 | Cliffhanger Optimizer | Make the ending binge-worthy | 🟡 Built | `/api/lenses/cliffhanger` |
| 4 | AI Rewrite Engine | One story → many genres | ⚪ Planned | `/api/lenses/rewrite` |
| 5 | AI Producer | Auto production + marketing | ⚪ Planned | `/api/lenses/producer` |
| 6 | Plot Hole Hunter | Catch contradictions early | ⚪ Planned | `/api/lenses/plot-holes` |
