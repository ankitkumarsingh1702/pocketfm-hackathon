/**
 * View-model mappers for the Story Canon (knowledge-graph) tab.
 *
 * Pure functions, same contract as the other `utils/*` mappers: return `null`
 * for missing input, default arrays to `[]`, and hand the view a flat,
 * render-ready object. Node layout is a deterministic, type-clustered circle so
 * the graph looks stable across refreshes (no physics engine needed).
 */

/** Even, deterministic fill of a disc (sunflower / phyllotaxis packing). */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

/** Order node types are clustered around the ring (bible first, then meta). */
const TYPE_ORDER = [
  'Episode',
  'Character',
  'Location',
  'PlotThread',
  'Clue',
  'Theme',
  'AudienceSegment',
  'Fact',
]

function typeRank(label) {
  const i = TYPE_ORDER.indexOf(label)
  return i === -1 ? TYPE_ORDER.length : i
}

/**
 * Map a raw CanonGraph into a laid-out, render-ready view (or null).
 *
 * Layout: one disc per node type (a "constellation"), spaced around a ring wide
 * enough that the two largest never touch. Each disc is filled with a
 * phyllotaxis pattern so 50 episodes pack as tidily as 6 themes, and node dots
 * shrink as a cluster gets denser. The result is deterministic (stable across
 * refreshes) and stays legible well past 100 nodes without per-node labels.
 */
export function toCanonGraphView(result) {
  if (!result) return null

  const allNodes = Array.isArray(result.nodes) ? result.nodes : []
  const rawEdges = Array.isArray(result.edges) ? result.edges : []

  // Facts are metadata for continuity search (Phase 2), not story-bible
  // entities — keep them out of the node-link view but surface their count.
  const factCount = allNodes.filter((n) => n.label === 'Fact').length
  const rawNodes = allNodes.filter((n) => n.label !== 'Fact')

  // Per-type counts for the legend, derived from the rendered nodes.
  const stats = {}
  for (const n of rawNodes) stats[n.label] = (stats[n.label] || 0) + 1

  // Group nodes by type; each group becomes one labelled constellation.
  const byType = new Map()
  for (const node of rawNodes) {
    const t = node.label || 'Entity'
    if (!byType.has(t)) byType.set(t, [])
    byType.get(t).push(node)
  }
  const types = [...byType.keys()].sort((a, b) => {
    const r = typeRank(a) - typeRank(b)
    return r !== 0 ? r : a.localeCompare(b)
  })
  for (const t of types) {
    byType.get(t).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }

  const T = types.length

  // Disc grows with sqrt(count) so bigger clusters get proportionally more room.
  const discOf = (c) => clamp(15 * Math.sqrt(c), 30, 132)
  let maxDisc = 0
  const discR = {}
  for (const t of types) {
    discR[t] = discOf(byType.get(t).length)
    if (discR[t] > maxDisc) maxDisc = discR[t]
  }

  // Ring radius sized so even the two largest discs, if adjacent, stay apart.
  const GAP = 54
  const ring =
    T > 1
      ? Math.max((maxDisc * 2 + GAP) / (2 * Math.sin(Math.PI / T)), maxDisc + GAP)
      : 0

  const pos = {}
  const nodes = []
  const clusters = []

  types.forEach((t, ti) => {
    const group = byType.get(t)
    const c = group.length
    const a = -Math.PI / 2 + (ti / T) * 2 * Math.PI
    const ccx = T > 1 ? ring * Math.cos(a) : 0
    const ccy = T > 1 ? ring * Math.sin(a) : 0
    const R = discR[t]
    const nodeR = clamp(Math.round((R / Math.sqrt(Math.max(c, 1))) * 0.82), 3, 7)

    group.forEach((node, k) => {
      const rr = c <= 1 ? 0 : R * Math.sqrt((k + 0.5) / c)
      const ang = k * GOLDEN_ANGLE
      const x = ccx + rr * Math.cos(ang)
      const y = ccy + rr * Math.sin(ang)
      pos[node.id] = { x, y }
      nodes.push({
        id: node.id,
        label: t,
        name: node.name || node.id,
        description: (node.props && node.props.description) || '',
        x,
        y,
        r: nodeR,
      })
    })

    // Type label sits just outside the disc, pushed away from the canvas centre.
    const out = T > 1 ? a : -Math.PI / 2
    clusters.push({
      type: t,
      label: t,
      count: c,
      cx: ccx,
      cy: ccy,
      discR: R,
      labelX: ccx + Math.cos(out) * (R + 16),
      labelY: ccy + Math.sin(out) * (R + 16),
    })
  })

  const edges = rawEdges
    .filter((e) => pos[e.source] && pos[e.target])
    .map((e, i) => ({
      id: `${e.source}->${e.target}:${i}`,
      source: e.source,
      target: e.target,
      type: e.type,
      x1: pos[e.source].x,
      y1: pos[e.source].y,
      x2: pos[e.target].x,
      y2: pos[e.target].y,
    }))

  // Tight view box around every disc + outward label, so the SVG scales to fill
  // its container with no dead space and nothing clipped.
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  const grow = (x, y) => {
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }
  for (const cl of clusters) {
    grow(cl.cx - cl.discR - 12, cl.cy - cl.discR - 12)
    grow(cl.cx + cl.discR + 12, cl.cy + cl.discR + 12)
    const half = (`${cl.label} · ${cl.count}`.length * 6.6) / 2
    grow(cl.labelX - half, cl.labelY - 9)
    grow(cl.labelX + half, cl.labelY + 9)
  }
  if (!Number.isFinite(minX)) {
    minX = -120
    minY = -120
    maxX = 120
    maxY = 120
  }
  const PAD = 24
  minX -= PAD
  minY -= PAD
  maxX += PAD
  maxY += PAD
  const width = Math.round(maxX - minX)
  const height = Math.round(maxY - minY)
  const viewBox = `${Math.round(minX)} ${Math.round(minY)} ${width} ${height}`

  // Plain, render-ready lists for the DB / Memory drill-downs (no layout).
  const nameById = {}
  for (const node of rawNodes) nameById[node.id] = node.name || node.id
  const entities = types.flatMap((t) =>
    byType.get(t).map((node) => ({
      id: node.id,
      label: t,
      name: node.name || node.id,
      description: (node.props && node.props.description) || '',
    })),
  )
  const relationships = rawEdges
    .filter((e) => pos[e.source] && pos[e.target])
    .map((e) => ({
      source: nameById[e.source] || e.source,
      target: nameById[e.target] || e.target,
      type: e.type,
      detail: e.detail || '',
    }))

  return {
    width,
    height,
    viewBox,
    nodes,
    edges,
    clusters,
    stats,
    entities,
    relationships,
    nodeCount: rawNodes.length,
    edgeCount: edges.length,
    factCount,
    isEmpty: rawNodes.length === 0,
  }
}

