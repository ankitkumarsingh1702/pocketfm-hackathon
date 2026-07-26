import { useEffect, useState } from 'react'

import * as api from '../../lib/api'
import { Button, Disclosure } from '../primitives'

/**
 * The comparison, and the retrieval trace.
 *
 * Runs the SAME query through genre/keyword search and through mood search, live
 * — not a screenshot, so it runs on whatever anyone types. Genre search returns
 * the trap arcs near the top precisely because they are lexically perfect and
 * emotionally wrong, which is the argument this whole lens exists to make.
 *
 * Folded shut by default and placed last. Shipping a genre search as a visible,
 * equal surface would concede the argument; keeping it as a collapsed comparison
 * makes the point without reintroducing the thing being replaced.
 */
export default function MoodBaselineLab({ queryId, lastText }) {
  const [text, setText] = useState(lastText || '')
  const [baseline, setBaseline] = useState(null)
  const [mood, setMood] = useState(null)
  const [trace, setTrace] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Follow the live query. The point of this panel is "the SAME query through
  // both systems", so opening it after a search must not present an empty box
  // that has to be retyped — that is exactly the friction that stops anyone
  // from running the comparison.
  useEffect(() => {
    if (lastText) setText(lastText)
  }, [lastText])

  async function compare() {
    const query = (text || lastText || '').trim()
    if (!query) return
    setBusy(true)
    setError(null)
    try {
      const [b, m] = await Promise.all([api.moodBaseline(query, 3), api.moodSearch(query)])
      setBaseline(b.results || [])
      setMood(m.shelves || [])
      if (queryId) {
        setTrace(await api.moodDebug(queryId).catch(() => null))
      }
    } catch (e) {
      setError(e.message || 'Comparison failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section style={{ borderTop: '1px solid var(--border)' }}>
      <Disclosure
        summary={
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>
              Compare against genre search
            </span>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
              same query, both systems — plus what retrieval blocked
            </span>
          </span>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingBottom: 8 }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch', lineHeight: 1.6 }}>
            Keyword search over the same catalog. It ranks on words, so an
            emotionally wrong arc that happens to share the query&apos;s vocabulary
            comes back near the top — which is what discovery looks like today.
          </p>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', maxWidth: 560 }}>
            <label htmlFor="mood-lab-query" className="label-upper" style={{ fontSize: 11, width: '100%' }}>
              Query
            </label>
            <input
              id="mood-lab-query"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && compare()}
              placeholder="Same query, both systems"
              style={{
                flex: 1,
                minWidth: 200,
                minHeight: 44,
                background: 'var(--canvas)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--ink)',
                padding: '0 14px',
                fontFamily: 'var(--font-sans)',
                fontSize: 15,
              }}
            />
            <Button variant="secondary" onClick={compare} disabled={busy}>
              {busy ? 'Comparing…' : 'Compare'}
            </Button>
          </div>

          {error && (
            <div role="alert" style={{ fontSize: 14, color: 'var(--accent-text-sm)' }}>
              {error}
            </div>
          )}

          {(baseline || mood) && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                gap: 24,
                alignItems: 'start',
              }}
            >
              <div>
                <div className="label-upper" style={{ fontSize: 11, marginBottom: 12 }}>
                  Genre / keyword search
                </div>
                {(baseline || []).map((hit) => (
                  <div
                    key={hit.content_id}
                    style={{
                      background: hit.is_trap ? 'var(--accent-soft)' : 'var(--canvas)',
                      border: `1px solid ${hit.is_trap ? 'var(--accent-line)' : 'var(--border)'}`,
                      borderRadius: 'var(--radius-md)',
                      padding: '12px 14px',
                      marginBottom: 8,
                    }}
                  >
                    <div style={{ fontSize: 15, color: 'var(--ink)' }}>{hit.series_title}</div>
                    <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4, lineHeight: 1.5 }}>
                      {hit.snippet}
                    </div>
                    {hit.is_trap && (
                      <div
                        style={{
                          fontSize: 12.5,
                          fontWeight: 600,
                          color: 'var(--accent-text-sm)',
                          marginTop: 8,
                        }}
                      >
                        ✕ emotionally wrong for this listener
                      </div>
                    )}
                  </div>
                ))}
                {baseline && !baseline.length && (
                  <div style={{ fontSize: 14, color: 'var(--muted)' }}>No matches.</div>
                )}
              </div>

              <div>
                <div className="label-upper" style={{ fontSize: 11, marginBottom: 12 }}>
                  Mood-first
                </div>
                {(mood || []).map((shelf) => (
                  <div key={shelf.id} style={{ marginBottom: 16 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--ink)',
                        marginBottom: 6,
                      }}
                    >
                      {shelf.label}
                    </div>
                    {shelf.results.slice(0, 2).map((result) => (
                      <div
                        key={result.content_id}
                        style={{
                          background: 'var(--canvas)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                          padding: '12px 14px',
                          marginBottom: 6,
                        }}
                      >
                        <div style={{ fontSize: 15, color: 'var(--ink)' }}>
                          {result.series_title}
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
                          {result.entry_label}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
                {mood && !mood.length && (
                  <div style={{ fontSize: 14, color: 'var(--muted)' }}>
                    No shelves — the query resolved to a question or the safety path.
                  </div>
                )}
              </div>
            </div>
          )}

          {trace && (
            <div>
              <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
                Retrieval trace
              </div>
              <div
                className="font-mono-num"
                style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.9 }}
              >
                <div>
                  listener: {trace.profile || 'anonymous'} · blocked before scoring:{' '}
                  {(trace.blocked || []).length}
                </div>
                {(trace.shelves || []).map((shelf) => (
                  <div key={shelf.destination}>
                    {shelf.destination}: pool {shelf.pool_size} · dropped{' '}
                    {shelf.dropped_by_reranker} · entry swaps {shelf.entry_swaps} ·{' '}
                    {shelf.latency_ms}ms
                  </div>
                ))}
              </div>
              {(trace.blocked || []).length > 0 && (
                <p
                  style={{
                    margin: '10px 0 0',
                    fontSize: 13,
                    color: 'var(--muted)',
                    maxWidth: '64ch',
                    lineHeight: 1.6,
                  }}
                >
                  Those blocked arcs are the same ones genre search puts near the
                  top. They are masked before anything is scored, so no amount of
                  lexical similarity can talk them back in.
                </p>
              )}
            </div>
          )}
        </div>
      </Disclosure>
    </section>
  )
}
