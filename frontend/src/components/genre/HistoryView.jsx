import { useCallback, useEffect, useState } from 'react'

import { getHistoryRecord, listHistory } from '../../lib/genreApi'
import { EmptyState, LoadingState } from '../StateViews'
import { Button, Tabs } from '../primitives'
import { useToast } from '../toast/useToast'
import FidelityReport from './FidelityReport'
import RewriteView from './RewriteView'
import SkeletonView from './SkeletonView'

const RECORD_TABS = [
  { id: 'rewrite', label: 'Rewrite' },
  { id: 'fidelity', label: 'Fidelity' },
  { id: 'skeleton', label: 'Plot skeleton' },
  { id: 'source', label: 'Source story' },
]

/** Epoch seconds -> "12 Jul, 14:05" in the viewer's locale. */
function when(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function pct(fidelity) {
  return fidelity == null ? '—' : `${Math.round(fidelity * 100)}%`
}

/** Beats the verifier could not find on the page, for the skeleton table. */
function droppedBeats(detail) {
  if (!detail) return []
  return [
    ...new Set([...(detail.missing_load_bearing ?? []), ...Object.keys(detail.beat_notes ?? {})]),
  ]
}

/** One conversion: a summary row that expands into the full record. */
function HistoryEntry({ entry, open, record, fetching, view, setView, onToggle }) {
  return (
    <li
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        listStyle: 'none',
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        style={{
          width: '100%',
          textAlign: 'left',
          background: open ? 'var(--surface)' : 'var(--canvas)',
          border: 'none',
          padding: '14px 16px',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--ink)',
              textTransform: 'capitalize',
            }}
          >
            {entry.genre}
          </span>
          <span
            className="font-mono-num"
            style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-text-sm)' }}
          >
            {pct(entry.fidelity)} fidelity
          </span>
          <span style={{ flex: 1 }} />
          <span className="font-mono-num" style={{ fontSize: 12.5, color: 'var(--muted)' }}>
            {entry.words != null && `${entry.words.toLocaleString()} words · `}
            {when(entry.created_at)}
          </span>
        </span>
        {(entry.logline || entry.excerpt) && (
          <span
            style={{
              fontSize: 13.5,
              lineHeight: 1.5,
              color: 'var(--muted)',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {entry.logline || entry.excerpt}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            borderTop: '1px solid var(--border)',
            padding: '18px 16px 24px',
            display: 'flex',
            flexDirection: 'column',
            gap: 24,
          }}
        >
          {fetching && (
            <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
              Loading the full record…
            </p>
          )}
          {record && (
            <>
              <Tabs tabs={RECORD_TABS} active={view} onChange={setView} />
              {view === 'rewrite' && (
                <RewriteView text={record.rewritten} genre={record.genre} />
              )}
              {view === 'fidelity' && (
                <FidelityReport
                  detail={record.detail}
                  skeleton={record.source_skeleton}
                  words={record.words}
                  seconds={record.seconds}
                />
              )}
              {view === 'skeleton' && (
                <SkeletonView
                  skeleton={record.source_skeleton}
                  dropped={droppedBeats(record.detail)}
                />
              )}
              {view === 'source' && (
                <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <span className="font-mono-num" style={{ fontSize: 13, color: 'var(--muted)' }}>
                    {record.chars?.toLocaleString()} characters, as submitted
                  </span>
                  <article
                    style={{
                      maxWidth: '68ch',
                      fontSize: 15.5,
                      lineHeight: 1.75,
                      color: 'var(--ink)',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {record.source_text}
                  </article>
                </section>
              )}
            </>
          )}
        </div>
      )}
    </li>
  )
}

/**
 * Everything this service has converted: one row per story+genre, expanding
 * into the full record — the story that went in, the skeleton the pipeline
 * extracted, the rewrite that came out, and how much of the plot survived.
 *
 * Fetches whenever the tab is shown and again when `refreshKey` changes (the
 * converter passes its latest result, so a conversion that just finished shows
 * up without a manual refresh).
 */
export default function HistoryView({ active, refreshKey }) {
  const toast = useToast()
  const [entries, setEntries] = useState(null) // null = never loaded
  const [loading, setLoading] = useState(false)
  const [openId, setOpenId] = useState(null)
  const [records, setRecords] = useState({})
  const [fetchingId, setFetchingId] = useState(null)
  const [view, setView] = useState('rewrite')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setEntries(await listHistory())
    } catch (err) {
      if (err.name !== 'AbortError') {
        toast.error(`Could not load the conversion history. ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (active) load()
  }, [active, load])

  // A conversion finishing refreshes the list even before the tab is opened.
  useEffect(() => {
    if (refreshKey) load()
  }, [refreshKey, load])


  const toggle = async (id) => {
    if (openId === id) {
      setOpenId(null)
      return
    }
    setOpenId(id)
    setView('rewrite')
    if (records[id]) return
    setFetchingId(id)
    try {
      const record = await getHistoryRecord(id)
      setRecords((current) => ({ ...current, [id]: record }))
    } catch (err) {
      toast.error(`Could not load that conversion. ${err.message}`)
      setOpenId((current) => (current === id ? null : current))
    } finally {
      setFetchingId((current) => (current === id ? null : current))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div className="label-upper" style={{ fontSize: 11, marginBottom: 4 }}>
            Stored conversions{entries ? ` · ${entries.length}` : ''}
          </div>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', lineHeight: 1.6 }}>
            Every finished conversion, kept by the service for the life of its instance.
          </p>
        </div>
        <span style={{ flex: 1 }} />
        <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>

      {entries === null && loading && <LoadingState label="Reading the conversion history…" />}

      {entries && entries.length === 0 && (
        <EmptyState
          title="No conversions yet"
          hint="Finished conversions land here automatically — run one from the Convert tab and come back."
        />
      )}

      {entries && entries.length > 0 && (
        <ul style={{ margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {entries.map((entry) => (
            <HistoryEntry
              key={entry.id}
              entry={entry}
              open={openId === entry.id}
              record={records[entry.id]}
              fetching={fetchingId === entry.id}
              view={view}
              setView={setView}
              onToggle={() => toggle(entry.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
