// Fetch client for the story genre converter (backend/story-genre-convertor).
//
// Separate from lib/api.js on purpose: this is a different service, on a
// different origin, with a different lifecycle. Conversions take five to eight
// minutes, so every mutating call returns a job id and the client polls.
//
// The base path is same-origin `/sgc` by default, which the Vite dev proxy
// forwards to Cloud Run with an Authorization header attached (vite.config.js).
// Set VITE_SGC_URL to call the service directly — that only works once it has a
// public `allUsers` invoker binding.

import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS } from '../config/genre'

const BASE_URL = (import.meta.env.VITE_SGC_URL ?? '/sgc').replace(/\/+$/, '')

/** Thrown when the proxy or Cloud Run rejects us rather than the app failing. */
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
    throw new Error('Could not reach the converter. Is the dev server running?')
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
        'The converter rejected the request. The hardcoded identity token has ' +
          'probably expired — they last about an hour. Refresh it with ' +
          '`npm run sgc:token` and restart the dev server.',
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
 * Poll a job until it finishes, calling `onUpdate` with every fresh snapshot.
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
  const deadline = Date.now() + POLL_TIMEOUT_MS

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
      const timer = setTimeout(resolve, POLL_INTERVAL_MS)
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
