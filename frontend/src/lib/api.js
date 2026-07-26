// Tiny fetch client for the Simulated Studio backend.
//
// Base URL is RELATIVE by default (empty string), so requests hit the same
// origin and are handled by the Vite dev proxy (see vite.config.js) in
// development and by the hosting layer in production. Override with VITE_API_URL
// when the backend lives on a different origin. See frontend/.env.example.

const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

/**
 * Core request helper. Sends/receives JSON and throws on any non-2xx response,
 * surfacing the backend's `detail` message (or raw response text) when present.
 */
async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    const raw = await res.text().catch(() => '')
    if (raw) {
      try {
        const data = JSON.parse(raw)
        detail = data && data.detail ? data.detail : raw
      } catch {
        detail = raw
      }
    }
    throw new Error(detail)
  }

  return res.json()
}

/** GET /health -> { status, provider, project, location, firestore } */
export function health() {
  return request('/health')
}

/** GET /api/personas -> { audience: Persona[], experts: Persona[] } */
export function getPersonas() {
  return request('/api/personas')
}

/**
 * POST /api/simulate/audience -> AudienceResult
 * @param {{title:string, episode:string, text:string}} story
 * @param {number} [n] optional audience fan-out size
 */
export function simulateAudience(story, n) {
  return request('/api/simulate/audience', {
    method: 'POST',
    body: n != null ? { story, n } : { story },
  })
}

/**
 * POST /api/lenses/writers-room -> WritersRoomResult
 * @param {{title:string, episode:string, text:string}} story
 */
export function writersRoom(story) {
  return request('/api/lenses/writers-room', { method: 'POST', body: { story } })
}

// --- Audience Simulator ("Living Audience") --------------------------------

/** GET /api/audience-sim/library -> AudienceLibrary { members[], total, source } */
export function getAudienceLibrary() {
  return request('/api/audience-sim/library')
}

/**
 * POST /api/audience-sim/generate -> AudienceLibrary
 * Synthesise a diverse audience of listener-agents (persisted by default).
 */
export function generateAudience({ n, brief, seedSegments, persist = true } = {}) {
  const body = { persist }
  if (n != null) body.n = n
  if (brief) body.brief = brief
  if (Array.isArray(seedSegments) && seedSegments.length) body.seed_segments = seedSegments
  return request('/api/audience-sim/generate', { method: 'POST', body })
}

/**
 * POST /api/audience-sim/run/stream -> NDJSON reaction events.
 *
 * Streams one event per agent as it reacts ("reaction"/"agent_error"), bookended
 * by "run_started" and a terminal "done" carrying the aggregated result. An
 * edited roster is sent as `audience` (honoured verbatim); omit it to reuse the
 * persisted knowledge-graph audience.
 *
 * @param {{story:object, audience?:object[], n?:number, useLibrary?:boolean}} payload
 * @param {(event:object)=>void} onEvent
 * @param {AbortSignal} [signal]
 */
export function audienceSimStream({ story, audience, n, useLibrary }, onEvent, signal) {
  const body = { story }
  if (Array.isArray(audience) && audience.length) body.audience = audience
  if (n != null) body.n = n
  if (useLibrary != null) body.use_library = useLibrary
  return ndjsonStream('/api/audience-sim/run/stream', body, onEvent, signal)
}

/**
 * POST /api/lenses/cliffhanger -> CliffhangerResult
 * @param {{title:string, episode:string, text:string}} story
 * @param {string} weakExcerpt the weak ending to rewrite
 */
export function cliffhanger(story, weakExcerpt) {
  return request('/api/lenses/cliffhanger', {
    method: 'POST',
    body: { story, weak_excerpt: weakExcerpt },
  })
}

/**
 * POST /api/lenses/cliffhanger/stream -> NDJSON run-log events.
 *
 * Streams the optimizer's own work as it happens so the UI can show a live,
 * CLI-style run log instead of a bare spinner: `run_started`, the `rewrite`
 * phase, one `agent_scored` per listener for the original then the optimized
 * ending, `panel_*` phase start/done, and a terminal `done` carrying the full
 * CliffhangerResult (same shape as the non-streaming lens).
 *
 * @param {{story:object, weakExcerpt:string}} payload
 * @param {(event:object)=>void} onEvent called once per event line
 * @param {AbortSignal} [signal] optional cancel signal
 */
export function cliffhangerStream({ story, weakExcerpt }, onEvent, signal) {
  return ndjsonStream(
    '/api/lenses/cliffhanger/stream',
    { story, weak_excerpt: weakExcerpt },
    onEvent,
    signal,
  )
}

/**
 * POST /api/lenses/cliffhanger/narrate -> NarrationResult
 *
 * Voices both endings (base64 audio, one call) so the UI can play an audible
 * A/B: the original read flat, the optimized cliffhanger read with dramatic,
 * in-character tension.
 *
 * @param {{original:string, optimized:string}} endings
 */
export function narrateCliffhanger({ original, optimized }) {
  return request('/api/lenses/cliffhanger/narrate', {
    method: 'POST',
    body: { original, optimized },
  })
}

