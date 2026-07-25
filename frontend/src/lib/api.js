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

export const apiBaseUrl = BASE_URL
