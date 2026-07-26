import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

/**
 * Full-viewport right sheet: scrim + a panel that slides in from the screen's
 * right edge. Portalled to <body> so no transformed ancestor can capture the
 * fixed positioning (the same fix the Writers Room profile drawer needed).
 *
 * Accessibility: dialog semantics, focus moves to the close button on open,
 * Escape and the scrim both close, and the page behind stops scrolling.
 */
export default function SideSheet({ title, onClose, children }) {
  const closeRef = useRef(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return createPortal(
    <div className="sheet" role="presentation">
      <button type="button" className="sheet__scrim" aria-label="Close" onClick={onClose} />
      <aside className="sheet__panel" role="dialog" aria-modal="true" aria-label={title}>
        <header className="sheet__head">
          <h2 className="sheet__title">{title}</h2>
          <button
            type="button"
            className="sheet__close"
            onClick={onClose}
            ref={closeRef}
            aria-label="Close"
          >
            ✕
          </button>
        </header>
        <div className="sheet__body">{children}</div>
      </aside>
    </div>,
    document.body,
  )
}
