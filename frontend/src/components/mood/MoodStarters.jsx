/**
 * Empty state: eight pre-written queries.
 *
 * We show QUERIES, not shows. A grid of available titles here would quietly
 * reinstate the browse experience this lens exists to replace, and it is the
 * first thing a reviewer would spot. The starters teach the interaction model in
 * one glance, they span the destination space so whoever opens the lens finds one
 * that is nearly true, and one of them is deliberately ambiguous so the
 * three-shelf answer can be demonstrated with a single tap.
 */
export default function MoodStarters({
  starters,
  onPick,
  disabled = false,
  ready = true,
  error = null,
}) {
  if (!ready) {
    return (
      <div style={{ fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
        Loading starters…
      </div>
    )
  }

  // "Loading" and "not there" must not look the same. A permanent spinner reads
  // as a hang; naming the outage tells you the box above still works.
  if (error || !starters.length) {
    return (
      <div
        role="status"
        style={{
          padding: '14px 16px',
          border: '1px dashed var(--border)',
          borderRadius: 'var(--radius-md)',
          fontSize: 14,
          lineHeight: 1.6,
          color: 'var(--muted)',
          maxWidth: '64ch',
        }}
      >
        Starters are unavailable right now{error ? ` — ${error}` : ''}. You can still
        type a feeling above.
      </div>
    )
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div className="label-upper" style={{ fontSize: 11 }}>
        Or start from a feeling
      </div>

      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 10,
        }}
      >
        {starters.map((starter) => (
          <li key={starter.id} style={{ display: 'flex' }}>
            <button
              type="button"
              onClick={() => onPick(starter.text)}
              disabled={disabled}
              style={{
                flex: 1,
                minHeight: 44,
                textAlign: 'left',
                background: 'var(--canvas)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--ink)',
                padding: '14px 16px',
                fontFamily: 'var(--font-sans)',
                fontSize: 14.5,
                lineHeight: 1.5,
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.55 : 1,
                transition: 'background var(--dur-fast) var(--ease-standard)',
              }}
            >
              {starter.text}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
