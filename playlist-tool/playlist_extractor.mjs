#!/usr/bin/env node
/**
 * playlist_extractor.mjs — Extract every track from a YouTube / YouTube Music
 * playlist into a JSON file, using only the playlist URL.
 *
 * No API key, no login, and NO third-party libraries. It reads the public
 * playlist page and then pages through YouTube's own `youtubei/v1/browse`
 * continuation endpoint — the same calls the website makes as you scroll — so
 * it keeps working even when scraping libraries fall out of date.
 *
 * Requires Node 18+ (uses the built-in global `fetch`).
 *
 * Usage:
 *     node playlist_extractor.mjs "https://www.youtube.com/playlist?list=XXXX"
 *     node playlist_extractor.mjs "https://music.youtube.com/playlist?list=XXXX" -o songs.json
 *     node playlist_extractor.mjs "URL" --print          # also print the list
 *     node playlist_extractor.mjs "URL" --limit 50        # first 50 tracks only
 *
 * Output JSON shape:
 *     {
 *       "playlist": { "title", "id", "uploader", "url", "source" },
 *       "count": 210,
 *       "tracks": [
 *         { "index": 1, "title", "artist", "duration": "4:33",
 *           "duration_seconds": 273, "video_id", "url" }, ...
 *       ]
 *     }
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const BASE_HEADERS = { "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", Cookie: "CONSENT=YES+1" };
const DUR_RE = /^\d{1,2}(:\d{2}){1,2}$/;

function die(msg, code = 1) {
  process.stderr.write(`error: ${msg}\n`);
  process.exit(code);
}

const USAGE = `Extract all tracks from a YouTube / YouTube Music playlist into JSON.

Usage:
  node playlist_extractor.mjs "<playlist url>" [-o out.json] [--print] [--limit N]

Options:
  -o, --output   Output JSON path (default: "<playlist title>.json")
  --print        Also print "Title - Artist" to the console
  --limit N      Only keep the first N tracks (default: all)
`;

function parseArgs(argv) {
  const args = { url: null, output: null, show: false, limit: Infinity, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-o" || a === "--output") args.output = argv[++i];
    else if (a === "--print") args.show = true;
    else if (a === "--limit") args.limit = Number(argv[++i]) || Infinity;
    else if (a === "-h" || a === "--help") args.help = true;
    else if (!a.startsWith("-") && !args.url) args.url = a;
  }
  return args;
}

function toPlaylistId(input) {
  try {
    const list = new URL(input).searchParams.get("list");
    if (list) return list;
  } catch {
    /* not a URL — treat as a raw id */
  }
  return input;
}

/** Extract a balanced JSON object that begins at/after `marker` in `str`. */
function grabJson(str, marker) {
  const at = str.indexOf(marker);
  if (at < 0) return null;
  const start = str.indexOf("{", at);
  if (start < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < str.length; i++) {
    const c = str[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
    } else if (c === '"') inStr = true;
    else if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return str.slice(start, i + 1);
  }
  return null;
}

