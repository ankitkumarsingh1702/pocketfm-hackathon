import { RECALL_LABELS } from '../../config/genre'
import { ScoreGauge } from '../primitives'

/** `0.8571` -> `86%`. Null components (no edges in the source) read as n/a. */
function pct(value) {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

function RecallRow({ name, value, counts }) {
  const { label, hint } = RECALL_LABELS[name]
  const width = value == null ? 0 : Math.round(value * 100)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{label}</span>
        <span className="font-mono-num" style={{ fontSize: 14, color: 'var(--ink)', whiteSpace: 'nowrap' }}>
          {pct(value)}{' '}
          <span style={{ color: 'var(--dim)', fontWeight: 400 }}>({counts})</span>
        </span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${pct(value)}, ${counts}`}
        style={{ height: 4, background: 'var(--grey-200)', borderRadius: 2, overflow: 'hidden' }}
      >
        <div style={{ width: `${width}%`, height: '100%', background: 'var(--accent)' }} />
      </div>
      <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>{hint}</span>
    </div>
  )
}

/**
 * How much of the plot survived the rewrite.
 *
 * The headline number is a weighted blend (60/20/20) of the three recalls, so
 * the components are shown alongside it — a 71% caused by one dropped pivot is
 * a different problem from a 71% caused by thin causal links, and the fix is
 * different too.
 */
export default function FidelityReport({ detail, skeleton, words, seconds }) {
  if (!detail) return null

  const beatById = new Map((skeleton?.beats ?? []).map((b) => [b.id, b]))
  const missing = detail.missing_load_bearing ?? []
  const broken = detail.broken_edges ?? []
  const notes = detail.beat_notes ?? {}

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <div
        style={{
          display: 'flex',
          gap: 40,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <ScoreGauge score={Math.round((detail.fidelity ?? 0) * 100)} label="Fidelity" />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, flex: '1 1 320px', minWidth: 280 }}>
          {['load_bearing_recall', 'beat_recall', 'edge_recall'].map((name) => (
            <RecallRow
              key={name}
              name={name}
              value={detail[name]}
              counts={detail[`${name}_counts`]}
            />
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13, color: 'var(--muted)' }}>
        {words != null && (
          <span>
            <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{words.toLocaleString()}</strong> words
          </span>
        )}
        {seconds != null && (
          <span>
            took <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>{seconds}s</strong>
          </span>
        )}
        <span>scored against the prose, not a re-extracted skeleton</span>
      </div>

      {missing.length > 0 && (
        <div
          style={{
            background: 'var(--accent-soft)',
            border: '1px solid var(--accent-line)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-6)',
          }}
        >
          <h4
            style={{
              margin: '0 0 4px',
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--accent-text-sm)',
            }}
          >
            {missing.length} load-bearing {missing.length === 1 ? 'beat' : 'beats'} did not make the page
          </h4>
          <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink)', lineHeight: 1.6 }}>
            Deleting any of these from the source would change the ending, so the rewrite
            is telling a different story where they are missing.
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {missing.map((id) => (
              <li key={id} style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.6 }}>
                <code style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{id}</code>{' '}
                {beatById.get(id)?.action ?? 'beat not found in the skeleton'}
                {notes[id] && (
                  <span style={{ color: 'var(--muted)' }}> — {notes[id]}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {broken.length > 0 && (
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>
            {broken.length} causal {broken.length === 1 ? 'link' : 'links'} no longer legible
          </h4>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, maxWidth: '62ch' }}>
            Both beats are on the page, but the rewrite does not make one cause the other.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {broken.map((edge) => (
              <code
                key={edge}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 13,
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                }}
              >
                {edge}
              </code>
            ))}
          </div>
        </div>
      )}

      {missing.length === 0 && broken.length === 0 && (
        <p style={{ margin: 0, fontSize: 14, color: 'var(--ink)', lineHeight: 1.6 }}>
          Every load-bearing beat and every causal link survived the rewrite.
        </p>
      )}
    </section>
  )
}
