/** A single listener reaction, rendered as a pull-quote with attribution. */
export default function QuoteCard({ quote, persona }) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-5)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 24,
          color: 'var(--accent-text-sm)',
          lineHeight: 1,
        }}
      >
        &ldquo;
      </span>
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-sans)',
          fontSize: 15,
          lineHeight: 1.5,
          color: 'var(--ink)',
        }}
      >
        {quote}
      </p>
      {persona && (
        <span className="label-upper" style={{ fontSize: 11 }}>
          {persona}
        </span>
      )}
    </div>
  )
}