// --- Knowledge graph (Story Canon) -----------------------------------------

/** GET /api/canon/health -> { configured, online } */
export function canonHealth() {
  return request('/api/canon/health')
}

/**
 * GET /api/canon/graph -> CanonGraph { nodes[], edges[], stats }
 * @param {string} [batch] scope to just what this session ingested ("your story")
 */
export function getCanonGraph(batch) {
  return request(batch ? `/api/canon/graph?batch=${encodeURIComponent(batch)}` : '/api/canon/graph')
}

/** GET /api/canon/activity -> { events: ActivityEvent[] } (recent reads/writes) */
export function getCanonActivity(limit = 100) {
  return request(`/api/canon/activity?limit=${limit}`)
}

/**
 * GET /api/canon/facts -> { facts[], conflicts[], dangling_clues[], episode_count }
 * @param {string} [batch] scope to just this session's story
 */
export function getCanonFacts(batch) {
  return request(batch ? `/api/canon/facts?batch=${encodeURIComponent(batch)}` : '/api/canon/facts')
}

/**
 * POST /api/canon/preview -> CanonPreviewResult (extract-only, nothing written)
 * The live "as you type" extraction that shows what the agents will remember.
 * @param {{title:string, episode:string, text:string}} story
 */
export function previewCanon(story) {
  return request('/api/canon/preview', { method: 'POST', body: { story } })
}

/**
 * POST /api/canon/ingest -> IngestResult
 * @param {{title:string, episode:string, text:string}} story
 * @param {string} [batch] session tag so this ingest is scopable/resettable as "your story"
 */
export function ingestCanon(story, batch) {
  return request('/api/canon/ingest', { method: 'POST', body: batch ? { story, batch } : { story } })
}

/**
 * POST /api/canon/reset -> { deleted, batch }
 * Clears only what this session ingested — never the seeded demo canon.
 * @param {string} batch the session tag to clear
 */
export function resetCanonSession(batch) {
  return request('/api/canon/reset', { method: 'POST', body: { batch } })
}

/** POST /api/lenses/plot-holes -> PlotHoleResult */
export function findPlotHoles(story) {
  return request('/api/lenses/plot-holes', { method: 'POST', body: { story } })
}

/**
 * POST /api/lenses/story-plot-holes -> StoryScanResult
 * Scans ONE loaded show's episodes for cross-episode contradictions — story-scoped
 * (never the seeded canon). Sends every episode's text so the result can cite the
 * exact clashing sentence on each side, for the book / highlighter view.
 * @param {{title:string, episodes:{label:string,text:string}[]}} story
 */
export function scanStoryPlotHoles(story) {
  const episodes = (story.episodes || []).map((e) => ({ episode: e.label, text: e.text }))
  return request('/api/lenses/story-plot-holes', {
    method: 'POST',
    body: { title: story.title, episodes },
  })
}

/**
 * POST /api/plan/cliffhanger/stream -> NDJSON tree-search events.
 * @param {{story:object, weakExcerpt:string, beamWidth?:number, depth?:number}} payload
 */
export function planCliffhangerStream(
  { story, weakExcerpt, batch, beamWidth, depth },
  onEvent,
  signal,
) {
  const body = { story, weak_excerpt: weakExcerpt, batch }
  if (beamWidth) body.beam_width = beamWidth
  if (depth) body.depth = depth
  return ndjsonStream('/api/plan/cliffhanger/stream', body, onEvent, signal)
}

/**
 * POST /api/agent/showrunner/stream -> NDJSON state-graph events.
 * @param {{story:object, weakExcerpt?:string}} payload
 */
export function showrunnerStream({ story, weakExcerpt }, onEvent, signal) {
  const body = { story }
  if (weakExcerpt) body.weak_excerpt = weakExcerpt
  return ndjsonStream('/api/agent/showrunner/stream', body, onEvent, signal)
}

/**
 * POST /api/mdp/optimize/stream -> NDJSON policy-search events.
 * @param {{story:object, weakExcerpt:string, iterations?:number, candidatesPerIter?:number}} payload
 */
export function mdpOptimizeStream({ story, weakExcerpt, iterations, candidatesPerIter }, onEvent, signal) {
  const body = { story, weak_excerpt: weakExcerpt }
  if (iterations) body.iterations = iterations
  if (candidatesPerIter) body.candidates_per_iter = candidatesPerIter
  return ndjsonStream('/api/mdp/optimize/stream', body, onEvent, signal)
}

/**
 * POST /api/lenses/writers-room/stream -> newline-delimited JSON (NDJSON).
 *
 * Streams the whole agentic loop: one JSON object per line
 * (media type application/x-ndjson). Each parsed event is handed to `onEvent`
 * as it arrives so the UI can render the loop live. Pass an AbortSignal to stop
 * the run early; aborting rejects the returned promise with an AbortError.
 *
 * The edited rosters are sent alongside the story so the simulation uses the
 * agents as edited in the UI. Empty rosters are omitted so the server falls back
 * to its default personas (skills/*.yaml) rather than running with no agents.
 *
 * @param {{story:{title:string,episode:string,text:string}, experts?:object[], audience?:object[]}} payload
 * @param {(event: object) => void} onEvent called once per complete event line
 * @param {AbortSignal} [signal] optional signal to cancel the stream
 */
