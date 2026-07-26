import { CANON_PANELS } from '../../config/constants'
import { AGENT_NODES, AGENT_NODE_LABELS } from '../../utils/canon'
import HowItWorks from '../HowItWorks'
import { Button, GraphCanvas, GraphLegend, MetricNumber, SurfaceCard, Tabs } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Plain-language "input → what the AI does → output" for each canon panel. */
const HOW_IT_WORKS = {
  graph: [
    { title: 'Paste an episode script', body: 'Drop in an episode — its story becomes structured memory.' },
    {
      title: 'The AI extracts the canon',
      body: 'An LLM pulls out characters, clues, and facts and merges them into the graph as nodes and edges.',
    },
    { title: 'Every agent reads it', body: 'This shared memory is what each agent reads before it reacts.' },
  ],
  holes: [
    { title: 'Paste an episode', body: 'Drop in the new episode script you want to publish.' },
    {
      title: 'Cross-check the whole canon',
      body:
        'We read every fact from all past episodes in the graph and catch contradictions between ' +
        'far-apart episodes — the continuity a human can’t hold across thousands of pages.',
    },
    { title: 'Get ranked fixes', body: 'Each issue cites the exact clashing episodes and a concrete fix.' },
  ],
  planner: [
    { title: 'Give a soft ending', body: 'Paste the episode and the weak ending to improve.' },
    {
      title: 'Search & score endings',
      body:
        'The AI writes several alternative endings and scores each on a simulated listener panel, ' +
        'keeping the best and improving them — a search tree.',
    },
    { title: 'Take the winner', body: 'The highest-scoring cliffhanger, with its hook-score lift.' },
  ],
  agent: [
    { title: 'Give an episode', body: 'Paste the episode (and optionally a weak beat to fix).' },
    {
      title: 'The agent runs the loop',
      body:
        'One agent reads canon → checks continuity → simulates the audience → decides if listeners ' +
        'will drop off → rewrites → re-tests — until it converges.',
    },
    { title: 'Get a fixed cut', body: 'A higher-retention rewrite, with the lift and contradictions fixed.' },
  ],
  mdp: [
    { title: 'Give a beat to improve', body: 'Paste the episode and the ending/beat to optimize.' },
    {
      title: 'The AI learns by trying',
      body:
        'It treats “which next beat?” as a decision: it tries candidate beats, scores each by ' +
        'simulated audience reaction (the reward), and keeps picking better ones over a few rounds.',
    },
    { title: 'Take the best beat', body: 'The beat with the highest reward, plus how the reward climbed.' },
  ],
}

/** Section heading in the studio's uppercase-label style. */
function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

const inputStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 14,
  color: 'var(--ink)',
  background: 'var(--surface-raised)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '10px 12px',
  width: '100%',
  boxSizing: 'border-box',
}

/** Type label + display order for extracted entities. */
const ENTITY_GROUPS = [
  ['Character', 'Characters'],
  ['Location', 'Locations'],
  ['PlotThread', 'Plot threads'],
  ['Clue', 'Clues'],
  ['Theme', 'Themes'],
]

const chip = {
  fontFamily: 'var(--font-sans)',
  fontSize: 12.5,
  fontWeight: 600,
  color: 'var(--ink)',
  background: 'var(--surface-raised)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-pill)',
  padding: '4px 11px',
  lineHeight: 1.3,
}

/** One extracted entity group (e.g. "Characters · 3" + name chips). */
function EntityGroup({ label, items }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <SectionLabel style={{ fontSize: 10 }}>
        {label} · {items.length}
      </SectionLabel>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {items.map((e) => (
          <span key={e.key || e.name} style={chip} title={e.description || ''}>
            {e.name}
          </span>
        ))}
      </div>
    </div>
  )
}

/**
 * Live "as you type" extraction — shows, in real time, the entities, connections,
 * and atomic facts the agents will remember from THIS script. Nothing is written
 * until you ingest; this is the proof the canon is built from your own words.
 */
