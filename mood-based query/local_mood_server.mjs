#!/usr/bin/env node
/**
 * local_mood_server.mjs — a dependency-free stand-in for the Python mood backend.
 *
 * WHY THIS EXISTS
 * The real retrieval stack (parser + fingerprint index + reranker) is Python and
 * needs a Vertex LLM to fingerprint each arc. This machine has neither. But the
 * things the three UI asks depend on — real song titles, artist, playable audio,
 * named listeners with characteristics, and "Start at track N" — need no LLM at
 * all. So this serves your REAL curated catalog (catalog.json / episodes.json /
 * profiles.json) on the same /api/mood/* contract the frontend already speaks,
 * with a small hand-tuned mood ranking so different queries give different
 * shelves. It is a demo/dev backend, not the production retrieval stack.
 *
 * Run:   node local_mood_server.mjs            (listens on :8000)
 * Front: VITE_STUDIO_TARGET=http://localhost:8000 npm run dev --prefix frontend
 */

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const HERE = dirname(fileURLToPath(import.meta.url));
const load = (f) => JSON.parse(readFileSync(resolve(HERE, f), "utf8"));

const CATALOG = load("catalog.json");
const EPISODES = load("episodes.json");
const PROFILES = load("profiles.json");
const PORT = Number(process.env.PORT || 8000);

// --- mood model -------------------------------------------------------------
// Hand-authored axes per collection (the same move seed_catalog.py makes for the
// fixture: known mood → axes, no model). valence is -1..1, the rest 0..1.
const AXIS_KEYS = ["valence", "arousal", "tension", "warmth", "pace", "catharsis", "hope", "companionship", "weight"];

const AXES = {
  pf_after_ending:     { valence: -0.7, arousal: 0.25, tension: 0.35, warmth: 0.60, pace: 0.25, catharsis: 0.85, hope: 0.30, companionship: 0.50, weight: 0.85 },
  pf_three_am_clarity: { valence: -0.1, arousal: 0.35, tension: 0.35, warmth: 0.55, pace: 0.35, catharsis: 0.55, hope: 0.55, companionship: 0.55, weight: 0.60 },
  pf_soft_morning:     { valence: 0.50, arousal: 0.40, tension: 0.15, warmth: 0.75, pace: 0.40, catharsis: 0.30, hope: 0.80, companionship: 0.55, weight: 0.30 },
  pf_held:             { valence: 0.55, arousal: 0.35, tension: 0.15, warmth: 0.90, pace: 0.35, catharsis: 0.40, hope: 0.70, companionship: 0.85, weight: 0.35 },
  pf_windows_down:     { valence: 0.35, arousal: 0.75, tension: 0.45, warmth: 0.40, pace: 0.85, catharsis: 0.30, hope: 0.60, companionship: 0.30, weight: 0.40 },
  pf_hands_up:         { valence: 0.75, arousal: 0.90, tension: 0.20, warmth: 0.55, pace: 0.90, catharsis: 0.35, hope: 0.75, companionship: 0.50, weight: 0.20 },
  pf_neon_shadow:      { valence: -0.2, arousal: 0.60, tension: 0.60, warmth: 0.35, pace: 0.60, catharsis: 0.30, hope: 0.35, companionship: 0.35, weight: 0.55 },
  pf_static_starlight: { valence: 0.10, arousal: 0.10, tension: 0.10, warmth: 0.60, pace: 0.15, catharsis: 0.15, hope: 0.50, companionship: 0.50, weight: 0.25 },
};

const VIBE = {
  pf_after_ending: "Quiet and low — it sits in the ache with you instead of rushing you out of it.",
  pf_three_am_clarity: "Clear-eyed and reflective — it puts a shape around the thing you can't name.",
  pf_soft_morning: "Warm and easy — it opens the curtains and ends better than it starts.",
  pf_held: "Tender and close to the mic — the sound of being wholly wanted.",
  pf_windows_down: "Propulsive and wide-screen — built for motion and an empty road.",
  pf_hands_up: "Pure euphoria — the hooks everyone knows and every hand in the air.",
  pf_neon_shadow: "Sleek, brooding and a little dangerous — after-midnight cool.",
  pf_static_starlight: "Slow and weightless — made to be half-heard on the way to sleep.",
};

