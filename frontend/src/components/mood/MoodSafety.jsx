/**
 * The safety path.
 *
 * A box that asks how you feel will receive genuine distress — this is not
 * hypothetical, it is among the most likely things such an input gets. When the
 * parser flags it, retrieval does not run at all: no shelves, no results, and
 * the lens hides every demo control above this, because someone in crisis does
 * not get a row of listener chips over the one thing that matters.
 *
 * Deliberately not styled as an error. It is the calmest surface in the studio.
 */
export default function MoodSafety({ message, resources }) {
  return (
    <section
      aria-live="polite"
      style={{
        maxWidth: '56ch',
        borderLeft: '2px solid var(--accent-line)',
        paddingLeft: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
      }}
    >
      <p style={{ margin: 0, fontSize: 17, lineHeight: 1.7, color: 'var(--ink)' }}>{message}</p>

      {resources?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="label-upper" style={{ fontSize: 11 }}>
            If you want to talk to someone
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
            {resources.map((resource) => (
              <li
                key={resource}
                style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}
              >
                {resource}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