function hms(sec) {
  sec = Math.floor(Number(sec));
  if (!Number.isFinite(sec) || sec <= 0) return null;
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function toSeconds(dur) {
  if (!dur) return null;
  const parts = dur.split(":").map(Number);
  if (parts.some(Number.isNaN)) return null;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

const cleanArtist = (name) =>
  name ? String(name).replace(/\s*-\s*Topic$/i, "").trim() || null : null;

function safeFilename(name) {
  return (
    String(name || "").replace(/[<>:"/\\|?* -]+/g, "_").trim().replace(/\.+$/, "") || "playlist"
  );
}

/** First string that looks like a duration (e.g. "4:33"), searched recursively. */
function findDuration(o) {
  let res = null;
  const walk = (x) => {
    if (res || !x) return;
    if (typeof x === "string") {
      if (DUR_RE.test(x)) res = x;
    } else if (typeof x === "object") {
      for (const k in x) {
        if (res) break;
        walk(x[k]);
      }
    }
  };
  walk(o);
  return res;
}

function lockupToTrack(L) {
  const meta = L.metadata?.lockupMetadataViewModel;
  const rows = meta?.metadata?.contentMetadataViewModel?.metadataRows || [];
  const channel =
    rows[0]?.metadataParts?.map((p) => p.text?.content).filter(Boolean).join(" ") || null;
  const duration = findDuration(L);
  return {
    videoId: L.contentId || null,
    title: meta?.title?.content ?? null,
    channel,
    duration,
    duration_seconds: toSeconds(duration),
  };
}

/** First continuation token (`continuationCommand.token`) found anywhere in `o`. */
function findToken(o) {
  let tok = null;
  const walk = (x) => {
    if (tok || !x || typeof x !== "object") return;
    if (x.continuationCommand?.token) { tok = x.continuationCommand.token; return; }
    for (const k in x) {
      if (tok) break;
      walk(x[k]);
    }
  };
  walk(o);
  return tok;
}

/** Every video lockup (`lockupViewModel` with a contentId) found anywhere in `o`. */
function collectLockups(o) {
  const out = [];
  const walk = (x) => {
    if (!x || typeof x !== "object") return;
    if (x.lockupViewModel?.contentId) out.push(x.lockupViewModel);
    for (const k in x) walk(x[k]);
  };
  walk(o);
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) return void process.stdout.write(USAGE);
  if (!args.url) die("no playlist URL given.\n\n" + USAGE);

  const listId = toPlaylistId(args.url);
  const pageUrl = `https://www.youtube.com/playlist?list=${encodeURIComponent(listId)}`;
  process.stderr.write("Reading playlist …\n");

  let html;
  try {
    const res = await fetch(pageUrl, { headers: BASE_HEADERS });
    if (!res.ok) die(`YouTube returned HTTP ${res.status} for that playlist.`);
    html = await res.text();
  } catch (e) {
    die(`could not fetch the playlist page: ${e.message}`);
  }

  const initRaw = grabJson(html, "ytInitialData");
  if (!initRaw) die("could not locate playlist data (is the URL a real, public playlist?).");
  let ytInitialData;
  try {
    ytInitialData = JSON.parse(initRaw);
  } catch (e) {
    die(`failed to parse playlist data: ${e.message}`);
  }

  const apiKey = (html.match(/"INNERTUBE_API_KEY":"([^"]+)"/) || [])[1];
  const ctxRaw = grabJson(html, '"INNERTUBE_CONTEXT":');
  const context = ctxRaw ? JSON.parse(ctxRaw) : null;

  // First page is embedded in the HTML; the rest come from the continuation API
  // (the same `youtubei/v1/browse` calls the site makes as you scroll).
  const seenIds = new Set();
  const collected = [];
  const absorb = (lockups) => {
    let added = 0;
    for (const L of lockups) {
      if (L.contentId && !seenIds.has(L.contentId)) {
        seenIds.add(L.contentId);
        collected.push(L);
        added++;
      }
    }
    return added;
  };

  absorb(collectLockups(ytInitialData));
  let token = findToken(ytInitialData);
  const usedTokens = new Set();
  let guard = 0;
  while (
    token && apiKey && context &&
    !usedTokens.has(token) &&
    collected.length < args.limit &&
    guard < 40
  ) {
    usedTokens.add(token);
    guard++;
    let json;
    try {
      const res = await fetch(
        `https://www.youtube.com/youtubei/v1/browse?key=${apiKey}&prettyPrint=false`,
        {
          method: "POST",
          headers: { ...BASE_HEADERS, "Content-Type": "application/json" },
          body: JSON.stringify({ context, continuation: token }),
        }
      );
      json = await res.json();
    } catch (e) {
      process.stderr.write(`warning: stopped paging early (${e.message})\n`);
      break;
    }
    const actions = json.onResponseReceivedActions || json.onResponseReceivedEndpoints || [];
    const added = absorb(collectLockups(actions));
    if (added === 0) break;
    process.stderr.write(`  …loaded ${collected.length} tracks\n`);
    token = findToken(actions);
  }

  // De-dupe by videoId, map to output records, honour --limit.
  const seen = new Set();
  const tracks = [];
  for (const L of collected) {
    const t = lockupToTrack(L);
    if (!t.videoId || seen.has(t.videoId)) continue;
    seen.add(t.videoId);
    tracks.push({
      index: tracks.length + 1,
      title: t.title,
      artist: cleanArtist(t.channel),
      duration: t.duration,
      duration_seconds: t.duration_seconds ?? (t.duration ? toSeconds(t.duration) : null),
      video_id: t.videoId,
      url: `https://www.youtube.com/watch?v=${t.videoId}`,
    });
    if (tracks.length >= args.limit) break;
  }

  if (tracks.length === 0) die("no tracks found — is the playlist public and non-empty?");

  const pageTitle = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || "";
  const title = pageTitle.replace(/\s*-\s*YouTube\s*$/i, "").trim() || "playlist";
  const uploader =
    (html.match(/"ownerText":\{"runs":\[\{"text":"([^"]+)"/) || [])[1] ||
    (html.match(/"videoOwnerChannelName":"([^"]+)"/) || [])[1] ||
    null;

  const data = {
    playlist: {
      title,
      id: listId,
      uploader,
      url: pageUrl,
      source: /music\.youtube/.test(args.url) ? "youtube_music" : "youtube",
    },
    count: tracks.length,
    tracks,
  };

  const outPath = resolve(args.output || `${safeFilename(title)}.json`);
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, JSON.stringify(data, null, 2), "utf8");
  process.stderr.write(`✓ ${tracks.length} tracks -> ${outPath}\n`);

  if (args.show) {
    for (const t of tracks) {
      const artist = t.artist ? ` - ${t.artist}` : "";
      const dur = t.duration ? `  [${t.duration}]` : "";
      process.stdout.write(`${String(t.index).padStart(3)}. ${t.title}${artist}${dur}\n`);
    }
  }
}

main().catch((e) => die(e.stack || String(e)));
