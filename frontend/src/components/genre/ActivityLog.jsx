import { useEffect, useRef, useState } from 'react'

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

/** How many steps stay visible when the log is folded to its tail. */
const TAIL = 3

/**
 * What the pipeline is doing, as a live tail with the full story one click
 * away.
 *
 * A percentage says a job is alive; it does not say what it is doing. Over
 * five to eight minutes that difference is the whole experience — so the last
 * few steps are always on screen, ticking over as the service reports them,
 * and "Show all" unfolds the complete, ordered log for anyone who wants the
 * blow-by-blow without making everyone scroll past it.
 *
 * Not a live region: the current step is already announced by the status
 * header above, and re-reading a growing log on every poll would be hostile.
 */
export default function ActivityLog({ events }) {
  const scroller = useRef(null)
  const [showAll, setShowAll] = useState(false)
  const count = events?.length ?? 0

  // Follow the tail when the full log is open, the way a build log does.
  useEffect(() => {
    const node = scroller.current
    if (node && showAll) node.scrollTop = node.scrollHeight
  }, [count, showAll])

  if (!count) return null

  const visible = showAll ? events : events.slice(-TAIL)
  const hidden = count - visible.length

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 8,
        }}
      >
        <span className="label-upper" style={{ fontSize: 11 }}>
          Activity · {count} {count === 1 ? 'step' : 'steps'}
        </span>
        {count > TAIL && (
          <button
            type="button"
            onClick={() => setShowAll((value) => !value)}
            aria-expanded={showAll}
            style={{
              background: 'none',
              border: 'none',
              padding: '4px 0',
              fontSize: 12.5,
              fontWeight: 600,
              color: 'var(--ink)',
              textDecoration: 'underline',
              textUnderlineOffset: 3,
              cursor: 'pointer',
            }}
          >
            {showAll ? 'Show recent only' : `Show all ${count} steps`}
          </button>
        )}
      </div>

      {!showAll && hidden > 0 && (
        <div
          aria-hidden="true"
          style={{
            fontSize: 11.5,
            color: 'var(--dim)',
            padding: '2px 0 4px',
            borderTop: '1px solid var(--border)',
          }}
        >
          ⋯ {hidden} earlier {hidden === 1 ? 'step' : 'steps'}
        </div>
      )}

      <ol
        ref={scroller}
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          maxHeight: showAll ? 260 : 'none',
          overflowY: showAll ? 'auto' : 'visible',
          borderTop: showAll || hidden === 0 ? '1px solid var(--border)' : 'none',
        }}
      >
        {visible.map((event, index) => {
          const latest = index === visible.length - 1
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
