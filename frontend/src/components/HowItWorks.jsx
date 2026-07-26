/**
 * HowItWorks — a compact, three-step "input → what the AI does → output"
 * explainer strip shared by every feature tab. Keeps each surface a glass box:
 * a non-technical viewer can tell, at a glance, what goes in, what the engine
 * is doing, and what comes out.
 *
 * Clean by design: one thin-bordered strip (not a card wall), sentence-case
 * copy, pale-red step numbers for gentle emphasis, and flex-wrap so the three
 * steps stack on narrow screens. Pass 2–4 `steps` of `{ title, body }`.
 */

const wrap = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 4,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface)',
  padding: 6,
}

const step = {
  flex: '1 1 220px',
  display: 'flex',
  gap: 12,
  alignItems: 'flex-start',
  padding: '12px 14px',
  minWidth: 0,
}

const numBadge = {
  flexShrink: 0,
  width: 24,
  height: 24,
  borderRadius: '50%',
  background: 'var(--danger-bg)',
  color: 'var(--red-ink)',
  fontSize: 12,
  fontWeight: 700,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  lineHeight: 1,
}

const stepTitle = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--ink)',
  marginBottom: 3,
  lineHeight: 1.35,
}

const stepBody = {
  fontSize: 12.5,
  color: 'var(--muted)',
  lineHeight: 1.5,
}

/**
 * @param {{steps: {title: string, body: string}[], label?: string, style?: object}} props
 */
export default function HowItWorks({ steps = [], label = 'How it works', style }) {
  if (!steps.length) return null
  return (
    <section aria-label={label} style={style}>
      {label && (
        <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
          {label}
        </div>
      )}
      <div style={wrap} role="list">
        {steps.map((s, i) => (
          <div key={i} style={step} role="listitem">
            <span style={numBadge} aria-hidden="true">
              {i + 1}
            </span>
            <div style={{ minWidth: 0 }}>
              <div style={stepTitle}>{s.title}</div>
              <div style={stepBody}>{s.body}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