function LiveExtractionPanel({ preview }) {
  const { loading, data, error } = preview
  if (!loading && !data && !error) return null

  const ex = data?.extraction
  const entities = ex?.entities || []
  const relations = ex?.relations || []
  const facts = ex?.facts || []
  const nameByKey = {}
  for (const e of entities) nameByKey[e.key] = e.name

  const byType = {}
  for (const e of entities) (byType[e.type] || (byType[e.type] = [])).push(e)
  const groups = [
    ...ENTITY_GROUPS.filter(([t]) => byType[t]?.length).map(([t, l]) => [l, byType[t]]),
    ...Object.keys(byType)
      .filter((t) => !ENTITY_GROUPS.some(([k]) => k === t))
      .map((t) => [t, byType[t]]),
  ]
  const hasContent = entities.length > 0 || facts.length > 0
  const firstLoad = loading && !data

  return (
    <SurfaceCard style={{ marginTop: 4, background: 'var(--surface)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <SectionLabel style={{ fontSize: 11 }}>Live extraction · what the agents will remember</SectionLabel>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
          {firstLoad
            ? 'reading your script…'
            : data
              ? `${data.entity_count} entities · ${data.relation_count} connections · ${data.fact_count} facts${loading ? ' · updating…' : ''}`
              : ''}
        </span>
      </div>

      {firstLoad && <LoadingState label="Extracting canon from your script…" />}
      {error && !data && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          Live preview unavailable right now — ingesting still works.
        </span>
      )}
      {data && !hasContent && !loading && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          No structured canon found yet — name a character, place, or a concrete detail and it will appear here.
        </span>
      )}

      {hasContent && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {groups.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {groups.map(([label, items]) => (
                <EntityGroup key={label} label={label} items={items} />
              ))}
            </div>
          )}

          {relations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <SectionLabel style={{ fontSize: 10 }}>Connections · {relations.length}</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {relations.slice(0, 6).map((r, i) => (
                  <div key={i} style={{ fontSize: 13, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600 }}>{nameByKey[r.source_key] || r.source_key}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-text-sm)' }}>
                      {r.type.replace(/_/g, ' ').toLowerCase()}
                    </span>
                    <span style={{ color: 'var(--dim)' }}>→</span>
                    <span style={{ fontWeight: 600 }}>{nameByKey[r.target_key] || r.target_key}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {facts.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <SectionLabel style={{ fontSize: 10 }}>Atomic facts · {facts.length}</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {facts.slice(0, 12).map((f, i) => (
                  <div
                    key={i}
                    style={{
                      padding: '8px 12px',
                      border: '1px solid var(--border)',
                      borderLeft: '3px solid var(--accent)',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface-raised)',
                      fontSize: 13, color: 'var(--ink)', lineHeight: 1.45,
                    }}
                  >
                    <strong>{nameByKey[f.subject_key] || f.subject_key}</strong>{' '}
                    <span style={{ color: 'var(--muted)' }}>· {f.predicate} =</span> {f.object}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </SurfaceCard>
  )
}

/** Composer: title/episode/text + the "Ingest episode" action + live preview. */
function CanonComposer({
  title,
  setTitle,
  episode,
  setEpisode,
  text,
  setText,
  ingest,
  ingesting,
  canIngest,
  ingestResult,
  ingestError,
  preview,
  isSample,
  clearText,
  resetSession,
  resetting,
}) {
  return (
    <SurfaceCard>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <SectionLabel>Build the canon</SectionLabel>
        {isSample && (
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            Showing a sample script ·{' '}
            <button
              type="button"
              onClick={clearText}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                font: 'inherit', color: 'var(--accent-text-sm)', fontWeight: 600,
              }}
            >
              clear and write your own
            </button>
          </span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <input
          style={{ ...inputStyle, flex: '2 1 220px' }}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Show title"
          aria-label="Show title"
        />
        <input
          style={{ ...inputStyle, flex: '1 1 140px' }}
          value={episode}
          onChange={(e) => setEpisode(e.target.value)}
          placeholder="Episode"
          aria-label="Episode"
        />
      </div>
      <textarea
        style={{ ...inputStyle, minHeight: 160, resize: 'vertical', lineHeight: 1.6 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste an episode script — its characters, clues, and plot threads become canon as you type."
        aria-label="Episode script"
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 14, flexWrap: 'wrap' }}>
        <Button onClick={ingest} disabled={!canIngest}>
          {ingesting ? 'Ingesting…' : 'Ingest episode into canon'}
        </Button>
        {ingestResult && (
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Wrote <strong style={{ color: 'var(--ink)' }}>{ingestResult.nodes_added}</strong> nodes,{' '}
            <strong style={{ color: 'var(--ink)' }}>{ingestResult.edges_added}</strong> edges,{' '}
            <strong style={{ color: 'var(--ink)' }}>{ingestResult.facts_added ?? 0}</strong> facts to shared memory
            {ingestResult.entities?.length ? ` · ${ingestResult.entities.slice(0, 6).join(', ')}` : ''}
          </span>
        )}
        {ingestResult && (
          <button
            type="button"
            onClick={resetSession}
            disabled={resetting}
            style={{
              background: 'none', border: 'none', padding: 0,
              cursor: resetting ? 'default' : 'pointer',
              font: 'inherit', fontSize: 13, color: 'var(--muted)', textDecoration: 'underline',
            }}
            title="Removes only what you added this session — the demo canon is untouched"
          >
            {resetting ? 'Clearing…' : "Clear this session's canon"}
          </button>
        )}
        {ingestError && <span style={{ fontSize: 13, color: 'var(--danger)' }}>{ingestError}</span>}
      </div>

      <LiveExtractionPanel preview={preview} />
    </SurfaceCard>
  )
}

/** The Canon Graph panel: the node-link view + a statefulness proof strip. */
function CanonGraphPanel({ graph, refresh }) {
  if (graph.loading) return <LoadingState label="Reading the story canon…" />
  if (graph.error) return <ErrorState message={graph.error} />
  if (!graph.data || graph.data.isEmpty) {
    return (
      <EmptyState
        title="No canon yet"
        hint="Ingest an episode above to build the shared story graph the agents remember."
      />
    )
  }

  const { nodeCount, edgeCount, factCount, stats } = graph.data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <MetricNumber value={nodeCount} size="lg" tone="ink" />
          <SectionLabel style={{ fontSize: 10 }}>Entities (nodes)</SectionLabel>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <MetricNumber value={edgeCount} size="lg" tone="accent" />
          <SectionLabel style={{ fontSize: 10 }}>Relationships (edges)</SectionLabel>
        </div>
        {factCount > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={factCount} size="lg" tone="muted" />
            <SectionLabel style={{ fontSize: 10 }}>Facts tracked</SectionLabel>
          </div>
        )}
        <Button variant="secondary" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>

      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', maxWidth: 620 }}>
        This graph is the <strong style={{ color: 'var(--ink)' }}>shared memory</strong> every
        agent reads before it reacts. The agents are stateful — they remember characters, clues,
        and plot threads across episodes, and write their verdicts back here. Not stateless. Not
        amnesiac.
      </p>

      <GraphLegend stats={stats} />
      <SurfaceCard style={{ padding: 'var(--space-4)', background: 'var(--surface-raised)' }}>
        <GraphCanvas data={graph.data} />
      </SurfaceCard>
    </div>
  )
}

const SEVERITY = {
  high: { color: 'var(--danger)', label: 'High' },
  medium: { color: 'var(--warning)', label: 'Medium' },
  low: { color: 'var(--muted)', label: 'Low' },
}

/** Pale-red pill that makes the cross-episode citation (e.g. "Ep 4 ↔ Ep 41") pop. */
const CITE_PILL = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--red-ink)',
  background: 'var(--danger-bg)',
  border: '1px solid var(--danger)',
  borderRadius: 'var(--radius-pill)',
  padding: '2px 10px',
  letterSpacing: '0.02em',
}

function SeverityTag({ severity }) {
  const s = SEVERITY[severity] || SEVERITY.low
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        color: s.color,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color }} />
      {s.label}
    </span>
  )
}

