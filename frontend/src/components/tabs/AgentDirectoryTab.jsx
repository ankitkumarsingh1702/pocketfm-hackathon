import { useNavigate } from 'react-router-dom'

import { AGENTS, PERSONA_MODEL } from '../../config/constants'
import { audienceSummary, displayGenre, effectiveTemp } from '../../lib/agents'
import { groupActivityBySource, initialsFor, timeAgo } from '../../utils/agentDirectory'
import { Button, Disclosure, MetricNumber, Pill } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Section heading in the studio's uppercase-label style. */
function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

/** Read/write/skip visual language, shared with the DB / Memory feed. */
const OP_STYLE = {
  read: { label: 'READ', color: 'var(--ink)' },
  write: { label: 'WRITE', color: 'var(--accent)' },
  skipped: { label: 'SKIP', color: 'var(--dim)' },
}

/** Small colored dot + uppercase op tag. */
function OpTag({ op }) {
  const s = OP_STYLE[op] || OP_STYLE.skipped
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: '0.04em',
        color: s.color,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
      {s.label}
    </span>
  )
}

/** Initials monogram avatar. `hub` gives it the soft-red highlight treatment. */
function Monogram({ name, hub = false }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 40,
        height: 40,
        flexShrink: 0,
        borderRadius: 'var(--radius-sm)',
        fontFamily: 'var(--font-mono)',
        fontSize: 14,
        fontWeight: 600,
        letterSpacing: '0.02em',
        color: hub ? 'var(--accent-text-sm)' : 'var(--ink)',
        background: hub ? 'var(--surface-raised)' : 'var(--surface)',
        border: `1px solid ${hub ? 'var(--accent-line)' : 'var(--border)'}`,
      }}
    >
      {initialsFor(name)}
    </span>
  )
}

const chipBase = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  fontSize: 11.5,
  fontWeight: 500,
  lineHeight: 1.2,
  borderRadius: 'var(--radius-pill)',
  padding: '4px 10px',
  border: '1px solid var(--border)',
  color: 'var(--muted)',
  background: 'var(--surface-raised)',
  whiteSpace: 'nowrap',
}

/** Neutral chip for a method, genre or trait. */
function Chip({ children, mono = false }) {
  return (
    <span style={{ ...chipBase, ...(mono ? { fontFamily: 'var(--font-mono)', fontSize: 11 } : null) }}>
      {children}
    </span>
  )
}

/** Reads / writes indicators — dot + word, never colour alone. */
function MemoryFlags({ reads, writes }) {
  const flag = (color, text) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {text}
    </span>
  )
  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
      {reads && flag('var(--ink)', 'Reads memory')}
      {writes && flag('var(--accent)', 'Writes memory')}
      {!reads && !writes && flag('var(--dim)', 'No memory access')}
    </div>
  )
}

/** One agent's live memory activity, joined from the feed by `source`. */
function LiveActivity({ stats }) {
  if (!stats || stats.total === 0) {
    return (
      <div style={{ fontSize: 12.5, color: 'var(--dim)', lineHeight: 1.5 }}>
        No memory activity yet — run it to see live reads &amp; writes.
      </div>
    )
  }
  const last = stats.last
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>
        <strong style={{ color: 'var(--ink)', fontWeight: 700 }}>{stats.total}</strong> memory ops
        {' · '}
        {stats.reads} read{stats.reads === 1 ? '' : 's'} · {stats.writes} write
        {stats.writes === 1 ? '' : 's'}
      </div>
      {last && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <OpTag op={last.op} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)' }}>
            {last.fn}
          </span>
          <span style={{ fontSize: 11, color: 'var(--dim)' }}>· {timeAgo(last.ts)}</span>
        </div>
      )}
    </div>
  )
}

