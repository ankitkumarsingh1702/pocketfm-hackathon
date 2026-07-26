import MoodRefineRow from './MoodRefineRow'

/**
 * The answer: three readings of one ambiguous feeling, side by side.
 *
 * This shape is the argument. A single ranked list would force the system to
 * guess which of three incompatible desires the listener meant — "after
 * heartbreak" can mean sit in it, be kept company, or get me out of here — and
 * guessing wrong is worse than asking. Showing all three makes the listener's
 * click the disambiguation: no friction, and the structure itself demonstrates
 * that the ambiguity was noticed rather than fumbled.
 *
 * Shelves are labelled in listener language, never "Romance / Thriller".
 */
function ResultCard({ result, onOpen }) {
  return (
    <li>
      <article
        style={{
          height: '100%',
          background: 'var(--canvas)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <h4 style={{ margin: 0, fontSize: 15.5, fontWeight: 600, color: 'var(--ink)' }}>
          {result.series_title}
        </h4>

        {/* The doorway. This is the whole "not a 200-episode series" point, so
            it is a real control, not decoration. */}
        <button
          type="button"
          onClick={() => onOpen(result)}
          style={{
            alignSelf: 'flex-start',
            minHeight: 44,
            display: 'inline-flex',
            alignItems: 'center',
            background: 'var(--accent-soft)',
            border: '1px solid var(--accent-line)',
            borderRadius: 'var(--radius-pill)',
            color: 'var(--accent-text-sm)',
            padding: '0 14px',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {result.entry_label}
        </button>

        {/* The line people quote. Give it room. */}
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
          {result.explanation}
        </p>

        <div
          className="font-mono-num"
          style={{ marginTop: 'auto', fontSize: 12, color: 'var(--dim)' }}
        >
          {result.duration_min} min
        </div>
      </article>
    </li>
  )
}

export default function MoodShelves({ shelves, sliders, onRefine, onOpen, refining }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
      {shelves.map((shelf) => {
        const isRefining = refining === shelf.id
        return (
          <section key={shelf.id} aria-label={shelf.label}>
            <header style={{ marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
                {shelf.label}
              </h3>
              <p style={{ margin: '4px 0 0', fontSize: 14, color: 'var(--muted)' }}>
                {shelf.subtitle}
              </p>
            </header>

            <ul
              aria-busy={isRefining}
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: 10,
                opacity: isRefining ? 0.5 : 1,
                transition: 'opacity var(--dur-fast) var(--ease-standard)',
              }}
            >
              {shelf.results.map((result) => (
                <ResultCard key={result.content_id} result={result} onOpen={onOpen} />
              ))}
            </ul>

            <MoodRefineRow
              shelf={shelf}
              sliders={sliders}
              onRefine={onRefine}
              busy={isRefining}
            />
          </section>
        )
      })}
    </div>
  )
}
