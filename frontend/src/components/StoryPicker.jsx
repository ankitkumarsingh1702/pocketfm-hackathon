import { useState } from 'react'

import { STORY_BY_ID, STORY_LIBRARY } from '../config/storyLibrary'

/**
 * StoryPicker — select a ready-made story (and one of its episodes) instead of
 * typing one.
 *
 * Reusable across every lens: the parent passes `onSelect(story)` and adapts the
 * picked `{ id, title, genre, blurb, episode, text, episodeN, episodeTitle }`
 * into its own inputs. Stories come from the STATIC bundled library (never the
 * knowledge graph), so a presenter can load and showcase any lens instantly.
 *
 * Every story is a full 40-episode show, so a second native <select> lets you
 * switch episodes. `onSelect` always fires with the CHOSEN episode's text — so
 * whatever the lens does downstream (canon extraction, plot-hole scan, audience
 * reactions) is driven by that episode's input, changing as you switch episodes.
 *
 * Native <select>s are used deliberately: they never clip inside a card, are
 * fully keyboard-accessible, and are rock-solid for a live demo.
 */
export default function StoryPicker({
  onSelect,
  label = 'Load a ready-made story',
  defaultId = '',
  hint = 'Pick one to showcase instantly — no typing needed.',
  showEpisodes = true,
}) {
  const [selectedId, setSelectedId] = useState(defaultId)
  const [epIndex, setEpIndex] = useState(0)
  const selected = selectedId ? STORY_BY_ID[selectedId] : null
  const episodes = selected?.episodes || []
  const episode = episodes[epIndex] || null

  // Flatten story + chosen episode into the shape every consumer already expects.
  const fire = (story, idx) => {
    if (!story) return
    const ep = story.episodes?.[idx]
    if (!ep) {
      onSelect(story)
      return
    }
    onSelect({
      ...story,
      episode: ep.label,
      text: ep.text,
      episodeN: ep.n,
      episodeTitle: ep.title,
    })
  }

  const handleStoryChange = (e) => {
    const id = e.target.value
    setSelectedId(id)
    setEpIndex(0)
    fire(STORY_BY_ID[id], 0)
  }

  const handleEpisodeChange = (e) => {
    const idx = Number(e.target.value)
    setEpIndex(idx)
    fire(selected, idx)
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: '12px 14px',
        border: '1px dashed var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--surface)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <label
          className="label-upper"
          htmlFor="story-picker-select"
          style={{ fontSize: 10, color: 'var(--muted)', whiteSpace: 'nowrap' }}
        >
          {label}
        </label>
        <div style={{ position: 'relative', flex: '2 1 240px', minWidth: 200 }}>
          <select
            id="story-picker-select"
            value={selectedId}
            onChange={handleStoryChange}
            style={SELECT_STYLE(!!selected)}
          >
            <option value="" disabled>
              Choose a story…
            </option>
            {STORY_LIBRARY.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} — {s.genre}
              </option>
            ))}
          </select>
          <Chevron />
        </div>

        {selected && showEpisodes && episodes.length > 1 && (
          <div style={{ position: 'relative', flex: '1 1 170px', minWidth: 150 }}>
            <select
              id="story-picker-episode"
              aria-label="Episode"
              value={epIndex}
              onChange={handleEpisodeChange}
              style={SELECT_STYLE(true)}
            >
              {episodes.map((ep, i) => (
                <option key={ep.n} value={i}>
                  {ep.label}
                  {ep.title ? ` · ${ep.title}` : ''}
                </option>
              ))}
            </select>
            <Chevron />
          </div>
        )}
      </div>

      {selected ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.02em',
              color: 'var(--red-ink)',
              background: 'var(--danger-bg)',
              border: '1px solid var(--danger)',
              borderRadius: 'var(--radius-pill)',
              padding: '2px 10px',
            }}
          >
            {selected.genre}
          </span>
          <span style={{ fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
            {episode ? `${episode.label} of ${episodes.length}` : `${episodes.length} episodes`}
          </span>
          <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
            {episode?.title || selected.blurb}
          </span>
        </div>
      ) : (
        <span style={{ fontSize: 12.5, color: 'var(--dim)' }}>{hint}</span>
      )}
    </div>
  )
}

/** Shared native-select styling — matches the studio's input tokens. */
const SELECT_STYLE = (filled) => ({
  appearance: 'none',
  WebkitAppearance: 'none',
  fontFamily: 'var(--font-sans)',
  fontSize: 14,
  fontWeight: 600,
  color: filled ? 'var(--ink)' : 'var(--muted)',
  background: 'var(--surface-raised)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '9px 34px 9px 12px',
  width: '100%',
  minHeight: 40,
  cursor: 'pointer',
  boxSizing: 'border-box',
})

/** Down chevron overlaid on a native select (pointer-events off). */
function Chevron() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
    >
      <path d="M6 9l6 6 6-6" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
