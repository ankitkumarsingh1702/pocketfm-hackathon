import { CANON_PANELS } from '../../config/constants'
import { AGENT_NODES, AGENT_NODE_LABELS } from '../../utils/canon'
import { splitScenes } from '../../utils/story'
import HowItWorks from '../HowItWorks'
import StoryPicker from '../StoryPicker'
import {
  Button,
  Disclosure,
  GraphCanvas,
  GraphLegend,
  Icon,
  MetricNumber,
  Pill,
  ProgressLine,
  SurfaceCard,
  Tabs,
} from '../primitives'
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
    { title: 'Load a show', body: 'Pick a ready-made show — the scan reads all of its episodes, not just one.' },
    {
      title: 'Read every episode',
      body:
        'The AI builds the show’s canon across all episodes and finds where its own facts disagree ' +
        'between far-apart episodes — the continuity a human can’t hold across thousands of pages.',
    },
    {
      title: 'See the clashing lines',
      body: 'Each contradiction opens like a book — the two episodes side by side, the exact lines highlighted, with a fix.',
    },
  ],
  planner: [
    { title: 'Give a soft ending', body: 'Paste the episode and the weak ending to improve.' },
    {
      title: 'Search with persistent agents',
      body:
        '100 stateful scouts explore every rewrite. The strongest endings and the original are then ' +
        'rated by the same 1,000 stored listener identities.',
    },
    {
      title: 'Compare the simulated signal',
      body: 'See the exact response count, formula and point lift. This is not measured listener retention.',
    },
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

const ENTITY_GROUPS = [
  ['Character', 'Characters'],
  ['Location', 'Locations'],
  ['PlotThread', 'Plot threads'],
  ['Clue', 'Clues'],
  ['Theme', 'Themes'],
]

const extractionChipStyle = {
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

function EntityGroup({ label, items }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <SectionLabel style={{ fontSize: 10 }}>
        {label} · {items.length}
      </SectionLabel>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {items.map((entity) => (
          <span
            key={entity.key || entity.name}
            style={extractionChipStyle}
            title={entity.description || ''}
          >
            {entity.name}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Extract-only preview: visible proof of what this script will persist. */
function LiveExtractionPanel({ preview }) {
  const { loading, data, error } = preview
  if (!loading && !data && !error) return null

  const extraction = data?.extraction
  const entities = extraction?.entities || []
  const relations = extraction?.relations || []
  const facts = extraction?.facts || []
  const nameByKey = Object.fromEntries(entities.map((entity) => [entity.key, entity.name]))
  const byType = {}
  for (const entity of entities) {
    ;(byType[entity.type] || (byType[entity.type] = [])).push(entity)
  }
  const groups = [
    ...ENTITY_GROUPS.filter(([type]) => byType[type]?.length).map(([type, label]) => [
      label,
      byType[type],
    ]),
    ...Object.keys(byType)
      .filter((type) => !ENTITY_GROUPS.some(([known]) => known === type))
      .map((type) => [type, byType[type]]),
  ]
  const hasContent = entities.length > 0 || facts.length > 0

  return (
    <SurfaceCard style={{ marginTop: 18, background: 'var(--surface)' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          flexWrap: 'wrap',
          marginBottom: 14,
        }}
      >
        <SectionLabel>Live extraction · what agents will remember</SectionLabel>
        <span style={{ fontSize: 12, color: 'var(--muted)' }} aria-live="polite">
          {data
            ? `${data.entity_count} entities · ${data.relation_count} connections · ${data.fact_count} facts${loading ? ' · updating…' : ''}`
            : 'reading your script…'}
        </span>
      </div>

      {loading && !data && <LoadingState label="Extracting canon from your script…" />}
      {error && !data && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          Live preview is unavailable right now; durable ingest can still be retried.
        </span>
      )}
      {data && !hasContent && !loading && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          No durable canon yet. Add a character, place, clue, or concrete fact.
        </span>
      )}

      {hasContent && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {groups.map(([label, items]) => (
            <EntityGroup key={label} label={label} items={items} />
          ))}
          {relations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <SectionLabel style={{ fontSize: 10 }}>Connections · {relations.length}</SectionLabel>
              {relations.slice(0, 6).map((relation, index) => (
                <div
                  key={`${relation.source_key}-${relation.type}-${relation.target_key}-${index}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    flexWrap: 'wrap',
                    fontSize: 13,
                  }}
                >
                  <strong>{nameByKey[relation.source_key] || relation.source_key}</strong>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--accent-text-sm)',
                    }}
                  >
                    {relation.type.replace(/_/g, ' ').toLowerCase()}
                  </span>
                  <span style={{ color: 'var(--dim)' }}>→</span>
                  <strong>{nameByKey[relation.target_key] || relation.target_key}</strong>
                </div>
              ))}
            </div>
          )}
          {facts.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <SectionLabel style={{ fontSize: 10 }}>Atomic facts · {facts.length}</SectionLabel>
              {facts.slice(0, 12).map((fact, index) => (
                <div
                  key={`${fact.subject_key}-${fact.predicate}-${index}`}
                  style={{
                    padding: '8px 12px',
                    border: '1px solid var(--border)',
                    borderLeft: '3px solid var(--accent)',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--surface-raised)',
                    fontSize: 13,
                    color: 'var(--ink)',
                    lineHeight: 1.45,
                  }}
                >
                  <strong>{nameByKey[fact.subject_key] || fact.subject_key}</strong>{' '}
                  <span style={{ color: 'var(--muted)' }}>· {fact.predicate} =</span>{' '}
                  {fact.object}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </SurfaceCard>
  )
}

/** Composer: current script + live preview + explicit session-safe persistence. */
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
  resetError,
  loadStory,
  locked = false,
}) {
  return (
    <SurfaceCard>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
          marginBottom: 14,
        }}
      >
        <SectionLabel>Build the canon</SectionLabel>
        {isSample && (
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            Showing a sample script ·{' '}
            <button
              type="button"
              onClick={clearText}
              disabled={locked}
              style={{
                minHeight: 44,
                background: 'none',
                border: 'none',
                padding: '8px 0',
                cursor: locked ? 'default' : 'pointer',
                font: 'inherit',
                color: 'var(--accent-text-sm)',
                fontWeight: 650,
              }}
            >
              clear and write your own
            </button>
          </span>
        )}
      </div>
      {loadStory && (
        <div style={{ marginBottom: 14 }}>
          <StoryPicker onSelect={loadStory} label="Load a ready-made story into the canon" />
        </div>
      )}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <input
          style={{ ...inputStyle, flex: '2 1 220px' }}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={locked}
          placeholder="Show title"
          aria-label="Show title"
        />
        <input
          style={{ ...inputStyle, flex: '1 1 140px' }}
          value={episode}
          onChange={(e) => setEpisode(e.target.value)}
          disabled={locked}
          placeholder="Episode"
          aria-label="Episode"
        />
      </div>
      <textarea
        style={{ ...inputStyle, minHeight: 160, resize: 'vertical', lineHeight: 1.6 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={locked}
        placeholder="Paste an episode script — its characters, clues, and facts appear below as you type."
        aria-label="Episode script"
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 14, flexWrap: 'wrap' }}>
        <Button onClick={ingest} disabled={!canIngest || locked}>
          {ingesting ? 'Ingesting…' : 'Ingest episode into canon'}
        </Button>
        {ingestResult && (
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Wrote <strong style={{ color: 'var(--ink)' }}>{ingestResult.nodes_added}</strong> nodes,{' '}
            <strong style={{ color: 'var(--ink)' }}>{ingestResult.edges_added}</strong> edges,{' '}
            <strong style={{ color: 'var(--ink)' }}>{ingestResult.facts_added || 0}</strong> facts
            to this session
            {ingestResult.entities?.length ? ` · ${ingestResult.entities.slice(0, 6).join(', ')}` : ''}
          </span>
        )}
        {ingestResult && (
          <button
            type="button"
            onClick={resetSession}
            disabled={resetting || locked}
            style={{
              minHeight: 44,
              background: 'none',
              border: 'none',
              padding: '8px 0',
              cursor: resetting || locked ? 'default' : 'pointer',
              font: 'inherit',
              fontSize: 13,
              color: 'var(--muted)',
              textDecoration: 'underline',
            }}
            title="Removes only this browser tab's memberships; seeded canon remains untouched"
          >
            {resetting ? 'Clearing…' : "Clear this session's canon"}
          </button>
        )}
        {ingestError && <span style={{ fontSize: 13, color: 'var(--danger)' }}>{ingestError}</span>}
        {resetError && <span style={{ fontSize: 13, color: 'var(--danger)' }}>{resetError}</span>}
      </div>
      <p style={{ margin: '12px 0 0', fontSize: 12.5, lineHeight: 1.55, color: 'var(--muted)' }}>
        Preview is extract-only. “Ingest” optionally persists this script to the shared graph for the
        other agents to read — it only affects your own session.
      </p>
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
        This view contains <strong style={{ color: 'var(--ink)' }}>only this browser tab’s story</strong>.
        The planner reads this same scope before its listener agents react; seeded ANDHERA data is
        excluded.
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

// --- Story-scoped plot holes: the "book / highlighter" view ---------------
// A loaded ready-made show is scanned directly from its episode scripts, so the
// result names the exact clashing sentence on each side. We locate that sentence
// in the episode text and highlight it, laying the two episodes out like an open
// book. Nothing here touches the seeded demo canon.

/** Soft-red highlighter mark for a clashing sentence. */
const MARK_STYLE = {
  background: 'var(--accent-soft)',
  color: 'var(--ink)',
  boxShadow: 'inset 0 0 0 1px var(--accent-line)',
  borderRadius: 'var(--radius-sm)',
  padding: '1px 4px',
}

const pageStyle = {
  flex: '1 1 300px',
  minWidth: 260,
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-5)',
}

const proseStyle = {
  margin: 0,
  fontFamily: 'var(--font-sans)',
  fontSize: 15,
  lineHeight: 1.85,
  color: 'var(--ink)',
  whiteSpace: 'pre-wrap',
}

/** Straighten quotes + collapse whitespace for tolerant matching. */
function normalizeQuote(s) {
  return String(s || '')
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Strip a leading "Scene N:" prefix so a scene reads as plain prose. */
function stripScenePrefix(s) {
  return String(s || '').replace(/^\s*Scene\s+\d+\s*:\s*/i, '').trim()
}

/** Find the episode in a loaded show by the label the scan returned. */
function episodeByLabel(episodes, label) {
  const digits = String(label || '').match(/\d+/)
  if (digits) {
    const n = Number(digits[0])
    const byNumber = episodes.find((e) => e.n === n)
    if (byNumber) return byNumber
  }
  const norm = (v) => String(v || '').toLowerCase().replace(/\s+/g, ' ').trim()
  return episodes.find((e) => norm(e.label) === norm(label)) || null
}

/** The scene (plain prose) within an episode that contains the quote. */
function sceneWithQuote(episodeText, quote) {
  const scenes = splitScenes(episodeText).map(stripScenePrefix)
  const needle = normalizeQuote(quote)
  const hit = needle && scenes.find((s) => normalizeQuote(s).includes(needle))
  return hit || scenes[0] || stripScenePrefix(episodeText)
}

/** Render a scene with its clashing sentence wrapped in a highlighter mark. */
function HighlightedScene({ scene, quote }) {
  const q = String(quote || '').trim()
  if (!q) return <p style={proseStyle}>{scene}</p>
  const lc = scene.toLowerCase()
  let start = lc.indexOf(q.toLowerCase())
  let len = q.length
  if (start < 0) {
    // Tolerant fallback: match a distinctive leading fragment of the sentence.
    const frag = q.replace(/[.?!"']+$/, '').slice(0, 48)
    start = frag ? lc.indexOf(frag.toLowerCase()) : -1
    len = frag.length
  }
  if (start < 0) return <p style={proseStyle}>{scene}</p>
  return (
    <p style={proseStyle}>
      {scene.slice(0, start)}
      <mark style={MARK_STYLE}>{scene.slice(start, start + len)}</mark>
      {scene.slice(start + len)}
    </p>
  )
}

/** One "page" of the book: an episode's relevant scene, quote highlighted. */
function BookPage({ episode, label, quote }) {
  const scene = episode ? sceneWithQuote(episode.text, quote) : stripScenePrefix(quote)
  const heading = episode
    ? `${episode.label}${episode.title ? ` · ${episode.title}` : ''}`
    : label
  return (
    <div style={pageStyle}>
      <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 10 }}>
        {heading}
      </div>
      <HighlightedScene scene={scene} quote={quote} />
    </div>
  )
}

/** One contradiction, laid out as an open book spread. */
function ContradictionSpread({ contradiction, episodes }) {
  const c = contradiction
  const epA = episodeByLabel(episodes, c.episode_a)
  const epB = episodeByLabel(episodes, c.episode_b)
  return (
    <SurfaceCard>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <SeverityTag severity={c.severity} />
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>
          <Icon name="book" size={16} /> {c.subject}
        </span>
        <span style={CITE_PILL} title="The two episodes that disagree">
          {`${c.episode_a} ↔ ${c.episode_b}`}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <BookPage episode={epA} label={c.episode_a} quote={c.quote_a} />
        <BookPage episode={epB} label={c.episode_b} quote={c.quote_b} />
      </div>
      {c.detail && (
        <p style={{ margin: '14px 0 6px', fontSize: 14, color: 'var(--ink)', lineHeight: 1.55 }}>
          {c.detail}
        </p>
      )}
      {c.fix && (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink)' }}>
          <strong>Fix:</strong> {c.fix}
        </p>
      )}
    </SurfaceCard>
  )
}

/** Story-scoped plot holes for a loaded show — the book / highlighter view. */
function StoryPlotHolesView({ story, scan, run }) {
  const { loading, data, error } = scan
  const episodes = story.episodes || []
  const contradictions = data?.contradictions || []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={run} disabled={loading}>
          {loading ? 'Reading every episode…' : 'Scan this show for plot holes'}
        </Button>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          {data
            ? `${story.title} · read ${data.episodes_scanned || episodes.length} episodes · ${contradictions.length} contradiction${contradictions.length === 1 ? '' : 's'}`
            : `${story.title} · ${episodes.length} episodes — scanned directly, not the seeded demo`}
        </span>
      </div>

      {loading && (
        <LoadingState label={`Reading all ${episodes.length} episodes for contradictions…`} />
      )}
      {error && <ErrorState message={error} />}
      {data && contradictions.length === 0 && !loading && (
        <EmptyState
          title="No contradictions found"
          hint="This show’s canon holds together across its episodes."
        />
      )}

      {contradictions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {contradictions.map((c, i) => (
            <ContradictionSpread key={i} contradiction={c} episodes={episodes} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Plot Hole panel — book view for a loaded show, else the whole-graph scan. */
function PlotHolesPanel({ plotHoles, runPlotHoles, loadedStory, storyScan, runStoryScan }) {
  if ((loadedStory?.episodes?.length || 0) > 1) {
    return <StoryPlotHolesView story={loadedStory} scan={storyScan} run={runStoryScan} />
  }
  return <GraphPlotHolesView plotHoles={plotHoles} runPlotHoles={runPlotHoles} />
}

/** Whole-graph plot-hole view — for custom pasted text (fallback). */
function GraphPlotHolesView({ plotHoles, runPlotHoles }) {
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

const plannerMetricStyle = {
  fontFamily: 'var(--font-sans)',
  fontVariantNumeric: 'tabular-nums',
  fontFeatureSettings: '"tnum" 1',
  fontSize: 'clamp(32px, 7vw, 44px)',
  lineHeight: 1,
  fontWeight: 650,
  letterSpacing: '-0.045em',
}

function PlannerMetric({ label, value, detail, tone = 'ink' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
      <span
        style={{
          ...plannerMetricStyle,
          color: tone === 'accent' ? 'var(--accent)' : 'var(--ink)',
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{label}</span>
      <span style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--muted)' }}>{detail}</span>
    </div>
  )
}

/** Cliffhanger Planner panel — streamed, stateful 1,000-agent search. */
export function PlannerPanel({ weakExcerpt, setWeakExcerpt, planner, runPlanner, stopPlanner }) {
  const ranked = [...planner.candidates]
    .filter((candidate) => typeof candidate.hookScore === 'number')
    .sort((a, b) => {
      if (a.stage === 'verified' && b.stage !== 'verified') return -1
      if (b.stage === 'verified' && a.stage !== 'verified') return 1
      return b.hookScore - a.hookScore
    })
  const best = planner.best
  const bestIsOriginal = best?.id === 'root'
  const lift = best?.delta ?? 0
  const meta = planner.meta
  const progress = planner.progress
  const liveBaseline = planner.runningScores?.root
  const hasResult = planner.baseline != null && best
  const memoryCoverage = meta.uniqueAgents
    ? Math.round((meta.memoryHits / meta.uniqueAgents) * 100)
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <label
          htmlFor="planner-weak-ending"
          style={{ display: 'block', fontSize: 13, fontWeight: 650, color: 'var(--ink)', marginBottom: 8 }}
        >
          Weak ending to improve
        </label>
        <p style={{ margin: '0 0 12px', fontSize: 13, lineHeight: 1.55, color: 'var(--muted)' }}>
          The complete episode stays fixed. Only this ending changes between test arms.
        </p>
      </div>
      <textarea
        id="planner-weak-ending"
        style={{ ...inputStyle, minHeight: 100, resize: 'vertical', lineHeight: 1.6 }}
        value={weakExcerpt}
        onChange={(e) => setWeakExcerpt(e.target.value)}
        disabled={planner.running}
        aria-label="Weak ending"
      />

      <SurfaceCard
        style={{
          padding: 'clamp(18px, 3vw, 28px)',
          background: 'var(--surface-raised)',
          borderColor: 'var(--border)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
          <div style={{ maxWidth: 650 }}>
            <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--accent-text-sm)', marginBottom: 8 }}>
              Audience test setup
            </div>
            <h3
              style={{
                margin: '0 0 10px',
                fontSize: 'clamp(22px, 4vw, 32px)',
                lineHeight: 1.15,
                letterSpacing: '-0.035em',
                color: 'var(--ink)',
              }}
            >
              Requested audience: 1,000 listener agents
            </h3>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: 'var(--muted)' }}>
              Every requested agent gets a stable identity and listener profile. When the knowledge
              graph is available, returning agents recall their own show-specific history. Story
              context comes only from this browser tab’s canon scope, never the seeded ANDHERA demo.
              This run reports the exact memory and canon coverage it loaded.
            </p>
          </div>
          <div style={{ alignSelf: 'flex-start' }}>
            {planner.running ? (
              <Button variant="secondary" onClick={stopPlanner}>
                Stop search
              </Button>
            ) : (
              <Button onClick={runPlanner}>Run 1,000-agent search</Button>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 18 }}>
          <Pill label="Scout cohort" value={`${meta.scoutSize ?? 100} agents`} />
          <Pill
            label="Requested verification"
            value={`${(meta.uniqueAgents || 1000).toLocaleString()} agents`}
            tone="accent"
          />
          <Pill label="Finalists" value={meta.finalistCount ?? 3} />
          <Pill label="Search rounds" value="2" />
          <Pill
            label="Canon scope"
            value={
              meta.uniqueAgents
                ? `this session · ${meta.canonNodesLoaded.toLocaleString()} nodes`
                : 'this browser session'
            }
          />
        </div>
      </SurfaceCard>

      {planner.error && <ErrorState message={planner.error} />}

      {(planner.running || planner.phase === 'cancelled') && (
        <SurfaceCard style={{ padding: 'clamp(18px, 3vw, 28px)' }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--accent-text-sm)', marginBottom: 8 }}>
              Live calculation
            </div>
            <h3
              aria-live="polite"
              style={{ margin: '0 0 8px', fontSize: 21, letterSpacing: '-0.025em' }}
            >
              {planner.phaseLabel || 'Preparing the audience panel'}
            </h3>
            {progress.total > 0 && (
              <p style={{ margin: '0 0 18px', fontSize: 13, color: 'var(--muted)' }}>
                {progress.completed.toLocaleString()} of {progress.total.toLocaleString()} agents responded
                {progress.dropped > 0 ? ` · ${progress.dropped} failed after retries` : ''}
                {typeof liveBaseline === 'number' ? ` · original mean so far ${liveBaseline}` : ''}
              </p>
            )}
            <ProgressLine
              label={
                progress.total
                  ? `${Math.round(progress.percent)}% of this stage complete`
                  : planner.phaseLabel || 'Preparing'
              }
              value={progress.total ? progress.percent : undefined}
            />
          </div>
          {planner.recentAgents.length > 0 && (
            <div style={{ marginTop: 20, display: 'grid', gap: 8 }}>
              {planner.recentAgents.slice(0, 3).map((agent) => (
                <div
                  key={agent.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                    gap: 12,
                    fontSize: 12,
                    lineHeight: 1.5,
                    color: 'var(--muted)',
                  }}
                >
                  <span>
                    <strong style={{ color: 'var(--ink)' }}>{agent.name}</strong> · {agent.segment}
                  </span>
                  <span>
                    {agent.memoryItemsLoaded > 0
                      ? `${agent.memoryItemsLoaded} memories read`
                      : 'new agent · no prior history'}
                    {agent.cached ? ' · cached result' : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </SurfaceCard>
      )}

      {hasResult && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
              gap: 18,
              padding: '8px 0',
            }}
          >
            <PlannerMetric
              label="Original ending score"
              value={`${planner.baseline} / 100`}
              detail={`Average from ${planner.baselineSampleSize.toLocaleString()} completed agents · ±${planner.baselineCi95} points`}
            />
            <PlannerMetric
              label={bestIsOriginal ? 'Original remains strongest' : 'Best ending score'}
              value={`${best.hookScore} / 100`}
              detail={`${best.sampleSize.toLocaleString()} matched agent ratings · ±${best.ci95} points`}
              tone="accent"
            />
            <PlannerMetric
              label="Estimated lift"
              value={`${lift > 0 ? '+' : ''}${lift} points`}
              detail="Best ending mean − original ending mean"
              tone={lift > 0 ? 'accent' : 'ink'}
            />
          </div>

          <SurfaceCard
            style={{
              padding: '18px 20px',
              background: 'var(--danger-bg)',
              borderColor: 'var(--danger)',
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 650, color: 'var(--red-ink)', marginBottom: 5 }}>
              Simulated research signal — not real listener retention
            </div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: 'var(--ink)' }}>
              This score is the average modeled hook strength across the simulated panel. Use it to
              compare endings, then validate the winner with production listener data.
            </p>
          </SurfaceCard>
        </>
      )}

      {ranked.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {ranked.map((c) => {
            const isBest = best && c.id === best.id
            const verified = c.stage === 'verified'
            return (
              <SurfaceCard
                key={c.id}
                elevated={isBest}
                style={{
                  padding: 'var(--space-4)',
                  borderColor: isBest ? 'var(--accent)' : 'var(--border)',
                  background: isBest ? 'var(--danger-bg)' : 'var(--surface-raised)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontVariantNumeric: 'tabular-nums',
                      fontWeight: 650,
                      fontSize: 18,
                      color: 'var(--ink)',
                    }}
                  >
                    {c.hookScore} / 100
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 650, color: c.delta >= 0 ? 'var(--accent-text-sm)' : 'var(--muted)' }}>
                    {c.delta > 0 ? `+${c.delta}` : c.delta} points{' '}
                    {verified ? 'vs full-panel original' : 'vs scout original'}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    {verified ? 'Full-panel verified' : 'Scout estimate'} · {c.sampleSize.toLocaleString()} agents
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Round {c.depth} refinement
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
                  {c.text || (isBest && best.text ? best.text : c.preview)}
                </p>
              </SurfaceCard>
            )
          })}
        </div>
      )}

      <SurfaceCard style={{ padding: '10px 20px' }}>
        <Disclosure
          summary={
            <span style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>
              How these scores are calculated
            </span>
          }
          defaultOpen
        >
          <div style={{ padding: '2px 0 18px 20px', display: 'grid', gap: 12 }}>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: 'var(--muted)' }}>
              Each agent reviews the original and all candidate endings in one matched comparison
              alongside the complete episode. It uses its stable listener profile, recalls up to four
              show-specific past reactions when available, reads only this browser session’s story
              canon, and returns a 0–100 hook score for every ending.
            </p>
            <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--ink)' }}>
              <div>
                <strong>Original ending score</strong> = sum of successful original-ending scores ÷
                successful responses.
              </div>
              <div>
                <strong>Best ending score</strong> = the same mean from the same verification cohort.
              </div>
              <div>
                <strong>Lift</strong> = best ending score − original ending score. It is a point
                difference, not a percentage.
              </div>
            </div>
          </div>
        </Disclosure>
        <Disclosure
          summary={
            <span style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>
              Stateful memory and experiment details
            </span>
          }
        >
          <div style={{ padding: '2px 0 18px 20px', display: 'grid', gap: 10 }}>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: 'var(--muted)' }}>
              Personal memory is frozen before the comparison so an earlier candidate cannot affect
              a later candidate. The winning experiment is archived separately from published
              listening history, so agents never “remember” an ending that listeners have not heard.
              “Search round” means rewrite-and-test refinement, not model reasoning depth.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Pill
                label="Personal memory recalled"
                value={
                  meta.uniqueAgents
                    ? `${meta.memoryHits.toLocaleString()} agents (${memoryCoverage}%)`
                    : 'shown after start'
                }
                tone="accent"
              />
              <Pill
                label="New agents"
                value={
                  meta.uniqueAgents
                    ? Math.max(0, meta.uniqueAgents - meta.memoryHits).toLocaleString()
                    : '—'
                }
              />
              <Pill label="Audience source" value={meta.audienceSource || 'knowledge graph'} />
              <Pill
                label="Session canon loaded"
                value={`${meta.canonNodesLoaded.toLocaleString()} nodes`}
              />
              <Pill label="Model" value={meta.model || 'shown after start'} />
              <Pill
                label="Experiment graph archive"
                value={meta.experimentArchived ? 'complete' : hasResult ? 'not persisted' : 'pending'}
              />
              {meta.verificationCachedAgents > 0 && (
                <Pill
                  label="Verification cache"
                  value={`${meta.verificationCachedAgents.toLocaleString()} reused · ${Math.max(
                    0,
                    planner.baselineSampleSize - meta.verificationCachedAgents,
                  ).toLocaleString()} fresh`}
                />
              )}
              {meta.completedEvaluations > 0 && (
                <Pill
                  label="Agent evaluations"
                  value={`${meta.completedEvaluations.toLocaleString()} / ${meta.plannedEvaluations.toLocaleString()}`}
                />
              )}
            </div>
          </div>
        </Disclosure>
        <Disclosure
          summary={
            <span style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>
              Statistical precision and limitations
            </span>
          }
        >
          <p style={{ margin: 0, padding: '2px 0 18px 20px', fontSize: 13, lineHeight: 1.65, color: 'var(--muted)' }}>
            The ± value is an approximate 95% interval around the simulated panel mean. It does not
            measure prediction accuracy against real PocketFM listeners, and model-generated agents
            are not independent human respondents. No separate uncertainty interval is claimed for lift.
          </p>
        </Disclosure>
      </SurfaceCard>
    </div>
  )
}

const STATUS_GLYPH = {
  pending: { glyph: '○', color: 'var(--dim)' },
  running: { glyph: '⟳', color: 'var(--accent)' },
  done: { glyph: '✓', color: 'var(--success)' },
}

function AudienceSourceBadge({ source, panelSize }) {
  if (!source) return null
  const living = source === 'living'
  return (
    <Pill
      label="Reward model"
      value={`${living ? 'Living Audience' : 'default archetypes'}${panelSize ? ` · ${panelSize}` : ''}`}
      tone={living ? 'accent' : undefined}
    />
  )
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

/** MDP Optimizer panel — policy search with the audience as the reward model. */
function MdpPanel({ mdp, runMdp }) {
  const lift = mdp.final != null && mdp.baseline != null ? Math.round((mdp.final - mdp.baseline) * 10) / 10 : null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Button onClick={runMdp} disabled={mdp.running}>
          {mdp.running ? 'Optimizing…' : 'Run policy search'}
        </Button>
        <AudienceSourceBadge source={mdp.audienceSource} panelSize={mdp.panelSize} />
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          State = story + canon · Action = candidate beat · Reward = simulated hook · γ look-ahead
        </span>
      </div>

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
          {mdp.steps.length > 0 && (
            <div style={{ display: 'grid', gap: 8 }}>
              {mdp.steps.map((step) => (
                <SurfaceCard key={step.iteration} style={{ padding: '12px 14px' }}>
                  <SectionLabel style={{ fontSize: 10 }}>Step {step.iteration}</SectionLabel>
                  <p style={{ margin: '6px 0 0', fontSize: 12.5, color: 'var(--muted)' }}>
                    {step.state || 'Updated story state'} · immediate reward {step.reward}
                    {step.qChosen != null ? ` · chosen Q-value ${step.qChosen}` : ''}
                  </p>
                </SurfaceCard>
              ))}
            </div>
          )}
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
      <CanonComposer {...props} locked={props.planner?.running} />

      {CANON_PANELS.length > 1 && (
        <Tabs tabs={CANON_PANELS} active={activePanel} onChange={setActivePanel} />
      )}

      {HOW_IT_WORKS[activePanel] && <HowItWorks steps={HOW_IT_WORKS[activePanel]} />}

      {activePanel === 'graph' && <CanonGraphPanel graph={graph} refresh={refresh} />}
      {activePanel === 'holes' && (
        <PlotHolesPanel
          plotHoles={props.plotHoles}
          runPlotHoles={props.runPlotHoles}
          loadedStory={props.loadedStory}
          storyScan={props.storyScan}
          runStoryScan={props.runStoryScan}
        />
      )}
      {activePanel === 'planner' && (
        <PlannerPanel
          weakExcerpt={props.weakExcerpt}
          setWeakExcerpt={props.setWeakExcerpt}
          planner={props.planner}
          runPlanner={props.runPlanner}
          stopPlanner={props.stopPlanner}
        />
      )}
      {activePanel === 'agent' && <ShowrunnerPanel agent={props.agent} runAgent={props.runAgent} />}
      {activePanel === 'mdp' && <MdpPanel mdp={props.mdp} runMdp={props.runMdp} />}
    </div>
  )
}
