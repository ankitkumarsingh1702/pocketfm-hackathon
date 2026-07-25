import { useEffect, useRef } from 'react'

import { STAGE_SHORT } from '../../config/genre'

/** m:ss from the job's own elapsed seconds, so the log agrees with the clock. */
function stamp(seconds) {
  const total = Math.max(0, Math.round(seconds ?? 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/**
 * Extra facts worth showing for an event, drawn from its `detail`.
 *
 * Deliberately a whitelist rather than a dump of every key: the service sends
 * more than a reader wants mid-run, and an unfiltered object is noise, not
 * reassurance.
 */
function summarise(detail) {
  if (!detail) return null
  const bits = []
  if (detail.cached) bits.push('from cache')
  if (detail.characters) bits.push(`${detail.characters.toLocaleString()} characters`)
  if (Array.isArray(detail.roles) && detail.roles.length) {
    bits.push(`${detail.roles.length} roles: ${detail.roles.map((r) => r.name).join(', ')}`)
  }
  if (detail.edges != null && detail.check !== 'links') bits.push(`${detail.edges} causal edges`)
  if (detail.words) bits.push(`${detail.words} words`)
  if (Array.isArray(detail.beats) && detail.beats.length && detail.phase) {
    bits.push(`beats ${detail.beats.map((b) => b.id).join(', ')}`)
  }
  if (Array.isArray(detail.complaints) && detail.complaints.length) {
    bits.push(`${detail.complaints.length} to fix`)
  }
  if (detail.fidelity != null) bits.push(`${Math.round(detail.fidelity * 100)}% of the plot survived`)
  return bits.length ? bits.join(' · ') : null
}

/**
 * Everything the pipeline has done, in order, with the newest at the bottom.
 *
 * A percentage says a job is alive; it does not say what it is doing. Over five
 * to eight minutes that difference is the whole experience, so each step the
 * service reports is kept and shown rather than overwriting the last one.
 *
 * Not a live region: the current step is already announced by the status header
 * above, and re-reading a growing log on every poll would be hostile.
 */
export default function ActivityLog({ events }) {
  const scroller = useRef(null)
  const count = events?.length ?? 0

  // Follow the tail, the way a build log does.
  useEffect(() => {
    const node = scroller.current
    if (node) node.scrollTop = node.scrollHeight
  }, [count])

  if (!count) return null

  return (
    <div>
      <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
        Activity
      </div>
      <ol
        ref={scroller}
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          maxHeight: 260,
          overflowY: 'auto',
          borderTop: '1px solid var(--border)',
        }}
      >
        {events.map((event, index) => {
          const latest = index === count - 1
          const extra = summarise(event.detail)
          return (
            <li
              key={event.seq}
              style={{
                display: 'flex',
                gap: 12,
                padding: '9px 0',
                borderBottom: '1px solid var(--border)',
                alignItems: 'baseline',
              }}
            >
              <span
                className="font-mono-num"
                style={{ fontSize: 12, color: 'var(--dim)', minWidth: 38 }}
              >
                {stamp(event.at)}
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--muted)',
                  minWidth: 58,
                  textTransform: 'uppercase',
                  letterSpacing: 'var(--tracking-label)',
                }}
              >
                {STAGE_SHORT[event.stage] ?? event.stage}
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span
                  style={{
                    fontSize: 14,
                    lineHeight: 1.5,
                    color: latest ? 'var(--ink)' : 'var(--muted)',
                    fontWeight: latest ? 600 : 400,
                  }}
                >
                  {event.note}
                </span>
                {extra && (
                  <span
                    style={{ display: 'block', fontSize: 12.5, color: 'var(--dim)', marginTop: 2 }}
                  >
                    {extra}
                  </span>
                )}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
