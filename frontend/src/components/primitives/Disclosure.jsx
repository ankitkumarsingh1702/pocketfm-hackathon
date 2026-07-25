import { useId, useState } from 'react'

/**
 * Accessible collapse: a full-width toggle row with a rotating chevron, and a
 * body that mounts hidden rather than unmounted so its state survives.
 *
 * Uncontrolled by default (`defaultOpen`); pass `open` + `onToggle` to
 * control it — the scene accordion does, so it can auto-open the scene being
 * written while still letting a reader pin any other one.
 */
export default function Disclosure({ summary, children, open, onToggle, defaultOpen = false }) {
  const bodyId = useId()
  const [own, setOwn] = useState(defaultOpen)
  const controlled = open !== undefined
  const isOpen = controlled ? open : own

  const toggle = () => {
    if (controlled) onToggle?.(!open)
    else setOwn((value) => !value)
  }

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={isOpen}
        aria-controls={bodyId}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          width: '100%',
          minHeight: 44,
          padding: '8px 0',
          background: 'none',
          border: 'none',
          textAlign: 'left',
          cursor: 'pointer',
          color: 'inherit',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            flexShrink: 0,
            fontSize: 10,
            color: 'var(--muted)',
            transition: 'transform var(--dur-fast) var(--ease-standard)',
            transform: isOpen ? 'rotate(90deg)' : 'none',
          }}
        >
          ▶
        </span>
        <span style={{ flex: 1, minWidth: 0 }}>{summary}</span>
      </button>
      <div id={bodyId} hidden={!isOpen}>
        {children}
      </div>
    </div>
  )
}
