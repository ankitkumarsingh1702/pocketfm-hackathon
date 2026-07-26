import { useState } from 'react'

import { Button, GraphCanvas, GraphLegend, MetricNumber, Pill, SurfaceCard } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Build-time fallback if the backend health payload has no browser_url. */
const NEO4J_BROWSER_FALLBACK = import.meta.env.VITE_NEO4J_BROWSER_URL || ''

/**
 * Deep-link one canon node into the Neo4j Browser with a prefilled Cypher query
 * that pulls up the node and its neighbourhood — so a judge can click a dot and
 * see it live in the actual database.
 */
function neo4jNodeUrl(browserUrl, nodeId) {
  if (!browserUrl || !nodeId) return null
  const key = String(nodeId).replace(/\\/g, '\\\\').replace(/'/g, "\\'")
  const cypher = `MATCH (n:Canon {key:'${key}'})-[r]-(m) RETURN n, r, m`
  const arg = encodeURIComponent(cypher)
  // Hosted Browser already carries ?connectURL=…; a self-hosted origin needs
  // the /browser/ app path added.
  return browserUrl.includes('?')
    ? `${browserUrl}&cmd=edit&arg=${arg}`
    : `${browserUrl.replace(/\/+$/, '')}/browser/?cmd=edit&arg=${arg}`
}

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
  read: { label: 'READ', color: 'var(--ink)' },
  write: { label: 'WRITE', color: 'var(--accent)' },
  skipped: { label: 'SKIP', color: 'var(--dim)' },
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
              <span key={k} style={chipStyle}>
                {k.replace(/_/g, ' ')} {v}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const chipStyle = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  color: 'var(--muted)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '1px 7px',
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
          background: '#fff',
          animation: 'dbPulse 1.4s ease-in-out infinite',
          flexShrink: 0,
        }}
      />
    </>
  )
}

function ConnectionPill({ health }) {
  const data = health.data
  if (!data) return <Pill label="Neo4j" value="checking…" />
  if (data.online) return <Pill label="Neo4j" value="online" tone="accent" />
  if (data.configured) return <Pill label="Neo4j" value="offline" />
  return <Pill label="Graph" value="not configured" />
}

/**
 * "Open in Neo4j" — the arrow next to the status pill that jumps to the live
 * database, so you can show the real graph in Neo4j during a demo. Uses the URL
 * the backend derives from NEO4J_URI, falling back to a build-time override.
 * Styled to match the secondary buttons in the same toolbar.
 */
function Neo4jLink({ health }) {
  const data = health.data
  const url = (data && data.browser_url) || NEO4J_BROWSER_FALLBACK
  if (!url) return null
  return (
    <>
      <style>{`
        .db-neo4j-link { transition: background var(--dur-fast) var(--ease-standard); }
        .db-neo4j-link:hover { background: var(--surface); }
      `}</style>
      <a
        className="db-neo4j-link"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Open the Neo4j database in a new tab"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 7,
          minHeight: 36,
          padding: '8px 14px',
          border: '1px solid var(--ink)',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--surface-raised)',
          color: 'var(--ink)',
          fontFamily: 'var(--font-sans)',
          fontSize: 13,
          fontWeight: 600,
          textDecoration: 'none',
          whiteSpace: 'nowrap',
          boxSizing: 'border-box',
        }}
      >
        Open in Neo4j
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          <path
            d="M7 17L17 7M17 7H8M17 7V16"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </a>
    </>
  )
}

/** One clickable stat tile — the entry point to a drill-down. */
function StatTile({ value, label, tone, active, disabled, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        alignItems: 'flex-start',
        textAlign: 'left',
        background: active ? 'var(--surface)' : 'transparent',
        border: `1px solid ${active ? 'var(--border)' : 'transparent'}`,
        borderRadius: 'var(--radius-md)',
        padding: '10px 14px',
        cursor: disabled ? 'default' : 'pointer',
        boxShadow: active ? 'var(--shadow-sm)' : 'none',
        minWidth: 104,
      }}
    >
      <MetricNumber value={value} size="lg" tone={tone} />
      <span
        className="label-upper"
        style={{ fontSize: 10, color: active ? 'var(--ink)' : 'var(--muted)' }}
      >
        {label}
      </span>
    </button>
  )
}

// --- drill-down detail views -----------------------------------------------

const TYPE_ORDER = ['Character', 'Location', 'PlotThread', 'Clue', 'Theme', 'Episode', 'AudienceSegment']

function EntityRow({ node }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 3,
        padding: '10px 14px',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{node.name}</span>
        <span style={{ ...chipStyle }}>{node.id}</span>
      </div>
      {node.description && (
        <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>{node.description}</span>
      )}
    </div>
  )
}

