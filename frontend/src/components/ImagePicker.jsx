import { useState } from 'react'

import { IMAGE_BY_ID, IMAGE_LIBRARY, renderCover } from '../config/imageLibrary'

/**
 * ImagePicker — attach a ready-made cover image instead of uploading one.
 *
 * Mirrors StoryPicker: a native <select> of sample covers. The chosen cover is
 * drawn client-side (canvas → JPEG) and tied to the current post `title`, then
 * handed to `onSelect({ dataUrl, base64, mime, name })` — the same shape the
 * upload path produces, so the vision agents genuinely "see" it.
 */
export default function ImagePicker({ onSelect, title }) {
  const [selectedId, setSelectedId] = useState('')

  const handleChange = (e) => {
    const id = e.target.value
    setSelectedId(id)
    const sample = IMAGE_BY_ID[id]
    if (sample) onSelect(renderCover(sample, title))
  }

  return (
    <div style={{ position: 'relative', minWidth: 190 }}>
      <select
        aria-label="Attach a ready-made cover image"
        value={selectedId}
        onChange={handleChange}
        style={{
          appearance: 'none',
          WebkitAppearance: 'none',
          fontFamily: 'var(--font-sans)',
          fontSize: 13,
          fontWeight: 600,
          color: selectedId ? 'var(--ink)' : 'var(--muted)',
          background: 'var(--surface-raised)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '8px 30px 8px 12px',
          minHeight: 36,
          cursor: 'pointer',
          boxSizing: 'border-box',
          width: '100%',
        }}
      >
        <option value="" disabled>
          Or pick a sample image…
        </option>
        {IMAGE_LIBRARY.map((i) => (
          <option key={i.id} value={i.id}>
            {i.label}
          </option>
        ))}
      </select>
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
        style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
      >
        <path d="M6 9l6 6 6-6" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}