export async function writersRoomStream({ story, experts, audience }, onEvent, signal) {
  const body = { story }
  if (Array.isArray(experts) && experts.length) body.experts = experts
  if (Array.isArray(audience) && audience.length) body.audience = audience
  return ndjsonStream('/api/lenses/writers-room/stream', body, onEvent, signal)
}

/**
 * POST a JSON body and consume a newline-delimited JSON (NDJSON) response,
 * handing each parsed event to `onEvent` as it arrives. Shared by every
 * streaming lens (Writers Room, planner, showrunner agent, MDP optimizer).
 *
 * Pass an AbortSignal to cancel; aborting rejects with an AbortError.
 *
 * @param {string} path                        endpoint path
 * @param {object} body                        JSON request body
 * @param {(event: object) => void} onEvent    called once per complete event line
 * @param {AbortSignal} [signal]               optional cancel signal
 */
export async function ndjsonStream(path, body, onEvent, signal) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    const raw = await res.text().catch(() => '')
    if (raw) {
      try {
        const data = JSON.parse(raw)
        detail = data && data.detail ? data.detail : raw
      } catch {
        detail = raw
      }
    }
    throw new Error(detail)
  }

  if (!res.body) {
    throw new Error('Live streaming is not supported in this browser.')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const emit = (line) => {
    const trimmed = line.trim()
    if (!trimmed) return
    let event
    try {
      event = JSON.parse(trimmed)
    } catch {
      return // ignore a malformed / partial line
    }
    onEvent(event)
  }

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let newline
      while ((newline = buffer.indexOf('\n')) >= 0) {
        emit(buffer.slice(0, newline))
        buffer = buffer.slice(newline + 1)
      }
    }
  } finally {
    reader.releaseLock?.()
  }

  // Flush any trailing bytes / final line without a newline terminator.
  buffer += decoder.decode()
  emit(buffer)
}

// --- Mood-First Search (feel-based discovery) ------------------------------
// Every route is mounted under /api/mood by the backend (see app/main.py). The
// frontend never sees the shape of the retrieval stack — only SearchResponse.

/** GET /api/mood/starters -> { starters: MoodStarter[] } (empty-state queries) */
export function moodStarters() {
  return request('/api/mood/starters')
}

/** GET /api/mood/sliders -> { sliders: {id,left,right}[] } (refine controls) */
export function moodSliders() {
  return request('/api/mood/sliders')
}

/** GET /api/mood/profiles -> { profiles: DemoListener[] } (demo persona picker) */
export function moodProfiles() {
  return request('/api/mood/profiles')
}

/**
 * POST /api/mood/search -> SearchResponse { mode: 'shelves'|'clarify'|'safety', ... }
 * @param {string} text free-text feeling
 * @param {string|null} [profileId] optional demo listener id
 */
export function moodSearch(text, profileId) {
  return request('/api/mood/search', {
    method: 'POST',
    body: { text, profile_id: profileId ?? null },
  })
}

/**
 * POST /api/mood/clarify -> SearchResponse (answer the one clarifying question)
 * @param {string} queryId
 * @param {string|null} optionId null = the user skipped
 */
export function moodClarify(queryId, optionId) {
  return request('/api/mood/clarify', {
    method: 'POST',
    body: { query_id: queryId, option_id: optionId ?? null },
  })
}

/**
 * POST /api/mood/refine -> SearchResponse with one re-ranked shelf.
 * Pure vector math on the backend — no LLM, sub-200ms. Send the shelf's own
 * target_axes and the raw slider positions (not pre-nudged axes).
 */
export function moodRefine(queryId, shelfId, currentAxes, sliderDeltas) {
  return request('/api/mood/refine', {
    method: 'POST',
    body: {
      query_id: queryId,
      shelf_id: shelfId,
      current_axes: currentAxes,
      slider_deltas: sliderDeltas,
    },
  })
}

/** GET /api/mood/episodes/{seriesId} -> episode window starting at the doorway */
export function moodEpisodes(seriesId, start = 1, limit = 12) {
  return request(
    `/api/mood/episodes/${encodeURIComponent(seriesId)}?start=${start}&limit=${limit}`,
  )
}

/** POST /api/mood/baseline -> { results } genre/keyword search (Lab only) */
export function moodBaseline(text, k = 3) {
  return request('/api/mood/baseline', { method: 'POST', body: { text, k } })
}

/** GET /api/mood/debug/{queryId} -> retrieval trace (Lab only) */
export function moodDebug(queryId) {
  return request(`/api/mood/debug/${encodeURIComponent(queryId)}`)
}

export const apiBaseUrl = BASE_URL