/** Non-clickable stat cell for the shared-memory strip. */
function StatCell({ value, label, tone = 'ink' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 88 }}>
      <MetricNumber value={value} size="md" tone={tone} />
      <span className="label-upper" style={{ fontSize: 10, color: 'var(--muted)' }}>
        {label}
      </span>
    </div>
  )
}

function ConnectionPill({ health }) {
  const data = health && health.data
  if (!data) return <Pill label="Neo4j" value="checking…" />
  if (data.online) return <Pill label="Neo4j" value="online" tone="accent" />
  if (data.configured) return <Pill label="Neo4j" value="offline" />
  return <Pill label="Graph" value="not configured" />
}

const cardStyle = (hub) => ({
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  padding: 18,
  borderRadius: 'var(--radius-md)',
  border: `1px solid ${hub ? 'var(--accent-line)' : 'var(--border)'}`,
  background: hub ? 'var(--accent-soft)' : 'var(--surface-raised)',
})

/** One reasoning-agent profile. */
function AgentCard({ agent, stats, onOpen }) {
  const insideCanon = agent.route === '/canon' && agent.id !== 'canon'
  return (
    <div style={cardStyle(agent.hub)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Monogram name={agent.name} hub={agent.hub} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 15.5, fontWeight: 700, color: 'var(--ink)' }}>{agent.name}</span>
            {agent.hub && (
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  color: 'var(--accent-text-sm)',
                  border: '1px solid var(--accent-line)',
                  borderRadius: 'var(--radius-pill)',
                  padding: '2px 8px',
                }}
              >
                Shared memory
              </span>
            )}
          </div>
          {insideCanon && (
            <span style={{ fontSize: 11.5, color: 'var(--dim)' }}>Runs inside Story Canon</span>
          )}
        </div>
      </div>

      <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.55 }}>{agent.role}</p>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {agent.methods.map((m) => (
          <Chip key={m}>{m}</Chip>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <MemoryFlags reads={agent.reads} writes={agent.writes} />
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5 }}>
          {agent.memory}
        </p>
      </div>

      <div
        style={{
          marginTop: 'auto',
          paddingTop: 12,
          borderTop: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <LiveActivity stats={stats} />
        <Button variant="secondary" size="sm" onClick={onOpen}>
          Open
        </Button>
      </div>
    </div>
  )
}

/** One persona (expert or audience listener) profile. */
function PersonaCard({ persona }) {
  const isAudience = persona.kind === 'audience'
  const subtitle = isAudience ? persona.segment || 'Audience listener' : persona.role || 'Expert'
  const meta = isAudience ? audienceSummary(persona) : ''
  const genres = (persona.genres || []).slice(0, 4)
  const traits = (persona.traits || []).slice(0, 4)
  const model = PERSONA_MODEL[persona.kind]

  return (
    <div style={cardStyle(false)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Monogram name={persona.name} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>{persona.name}</div>
          <div style={{ fontSize: 12.5, color: 'var(--accent-text-sm)', fontWeight: 600 }}>{subtitle}</div>
        </div>
      </div>

      {meta && <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>{meta}</div>}

      {genres.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {genres.map((genre) => (
            <Chip key={genre}>{displayGenre(genre)}</Chip>
          ))}
        </div>
      )}

      {traits.length > 0 && (
        <div style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5 }}>
          {traits.join(' · ')}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Chip mono>temp {effectiveTemp(persona).toFixed(1)}</Chip>
        {model && <Chip mono>{model}</Chip>}
      </div>

      {persona.system_prompt && (
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 2 }}>
          <Disclosure
            summary={
              <span className="label-upper" style={{ fontSize: 10.5 }}>
                System prompt
              </span>
            }
          >
            <p
              style={{
                margin: '4px 0 8px',
                fontSize: 12.5,
                color: 'var(--muted)',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
              }}
            >
              {persona.system_prompt}
            </p>
          </Disclosure>
        </div>
      )}
    </div>
  )
}

const gridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(min(280px, 100%), 1fr))',
  gap: 16,
}

