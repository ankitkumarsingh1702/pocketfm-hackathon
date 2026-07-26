import { useCountUp } from '../../hooks/useCountUp'
import { formatInt } from '../../utils/format'
import { BarChart, MetricNumber, QuoteCard } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Section heading in the studio's uppercase-label style. */
function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

function SegmentTable({ segments }) {
  if (!segments.length) return null
  return (
    <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--muted)' }}>
            <th style={cellHead}>Segment</th>
            <th style={{ ...cellHead, textAlign: 'right' }}>Listeners</th>
            <th style={{ ...cellHead, textAlign: 'right' }}>Continue&nbsp;%</th>
            <th style={{ ...cellHead, textAlign: 'right' }}>Avg&nbsp;hook</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((s) => (
            <tr key={s.segment}>
              <td style={{ ...cell, color: 'var(--ink)' }}>{s.segment}</td>
              <td style={{ ...cell, textAlign: 'right', ...num }}>{formatInt(s.count)}</td>
              <td style={{ ...cell, textAlign: 'right', ...num }}>{s.bingePct}%</td>
              <td style={{ ...cell, textAlign: 'right', ...num }}>{s.avgHook}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const cellHead = { padding: '10px 14px', borderBottom: '1px solid var(--border)', fontWeight: 600 }
const cell = { padding: '10px 14px', borderBottom: '1px solid var(--border)' }
const num = { fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }

/**
 * Audience Simulator results. Pure view of the audience view-model; the hero
 * count-up is the only local animation.
 */
export default function AudienceSimulatorTab({ loading, error, data }) {
  const continueRate = useCountUp(data ? data.continueRate : 0, Boolean(data))

  if (loading) return <LoadingState label="Polling simulated listeners…" />
  if (error) return <ErrorState message={error} />
  if (!data) {
    return (
      <EmptyState
        title="No simulation yet"
        hint="Run the simulation to fan this episode out to a panel of AI listeners."
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 48, paddingTop: 8 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 28, flexWrap: 'wrap' }}>
          <MetricNumber value={continueRate} suffix="%" size="hero" tone="accent" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={data.avgHook} size="md" tone="ink" />
            <SectionLabel style={{ fontSize: 10 }}>Avg hook score</SectionLabel>
          </div>
        </div>
        <SectionLabel style={{ marginTop: 8, fontSize: 13 }}>
          Overall continue-rate · across {formatInt(data.total)} simulated listeners
        </SectionLabel>
      </div>

      {data.dropOff.length > 0 && (
        <div style={{ maxWidth: 640 }}>
          <SectionLabel style={{ marginBottom: 16 }}>Drop-off By Stage</SectionLabel>
          <BarChart data={data.dropOff} />
        </div>
      )}

      {data.reactions.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 16 }}>Listener Reactions</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {data.reactions.map((q, i) => (
              <QuoteCard key={i} quote={q.quote} persona={q.persona} />
            ))}
          </div>
        </div>
      )}

      {data.segments.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 16 }}>By Segment</SectionLabel>
          <SegmentTable segments={data.segments} />
        </div>
      )}

      {data.churnReasons.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 12 }}>Why Listeners Dropped</SectionLabel>
          <ul style={{ margin: 0, paddingLeft: 20, fontSize: 14, color: 'var(--ink)', lineHeight: 1.7 }}>
            {data.churnReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
