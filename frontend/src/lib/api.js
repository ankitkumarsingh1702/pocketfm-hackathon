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

  const res = await fetch(`${BASE_URL}/api/lenses/writers-room/stream`, {
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

export const apiBaseUrl = BASE_URL
