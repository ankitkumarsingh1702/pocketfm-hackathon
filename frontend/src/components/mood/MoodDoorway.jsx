import { useCallback, useEffect, useState } from 'react'

import * as api from '../../lib/api'
import { Button, Icon } from '../primitives'

/**
 * The doorway — the episode window that BEGINS where the shelf pointed.
 *
 * This is arc-level indexing surviving all the way into the UI. Landing "Start
 * at Ep 34" at the top of a 212-episode list would quietly reduce the whole
 * recommendation back to a series title in the last inch of the journey, so the
 * fetch defaults to the entry point rather than episode 1. Earlier episodes stay
 * reachable — the control below refetches from 1 — they are simply not where you
 * land.
 */
function minutes(seconds) {
  return `${Math.max(1, Math.round((seconds || 0) / 60))} min`
}

export default function MoodDoorway({ playing, onBack }) {
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
      } catch (e) {
        setError(e.message || 'Could not reach the catalog.')
      } finally {
        setLoading(false)
      }
    },
    [playing?.seriesId],
  )

  useEffect(() => {
    load(start)
  }, [load, start])

  const lastNumber = data?.episodes?.length
    ? data.episodes[data.episodes.length - 1].number
    : null

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 720 }}>
      <div>
        <Button variant="ghost" size="sm" onClick={onBack}>
          <Icon name="arrowLeft" size={16} />
          Back to shelves
        </Button>
      </div>

      <header>
        <h3 style={{ margin: 0, fontSize: 22, fontWeight: 600, color: 'var(--ink)' }}>
          {data?.series_title || playing.seriesTitle}
        </h3>
        <p
          style={{
            margin: '6px 0 0',
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--accent-text-sm)',
          }}
        >
          {playing.entryLabel}
        </p>
      </header>

      {loading && (
        <div style={{ fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
          Loading episodes…
        </div>
      )}

      {error && (
        <div
          role="alert"
          style={{
            padding: '14px 16px',
            border: '1px solid var(--accent-line)',
            background: 'var(--accent-soft)',
            borderRadius: 'var(--radius-md)',
            fontSize: 14,
            color: 'var(--ink)',
            display: 'flex',
            gap: 12,
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <span>{error}</span>
          <Button variant="secondary" size="sm" onClick={() => load(start)}>
            Retry
          </Button>
        </div>
      )}

      {data && (
        <>
          {start > 1 && (
            <Button variant="secondary" size="sm" onClick={() => setStart(1)}>
              Show earlier episodes (1–{start - 1})
            </Button>
          )}

          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 8 }}>
            {data.episodes.map((episode) => (
              <li
                key={episode.number}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 14,
                  background: episode.is_arc_start ? 'var(--accent-soft)' : 'var(--canvas)',
                  border: `1px solid ${
                    episode.is_arc_start ? 'var(--accent-line)' : 'var(--border)'
                  }`,
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                }}
              >
                <span
                  className="font-mono-num"
                  style={{
                    minWidth: 30,
                    fontSize: 13,
                    color: episode.is_arc_start ? 'var(--accent-text-sm)' : 'var(--muted)',
                  }}
                >
                  {episode.number}
                </span>

                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 15, color: 'var(--ink)' }}>
                    {episode.title}
                  </span>
                  <span
                    style={{ display: 'block', fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}
                  >
                    {minutes(episode.duration_sec)}
                    {episode.is_arc_start ? ' · the arc starts here' : ''}
                  </span>
                </span>

                {/* A missing file is a content gap, not a reason to hide the
                    episode. Show it, disable play, and say why. */}
                <Button variant="secondary" size="sm" disabled={!episode.audio_url}>
                  {episode.audio_url ? 'Play' : 'No audio'}
                </Button>
              </li>
            ))}
          </ol>

          {data.has_more && lastNumber != null && (
            <Button variant="secondary" size="sm" onClick={() => setStart(lastNumber + 1)}>
              More episodes ({data.total - lastNumber} left)
            </Button>
          )}
        </>
      )}
    </section>
  )
}