/**
 * Agent Directory — a live, jury-facing roster of every agent in the studio.
 *
 * The reasoning agents render instantly from static config, each joined to its
 * real reads/writes in shared memory; the persona cast (experts + audience) is
 * fetched live from `/api/personas`, every card exposing that persona's own
 * system prompt — its character memory. One knowledge graph sits behind them
 * all, summarised at the top.
 */
export default function AgentDirectoryTab({
  personas,
  activity,
  graph,
  facts,
  health,
  refresh,
  live,
  setLive,
}) {
  const navigate = useNavigate()
  const bySource = groupActivityBySource(activity.data)
  const g = graph.data
  const f = facts.data
  const a = activity.data
  const roster = personas.data

  const dash = (v) => (v === undefined || v === null ? '—' : v)
  const stats = [
    { value: dash(f && f.episodeCount), label: 'Episodes', tone: 'ink' },
    { value: dash(g && g.nodeCount), label: 'Entities', tone: 'ink' },
    { value: dash(g && g.factCount), label: 'Facts', tone: 'muted' },
    { value: dash(a && a.reads), label: 'Memory reads', tone: 'ink' },
    { value: dash(a && a.writes), label: 'Log writes', tone: 'accent' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 36, paddingTop: 4 }}>
      {/* Framing + live controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 16,
          flexWrap: 'wrap',
          justifyContent: 'space-between',
        }}
      >
        <p style={{ margin: 0, maxWidth: 640, fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
          Eight reasoning agents and a cast of personas, all working over{' '}
          <strong style={{ color: 'var(--ink)' }}>one shared knowledge graph</strong>. Each profile
          shows what the agent does, the method it runs, and its real reads and writes to that memory
          — updating live.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <ConnectionPill health={health} />
          <Button variant={live ? 'primary' : 'secondary'} size="sm" onClick={() => setLive(!live)}>
            {live ? 'Live' : 'Paused'}
          </Button>
          <Button variant="secondary" size="sm" onClick={refresh}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Shared-memory strip */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 28,
          padding: '18px 20px',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          background: 'var(--surface)',
        }}
      >
        {stats.map((s) => (
          <StatCell key={s.label} value={s.value} label={s.label} tone={s.tone} />
        ))}
      </div>

      {/* Reasoning agents */}
      <section aria-label="Reasoning agents" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <SectionLabel>Reasoning agents · {AGENTS.length}</SectionLabel>
        <div style={gridStyle}>
          {AGENTS.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              stats={bySource[agent.source]}
              onOpen={() => navigate(agent.route)}
            />
          ))}
        </div>
      </section>

      {/* Persona cast */}
      <section aria-label="Persona cast" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <SectionLabel>The cast — personas the agents convene</SectionLabel>
          <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.55, maxWidth: 640 }}>
            The Writers&rsquo; Room and Audience Simulator run these personas. Each one&rsquo;s system
            prompt is its character memory — open it to read exactly how it thinks.
          </p>
        </div>

        {personas.error && <ErrorState message={personas.error} />}
        {personas.loading && !roster && <LoadingState label="Loading the persona cast…" />}
        {roster && roster.isEmpty && (
          <EmptyState
            title="No personas found"
            hint="The backend returned an empty roster — check that the persona YAML files are present."
          />
        )}

        {roster && !roster.isEmpty && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <SectionLabel style={{ color: 'var(--muted)' }}>
                Expert panel · {roster.experts.length}
              </SectionLabel>
              <div style={gridStyle}>
                {roster.experts.map((persona) => (
                  <PersonaCard key={persona.id} persona={persona} />
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <SectionLabel style={{ color: 'var(--muted)' }}>
                Audience panel · {roster.audience.length}
              </SectionLabel>
              <div style={gridStyle}>
                {roster.audience.map((persona) => (
                  <PersonaCard key={persona.id} persona={persona} />
                ))}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
