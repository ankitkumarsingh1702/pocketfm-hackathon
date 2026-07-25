/**
 * One expert-critic's feedback card for the Writers Room.
 *
 * Pure view of a writers-room note view-model (role, verdict, score, fix,
 * strengths, issues). Verdict colour mapping is the only local concern.
 */

const VERDICT_TONE = {
  strong: 'var(--success)',
  mixed: 'var(--warning)',
  weak: 'var(--danger)',
}

function Chips({ items, symbol, color }) {
  if (!items.length) return null
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((item, i) => (
        <li key={i} style={{ fontSize: 13, lineHeight: 1.45, color: 'var(--muted)', display: 'flex', gap: 8 }}>
          <span style={{ color, flexShrink: 0 }}>{symbol}</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

export default function ExpertNote({ note }) {
  const tone = VERDICT_TONE[note.verdict] || 'var(--muted)'

  return (
    <div style={{ padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span className="label-upper" style={{ color: 'var(--accent-text-sm)', fontSize: 11 }}>
          {note.role}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: tone,
            }}
          >
            {note.verdict}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--ink)',
            }}
          >
            {note.score}
          </span>
        </span>
      </div>

      {note.fix && (
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: 'var(--ink)' }}>{note.fix}</p>
      )}

      <Chips items={note.strengths} symbol="+" color="var(--success)" />
      <Chips items={note.issues} symbol="–" color="var(--danger)" />
    </div>
  )
}
