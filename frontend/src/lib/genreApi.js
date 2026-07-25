// Fetch client for the story genre converter (backend/story-genre-convertor).
//
// Separate from lib/api.js on purpose: this is a different service, on a
// different origin, with a different lifecycle. Conversions take five to eight
// minutes, so every mutating call returns a job id and the client polls.
//
// Calls go straight to the convertor's own Cloud Run origin, in dev and in
// production alike. The service is deployed `--allow-unauthenticated` and
// answers CORS with `*`, so the browser reaches it directly — no dev proxy and
// no credential in the client. Point VITE_SGC_URL at http://localhost:8080 to
// develop against a local `uv run uvicorn api:app`.

import {
  POLL_FAST_AFTER_MS,
  POLL_INTERVAL_EARLY_MS,
  POLL_INTERVAL_LATE_MS,
  POLL_TIMEOUT_MS,
} from '../config/genre'

/** Deployed by .github/workflows/deploy-backend.yml (story-genre-convertor). */
const SGC_URL = 'https://story-genre-convertor-v4c7wg52ia-uc.a.run.app'

const BASE_URL = (import.meta.env.VITE_SGC_URL || SGC_URL).replace(/\/+$/, '')

/** Thrown when Cloud Run rejects us rather than the app failing. */
export class AuthError extends Error {}

async function request(path, { method = 'GET', body, signal } = {}) {
  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error('Could not reach the converter. Check your connection and retry.')
  }

  if (!res.ok) {
    const raw = await res.text().catch(() => '')
    let detail = `${res.status} ${res.statusText}`
    if (raw) {
      try {
        const data = JSON.parse(raw)
        detail = data && data.detail ? data.detail : raw
      } catch {
        detail = raw
      }
    }
    if (res.status === 401 || res.status === 403) {
      throw new AuthError(
        'The converter rejected the request. The service should be public — its ' +
          '`allUsers` invoker binding has probably been removed. Redeploy it from ' +
          'the deploy backend workflow.',
      )
    }
    throw new Error(detail)
  }

  return res.json()
}

/** GET /health -> { status, genres[], jobs: { tracked, running } } */
export function health(signal) {
  return request('/health', { signal })
}

/** GET /api/genres -> [{ name, premise, pacing, taboo_moves[] }] */
export function listGenres(signal) {
  return request('/api/genres', { signal })
}

/** POST /api/extract -> Job. Skeleton only; no rewrite, no spend on prose. */
export function submitExtract(text, signal) {
  return request('/api/extract', { method: 'POST', body: { text }, signal })
}

/** POST /api/convert -> Job. The full extract -> rewrite -> verify pipeline. */
export function submitConvert(text, genre, signal) {
  return request('/api/convert', { method: 'POST', body: { text, genre }, signal })
}

/** GET /api/jobs/{id} -> Job */
export function getJob(id, signal) {
  return request(`/api/jobs/${encodeURIComponent(id)}`, { signal })
}

/**
 * How long to wait before the next poll, given how long we have been watching.
 *
 * Slow while the job cannot plausibly be finished, then faster once it can —
 * see POLL_INTERVAL_EARLY_MS in config/genre.js for why that way round.
 *
 * @param {number} watchedMs  milliseconds since polling began
 */
function pollDelay(watchedMs) {
  return watchedMs < POLL_FAST_AFTER_MS ? POLL_INTERVAL_EARLY_MS : POLL_INTERVAL_LATE_MS
}

/**
 * Poll a job until it finishes, calling `onUpdate` with every fresh snapshot.
 *
 * The first snapshot is fetched immediately; every later one waits out
 * `pollDelay`, so the UI still gets an instant first reading.
 *
 * Resolves with the terminal job on `done`, rejects on `error` or timeout.
 * Aborting via `signal` stops the polling only — the job keeps running on the
 * server, which is why the UI says so rather than claiming it cancelled.
 *
 * @param {string} id                        job id from a submit call
 * @param {(job: object) => void} onUpdate   called on each poll
 * @param {AbortSignal} [signal]             stop watching
 */
export async function pollJob(id, onUpdate, signal) {
  const started = Date.now()
  const deadline = started + POLL_TIMEOUT_MS

  for (;;) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')

    const job = await getJob(id, signal)
    onUpdate?.(job)

    if (job.status === 'done') return job
    if (job.status === 'error') throw new Error(job.error || 'The conversion failed.')

    if (Date.now() > deadline) {
      throw new Error(
        `Gave up watching job ${id} after 20 minutes. It may still be running — ` +
          'the service keeps jobs in memory until it restarts.',
      )
    }

    await new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, pollDelay(Date.now() - started))
      signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timer)
          reject(new DOMException('Aborted', 'AbortError'))
        },
        { once: true },
      )
    })
  }
}

export const genreApiBaseUrl = BASE_URL
