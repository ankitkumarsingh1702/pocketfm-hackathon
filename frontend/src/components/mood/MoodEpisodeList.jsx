/**
 * The doorway — GET /api/mood/episodes/{series_id}?start={entry_episode}.
 *
 * Fetches the window that BEGINS at the entry point the shelf promised, not
 * episode 1. That default is arc-level indexing surviving all the way into the
 * UI: landing "Start at Ep 34" at the top of a 212-episode list would quietly
 * reduce the recommendation back to a plain series title. Earlier episodes stay
 * reachable — the "Earlier episodes" control refetches from 1 — they just are
 * not where you land.
 */

import { useCallback, useEffect, useState } from 'react'

import * as api from '../../lib/api'
import { Button } from '../primitives'

function minutes(seconds) {
  return `${Math.max(1, Math.round((seconds || 0) / 60))} min`
}

export default function MoodEpisodeList({ playing, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [start, setStart] = useState(playing?.entryEpisode ?? 1)

  useEffect(() => {
    setStart(playing?.entryEpisode ?? 1)
  }, [playing?.seriesId, playing?.entryEpisode])

  const load = useCallback(
    async (from) => {
      if (!playing?.seriesId) return
      setLoading(true)
      setError(null)
      try {
        const json = await api.moodEpisodes(playing.seriesId, from, 12)
        if (json.error) setError(json.error)
        else setData(json)
      } catch {
        setError("Couldn't reach the catalog.")
      } finally {
        setLoading(false)
      }
    },
    [playing?.seriesId],
  )

  useEffect(() => {
    load(start)
  }, [load, start])

  if (!playing?.seriesId) {
    return (
      <div style={{ padding: '48px 0', color: 'var(--muted)', fontSize: 14 }}>
        Nothing playing yet. Pick something from a shelf.
      </div>
    )
  }

  const pager = {
    width: '100%',
    background: 'var(--surface-raised)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--muted)',
    padding: '11px 12px',
    fontSize: 13,
    fontFamily: 'var(--font-sans)',
    cursor: 'pointer',
  }

  return (
    <div style={{ paddingTop: 8, maxWidth: 680 }}>
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
        ← Back to shelves
      </button>

      <h2 style={{ fontSize: 'var(--text-h2)', color: 'var(--ink)', margin: '0 0 4px' }}>
        {data?.series_title || playing.seriesTitle}
      </h2>
      <div
        style={{
          fontSize: 13,
          color: 'var(--accent-text-sm)',
          fontWeight: 600,
          marginBottom: 20,
        }}
      >
        {playing.entryLabel}
      </div>

      {loading && <div style={{ fontSize: 14, color: 'var(--muted)' }}>Loading episodes…</div>}

      {error && (
        <div style={{ fontSize: 14, color: 'var(--ink)', marginBottom: 12 }}>
          {error}{' '}
          <button
            onClick={() => load(start)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent-text-sm)',
              fontWeight: 600,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {data && (
        <>
          {start > 1 && (
            <button onClick={() => setStart(1)} style={{ ...pager, marginBottom: 10 }}>
              Earlier episodes (1–{start - 1})
            </button>
          )}

          <div style={{ display: 'grid', gap: 8 }}>
            {data.episodes.map((ep) => (
              <div
                key={ep.number}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 14,
                  background: 'var(--surface)',
                  border: ep.is_arc_start
                    ? '1.5px solid var(--accent)'
                    : '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                }}
              >
                <div
                  className="font-mono-num"
                  style={{
                    fontSize: 13,
                    color: ep.is_arc_start ? 'var(--accent-text-sm)' : 'var(--muted)',
                    minWidth: 32,
                  }}
                >
                  {ep.number}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, color: 'var(--ink)' }}>{ep.title}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>
                    {minutes(ep.duration_sec)}
                    {ep.is_arc_start ? ' · the arc starts here' : ''}
                  </div>
                </div>
                {/* A missing file is a content gap, not a reason to hide the
                    episode. Show it, disable play, say why. */}
                <Button
                  variant={ep.audio_url ? 'secondary' : 'ghost'}
                  size="sm"
                  disabled={!ep.audio_url}
                >
                  {ep.audio_url ? 'Play' : 'No audio'}
                </Button>
              </div>
            ))}
          </div>

          {data.has_more && data.episodes.length > 0 && (
            <button
              onClick={() => setStart(data.episodes[data.episodes.length - 1].number + 1)}
              style={{ ...pager, marginTop: 10 }}
            >
              More episodes ({data.total - data.episodes[data.episodes.length - 1].number} left)
            </button>
          )}
        </>
      )}
    </div>
  )
}