/** Map the raw canon facts payload into a render-ready view (or null). */
export function toFactsView(result) {
  if (!result) return null
  const facts = Array.isArray(result.facts) ? result.facts : []
  const conflicts = Array.isArray(result.conflicts) ? result.conflicts : []
  const dangling = Array.isArray(result.dangling_clues) ? result.dangling_clues : []
  return {
    facts,
    conflicts,
    dangling,
    episodeCount: result.episode_count || 0,
    isEmpty: facts.length === 0 && conflicts.length === 0 && dangling.length === 0,
  }
}

// --- Plot holes ------------------------------------------------------------

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 }

/** Map a PlotHoleResult into a severity-sorted view (or null). */
export function toPlotHolesView(result) {
  if (!result) return null
  const holes = [...(result.holes || [])]
    .sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3))
    .map((h) => ({ ...h, episodes: Array.isArray(h.episodes) ? h.episodes : [] }))
  return {
    holes,
    canonUsed: Boolean(result.canon_used),
    episodesScanned: result.episodes_scanned || 0,
    factsScanned: result.facts_scanned || 0,
    pagesEstimate: result.pages_estimate || 0,
    count: holes.length,
    isEmpty: holes.length === 0,
  }
}

// --- Cliffhanger planner (streaming tree search) ---------------------------

/** Fresh planner state for the streaming reducer. */
export function emptyPlanner() {
  return { running: false, error: null, baseline: null, candidates: [], best: null, rounds: 0 }
}

