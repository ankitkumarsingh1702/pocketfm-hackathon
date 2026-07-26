/**
 * Lab — dev-only surface, reachable at ?dev.
 *
 * Two things that must exist for the demo but must NOT sit in the primary flow:
 *
 *   1. The genre/keyword baseline, side by side with mood-first on the SAME
 *      query. Live, not a screenshot — it runs on whatever a judge types.
 *      Shipping genre search as a real tab would concede the argument the
 *      product exists to win.
 *
 *   2. /debug — what retrieval actually did: blocked (contraindicated) items,
 *      pool sizes, per-shelf latency. The traps the baseline surfaces at rank 1
 *      are the same rows this trace shows as blocked.
 */

import { useEffect, useState } from 'react'

import * as api from '../../lib/api'
import { Button } from '../primitives'

function SectionLabel({ children }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, marginBottom: 12 }}>
      {children}
    </div>
  )
}

export default function MoodLab({ queryId, lastText, onBack }) {
  const [text, setText] = useState(lastText || '')
  const [baseline, setBaseline] = useState(null)
  const [mood, setMood] = useState(null)
  const [debug, setDebug] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!queryId) return
    api.moodDebug(queryId).then(setDebug).catch(() => setDebug(null))
  }, [queryId])

  async function compare() {
    if (!text.trim()) return
    setBusy(true)
    try {
      const [b, m] = await Promise.all([api.moodBaseline(text, 3), api.moodSearch(text)])
      setBaseline(b.results || [])
      setMood(m.shelves || [])
    } finally {
      setBusy(false)
    }
  }

  const card = (borderTrap) => ({
    background: 'var(--surface)',
    border: `1px solid ${borderTrap ? 'var(--danger)' : 'var(--border)'}`,
    borderRadius: 'var(--radius-md)',
    padding: '12px 14px',
    marginBottom: 8,
  })

  return (
    <div style={{ maxWidth: 920 }}>
      <button
        onClick={onBack}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--muted)',
          fontSize: 14,
          fontFamily: 'var(--font-sans)',
          padding: 0,
          marginBottom: 16,
          cursor: 'pointer',
        }}
      >
        ← Back to search
      </button>

      <div style={{ display: 'flex', gap: 10, marginBottom: 28, maxWidth: 560 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && compare()}
          placeholder="Same query, both systems"
          style={{
            flex: 1,
            background: 'var(--surface-raised)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--ink)',
            padding: '10px 14px',
            fontSize: 15,
            fontFamily: 'var(--font-sans)',
            outline: 'none',
          }}
        />
        <Button variant="primary" onClick={compare} disabled={busy}>
          {busy ? '…' : 'Compare'}
        </Button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 24,
          alignItems: 'start',
        }}
      >
        <div>
          <SectionLabel>Genre / keyword search</SectionLabel>
          {(baseline || []).map((h) => (
            <div key={h.content_id} style={card(h.is_trap)}>
              <div style={{ fontSize: 15, color: 'var(--ink)' }}>{h.series_title}</div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4, lineHeight: 1.5 }}>
                {h.snippet}
              </div>
              {h.is_trap && (
                <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 6, fontWeight: 600 }}>
                  ✕ contraindicated for this listener
                </div>
              )}
            </div>
          ))}
          {baseline && !baseline.length && (
            <div style={{ fontSize: 14, color: 'var(--muted)' }}>No matches.</div>
          )}
        </div>

        <div>
          <SectionLabel>Mood-first</SectionLabel>
          {(mood || []).map((s) => (
            <div key={s.id} style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--accent-text-sm)',
                  fontWeight: 600,
                  marginBottom: 6,
                }}
              >
                {s.label}
              </div>
              {s.results.slice(0, 2).map((r) => (
                <div key={r.content_id} style={card(false)}>
                  <div style={{ fontSize: 15, color: 'var(--ink)' }}>{r.series_title}</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
                    {r.entry_label}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {debug && (
        <div style={{ marginTop: 32 }}>
          <SectionLabel>Retrieval trace</SectionLabel>
          <div
            className="font-mono-num"
            style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.9 }}
          >
            <div>
              profile: {debug.profile || 'anonymous'} · blocked by contraindication:{' '}
              {(debug.blocked || []).length}
            </div>
            {(debug.shelves || []).map((s) => (
              <div key={s.destination}>
                {s.destination}: pool {s.pool_size} · dropped {s.dropped_by_reranker} · entry
                swaps {s.entry_swaps} · {s.latency_ms}ms
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
