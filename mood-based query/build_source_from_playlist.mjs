#!/usr/bin/env node
/**
 * build_source_from_playlist.mjs
 * ------------------------------------------------------------------------
 * Curate the Mood-First-Search source files from a real YouTube playlist.
 *
 * Input : playlist-tool/songs.json  (210 real tracks: title, artist, duration, url)
 * Output: catalog.json, episodes.json, profiles.json  (SOURCE_SCHEMA.md shape)
 *
 * Mapping
 *   playlist ─┐
 *             ├─ 8 mood COLLECTIONS  → catalog series (fingerprinted at arc level)
 *   each song ┘                       → episode (playable unit; real title/dur/url)
 *
 * The songs, titles, durations and URLs are REAL (source = "youtube_playlist").
 * The mood grouping, synopses and arc summaries are editorial curation — treat
 * this as demo/padding data, not the eval set (per SOURCE_SCHEMA.md).
 *
 * 7 travel-vlog entries (F & T Reviews) are dropped: they are not music and
 * would poison a music mood index.
 *
 * Run:  node build_source_from_playlist.mjs
 * It also runs a faithful port of validate_sources.py and prints the report.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SONGS_PATH = resolve(HERE, "..", "playlist-tool", "songs.json");

// ---------------------------------------------------------------------------
// 1. Mood collections (series). Aligned to the system's destination
//    neighbourhoods. Synopsis is felt-experience, ≥120 chars, no genre words.
// ---------------------------------------------------------------------------

const COLLECTIONS = {
  A: {
    series_id: "pf_after_ending",
    title: "After the Ending",
    synopsis:
      "The hours right after it ends, when the room is too quiet and you are not ready to be told it gets better. Voices that stay low and sit in the ache with you instead of rushing you out of it — grief, longing, and the slow tidal pull of missing someone who is not coming back.",
    arcs: [
      { label: "the fresh wound", summary: "Rawest and closest to the moment it broke — nothing softened yet, the ache still sharp." },
      { label: "the long ache", summary: "The dull, ongoing weight of missing them once the shock wears off; quieter, heavier, endless." },
      { label: "letting it settle", summary: "Not over it, but starting to carry it — the first inch toward acceptance and a held kind of calm." },
    ],
  },
  B: {
    series_id: "pf_three_am_clarity",
    title: "The 3 A.M. Clarity",
    synopsis:
      "The reflective hour when the noise dies down and you finally think a thought all the way through. Bittersweet, clear-eyed songs about growing up, drifting apart, and the small revelations that only arrive when you are half-awake and honest with yourself for once.",
    arcs: [
      { label: "the quiet turn", summary: "The noise fades and the first honest thought arrives, unhurried and a little raw." },
      { label: "what it added up to", summary: "Looking back at what changed, who drifted, and who you quietly became along the way." },
      { label: "making peace", summary: "Reflective and clear-eyed, landing somewhere gentler than where it started." },
    ],
  },
  C: {
    series_id: "pf_soft_morning",
    title: "Soft Morning Light",
    synopsis:
      "The gentle lift of a good morning — warm without shouting about it, hopeful without pretending nothing ever hurt. Easy, kind songs that open the curtains and let a little sun in, the sound of small things quietly turning out okay after a long stretch of them not.",
    arcs: [
      { label: "curtains open", summary: "The first warm light easing in; soft, unforced, no rush to be anything yet." },
      { label: "small good things", summary: "Little joys landing one after another — nothing loud, just genuinely nice." },
      { label: "into the day", summary: "Brighter and readier, hopeful and light on its feet, out the door." },
    ],
  },
  D: {
    series_id: "pf_held",
    title: "Held",
    synopsis:
      "Being wholly wanted by someone. Tender, unhurried love songs — the slow-dance kind, the ones for a first look across a room and a hand you do not want to let go of. Devotion sung close to the mic, all warmth and no distance, the safest place in the room.",
    arcs: [
      { label: "the first look", summary: "The catch of breath when it begins — new, bright, a little disbelieving." },
      { label: "close and warm", summary: "Settled devotion sung near the mic; steady, tender, sure of itself." },
      { label: "yours", summary: "All-in and unguarded — the fully-held, nothing-between-us stretch." },
    ],
  },
  E: {
    series_id: "pf_windows_down",
    title: "Windows Down",
    synopsis:
      "Windows down, foot heavier on the pedal, the world blurring past. Big, propulsive, wide-screen songs built for motion and momentum — the kind that make an empty highway at dusk feel like the finest hour of your own private movie, no destination required.",
    arcs: [
      { label: "ignition", summary: "The engine turns over and momentum starts to build; anticipation with a pulse." },
      { label: "open road", summary: "Full speed, wide screen, no brakes — pure forward motion." },
      { label: "the summit", summary: "The soaring, arms-out crest where the whole thing lifts off." },
    ],
  },
  F: {
    series_id: "pf_hands_up",
    title: "Hands in the Air",
    synopsis:
      "The floor is full and nobody is checking the time. Pure, unbothered euphoria — the hooks everyone already knows by heart, the drops that put every hand in the air, the sound of a night that is going exactly the way you hoped it would when you got ready for it.",
    arcs: [
      { label: "doors open", summary: "The night starts to fill up; warm-up energy, grins, first drinks." },
      { label: "peak floor", summary: "Hooks everyone knows, hands up, the room fully committed." },
      { label: "the drop", summary: "Full euphoria, nobody checking the time, the night at its loudest and best." },
      { label: "last-call glow", summary: "Still going on fumes and joy — sweat, singalongs, and no wish to leave." },
    ],
  },
  G: {
    series_id: "pf_neon_shadow",
    title: "Neon and Shadow",
    synopsis:
      "After midnight in a city that never fully turns the lights off — sleek, brooding, and a little dangerous. Dark-edged songs with a low pulse and a smirk, the cool-toned corner of the decade where the shadows are not a warning so much as part of the appeal.",
    arcs: [
      { label: "after midnight", summary: "Lights low, pulse steady, a little dangerous — the night tipping over." },
      { label: "neon", summary: "Sleek and brooding, cool to the touch, all reflected light and attitude." },
      { label: "the shadow", summary: "The darkest-edged stretch — the smirk in the dark, unbothered and cold." },
    ],
  },
  H: {
    series_id: "pf_static_starlight",
    title: "Static and Starlight",
    synopsis:
      "Almost-silence with a heartbeat under it. Instrumental and ambient pieces to fold the day away to — slow, weightless, and asking nothing of you, made to be half-heard on the long drift down into sleep when words would only get in the way of it.",
    arcs: [
      { label: "settling", summary: "The day folds away; the first slow exhale, lights going down." },
      { label: "weightless", summary: "Slow and floating, asking nothing, the mind finally loosening its grip." },
      { label: "under", summary: "The quiet drift all the way down into sleep." },
    ],
  },
};

// Per-collection arc weights (relative sizes). Equal unless tuned.
const ARC_WEIGHTS = {
  A: [1.2, 1, 0.9],
  B: [1, 1, 1],
  C: [1, 1, 1],
  D: [1, 1, 1],
  E: [1, 1.1, 0.9],
  F: [1, 1.1, 1.1, 0.9],
  G: [1, 1, 1],
  H: [1, 1, 1],
};

// ---------------------------------------------------------------------------
// 2. Song → collection assignment, by playlist position (1-based). "S" = skip
//    (the 7 F & T Reviews travel vlogs — not music). One token per track.
// ---------------------------------------------------------------------------

// prettier-ignore
const ASSIGN = [
  // 1-10
  "G","G","E","B","D","C","F","F","F","A",
  // 11-20
  "F","A","C","F","C","B","D","A","B","G",
  // 21-30
  "F","C","F","E","F","S","E","G","B","D",
  // 31-40
  "A","D","D","C","A","H","C","B","F","H",
  // 41-50
  "S","F","G","B","F","B","G","H","F","A",
  // 51-60
  "F","C","A","D","S","F","G","C","G","H",
  // 61-70
  "C","A","A","B","F","F","D","F","F","S",
  // 71-80
  "D","H","G","A","C","A","E","F","C","F",
  // 81-90
  "F","E","C","H","B","D","S","F","B","G",
  // 91-100
  "F","F","E","F","H","F","B","A","F","B",
  // 101-110
  "D","D","D","S","B","H","C","C","B","B",
  // 111-120
  "D","F","F","F","A","D","H","C","F","A",
  // 121-130
  "S","A","F","D","A","C","B","B","E","F",
  // 131-140
  "C","E","F","A","F","F","E","C","G","A",
  // 141-150
  "B","F","F","A","G","E","F","F","B","G",
  // 151-160
  "B","F","F","C","F","F","F","F","F","D",
  // 161-170
  "F","E","E","C","G","C","F","E","F","D",
  // 171-180
  "A","D","A","C","B","C","D","C","C","F",
  // 181-190
  "B","D","B","F","F","F","F","E","G","B",
  // 191-200
  "B","C","E","D","A","D","F","D","E","F",
  // 201-210
  "B","E","E","D","F","E","F","H","H","H",
];

// ---------------------------------------------------------------------------
// 3. Demo listeners (10). Spread across all 5 slots; each has a lane it
//    finishes and a lane it abandons, so the taste centroid means something.
// ---------------------------------------------------------------------------

const H_ = (series_id, episodes_listened, completed, liked = null, dropped_at_episode = null) =>
  ({ series_id, episodes_listened, completed, liked, dropped_at_episode });

const PROFILES = [
  { persona_id: "p_ananya", display_name: "Ananya",
    attrs: { listening_time_slot: "late_night", primary_language: "en", series_completion_rate: 0.35, typical_dropoff_episode: 12, tolerance_for_heaviness: 0.85 },
    history: [ H_("pf_after_ending", 22, true, true), H_("pf_three_am_clarity", 18, true, true), H_("pf_hands_up", 3, false, false, 3) ] },
  { persona_id: "p_rohan", display_name: "Rohan",
    attrs: { listening_time_slot: "commute", primary_language: "en", series_completion_rate: 0.72, typical_dropoff_episode: 40, tolerance_for_heaviness: 0.4 },
    history: [ H_("pf_windows_down", 21, true, true), H_("pf_hands_up", 33, true, true), H_("pf_static_starlight", 2, false, false, 2) ] },
  { persona_id: "p_meera", display_name: "Meera",
    attrs: { listening_time_slot: "bedtime", primary_language: "en", series_completion_rate: 0.5, typical_dropoff_episode: 20, tolerance_for_heaviness: 0.6 },
    history: [ H_("pf_static_starlight", 14, true, true), H_("pf_held", 16, true, true), H_("pf_neon_shadow", 4, false, false, 4) ] },
  { persona_id: "p_kabir", display_name: "Kabir",
    attrs: { listening_time_slot: "work_break", primary_language: "en", series_completion_rate: 0.45, typical_dropoff_episode: 15, tolerance_for_heaviness: 0.5 },
    history: [ H_("pf_hands_up", 28, true, true), H_("pf_soft_morning", 12, true, true), H_("pf_after_ending", 5, false, false, 5) ] },
  { persona_id: "p_sara", display_name: "Sara",
    attrs: { listening_time_slot: "chores", primary_language: "en", series_completion_rate: 0.6, typical_dropoff_episode: 25, tolerance_for_heaviness: 0.35 },
    history: [ H_("pf_soft_morning", 19, true, true), H_("pf_held", 20, true, true), H_("pf_neon_shadow", 3, false, false, 3) ] },
  { persona_id: "p_dev", display_name: "Dev",
    attrs: { listening_time_slot: "late_night", primary_language: "en", series_completion_rate: 0.3, typical_dropoff_episode: 10, tolerance_for_heaviness: 0.9 },
    history: [ H_("pf_neon_shadow", 15, true, true), H_("pf_after_ending", 12, true, true), H_("pf_hands_up", 2, false, false, 2) ] },
  { persona_id: "p_isha", display_name: "Isha",
    attrs: { listening_time_slot: "commute", primary_language: "en", series_completion_rate: 0.65, typical_dropoff_episode: 35, tolerance_for_heaviness: 0.5 },
    history: [ H_("pf_windows_down", 24, true, true), H_("pf_three_am_clarity", 17, true, true), H_("pf_static_starlight", 3, false, false, 3) ] },
  { persona_id: "p_arjun", display_name: "Arjun",
    attrs: { listening_time_slot: "bedtime", primary_language: "en", series_completion_rate: 0.55, typical_dropoff_episode: 18, tolerance_for_heaviness: 0.7 },
    history: [ H_("pf_static_starlight", 16, true, true), H_("pf_three_am_clarity", 15, true, true), H_("pf_hands_up", 4, false, false, 4) ] },
  { persona_id: "p_naina", display_name: "Naina",
    attrs: { listening_time_slot: "work_break", primary_language: "en", series_completion_rate: 0.5, typical_dropoff_episode: 22, tolerance_for_heaviness: 0.4 },
    history: [ H_("pf_held", 18, true, true), H_("pf_soft_morning", 16, true, true), H_("pf_windows_down", 3, false, false, 3) ] },
  { persona_id: "p_veer", display_name: "Veer",
    attrs: { listening_time_slot: "chores", primary_language: "en", series_completion_rate: 0.42, typical_dropoff_episode: 14, tolerance_for_heaviness: 0.6 },
    history: [ H_("pf_hands_up", 20, true, true), H_("pf_neon_shadow", 13, true, true), H_("pf_after_ending", 4, false, false, 4) ] },
];

// ---------------------------------------------------------------------------
// 4. Build
// ---------------------------------------------------------------------------

function arcBoundaries(n, weights) {
  const total = weights.reduce((a, b) => a + b, 0);
  const spans = [];
  let start = 1;
  let acc = 0;
  for (let i = 0; i < weights.length; i++) {
    acc += weights[i];
    let end = i === weights.length - 1 ? n : Math.round((acc / total) * n);
    if (end < start) end = start;
    if (end > n) end = n;
    spans.push([start, end]);
    start = end + 1;
    if (start > n && i < weights.length - 1) {
      // ran out of episodes for remaining arcs — stop; fewer arcs is valid
      break;
    }
  }
  return spans;
}

function build() {
  const songs = JSON.parse(readFileSync(SONGS_PATH, "utf8")).tracks;
  if (!Array.isArray(songs) || songs.length !== ASSIGN.length) {
    throw new Error(`song count ${songs?.length} != ASSIGN length ${ASSIGN.length}`);
  }

  // group songs (in playlist order) by collection
  const grouped = {}; // letter -> [song,...]
  const counts = {};
  let skipped = 0;
  songs.forEach((s, i) => {
    const letter = ASSIGN[i];
    if (letter === "S") { skipped++; return; }
    if (!COLLECTIONS[letter]) throw new Error(`unknown collection '${letter}' at track ${i + 1}`);
    (grouped[letter] ??= []).push(s);
    counts[letter] = (counts[letter] || 0) + 1;
  });

  const catalog = [];
  const episodesFile = [];

  for (const letter of Object.keys(COLLECTIONS)) {
    const c = COLLECTIONS[letter];
    const list = grouped[letter] || [];
    const n = list.length;
    if (n === 0) continue;

    const spans = arcBoundaries(n, ARC_WEIGHTS[letter] || [1, 1, 1]);
    const arcStarts = new Set(spans.map(([s]) => s));

    const arcs = spans.map(([start, end], i) => ({
      arc_id: `${c.series_id}_a${i}`,
      label: c.arcs[i]?.label || `arc ${i + 1}`,
      start_episode: start,
      end_episode: end,
      summary: c.arcs[i]?.summary || c.synopsis,
    }));

    catalog.push({
      series_id: c.series_id,
      title: c.title,
      synopsis: c.synopsis,
      total_episodes: n,
      language: "en",
      source: "youtube_playlist",
      arcs,
    });

    episodesFile.push({
      series_id: c.series_id,
      episodes: list.map((s, idx) => {
        const number = idx + 1;
        return {
          number,
          title: s.title,
          duration_sec: Number.isInteger(s.duration_seconds) ? s.duration_seconds : 0,
          synopsis: s.artist || null,
          audio_url: s.url || null,
          is_arc_start: arcStarts.has(number),
        };
      }),
    });
  }

  return { catalog, episodesFile, counts, skipped, songTotal: songs.length };
}

// ---------------------------------------------------------------------------
// 5. Validator — faithful port of validate_sources.py (errors block ingest)
// ---------------------------------------------------------------------------

const SYNTHETIC_SOURCES = new Set(["synthetic", "llm", "generated", "fixture", "gpt", "claude"]);
const MIN_SYNOPSIS_CHARS = 120;
const MIN_EPISODES_FOR_ARCS = 6;
const LOAD_BEARING_ATTRS = ["listening_time_slot", "primary_language", "series_completion_rate", "typical_dropoff_episode", "tolerance_for_heaviness"];
const VALID_SLOTS = new Set(["late_night", "bedtime", "commute", "chores", "work_break"]);

function validate(catalog, episodes, profiles) {
  const errors = [], warnings = [], notes = [];
  const E = (m) => errors.push(m), W = (m) => warnings.push(m), N = (m) => notes.push(m);

  // --- catalog ---
  const byId = {};
  const arcIds = {};
  for (let i = 0; i < catalog.length; i++) {
    const rec = catalog[i];
    const sid = rec.series_id;
    if (!sid) { E(`catalog[${i}]: missing series_id`); continue; }
    if (byId[sid]) { E(`series ${sid}: duplicate series_id`); continue; }
    if (!rec.title) E(`series ${sid}: missing title`);
    const syn = (rec.synopsis || "").trim();
    if (syn.length < MIN_SYNOPSIS_CHARS) W(`series ${sid}: synopsis ${syn.length} chars (< ${MIN_SYNOPSIS_CHARS})`);
    const source = String(rec.source || "").toLowerCase();
    if (!source) E(`series ${sid}: missing 'source'`);
    else if (SYNTHETIC_SOURCES.has(source)) W(`series ${sid}: source='${source}' is model-written (padding only)`);
    let total = rec.total_episodes;
    if (!Number.isInteger(total) || total < 1) { E(`series ${sid}: total_episodes must be positive int, got ${total}`); total = 0; }
    const arcs = rec.arcs || [];
    if (!arcs.length) {
      if (total >= MIN_EPISODES_FOR_ARCS) W(`series ${sid}: no arcs — even splits synthesised`);
    } else {
      const spans = [];
      arcs.forEach((arc, j) => {
        const aid = arc.arc_id || `${sid}_a${j}`;
        arcIds[aid] = (arcIds[aid] || 0) + 1;
        const { start_episode: st, end_episode: en } = arc;
        if (!Number.isInteger(st) || !Number.isInteger(en)) { E(`series ${sid} arc ${aid}: start/end must be ints`); return; }
        if (st > en) E(`series ${sid} arc ${aid}: start ${st} > end ${en}`);
        if (total && en > total) E(`series ${sid} arc ${aid}: ends at ep ${en} but series has ${total}`);
        if (!arc.label) W(`series ${sid} arc ${aid}: no label`);
        spans.push([st, en, aid]);
      });
      spans.sort((a, b) => a[0] - b[0]);
      for (let k = 0; k < spans.length - 1; k++) {
        if (spans[k + 1][0] <= spans[k][1]) W(`series ${sid}: arcs ${spans[k][2]} and ${spans[k + 1][2]} overlap`);
      }
    }
    byId[sid] = rec;
  }
  for (const [aid, ct] of Object.entries(arcIds)) if (ct > 1) E(`arc_id ${aid} used ${ct}× — must be globally unique`);
  N(`catalog: ${Object.keys(byId).length} series, ${Object.values(arcIds).reduce((a, b) => a + b, 0)} arcs`);
  const real = Object.values(byId).filter((r) => !SYNTHETIC_SOURCES.has(String(r.source || "").toLowerCase())).length;
  N(`catalog: ${real} from real sources, ${Object.keys(byId).length - real} model-written`);

  // --- episodes ---
  const bySeries = {};
  for (let i = 0; i < episodes.length; i++) {
    const rec = episodes[i];
    const sid = rec.series_id;
    const eps = rec.episodes ? rec.episodes : [rec];
    if (!sid) { E(`episodes[${i}]: missing series_id`); continue; }
    if (Object.keys(byId).length && !byId[sid]) { E(`episodes: series_id ${sid} not in catalog`); continue; }
    const numbers = (bySeries[sid] ??= new Set());
    for (const ep of eps) {
      const nnum = ep.number;
      if (!Number.isInteger(nnum) || nnum < 1) { E(`series ${sid}: episode number must be positive int, got ${nnum}`); continue; }
      if (numbers.has(nnum)) E(`series ${sid}: duplicate episode ${nnum}`);
      numbers.add(nnum);
      if (!ep.title) W(`series ${sid} ep ${nnum}: no title`);
      const dur = ep.duration_sec;
      if (dur != null && (!Number.isInteger(dur) || dur < 0)) E(`series ${sid} ep ${nnum}: duration_sec must be non-negative int`);
    }
  }
  // cross-check: every arc start must exist
  for (const [sid, rec] of Object.entries(byId)) {
    const have = bySeries[sid];
    if (!have) continue;
    for (const arc of rec.arcs || []) {
      if (Number.isInteger(arc.start_episode) && !have.has(arc.start_episode))
        E(`series ${sid}: arc ${arc.arc_id} → ep ${arc.start_episode} missing in episodes (404 in player)`);
    }
  }
  const epTotal = Object.values(bySeries).reduce((a, s) => a + s.size, 0);
  if (epTotal) N(`episodes: ${epTotal} authored across ${Object.keys(bySeries).length} series`);

  // --- profiles ---
  const seen = new Set();
  const slots = {};
  for (let i = 0; i < profiles.length; i++) {
    const rec = profiles[i];
    const pid = rec.persona_id || rec.id;
    const where = pid ? `persona ${pid}` : `profiles[${i}]`;
    if (!pid) { E(`${where}: missing persona_id`); continue; }
    if (seen.has(pid)) E(`${where}: duplicate persona_id`);
    seen.add(pid);
    if (!rec.display_name) W(`${where}: no display_name`);
    const attrs = rec.attrs || {};
    const missing = LOAD_BEARING_ATTRS.filter((a) => !(a in attrs));
    if (missing.length) W(`${where}: missing load-bearing attrs ${JSON.stringify(missing)}`);
    const slot = attrs.listening_time_slot;
    if (slot) { slots[slot] = (slots[slot] || 0) + 1; if (!VALID_SLOTS.has(slot)) W(`${where}: slot='${slot}' not valid`); }
    const history = rec.history || [];
    if (!history.length) W(`${where}: no history`);
    for (const h of history) {
      if (Object.keys(byId).length && !byId[h.series_id]) E(`${where}: history references unknown series ${h.series_id}`);
      if (typeof h.completed !== "boolean") E(`${where}: history entry for ${h.series_id} needs boolean 'completed'`);
    }
  }
  N(`profiles: ${seen.size} listeners, slots ${JSON.stringify(slots)}`);
  if (Object.keys(slots).length < 3 && seen.size >= 5) W(`profiles: fewer than 3 listening slots`);

  return { errors, warnings, notes };
}

// ---------------------------------------------------------------------------
// 6. Run
// ---------------------------------------------------------------------------

const { catalog, episodesFile, counts, skipped, songTotal } = build();

const catPath = resolve(HERE, "catalog.json");
const epPath = resolve(HERE, "episodes.json");
const profPath = resolve(HERE, "profiles.json");
writeFileSync(catPath, JSON.stringify(catalog, null, 2), "utf8");
writeFileSync(epPath, JSON.stringify(episodesFile, null, 2), "utf8");
writeFileSync(profPath, JSON.stringify(PROFILES, null, 2), "utf8");

const { errors, warnings, notes } = validate(catalog, episodesFile, PROFILES);

const emitted = Object.values(counts).reduce((a, b) => a + b, 0);
console.log("BUILD");
console.log(`  songs in       : ${songTotal}`);
console.log(`  skipped (vlogs): ${skipped}`);
console.log(`  → episodes     : ${emitted}`);
console.log("  collection sizes:");
for (const letter of Object.keys(COLLECTIONS)) {
  const c = COLLECTIONS[letter];
  console.log(`    ${c.series_id.padEnd(22)} ${String(counts[letter] || 0).padStart(3)} songs`);
}
console.log("\nVALIDATE (port of validate_sources.py)");
for (const m of notes) console.log(`  ·  ${m}`);
for (const m of warnings) console.log(`  !  ${m}`);
for (const m of errors) console.log(`  X  ${m}`);
console.log(`\n${errors.length} errors, ${warnings.length} warnings` + (errors.length ? "  — fix errors first" : "  — ready to ingest"));
console.log(`\nwrote:\n  ${catPath}\n  ${epPath}\n  ${profPath}`);

process.exit(errors.length ? 1 : 0);