// The "readings" a query can resolve to. Each points at the collection whose
// axes anchor it, plus the keywords that vote for it.
const INTENTS = [
  { key: "sit_with", label: "Sit in it", subtitle: "Stays low and doesn't rush you out of it.", ref: "pf_after_ending",
    kw: ["sad", "heartbreak", "heartbroken", "cry", "crying", "breakup", "broke up", "alone", "lonely", "miss", "grief", "hurt", "tears", "down", "blue", "sob"] },
  { key: "reflect", label: "Help me think", subtitle: "Clear-eyed and reflective.", ref: "pf_three_am_clarity",
    kw: ["think", "thinking", "reflect", "reflective", "nostalgia", "nostalgic", "memories", "introspect", "process", "ponder", "clarity"] },
  { key: "lift", label: "Lift me out of it", subtitle: "Warm and hopeful — ends better than it starts.", ref: "pf_soft_morning",
    kw: ["happy", "cheer", "lift", "hopeful", "hope", "sunshine", "better", "uplift", "bright", "morning", "good mood", "smile", "sunny"] },
  { key: "company", label: "Keep me company", subtitle: "Close and warm, someone right there.", ref: "pf_held",
    kw: ["cozy", "cosy", "warm", "company", "comfort", "love", "romantic", "romance", "together", "hold", "tender", "sweet", "cuddle", "in love"] },
  { key: "escape", label: "Take me somewhere", subtitle: "Propulsive and wide-screen, full of motion.", ref: "pf_windows_down",
    kw: ["drive", "driving", "road", "motion", "adventure", "escape", "energy", "energetic", "workout", "run", "running", "gym", "fast", "highway"] },
  { key: "party", label: "Turn it up", subtitle: "Pure euphoria — hands in the air.", ref: "pf_hands_up",
    kw: ["party", "dance", "dancing", "hype", "club", "turn up", "celebrate", "banger", "upbeat", "fun", "pump", "hyped"] },
  { key: "wind_down", label: "Wind down", subtitle: "Slow and weightless, for the drift to sleep.", ref: "pf_static_starlight",
    kw: ["sleep", "sleepy", "calm", "relax", "wind down", "chill", "ambient", "quiet", "bedtime", "unwind", "peaceful", "study", "focus", "soothe"] },
  { key: "neon", label: "Something with an edge", subtitle: "Sleek, brooding, after-midnight.", ref: "pf_neon_shadow",
    kw: ["dark", "moody", "edgy", "midnight", "brooding", "cool", "sleek", "intense", "night", "neon"] },
];

const DEFAULT_READINGS = ["sit_with", "company", "lift"]; // for a query with no clear signal
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

// Episodes indexed by series, sorted by number.
const EPS_BY_SERIES = {};
for (const block of EPISODES) {
  EPS_BY_SERIES[block.series_id] = [...block.episodes].sort((a, b) => a.number - b.number);
}

// One candidate per arc, with a small per-arc drift so deeper arcs differ (which
// is what lets an entry point land on "track 16" rather than always track 1).
const CANDIDATES = [];
for (const series of CATALOG) {
  const base = AXES[series.series_id];
  if (!base) continue;
  const eps = EPS_BY_SERIES[series.series_id] || [];
  (series.arcs || []).forEach((arc, j) => {
    const axes = { ...base };
    // drift a couple of axes outward with arc depth
    axes.weight = clamp(axes.weight + j * 0.05, 0, 1);
    axes.pace = clamp(axes.pace - j * 0.04, 0, 1);
    axes.hope = clamp(axes.hope + j * 0.05, -1, 1);
    const span = eps.filter((e) => e.number >= arc.start_episode && e.number <= arc.end_episode);
    const avgSec = span.length ? span.reduce((s, e) => s + (e.duration_sec || 0), 0) / span.length : 240;
    CANDIDATES.push({
      content_id: arc.arc_id,
      series_id: series.series_id,
      series_title: series.title,
      entry_episode: arc.start_episode,
      arc_label: arc.label,
      axes,
      explanation: `${VIBE[series.series_id]} — ${arc.summary}`,
      duration_min: Math.max(1, Math.round(avgSec / 60)),
    });
  });
}

const dist = (a, b) => Math.sqrt(AXIS_KEYS.reduce((s, k) => s + ((a[k] ?? 0.5) - (b[k] ?? 0.5)) ** 2, 0));

function pickReadings(text) {
  const q = (text || "").toLowerCase();
  const scored = INTENTS.map((it) => ({ it, score: it.kw.reduce((s, w) => s + (q.includes(w) ? 1 : 0), 0) }))
    .sort((a, b) => b.score - a.score);
  const chosen = scored.filter((s) => s.score > 0).map((s) => s.it.key);
  for (const k of DEFAULT_READINGS) if (chosen.length < 3 && !chosen.includes(k)) chosen.push(k);
  for (const it of INTENTS) if (chosen.length < 3 && !chosen.includes(it.key)) chosen.push(it.key);
  return chosen.slice(0, 3).map((k) => INTENTS.find((i) => i.key === k));
}

