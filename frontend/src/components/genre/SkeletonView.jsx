/**
 * The genre-neutral plot skeleton the pipeline extracted.
 *
 * A table rather than cards: this is dense, uniform, comparable data, and a
 * reader scanning for "which beats dropped" needs rows they can run an eye
 * down. `dropped` marks beats the verifier could not find in the rewrite.
 */
export default function SkeletonView({ skeleton, dropped, lint }) {
  if (!skeleton) return null

  const droppedSet = new Set(dropped ?? [])
  const roleName = new Map((skeleton.roles ?? []).map((r) => [r.slug, r.name]))

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
          Logline
        </div>
        <p style={{ margin: 0, fontSize: 17, lineHeight: 1.6, color: 'var(--ink)', maxWidth: '62ch' }}>
          {skeleton.logline}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13, color: 'var(--muted)' }}>
        <span>
          <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{skeleton.counts?.beats}</strong> beats
        </span>
        <span>
          <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{skeleton.counts?.load_bearing}</strong>{' '}
          load-bearing
        </span>
        <span>
          <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{skeleton.counts?.edges}</strong> causal
          edges
        </span>
        <span>
          <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{skeleton.roles?.length}</strong> roles
        </span>
      </div>

      {lint?.length > 0 && (
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
          }}
        >
          <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
            Lint
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--muted)' }}>
            {lint.map((issue) => (
              <li key={issue} style={{ fontSize: 13, lineHeight: 1.6 }}>
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            minWidth: 640,
            borderCollapse: 'collapse',
            fontSize: 14,
          }}
        >
          <caption className="label-upper" style={{ fontSize: 11, textAlign: 'left', marginBottom: 10 }}>
            Beats, in causal order
          </caption>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Beat', 'Actor', 'What happens', 'Outcome', 'Causes'].map((h) => (
                <th
                  key={h}
                  scope="col"
                  style={{
                    textAlign: 'left',
                    padding: '10px 12px 10px 0',
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--muted)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(skeleton.beats ?? []).map((beat) => {
              const isDropped = droppedSet.has(beat.id)
              return (
                <tr
                  key={beat.id}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    background: isDropped ? 'var(--accent-soft)' : 'transparent',
                  }}
                >
                  <td style={{ padding: '12px 12px 12px 0', whiteSpace: 'nowrap', verticalAlign: 'top' }}>
                    <code style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)' }}>
                      {beat.id}
                    </code>
                    {beat.load_bearing && (
                      <span
                        title="Load-bearing: deleting this changes the ending"
                        style={{
                          marginLeft: 6,
                          fontSize: 11,
                          fontWeight: 700,
                          color: 'var(--accent-text-sm)',
                        }}
                      >
                        ●
                      </span>
                    )}
                  </td>
                  <td
                    style={{
                      padding: '12px 12px 12px 0',
                      color: 'var(--muted)',
                      verticalAlign: 'top',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {roleName.get(beat.actor_role) || beat.actor_role}
                  </td>
                  <td style={{ padding: '12px 12px 12px 0', color: 'var(--ink)', lineHeight: 1.6, verticalAlign: 'top' }}>
                    {beat.action}
                    {isDropped && (
                      <strong style={{ color: 'var(--accent-text-sm)', fontWeight: 600 }}>
                        {' '}
                        — not on the page
                      </strong>
                    )}
                  </td>
                  <td
                    style={{
                      padding: '12px 12px 12px 0',
                      color: 'var(--muted)',
                      verticalAlign: 'top',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {beat.outcome}
                  </td>
                  <td
                    style={{
                      padding: '12px 0',
                      color: 'var(--dim)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 13,
                      verticalAlign: 'top',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {beat.causes?.length ? beat.causes.join(', ') : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>
        <span style={{ color: 'var(--accent-text-sm)', fontWeight: 700 }}>●</span> marks a
        load-bearing beat. Shaded rows did not survive into the rewrite.
      </p>
    </section>
  )
}