/** Fold one streamed beam-search event into planner state (pure). */
export function reducePlanner(state, ev) {
  switch (ev.type) {
    case 'baseline':
      return { ...state, baseline: ev.score }
    case 'candidate_scored':
      return {
        ...state,
        candidates: [
          ...state.candidates,
          {
            id: ev.id,
            parentId: ev.parent_id,
            depth: ev.depth,
            hookScore: ev.hook_score,
            delta: ev.delta,
            preview: ev.preview,
          },
        ],
      }
    case 'round_done':
      return { ...state, rounds: ev.round }
    case 'done': {
      const tree = ev.result || {}
      const cands = tree.candidates || []
      const best = cands.find((c) => c.id === tree.best_id) || null
      return {
        ...state,
        running: false,
        baseline: tree.baseline_score ?? state.baseline,
        rounds: tree.rounds ?? state.rounds,
        best: best
          ? { id: best.id, text: best.text, hookScore: best.hook_score, delta: best.delta }
          : null,
      }
    }
    case 'error':
      return { ...state, running: false, error: ev.error }
    default:
      return state
  }
}

// --- Showrunner state-graph agent ------------------------------------------

export const AGENT_NODES = [
  'ingest',
  'continuity',
  'simulate',
  'decide',
  'propose_fix',
  'resimulate',
  'converge',
]

export const AGENT_NODE_LABELS = {
  ingest: 'Read the episode into canon',
  continuity: 'Check continuity against canon',
  simulate: 'Simulate the audience',
  decide: 'Decide: will listeners drop off?',
  propose_fix: 'Rewrite the weak beat',
  resimulate: 'Re-test with the audience',
  converge: 'Converge',
}

export function emptyAgent() {
  const nodes = {}
  for (const n of AGENT_NODES) nodes[n] = { status: 'pending', detail: '' }
  return { running: false, error: null, nodes, log: [], decision: null, result: null }
}

/** Fold one streamed showrunner event into agent state (pure). */
export function reduceAgent(state, ev) {
  const nodes = { ...state.nodes }
  switch (ev.type) {
    case 'run_started':
      return state
    case 'node_started':
      nodes[ev.node] = { ...(nodes[ev.node] || {}), status: 'running' }
      return { ...state, nodes }
    case 'node_done':
      nodes[ev.node] = { ...(nodes[ev.node] || {}), status: 'done' }
      return { ...state, nodes }
    case 'agent':
      nodes[ev.node] = { ...(nodes[ev.node] || {}), detail: ev.detail }
      return { ...state, nodes, log: [...state.log, { node: ev.node, detail: ev.detail }] }
    case 'decision': {
      const outcome = ev.decision === 'fix' ? 'rewrite to keep listeners' : 'strong enough — converge'
      const detail =
        `${ev.churn_risk ? 'listeners likely to drop off' : 'listeners staying with it'} ` +
        `(${ev.binge_pct}% would continue) → ${outcome}`
      nodes.decide = { ...(nodes.decide || {}), detail }
      return {
        ...state,
        nodes,
        decision: { churn: ev.churn_risk, decision: ev.decision, iteration: ev.iteration },
        log: [...state.log, { node: 'decide', detail }],
      }
    }
    case 'done':
      return { ...state, running: false, result: ev.result || null }
    case 'error':
      return { ...state, running: false, error: ev.error }
    default:
      return state
  }
}

// --- DB / Memory activity feed ---------------------------------------------

/**
 * Map the raw canon activity feed into a render-ready view (or null).
 *
 * The backend returns events oldest-first; the live feed shows newest-first so
 * the most recent read/write is always at the top.
 */
export function toActivityView(result) {
  if (!result) return null
  const raw = Array.isArray(result.events) ? result.events : []
  return {
    events: [...raw].reverse(),
    reads: raw.filter((e) => e.op === 'read').length,
    writes: raw.filter((e) => e.op === 'write').length,
    total: raw.length,
    isEmpty: raw.length === 0,
  }
}

// --- MDP policy search -----------------------------------------------------

export function emptyMdp() {
  return { running: false, error: null, baseline: null, steps: [], final: null, best: null }
}

/** Fold one streamed MDP event into policy-search state (pure). */
export function reduceMdp(state, ev) {
  switch (ev.type) {
    case 'baseline':
      return { ...state, baseline: ev.reward }
    case 'iteration_done':
      return {
        ...state,
        steps: [
          ...state.steps,
          {
            iteration: ev.iteration,
            reward: ev.reward,
            bestReward: ev.best_reward,
            qValues: ev.q_values || [],
            preview: ev.preview,
          },
        ],
      }
    case 'done': {
      const r = ev.result || {}
      return {
        ...state,
        running: false,
        baseline: r.baseline_reward ?? state.baseline,
        final: r.final_reward ?? state.final,
        best: r.best_action_text ?? state.best,
      }
    }
    case 'error':
      return { ...state, running: false, error: ev.error }
    default:
      return state
  }
}