function shelfFor(intent, target, finished) {
  const seen = new Set();
  const ranked = CANDIDATES
    .filter((c) => !finished.has(c.series_id))
    .map((c) => ({ c, d: dist(c.axes, target) }))
    .sort((a, b) => a.d - b.d);
  const results = [];
  for (const { c } of ranked) {
    if (seen.has(c.series_id)) continue; // one arc per series per shelf
    seen.add(c.series_id);
    const entryEp = (EPS_BY_SERIES[c.series_id] || []).find((e) => e.number === c.entry_episode);
    results.push({
      content_id: c.content_id,
      series_id: c.series_id,
      series_title: c.series_title,
      entry_episode: c.entry_episode,
      entry_label: c.entry_episode <= 1
        ? "Start from the beginning"
        : `Start at track ${c.entry_episode} — ${c.arc_label}`,
      entry_title: entryEp?.title ?? null,
      entry_artist: entryEp?.synopsis ?? null,
      entry_audio_url: entryEp?.audio_url ?? null,
      explanation: c.explanation,
      duration_min: c.duration_min,
    });
    if (results.length >= 4) break;
  }
  return { id: `shelf_${intent.key}`, label: intent.label, subtitle: intent.subtitle, target_axes: target, results };
}

function profileView(p) {
  const hist = p.history || [];
  const completed = hist.filter((h) => h.completed).length;
  const finished = hist.filter((h) => h.completed || h.liked === false).map((h) => h.series_id);
  const a = p.attrs || {};
  return {
    persona_id: p.persona_id,
    display_name: p.display_name,
    slot: a.listening_time_slot,
    language: a.primary_language,
    completion_rate: hist.length ? Math.round((completed / hist.length) * 100) / 100 : (a.series_completion_rate ?? null),
    typical_dropoff_episode: a.typical_dropoff_episode ?? null,
    tolerance_for_heaviness: a.tolerance_for_heaviness ?? null,
    history_count: hist.length,
    finished: [...new Set(finished)].sort().slice(0, 5),
  };
}
const finishedSet = (profileId) => {
  const p = PROFILES.find((x) => x.persona_id === profileId);
  if (!p) return new Set();
  return new Set((p.history || []).filter((h) => h.completed || h.liked === false).map((h) => h.series_id));
};

const SESSIONS = new Map(); // query_id -> { text, profileId }

const STARTERS = [
  "something that feels like a rainy Sunday after heartbreak",
  "I want to feel hopeful again",
  "songs to cry to, alone at night",
  "keep me company while I cook",
  "a long night drive with the windows down",
  "turn it up — I want to dance",
  "help me wind down for sleep",
  "something with a dark edge after midnight",
].map((text, i) => ({ id: `s${i}`, text }));

const SLIDERS = [
  { id: "weight", left: "Lighter", right: "Heavier" },
  { id: "pace", left: "Slower", right: "Faster" },
  { id: "warmth", left: "Cooler", right: "Warmer" },
  { id: "arousal", left: "Calmer", right: "More intense" },
  { id: "hope", left: "Bleaker", right: "More hopeful" },
];

function search(text, profileId) {
  const query_id = randomUUID().slice(0, 8);
  SESSIONS.set(query_id, { text, profileId });
  const finished = finishedSet(profileId);
  const readings = pickReadings(text);
  const shelves = readings.map((it) => shelfFor(it, AXES[it.ref], finished));
  return { query_id, mode: "shelves", parsed: { text, destination: readings[0].key, sparsity_score: 0 }, shelves, latency_ms: 3 };
}

// --- lexical baseline (the genre/keyword search we argue against) -----------
// Pure term overlap over song title + artist. NO mood axes — so it ranks the
// lexically-strongest match, which is exactly how it surfaces the wrong song
// for an emotional query. is_trap marks a hit whose collection mood is far from
// what the query actually wants: lexically perfect, emotionally wrong.
const STOP = new Set(
  "a an the and or of to in on at for with without from by is are was were be been i me my you your it its this that these those something anything some any like feels feel felt want wanted need needed after before".split(/\s+/)
);
const tokenize = (t) =>
  ((t || "").toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1 && !STOP.has(w));

const ALL_SONGS = [];
for (const series of CATALOG) {
  for (const ep of EPS_BY_SERIES[series.series_id] || []) {
    const vid = ((ep.audio_url || "").match(/[?&]v=([^&]+)/) || [])[1] || `${series.series_id}-${ep.number}`;
    ALL_SONGS.push({ content_id: vid, title: ep.title || "", artist: ep.synopsis || "", series_id: series.series_id });
  }
}
const SONG_DOCS = ALL_SONGS.map((s) => tokenize(`${s.title} ${s.artist}`));
const DF = {};
for (const doc of SONG_DOCS) for (const t of new Set(doc)) DF[t] = (DF[t] || 0) + 1;
const NDOCS = Math.max(1, SONG_DOCS.length);
const idf = (t) => Math.log(1 + NDOCS / (1 + (DF[t] || 0)));

