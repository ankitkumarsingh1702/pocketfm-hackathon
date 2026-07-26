import { useCallback, useEffect, useState } from 'react'

import * as api from '../../lib/api'
import { Button, Icon } from '../primitives'

/**
 * The doorway — the song window that BEGINS where the shelf pointed.
 *
 * This is arc-level indexing surviving all the way into the UI. Landing "Start
 * at track 34" at the top of a 200-song collection would quietly reduce the
 * whole recommendation back to a collection title in the last inch of the
 * journey, so the fetch defaults to the entry point rather than track 1. Earlier
 * tracks stay reachable — the control below refetches from 1 — they are simply
 * not where you land.
 *
 * Each track carries a real audio URL, so tapping Play opens an inline player
 * rather than a dead button: the catalog is playable, and the doorway is where
 * you actually listen.
 */
function minutes(seconds) {
  return `${Math.max(1, Math.round((seconds || 0) / 60))} min`
}

/** Pull the YouTube video id out of a watch / share / embed URL. */
function youtubeId(url) {
  if (!url) return null
  try {
    const u = new URL(url)
    if (u.searchParams.get('v')) return u.searchParams.get('v')
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1) || null
    const parts = u.pathname.split('/').filter(Boolean)
    const i = parts.indexOf('embed')
    if (i >= 0 && parts[i + 1]) return parts[i + 1]
  } catch {
    /* not a URL — nothing to embed */
  }
  return null
}

/** The inline player for the tapped track. YouTube when we can embed it. */
function NowPlaying({ track, onClose }) {
  const id = youtubeId(track.audio_url)
  return (
    <div
      style={{
        border: '1px solid var(--accent-line)',
        background: 'var(--accent-soft)',
        borderRadius: 'var(--radius-md)',
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="label-upper" style={{ fontSize: 10, color: 'var(--accent-text-sm)' }}>
            Now playing · track {track.number}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
            {track.title}
          </div>
          {track.synopsis && (
            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>
              {track.synopsis}
            </div>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <Icon name="close" size={16} />
          Close
        </Button>
      </div>

      {id ? (
        <div
          style={{
            position: 'relative',
            width: '100%',
            aspectRatio: '16 / 9',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            background: '#000',
          }}
        >
          <iframe
            key={id}
            title={`Player — ${track.title}`}
            src={`https://www.youtube.com/embed/${id}?autoplay=1&rel=0`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
          />
        </div>
      ) : (
        <a
          href={track.audio_url}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 13.5, color: 'var(--accent-text-sm)' }}
        >
          Open this track in a new tab ↗
        </a>
      )}
    </div>
  )
}

export default function MoodDoorway({ playing, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [start, setStart] = useState(playing?.entryEpisode ?? 1)
  // The track currently in the player. Reset whenever the collection changes.
  const [nowPlaying, setNowPlaying] = useState(null)

  useEffect(() => {
    setStart(playing?.entryEpisode ?? 1)
    setNowPlaying(null)
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

      {nowPlaying && (
        <NowPlaying track={nowPlaying} onClose={() => setNowPlaying(null)} />
      )}

      {loading && (
        <div style={{ fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
          Loading songs…
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
              Show earlier songs (1–{start - 1})
            </Button>
          )}

          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 8 }}>
            {data.episodes.map((episode) => {
              const isPlaying = nowPlaying?.number === episode.number
              return (
                <li
                  key={episode.number}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                    background:
                      isPlaying || episode.is_arc_start ? 'var(--accent-soft)' : 'var(--canvas)',
                    border: `1px solid ${
                      isPlaying || episode.is_arc_start ? 'var(--accent-line)' : 'var(--border)'
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
                      {episode.synopsis ? `${episode.synopsis} · ` : ''}
                      {minutes(episode.duration_sec)}
                      {episode.is_arc_start ? ' · the entry point' : ''}
                    </span>
                  </span>

                  {/* A missing file is a content gap, not a reason to hide the
                      track. Show it, disable play, and say why. */}
                  <Button
                    variant={isPlaying ? 'primary' : 'secondary'}
                    size="sm"
                    disabled={!episode.audio_url}
                    onClick={() => setNowPlaying(episode)}
                  >
                    {!episode.audio_url ? 'No audio' : isPlaying ? 'Playing' : 'Play'}
                  </Button>
                </li>
              )
            })}
          </ol>

          {data.has_more && lastNumber != null && (
            <Button variant="secondary" size="sm" onClick={() => setStart(lastNumber + 1)}>
              More songs ({data.total - lastNumber} left)
            </Button>
          )}
        </>
      )}
    </section>
  )
}