/** Entities grouped by type. */
function NodesDetail({ graph }) {
  const g = graph.data
  if (!g || !g.entities || !g.entities.length) {
    return <EmptyState title="No entities yet" hint="Ingest an episode in the Story Canon tab to build the canon." />
  }
  const byType = {}
  for (const n of g.entities) (byType[n.label] || (byType[n.label] = [])).push(n)
  const types = Object.keys(byType).sort(
    (a, b) => (TYPE_ORDER.indexOf(a) + 1 || 99) - (TYPE_ORDER.indexOf(b) + 1 || 99),
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {types.map((t) => (
        <div key={t} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SectionLabel>
            {t} · {byType[t].length}
          </SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {byType[t].map((n) => (
              <EntityRow key={n.id} node={n} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Relationships (edges) — how entities connect, and why. */
function EdgesDetail({ graph }) {
  const rels = (graph.data && graph.data.relationships) || []
  if (!rels.length) {
    return <EmptyState title="No relationships yet" hint="Ingest an episode to connect the canon." />
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rels.map((r, i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            padding: '10px 14px',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{r.source}</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--accent-text-sm)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-pill)',
                padding: '2px 9px',
              }}
            >
              {r.type.replace(/_/g, ' ')}
            </span>
            <span style={{ color: 'var(--dim)' }}>→</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{r.target}</span>
          </div>
          {r.detail && (
            <span style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>{r.detail}</span>
          )}
        </div>
      ))}
    </div>
  )
}

/** Facts + structural contradictions + dangling clues. */
function FactsDetail({ facts }) {
  const f = facts.data
  if (facts.loading && !f) return <LoadingState label="Traversing the canon for facts…" />
  if (facts.error) return <ErrorState message={facts.error} />
  if (!f || f.isEmpty) {
    return <EmptyState title="No facts yet" hint="Ingest an episode — atomic facts power the contradiction checks." />
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
      {f.conflicts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SectionLabel style={{ color: 'var(--accent-text-sm)' }}>
            Contradictions · {f.conflicts.length}
          </SectionLabel>
          {f.conflicts.map((c, i) => (
            <div
              key={i}
              style={{
                padding: '10px 14px',
                border: '1px solid var(--border)',
                borderLeft: '3px solid var(--accent)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                fontSize: 13.5,
                color: 'var(--ink)',
                lineHeight: 1.5,
              }}
            >
              <strong>{c.subject}</strong> · {c.predicate}:{' '}
              <span style={{ color: 'var(--accent-text-sm)', fontWeight: 600 }}>“{c.a}”</span> vs{' '}
              <span style={{ color: 'var(--accent-text-sm)', fontWeight: 600 }}>“{c.b}”</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <SectionLabel>Facts · {f.facts.length}</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {f.facts.map((x, i) => (
            <div
              key={i}
              style={{
                padding: '9px 14px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                fontSize: 13.5,
                color: 'var(--ink)',
              }}
            >
              <strong>{x.subject}</strong>{' '}
              <span style={{ color: 'var(--muted)' }}>· {x.predicate} =</span> {x.object}
            </div>
          ))}
        </div>
      </div>

      {f.dangling.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SectionLabel>Dangling clues · {f.dangling.length}</SectionLabel>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.7 }}>
            {f.dangling.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Read or write events filtered from the activity feed. */
function EventsDetail({ activity, op }) {
  const events = ((activity.data && activity.data.events) || []).filter((e) => e.op === op)
  if (!events.length) {
    return (
      <EmptyState
        title={op === 'read' ? 'No memory reads yet' : 'No log writes yet'}
        hint="Run a lens (Writers Room, Audience, or the Showrunner agent) and it will appear here."
      />
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {events.map((e) => (
        <ActivityRow key={e.seq} event={e} />
      ))}
    </div>
  )
}

const DETAIL_TITLE = {
  nodes: 'Entities — every node in the graph',
  edges: 'Relationships — how entities connect, and why',
  facts: 'Facts & contradictions',
  reads: 'Memory reads — who read what, when',
  writes: 'Log writes — who wrote what, when',
}

/**
 * DB / Memory tab — the judge-facing proof that the agents share one memory.
 *
 * The five headline numbers are clickable: each opens a full drill-down so
 * nothing is "just a number" — you can inspect every entity, every relationship
 * (and why it was made), every fact and contradiction, and every read/write
 * with the agent that did it.
 */
export default function DbMemoryTab({
  activity,
  health,
  graph,
  facts,
  refresh,
  live,
  setLive,
  scope,
  setScope,
}) {
  const [selected, setSelected] = useState(null)
  const a = activity.data
  const g = graph.data
  const firstLoad = !a && activity.loading
  const browserUrl = (health.data && health.data.browser_url) || NEO4J_BROWSER_FALLBACK

  const tiles = [
    { key: 'nodes', value: g ? g.nodeCount : '—', label: 'Entities (nodes)', tone: 'ink' },
    { key: 'edges', value: g ? g.edgeCount : '—', label: 'Relationships (edges)', tone: 'accent' },
    { key: 'facts', value: g ? g.factCount : '—', label: 'Facts tracked', tone: 'muted' },
    { key: 'reads', value: a ? a.reads : '—', label: 'Memory reads', tone: 'ink' },
    { key: 'writes', value: a ? a.writes : '—', label: 'Log writes', tone: 'accent' },
  ]

  const toggle = (key) => setSelected((cur) => (cur === key ? null : key))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, paddingTop: 4 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap', justifyContent: 'space-between' }}>
        <div style={{ maxWidth: 640 }}>
          <SectionLabel style={{ marginBottom: 8 }}>Shared memory · live</SectionLabel>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
            Every row is a real query against the Neo4j knowledge graph. Agents{' '}
            <strong style={{ color: 'var(--ink)' }}>read</strong> the shared story canon before they
            react, and <strong style={{ color: 'var(--accent-text-sm)' }}>write</strong> their
            verdicts and new canon back. Tap any number below to inspect exactly what is in the graph
            and who touched it.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <ConnectionPill health={health} />
          <Neo4jLink health={health} />
          <Button variant={live ? 'primary' : 'secondary'} size="sm" onClick={() => setLive(!live)}>
            {live && <LiveDot />}
            {live ? 'Live' : 'Paused'}
          </Button>
          <Button variant="secondary" size="sm" onClick={refresh}>
            Refresh
          </Button>
        </div>
      </div>

      <div
        aria-label="Canon graph scope"
        style={{
          display: 'inline-flex',
          alignSelf: 'flex-start',
          padding: 4,
          gap: 4,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--surface-raised)',
        }}
      >
        {[
          ['session', 'Your story'],
          ['full', 'Full canon'],
        ].map(([value, label]) => {
          const active = scope === value
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              onClick={() => setScope(value)}
              style={{
                minHeight: 44,
                padding: '8px 16px',
                border: active ? '1px solid var(--ink)' : '1px solid transparent',
                borderRadius: 'var(--radius-sm)',
                background: active ? 'var(--ink)' : 'transparent',
                color: active ? 'white' : 'var(--muted)',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                fontWeight: 650,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          )
        })}
      </div>
      <p style={{ margin: '-22px 0 0', fontSize: 12.5, lineHeight: 1.55, color: 'var(--muted)' }}>
        {scope === 'session'
          ? 'Only canon ingested in this browser tab. Seeded ANDHERA data is excluded.'
          : 'All persisted canon, including the seeded ANDHERA demo and every session.'}
      </p>

      {/* Clickable stat strip */}
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 8, flexWrap: 'wrap', marginLeft: -14 }}>
        {tiles.map((t) => (
          <StatTile
            key={t.key}
            value={t.value}
            label={t.label}
            tone={t.tone}
            active={selected === t.key}
            disabled={t.value === '—'}
            onClick={() => toggle(t.key)}
          />
        ))}
      </div>

      {selected ? (
        /* Drill-down for the selected tile */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
              ← Back
            </Button>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>
              {DETAIL_TITLE[selected]}
            </span>
          </div>
          {selected === 'nodes' && <NodesDetail graph={graph} />}
          {selected === 'edges' && <EdgesDetail graph={graph} />}
          {selected === 'facts' && <FactsDetail facts={facts} />}
          {selected === 'reads' && <EventsDetail activity={activity} op="read" />}
          {selected === 'writes' && <EventsDetail activity={activity} op="write" />}
        </div>
      ) : (
        /* Overview: live feed + graph snapshot */
        <>
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

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <SectionLabel>The graph right now</SectionLabel>
            {graph.error && <ErrorState message={graph.error} />}
            {g && g.isEmpty && (
              <EmptyState
                title={scope === 'session' ? 'Your story has not been ingested yet' : 'Graph is empty'}
                hint={
                  scope === 'session'
                    ? 'Ingest the current episode in Story Canon. The seeded demo stays hidden here.'
                    : 'Ingest an episode in the Story Canon tab to build shared memory.'
                }
              />
            )}
            {g && !g.isEmpty && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  <GraphLegend stats={g.stats} />
                  {browserUrl && (
                    <span style={{ fontSize: 12, color: 'var(--dim)' }}>· tap a node to open it in Neo4j</span>
                  )}
                </div>
                <SurfaceCard style={{ padding: 'var(--space-4)', background: 'var(--surface-raised)' }}>
                  <GraphCanvas
                    data={g}
                    nodeHref={browserUrl ? (node) => neo4jNodeUrl(browserUrl, node.id) : undefined}
                  />
                </SurfaceCard>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
