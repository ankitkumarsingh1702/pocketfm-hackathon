/**
 * View-model mappers for the Story Canon (knowledge-graph) tab.
 *
 * Pure functions, same contract as the other `utils/*` mappers: return `null`
 * for missing input, default arrays to `[]`, and hand the view a flat,
 * render-ready object. Node layout is a deterministic, type-clustered circle so
 * the graph looks stable across refreshes (no physics engine needed).
 */

const CANVAS_W = 840
const CANVAS_H = 540
const MARGIN = 80

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

/** Map a raw CanonGraph into a laid-out, render-ready view (or null). */
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

  // Cluster same-type nodes together around the circle for legibility.
  const ordered = [...rawNodes].sort((a, b) => {
    const r = typeRank(a.label) - typeRank(b.label)
    return r !== 0 ? r : (a.name || '').localeCompare(b.name || '')
  })

  const cx = CANVAS_W / 2
  const cy = CANVAS_H / 2
  const radius = Math.min(cx, cy) - MARGIN
  const n = Math.max(ordered.length, 1)

  const pos = {}
  const nodes = ordered.map((node, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2
    const x = cx + radius * Math.cos(angle)
    const y = cy + radius * Math.sin(angle)
    pos[node.id] = { x, y }
    return {
      id: node.id,
      label: node.label || 'Entity',
      name: node.name || node.id,
      description: (node.props && node.props.description) || '',
      x,
      y,
    }
  })

  const edges = rawEdges
    .filter((e) => pos[e.source] && pos[e.target])
    .map((e, i) => ({
      id: `${e.source}->${e.target}:${i}`,
      type: e.type,
      x1: pos[e.source].x,
      y1: pos[e.source].y,
      x2: pos[e.target].x,
      y2: pos[e.target].y,
    }))

  return {
    width: CANVAS_W,
    height: CANVAS_H,
    nodes,
    edges,
    stats,
    nodeCount: rawNodes.length,
    edgeCount: edges.length,
    factCount,
    isEmpty: rawNodes.length === 0,
  }
}

// --- Plot holes ------------------------------------------------------------

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 }

/** Map a PlotHoleResult into a severity-sorted view (or null). */
export function toPlotHolesView(result) {
  if (!result) return null
  const holes = [...(result.holes || [])].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3),
  )
  return {
    holes,
    canonUsed: Boolean(result.canon_used),
    episodesScanned: result.episodes_scanned || 0,
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
  ingest: 'Ingest → canon',
  continuity: 'Continuity check',
  simulate: 'Simulate audience',
  decide: 'Decide (churn?)',
  propose_fix: 'Propose fix',
  resimulate: 'Re-simulate',
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
    case 'decision':
      nodes.decide = {
        ...(nodes.decide || {}),
        detail: `churn=${ev.churn_risk} → ${ev.decision} (binge ${ev.binge_pct}%)`,
      }
      return {
        ...state,
        nodes,
        decision: { churn: ev.churn_risk, decision: ev.decision, iteration: ev.iteration },
        log: [...state.log, { node: 'decide', detail: `iteration ${ev.iteration}: ${ev.decision}` }],
      }
    case 'done':
      return { ...state, running: false, result: ev.result || null }
    case 'error':
      return { ...state, running: false, error: ev.error }
    default:
      return state
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
