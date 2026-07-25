/** Rounded label/value chip, e.g. "Superpower Army = 1,000". */
export default function Pill({ label, value, tone = 'neutral' }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-pill)',
        padding: '6px 14px',
        fontFamily: 'var(--font-sans)',
        fontSize: 13,
        color: 'var(--muted)',
        fontWeight: 500,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
      {value !== undefined && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            color: tone === 'accent' ? 'var(--accent-text-sm)' : 'var(--ink)',
          }}
        >
          {value}
        </span>
      )}
    </span>
  )
}
