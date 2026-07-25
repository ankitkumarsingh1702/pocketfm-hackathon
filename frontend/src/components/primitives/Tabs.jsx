/** Underline tab bar. `active` is the selected tab id; `onChange(id)` switches. */
export default function Tabs({ tabs, active, onChange }) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 32,
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
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '14px 2px 12px',
              fontFamily: 'var(--font-sans)',
              fontSize: 15,
              fontWeight: 600,
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