/** Plot Hole Hunter panel — graph-grounded continuity issues. */
function PlotHolesPanel({ plotHoles, runPlotHoles }) {
  const { loading, error, data } = plotHoles
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={runPlotHoles} disabled={loading}>
          {loading ? 'Scanning…' : 'Scan for plot holes'}
        </Button>
        {data && (
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            {data.canonUsed ? 'Grounded in the canon graph' : 'Canon empty — text-only scan'} · cross-checked{' '}
            {data.episodesScanned} episodes · {data.factsScanned} facts · ≈{data.pagesEstimate} pages
          </span>
        )}
      </div>

      {loading && <LoadingState label="Traversing the canon for contradictions…" />}
      {error && <ErrorState message={error} />}
      {data && data.isEmpty && (
        <EmptyState title="No plot holes found" hint="The episode is consistent with the canon." />
      )}

      {data && !data.isEmpty && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {data.holes.map((h, i) => (
            <SurfaceCard key={i}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
                <SeverityTag severity={h.severity} />
                <span className="label-upper" style={{ fontSize: 10 }}>
                  {h.kind}
                </span>
                {h.episodes?.length >= 2 ? (
                  <span style={CITE_PILL} title="Contradiction found across these episodes">
                    {h.episodes.join(' ↔ ')}
                  </span>
                ) : (
                  h.location && (
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>· {h.location}</span>
                  )
                )}
              </div>
              <p style={{ margin: '0 0 8px', fontSize: 14, color: 'var(--ink)', lineHeight: 1.55 }}>
                {h.description}
              </p>
              {h.evidence?.length > 0 && (
                <ul style={{ margin: '0 0 8px', paddingLeft: 18, fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
                  {h.evidence.map((e, j) => (
                    <li key={j}>{e}</li>
                  ))}
                </ul>
              )}
              <p style={{ margin: 0, fontSize: 13, color: 'var(--ink)' }}>
                <strong>Fix:</strong> {h.fix}
              </p>
            </SurfaceCard>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Shows whether a planning lens scored against the persisted "Living Audience"
 * population (the same stateful listeners on the Audience tab) or the built-in
 * default archetypes — i.e. the persona↔machinery wiring, made visible.
 */
function AudienceSourceBadge({ source, panelSize }) {
  if (!source) return null
  const living = source === 'living'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 11.5,
        fontWeight: 600,
        color: living ? 'var(--red-ink)' : 'var(--muted)',
        background: living ? 'var(--danger-bg)' : 'var(--surface-raised)',
        border: `1px solid ${living ? 'var(--danger)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-pill)',
        padding: '3px 11px',
      }}
      title={
        living
          ? 'Scored against the persisted Living Audience — the same stateful listeners from the Audience tab.'
          : 'No saved audience yet — scored against built-in listeners. Generate an audience to ground this in your real population.'
      }
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: living ? 'var(--danger)' : 'var(--dim)',
        }}
      />
      {living ? 'Reward model: Living Audience' : 'Reward model: default archetypes'}
      {panelSize ? ` · ${panelSize} listeners` : ''}
    </span>
  )
}

/** Cliffhanger Planner panel — streamed audience-scored beam search. */
function PlannerPanel({ weakExcerpt, setWeakExcerpt, planner, runPlanner }) {
  const ranked = [...planner.candidates].sort((a, b) => b.hookScore - a.hookScore)
  const best = planner.best
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <SectionLabel>Weak ending to improve</SectionLabel>
      <textarea
        style={{ ...inputStyle, minHeight: 100, resize: 'vertical', lineHeight: 1.6 }}
        value={weakExcerpt}
        onChange={(e) => setWeakExcerpt(e.target.value)}
        aria-label="Weak ending"
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={runPlanner} disabled={planner.running}>
          {planner.running ? 'Searching…' : 'Search cliffhangers'}
        </Button>
        <AudienceSourceBadge source={planner.audienceSource} panelSize={planner.panelSize} />
      </div>

      {planner.error && <ErrorState message={planner.error} />}

      {(planner.baseline != null || ranked.length > 0) && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap' }}>
          {planner.baseline != null && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <MetricNumber value={planner.baseline} size="md" tone="muted" />
              <SectionLabel style={{ fontSize: 10 }}>Baseline hook</SectionLabel>
            </div>
          )}
          {best && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <MetricNumber value={best.hookScore} size="lg" tone="accent" />
              <SectionLabel style={{ fontSize: 10 }}>Best · {best.delta > 0 ? `+${best.delta}` : best.delta} lift</SectionLabel>
            </div>
          )}
        </div>
      )}

      {ranked.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {ranked.map((c) => {
            const isBest = best && c.id === best.id
            return (
              <SurfaceCard key={c.id} elevated={isBest} style={{ padding: 'var(--space-4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--ink)' }}>
                    {c.hookScore}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: c.delta >= 0 ? 'var(--accent-text-sm)' : 'var(--muted)' }}>
                    {c.delta > 0 ? `+${c.delta}` : c.delta}
                  </span>
                  <span className="label-upper" style={{ fontSize: 10 }}>
                    depth {c.depth}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
                  {isBest && best.text ? best.text : c.preview}
                </p>
              </SurfaceCard>
            )
          })}
        </div>
      )}
    </div>
  )
}

const STATUS_GLYPH = {
  pending: { glyph: '○', color: 'var(--dim)' },
  running: { glyph: '⟳', color: 'var(--accent)' },
  done: { glyph: '✓', color: 'var(--success)' },
}

/** Showrunner Agent panel — the state-graph loop, streamed node by node. */
function ShowrunnerPanel({ agent, runAgent }) {
  const result = agent.result
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={runAgent} disabled={agent.running}>
          {agent.running ? 'Agent running…' : 'Run showrunner agent'}
        </Button>
        <AudienceSourceBadge source={agent.audienceSource} panelSize={agent.panelSize} />
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          One agent: ingest → check continuity → simulate → decide → fix → re-simulate → converge
        </span>
      </div>

      {agent.error && <ErrorState message={agent.error} />}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {AGENT_NODES.map((n) => {
          const node = agent.nodes[n] || { status: 'pending' }
          const s = STATUS_GLYPH[node.status] || STATUS_GLYPH.pending
          return (
            <div
              key={n}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
                padding: '10px 14px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                background: node.status === 'running' ? 'var(--surface)' : 'transparent',
              }}
            >
              <span style={{ color: s.color, fontFamily: 'var(--font-mono)', fontWeight: 700, width: 16 }}>
                {s.glyph}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                  {AGENT_NODE_LABELS[n] || n}
                </span>
                {node.detail && (
                  <span style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5 }}>
                    {node.detail}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {result && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap', paddingTop: 4 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={result.before_score} size="md" tone="muted" />
            <SectionLabel style={{ fontSize: 10 }}>Hook before</SectionLabel>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={result.after_score} size="lg" tone="accent" />
            <SectionLabel style={{ fontSize: 10 }}>
              Hook after · {result.lift > 0 ? `+${result.lift}` : result.lift} lift
            </SectionLabel>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={`${result.contradictions_fixed}/${result.contradictions_found}`} size="md" tone="ink" />
            <SectionLabel style={{ fontSize: 10 }}>Contradictions fixed</SectionLabel>
          </div>
        </div>
      )}
    </div>
  )
}

/** Small hand-rolled reward-vs-iteration line chart for the MDP panel. */
function RewardCurve({ baseline, steps }) {
  const W = 560
  const H = 200
  const pad = 32
  const pts = [{ i: 0, r: baseline ?? 0 }, ...steps.map((s) => ({ i: s.iteration, r: s.reward }))]
  const maxI = Math.max(1, ...pts.map((p) => p.i))
  const x = (i) => pad + (i / maxI) * (W - 2 * pad)
  const y = (r) => H - pad - (Math.max(0, Math.min(100, r)) / 100) * (H - 2 * pad)
  const line = pts.map((p, k) => `${k === 0 ? 'M' : 'L'}${x(p.i)},${y(p.r)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }} role="img" aria-label="Reward vs iteration">
      <line x1={pad} y1={y(baseline ?? 0)} x2={W - pad} y2={y(baseline ?? 0)} stroke="var(--border)" strokeDasharray="4 4" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
      {pts.map((p, k) => (
        <g key={k}>
          <circle cx={x(p.i)} cy={y(p.r)} r={4} fill="var(--accent)" />
          <text x={x(p.i)} y={y(p.r) - 10} textAnchor="middle" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: 'var(--ink)' }}>
            {p.r}
          </text>
        </g>
      ))}
    </svg>
  )
}

/** Candidate Q-values for one MDP step; the chosen (argmax) action is highlighted. */
function QChips({ values, chosenReward }) {
  if (!values || values.length === 0) return null
  const max = Math.max(...values)
  const target = chosenReward ?? max
  let marked = false
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      {values.map((q, i) => {
        // Highlight the single chosen action (first value equal to the target).
        const chosen = !marked && q === target
        if (chosen) marked = true
        return (
          <span
            key={i}
            title={chosen ? 'Chosen action (argmax reward)' : 'Candidate action Q-value'}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 600,
              color: chosen ? 'var(--red-ink)' : 'var(--muted)',
              background: chosen ? 'var(--danger-bg)' : 'var(--surface-raised)',
              border: `1px solid ${chosen ? 'var(--danger)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-sm)',
              padding: '2px 8px',
            }}
          >
            {q}
          </span>
        )
      })}
    </div>
  )
}

/** Per-iteration MDP trace: the state, the candidate Q-values scored on the
 *  audience, and the discounted one-step look-ahead value of the chosen action. */
function MdpSteps({ steps, discount }) {
  if (!steps || steps.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <SectionLabel style={{ fontSize: 10 }}>Policy trace · state → actions → value</SectionLabel>
      {steps.map((s) => (
        <div
          key={s.iteration}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            padding: '10px 14px',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--accent)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-raised)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span className="label-upper" style={{ fontSize: 10 }}>
              Step {s.iteration}
            </span>
            {s.state && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--muted)' }}>
                {s.state}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>Q(s,a):</span>
            <QChips values={s.qValues} chosenReward={s.reward} />
          </div>
          {s.qChosen != null && (
            <div style={{ fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.5 }}>
              <span style={{ color: 'var(--muted)' }}>Q(s,a*) = reward + γ·V(s′) = </span>
              <strong style={{ fontFamily: 'var(--font-mono)' }}>{s.reward}</strong>
              {s.valueNext != null && discount != null && (
                <>
                  {' '}
                  + {discount}·<strong style={{ fontFamily: 'var(--font-mono)' }}>{s.valueNext}</strong>
                </>
              )}
              {' = '}
              <strong style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-text-sm)' }}>
                {s.qChosen}
              </strong>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/**
 * MDP Optimizer panel — a finite-horizon MDP: the state transitions each step,
 * the audience simulator is the reward model, and the chosen action's value uses
 * a discounted (γ) one-step Bellman look-ahead. Q-values, state, and the
 * discounted return are all surfaced so the "MDP" is provable, not just a label.
 */
function MdpPanel({ mdp, runMdp }) {
  const lift = mdp.final != null && mdp.baseline != null ? Math.round((mdp.final - mdp.baseline) * 10) / 10 : null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={runMdp} disabled={mdp.running}>
          {mdp.running ? 'Optimizing…' : 'Run policy search'}
        </Button>
        <AudienceSourceBadge source={mdp.audienceSource} panelSize={mdp.panelSize} />
      </div>
      <span style={{ fontSize: 13, color: 'var(--muted)' }}>
        State = story-so-far + canon · Action = candidate beat · Reward = simulated hook · γ look-ahead
      </span>

      {mdp.error && <ErrorState message={mdp.error} />}

      {(mdp.baseline != null || mdp.steps.length > 0) && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap' }}>
            {mdp.baseline != null && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <MetricNumber value={mdp.baseline} size="md" tone="muted" />
                <SectionLabel style={{ fontSize: 10 }}>Baseline reward</SectionLabel>
              </div>
            )}
            {mdp.final != null && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <MetricNumber value={mdp.final} size="lg" tone="accent" />
                <SectionLabel style={{ fontSize: 10 }}>
                  Final reward{lift != null ? ` · +${lift}` : ''}
                </SectionLabel>
              </div>
            )}
            {mdp.discountedReturn != null && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <MetricNumber value={mdp.discountedReturn} size="md" tone="ink" />
                <SectionLabel style={{ fontSize: 10 }}>Discounted return</SectionLabel>
              </div>
            )}
          </div>
          {(mdp.policy || mdp.discount != null) && (
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              {mdp.policy ? `policy: ${mdp.policy}` : ''}
              {mdp.discount != null ? `${mdp.policy ? ' · ' : ''}discount γ = ${mdp.discount}` : ''}
            </span>
          )}
          <SurfaceCard style={{ padding: 'var(--space-4)' }}>
            <RewardCurve baseline={mdp.baseline} steps={mdp.steps} />
          </SurfaceCard>
          <MdpSteps steps={mdp.steps} discount={mdp.discount} />
        </>
      )}

      {mdp.best && (
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>Best beat found</SectionLabel>
          <p style={{ margin: 0, fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.6 }}>{mdp.best}</p>
        </div>
      )}
    </div>
  )
}

/**
 * Story Canon tab — the knowledge-graph surface. Self-contained: its own
 * composer + ingest, plus an inner panel switcher for the graph, plot holes,
 * the cliffhanger planner, the showrunner agent, and the MDP optimizer.
 */
export default function StoryCanonTab(props) {
  const { activePanel, setActivePanel, graph, refresh } = props

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, paddingTop: 4 }}>
      <CanonComposer {...props} />

      {CANON_PANELS.length > 1 && (
        <Tabs tabs={CANON_PANELS} active={activePanel} onChange={setActivePanel} />
      )}

      {HOW_IT_WORKS[activePanel] && <HowItWorks steps={HOW_IT_WORKS[activePanel]} />}

      {activePanel === 'graph' && <CanonGraphPanel graph={graph} refresh={refresh} />}
      {activePanel === 'holes' && (
        <PlotHolesPanel plotHoles={props.plotHoles} runPlotHoles={props.runPlotHoles} />
      )}
      {activePanel === 'planner' && (
        <PlannerPanel
          weakExcerpt={props.weakExcerpt}
          setWeakExcerpt={props.setWeakExcerpt}
          planner={props.planner}
          runPlanner={props.runPlanner}
        />
      )}
      {activePanel === 'agent' && <ShowrunnerPanel agent={props.agent} runAgent={props.runAgent} />}
      {activePanel === 'mdp' && <MdpPanel mdp={props.mdp} runMdp={props.runMdp} />}
    </div>
  )
}
