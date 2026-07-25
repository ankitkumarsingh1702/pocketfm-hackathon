import { Button, GraphCanvas, MetricNumber, Pill, SurfaceCard } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Section heading in the studio's uppercase-label style. */
function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

/** Read/write/skip visual language for one activity row. */
const OP_STYLE = {
  read: { label: 'READ', color: 'var(--ink)', verb: 'read shared memory' },
  write: { label: 'WRITE', color: 'var(--accent)', verb: 'wrote to memory' },
  skipped: { label: 'SKIP', color: 'var(--dim)', verb: 'skipped' },
}

/** Compact relative time from a unix-seconds timestamp. */
function timeAgo(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - (ts || 0)))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

/** Small colored dot + uppercase op tag. */
function OpTag({ op }) {
  const s = OP_STYLE[op] || OP_STYLE.skipped
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        color: s.color,
        minWidth: 58,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
      {s.label}
    </span>
  )
}

/** One recorded graph read/write. */
function ActivityRow({ event }) {
  const s = OP_STYLE[event.op] || OP_STYLE.skipped
  const counts = Object.entries(event.counts || {})
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 14,
        padding: '11px 14px',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${s.color}`,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface)',
      }}
    >
      <OpTag op={event.op} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{event.source}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--muted)' }}>
            {event.fn}
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--dim)' }}>· {timeAgo(event.ts)}</span>
        </div>
        <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>{event.detail}</span>
        {counts.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 2 }}>
            {counts.map(([k, v]) => (
              <span
                key={k}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--muted)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '1px 7px',
                }}
              >
                {k.replace(/_/g, ' ')} {v}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Live pulse dot for the "LIVE" indicator (honours reduced motion). */
function LiveDot() {
  return (
    <>
      <style>{`
        @keyframes dbPulse { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } }
        @media (prefers-reduced-motion: reduce) { .db-live-dot { animation: none !important } }
      `}</style>
      <span
        className="db-live-dot"
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: 'var(--accent)',
          animation: 'dbPulse 1.4s ease-in-out infinite',
          flexShrink: 0,
        }}
      />
    </>
  )
}

/** Legend chip per node type, derived from graph stats. */
function GraphLegend({ stats }) {
  const types = Object.keys(stats || {}).filter((k) => k !== 'edges')
  if (!types.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14 }}>
      {types.map((t) => (
        <span
          key={t}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--muted)' }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: 'var(--surface-raised)',
              border: '1.5px solid var(--ink)',
              flexShrink: 0,
            }}
          />
          {t} · {stats[t]}
        </span>
      ))}
    </div>
  )
}

function ConnectionPill({ health }) {
  const data = health.data
  if (!data) return <Pill label="Neo4j" value="checking…" />
  if (data.online) return <Pill label="Neo4j" value="online" tone="accent" />
  if (data.configured) return <Pill label="Neo4j" value="offline" />
  return <Pill label="Graph" value="not configured" />
}

/** DB / Memory metrics strip — graph size + read/write tallies. */
function StatStrip({ graph, activity }) {
  const g = graph.data
  const a = activity.data
  const stat = (value, label, tone) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <MetricNumber value={value} size="lg" tone={tone} />
      <SectionLabel style={{ fontSize: 10 }}>{label}</SectionLabel>
    </div>
  )
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap' }}>
      {stat(g ? g.nodeCount : '—', 'Entities (nodes)', 'ink')}
      {stat(g ? g.edgeCount : '—', 'Relationships (edges)', 'accent')}
      {g && g.factCount > 0 && stat(g.factCount, 'Facts tracked', 'muted')}
      {stat(a ? a.reads : '—', 'Memory reads', 'ink')}
      {stat(a ? a.writes : '—', 'Log writes', 'accent')}
    </div>
  )
}

/**
 * DB / Memory tab — the judge-facing proof that the agents share one memory.
 *
 * Shows the Neo4j connection, live counts, a real-time feed of every read from /
 * write to the canon graph (attributed to the agent that did it), and the graph
 * itself. Run any lens in another tab, come here, and watch the reads/writes land.
 */
export default function DbMemoryTab({ activity, health, graph, refresh, live, setLive }) {
  const a = activity.data
  const g = graph.data
  const firstLoad = !a && activity.loading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, paddingTop: 32 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap', justifyContent: 'space-between' }}>
        <div style={{ maxWidth: 640 }}>
          <SectionLabel style={{ marginBottom: 8 }}>Shared memory · live</SectionLabel>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
            Every row below is a real query against the Neo4j knowledge graph. Agents{' '}
            <strong style={{ color: 'var(--ink)' }}>read</strong> the shared story canon before they
            react, and <strong style={{ color: 'var(--accent-text-sm)' }}>write</strong> their
            verdicts and new canon back. This is the proof they are stateful, not amnesiac.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <ConnectionPill health={health} />
          <Button variant={live ? 'primary' : 'secondary'} size="sm" onClick={() => setLive(!live)}>
            {live && <LiveDot />}
            {live ? 'Live' : 'Paused'}
          </Button>
          <Button variant="secondary" size="sm" onClick={refresh}>
            Refresh
          </Button>
        </div>
      </div>

      <StatStrip graph={graph} activity={activity} />

      {/* Activity feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <SectionLabel>Activity feed — reads &amp; writes</SectionLabel>
        {activity.error && <ErrorState message={activity.error} />}
        {firstLoad && <LoadingState label="Reading the activity log…" />}
        {a && a.isEmpty && (
          <EmptyState
            title="No activity yet"
            hint="Run a lens (Writers Room, Audience, or the Showrunner agent) in another tab, then come back — every memory read and log write shows up here live."
          />
        )}
        {a && !a.isEmpty && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {a.events.map((e) => (
              <ActivityRow key={e.seq} event={e} />
            ))}
          </div>
        )}
      </div>

      {/* Graph snapshot */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <SectionLabel>The graph right now</SectionLabel>
        {graph.error && <ErrorState message={graph.error} />}
        {g && g.isEmpty && (
          <EmptyState
            title="Graph is empty"
            hint="Ingest an episode in the Story Canon tab to build the shared memory."
          />
        )}
        {g && !g.isEmpty && (
          <>
            <GraphLegend stats={g.stats} />
            <SurfaceCard style={{ padding: 'var(--space-4)' }}>
              <GraphCanvas data={g} />
            </SurfaceCard>
          </>
        )}
      </div>
    </div>
  )
}
