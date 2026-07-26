import { useState } from 'react'

import MoodPlayer from './MoodPlayer'
import MoodRefineRow from './MoodRefineRow'

/**
 * The answer: three readings of one ambiguous feeling, side by side.
 *
 * This shape is the argument. A single ranked list would force the system to
 * guess which of three incompatible desires the listener meant — "after
 * heartbreak" can mean sit in it, be kept company, or get me out of here — and
 * guessing wrong is worse than asking. Showing all three makes the listener's
 * click the disambiguation: no friction, and the structure itself demonstrates
 * that the ambiguity was noticed rather than fumbled.
 *
 * Each card carries two actions: open the doorway (the full song list from the
 * entry point), or play the entry track right here without leaving the shelves.
 *
 * Shelves are labelled in listener language, never "Romance / Thriller".
 */
function ResultCard({ result, onOpen, onPlay, isPlaying }) {
  const canPlay = Boolean(result.entry_audio_url)
  return (
    <li>
      <article
        style={{
          height: '100%',
          background: 'var(--canvas)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <h4 style={{ margin: 0, fontSize: 15.5, fontWeight: 600, color: 'var(--ink)' }}>
          {result.series_title}
        </h4>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {/* The doorway. This is the whole "not a 200-episode series" point, so
              it is a real control, not decoration. */}
          <button
            type="button"
            onClick={() => onOpen(result)}
            style={{
              minHeight: 44,
              display: 'inline-flex',
              alignItems: 'center',
              background: 'var(--accent-soft)',
              border: '1px solid var(--accent-line)',
              borderRadius: 'var(--radius-pill)',
              color: 'var(--accent-text-sm)',
              padding: '0 14px',
              fontFamily: 'var(--font-sans)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {result.entry_label}
          </button>

          {/* Play the entry track inline. */}
          {canPlay && (
            <button
              type="button"
              onClick={() => onPlay(result)}
              aria-label={`Play ${result.entry_title || result.series_title}`}
              style={{
                minHeight: 44,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: isPlaying ? 'var(--ink)' : 'var(--canvas)',
                border: `1px solid ${isPlaying ? 'var(--ink)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-pill)',
                color: isPlaying ? 'var(--canvas)' : 'var(--ink)',
                padding: '0 14px',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <span aria-hidden="true">{isPlaying ? '❚❚' : '▶'}</span>
              {isPlaying ? 'Playing' : 'Play'}
            </button>
          )}
        </div>

        {/* If we know the entry track, name it — the card is otherwise a
            collection, and Play is playing one specific song. */}
        {result.entry_title && (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--dim)' }}>
            ▶ {result.entry_title}
            {result.entry_artist ? ` · ${result.entry_artist}` : ''}
          </p>
        )}

        {/* The line people quote. Give it room. */}
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
          {result.explanation}
        </p>

        <div
          className="font-mono-num"
          style={{ marginTop: 'auto', fontSize: 12, color: 'var(--dim)' }}
        >
          {result.duration_min} min
        </div>
      </article>
    </li>
  )
}

export default function MoodShelves({ shelves, sliders, onRefine, onOpen, refining }) {
  // One shared player for all shelves — clicking Play on any card replaces it.
  const [nowPlaying, setNowPlaying] = useState(null)

  const play = (result) =>
    setNowPlaying({
      id: result.content_id,
      title: result.entry_title || result.series_title,
      synopsis: result.entry_artist,
      audio_url: result.entry_audio_url,
      number: result.entry_episode,
    })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
      {nowPlaying && (
        <div style={{ position: 'sticky', top: 8, zIndex: 5 }}>
          <MoodPlayer track={nowPlaying} onClose={() => setNowPlaying(null)} />
        </div>
      )}

      {shelves.map((shelf) => {
        const isRefining = refining === shelf.id
        return (
          <section key={shelf.id} aria-label={shelf.label}>
            <header style={{ marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
                {shelf.label}
              </h3>
              <p style={{ margin: '4px 0 0', fontSize: 14, color: 'var(--muted)' }}>
                {shelf.subtitle}
              </p>
            </header>

            <ul
              aria-busy={isRefining}
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: 10,
                opacity: isRefining ? 0.5 : 1,
                transition: 'opacity var(--dur-fast) var(--ease-standard)',
              }}
            >
              {shelf.results.map((result) => (
                <ResultCard
                  key={result.content_id}
                  result={result}
                  onOpen={onOpen}
                  onPlay={play}
                  isPlaying={nowPlaying?.id === result.content_id}
                />
              ))}
            </ul>

            <MoodRefineRow
              shelf={shelf}
              sliders={sliders}
              onRefine={onRefine}
              busy={isRefining}
            />
          </section>
        )
      })}
    </div>
  )
}
