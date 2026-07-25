/**
 * Underline tab bar for switching panels inside a lens. `active` is the
 * selected tab id; `onChange(id)` switches. The active marker is the studio's
 * restrained red underline; hierarchy stays black-on-white.
 */
export default function Tabs({ tabs, active, onChange }) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 28,
        borderBottom: '1px solid var(--border)',
        overflowX: 'auto',
        overflowY: 'hidden',
      }}
    >
      {tabs.map((t) => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            aria-pressed={isActive}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              minHeight: 44,
              padding: '12px 2px 10px',
              fontFamily: 'var(--font-sans)',
              fontSize: 14.5,
              fontWeight: isActive ? 600 : 500,
              whiteSpace: 'nowrap',
              flexShrink: 0,
              color: isActive ? 'var(--ink)' : 'var(--muted)',
              borderBottom: isActive
                ? '2px solid var(--accent)'
                : '2px solid transparent',
              marginBottom: -1,
              transition: 'color var(--dur-fast) var(--ease-standard)',
            }}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
