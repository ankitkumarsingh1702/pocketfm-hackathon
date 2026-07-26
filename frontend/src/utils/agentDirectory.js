/**
 * Pure view-model mappers for the Agent Directory.
 *
 * Same contract as the other `utils/*` mappers: return `null` for missing
 * input, default arrays to `[]`, and hand the view a flat, render-ready shape.
 * No React, no side effects — trivially testable.
 */

/** Normalise the `/api/personas` payload into the two rosters (or null). */
export function toPersonaRoster(raw) {
  if (!raw) return null
  const experts = Array.isArray(raw.experts) ? raw.experts : []
  const audience = Array.isArray(raw.audience) ? raw.audience : []
  return {
    experts,
    audience,
    total: experts.length + audience.length,
    isEmpty: experts.length === 0 && audience.length === 0,
  }
}

/**
 * Group the activity feed by `source` (the agent identity) so each profile can
 * show its own live reads/writes. Expects the already-mapped activity view
 * (`toActivityView`), whose `events` are newest-first — so the first event seen
 * for a source is its most recent one.
 *
 * @returns {Record<string, {source, reads, writes, skips, total, last}>}
 */
export function groupActivityBySource(activityData) {
  const out = {}
  const events = (activityData && activityData.events) || []
  for (const e of events) {
    const key = e.source || 'unknown'
    const g =
      out[key] || (out[key] = { source: key, reads: 0, writes: 0, skips: 0, total: 0, last: null })
    if (e.op === 'read') g.reads += 1
    else if (e.op === 'write') g.writes += 1
    else g.skips += 1
    g.total += 1
    if (!g.last) g.last = e // events are newest-first, so first seen is latest
  }
  return out
}

/** Up-to-two-letter monogram for an agent/persona avatar. */
export function initialsFor(name) {
  const words = String(name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (words.length === 0) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

/** Compact relative time from a unix-seconds timestamp (mirrors DB / Memory). */
export function timeAgo(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - (ts || 0)))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}