function baselineSearch(text, k) {
  const terms = [...new Set(tokenize(text))];
  if (!terms.length) return [];
  const targets = pickReadings(text).map((it) => AXES[it.ref]);
  const scored = [];
  for (let i = 0; i < SONG_DOCS.length; i++) {
    const doc = SONG_DOCS[i];
    if (!doc.length) continue;
    const counts = {};
    for (const w of doc) counts[w] = (counts[w] || 0) + 1;
    let score = 0;
    const matched = [];
    for (const t of terms) if (counts[t]) { score += (1 + Math.log(counts[t])) * idf(t); matched.push(t); }
    if (score > 0) scored.push({ s: score / Math.sqrt(doc.length), i, matched });
  }
  scored.sort((a, b) => b.s - a.s);
  return scored.slice(0, k).map(({ i, matched }) => {
    const song = ALL_SONGS[i];
    // Trap = lexically matched but far from what the query PRIMARILY wants.
    const primaryDist = targets.length ? dist(AXES[song.series_id], targets[0]) : 0;
    return {
      content_id: song.content_id,
      series_title: song.title,
      snippet: `${song.artist} · matched "${matched.slice(0, 3).join(", ")}" — ranked on the words, not on how it feels.`,
      is_trap: primaryDist > 1.0,
    };
  });
}

// --- http -------------------------------------------------------------------
const json = (res, code, body) => {
  res.writeHead(code, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
  res.end(JSON.stringify(body));
};
const readBody = (req) => new Promise((r) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => { try { r(b ? JSON.parse(b) : {}); } catch { r({}); } }); });

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const path = url.pathname;
  try {
    if (path === "/health") return json(res, 200, { status: "ok", backend: "local-node-mood" });
    if (path === "/api/mood/starters") return json(res, 200, { starters: STARTERS });
    if (path === "/api/mood/sliders") return json(res, 200, { sliders: SLIDERS });
    if (path === "/api/mood/profiles") return json(res, 200, { profiles: PROFILES.map(profileView) });

    if (path === "/api/mood/search" && req.method === "POST") {
      const b = await readBody(req);
      return json(res, 200, search(b.text || "", b.profile_id ?? null));
    }
    if (path === "/api/mood/clarify" && req.method === "POST") {
      const b = await readBody(req);
      const s = SESSIONS.get(b.query_id) || {};
      return json(res, 200, search(s.text || "", s.profileId ?? null)); // skip → shelves
    }
    if (path === "/api/mood/refine" && req.method === "POST") {
      const b = await readBody(req);
      const s = SESSIONS.get(b.query_id) || {};
      const intentKey = String(b.shelf_id || "").replace("shelf_", "");
      const intent = INTENTS.find((i) => i.key === intentKey) || INTENTS[0];
      const target = { ...(b.current_axes || AXES[intent.ref]) };
      for (const [ax, delta] of Object.entries(b.slider_deltas || {})) {
        target[ax] = clamp((target[ax] ?? 0.5) + Number(delta) * 0.2, ax === "valence" ? -1 : 0, 1);
      }
      const shelf = shelfFor(intent, target, finishedSet(s.profileId ?? null));
      shelf.id = b.shelf_id; // preserve so the frontend replaces in place
      return json(res, 200, { query_id: b.query_id, mode: "shelves", shelves: [shelf], latency_ms: 2 });
    }

    const epMatch = path.match(/^\/api\/mood\/episodes\/(.+)$/);
    if (epMatch) {
      const sid = decodeURIComponent(epMatch[1]);
      const eps = EPS_BY_SERIES[sid];
      if (!eps) return json(res, 200, { error: "unknown series", series_id: sid });
      const start = Math.max(1, Number(url.searchParams.get("start") || 1));
      const limit = Number(url.searchParams.get("limit") || 12);
      const chosen = eps.filter((e) => e.number >= start).slice(0, limit);
      const title = (CATALOG.find((c) => c.series_id === sid) || {}).title || sid;
      return json(res, 200, {
        series_id: sid, series_title: title, start, total: eps.length,
        has_more: chosen.length > 0 && chosen[chosen.length - 1].number < eps[eps.length - 1].number,
        episodes: chosen,
      });
    }

    if (path === "/api/mood/baseline" && req.method === "POST") {
      const b = await readBody(req);
      return json(res, 200, { results: baselineSearch(b.text || "", Number(b.k || 3)) });
    }

    return json(res, 404, { error: "not found", path });
  } catch (e) {
    return json(res, 500, { error: String(e && e.message || e) });
  }
});

server.listen(PORT, () => {
  console.log(`local mood backend on http://localhost:${PORT}`);
  console.log(`  catalog:  ${CATALOG.length} series, ${CANDIDATES.length} arcs`);
  console.log(`  episodes: ${Object.values(EPS_BY_SERIES).reduce((s, e) => s + e.length, 0)} songs`);
  console.log(`  profiles: ${PROFILES.length} listeners`);
});
