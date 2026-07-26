import { useState } from 'react'

import { STORY_BY_ID, STORY_LIBRARY } from '../config/storyLibrary'

/**
 * StoryPicker — select a ready-made story instead of typing one.
 *
 * Reusable across every lens: the parent passes `onSelect(story)` and adapts the
 * picked `{ id, title, genre, blurb, episode, text }` into its own inputs. Stories
 * come from the STATIC bundled library (never the knowledge graph), so a presenter
 * can load and showcase any lens instantly.
 *
 * A native <select> is used deliberately: it never clips inside a card, is fully
 * keyboard-accessible, and is rock-solid for a live demo.
 */
export default function StoryPicker({
  onSelect,
  label = 'Load a ready-made story',
  defaultId = '',
  hint = 'Pick one to showcase instantly — no typing needed.',
}) {
  const [selectedId, setSelectedId] = useState(defaultId)
  const selected = selectedId ? STORY_BY_ID[selectedId] : null

  const handleChange = (e) => {
    const id = e.target.value
    setSelectedId(id)
    const story = STORY_BY_ID[id]
    if (story) onSelect(story)
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
        <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 200 }}>
          <select
            id="story-picker-select"
            value={selectedId}
            onChange={handleChange}
            style={{
              appearance: 'none',
              WebkitAppearance: 'none',
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              fontWeight: 600,
              color: selected ? 'var(--ink)' : 'var(--muted)',
              background: 'var(--surface-raised)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '9px 34px 9px 12px',
              width: '100%',
              minHeight: 40,
              cursor: 'pointer',
              boxSizing: 'border-box',
            }}
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
          {/* Chevron */}
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
        </div>
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
          <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>{selected.blurb}</span>
        </div>
      ) : (
        <span style={{ fontSize: 12.5, color: 'var(--dim)' }}>{hint}</span>
      )}
    </div>
  )
}
