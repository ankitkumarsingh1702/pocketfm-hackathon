/**
 * Client state + layout for the A2A Word-of-Mouth cascade.
 *
 * Folds the NDJSON event stream (run_started / round_started / reaction /
 * message / round_done / done / error) into a single state object, and lays the
 * reached agents out as concentric rings by round so `GraphCanvas` can render
 * the post spreading outward from the seed. Pure functions — no React here.
 */

// GraphCanvas colours nodes by a type `label`. We reuse its palette to colour
// agents by the round they were reached in: seed = black, hop 1 = soft red, then
// a calm grey ramp outward. Order maps round -> label.
const RING_STYLE = ['Character', 'Episode', 'PlotThread', 'Clue', 'Location', 'AudienceSegment']

/** Legend rows (round -> human label + the exact GraphCanvas colour). */
export const RING_LEGEND = [
  { round: 0, label: 'Seeded', color: 'var(--ink)' },
  { round: 1, label: 'Hop 1', color: 'var(--accent)' },
  { round: 2, label: 'Hop 2', color: 'var(--grey-600, #8a8a8a)' },
  { round: 3, label: 'Hop 3', color: 'var(--dim)' },
  { round: 4, label: 'Hop 4+', color: 'var(--muted)' },
]

const VIEW = 720
const CENTER = VIEW / 2

/** Fresh state for one run. */
export function createInitialState() {
  return {
    running: false,
    runMeta: null, // { seed, population, maxRounds, model }
    nodesById: {}, // id -> { id, name, segment, round, engagement }
    edges: [], // { source, target, round }
    messages: [], // { round, from, to, comment }
    log: [], // { id, kind, text, detail } for AgentLogConsole
    rounds: [], // { round, newReach, cumulativeReach, newSharers }
    reactions: [], // CascadeReactionView (capped)
    progress: { reached: 0, rounds: 0 },
    dropped: 0,
    result: null,
    error: null,
    _logSeq: 0,
  }
}

function withLog(state, kind, text, detail) {
  const id = state._logSeq
  return {
    log: [...state.log, { id, kind, text, detail }],
    _logSeq: id + 1,
  }
}

const MSG_CAP = 160
const REACTION_CAP = 150
const EDGE_CAP = 600

/** Fold one NDJSON event into the state (pure). */
export function reduceEvent(state, ev) {
  switch (ev.type) {
    case 'run_started':
      return {
        ...state,
        running: true,
        runMeta: {
          seed: ev.seed,
          population: ev.population,
          maxRounds: ev.max_rounds,
          model: ev.model,
        },
        ...withLog(
          state,
          'system',
          `Seeded to ${ev.seed} agents · network of ${ev.population}`,
          ev.model,
        ),
      }

    case 'round_started':
      return {
        ...state,
        ...withLog(
          state,
          'phase',
          `Round ${ev.round} — ${ev.exposed} agent${ev.exposed === 1 ? '' : 's'} exposed`,
        ),
      }

    case 'reaction': {
      const node = {
        id: ev.persona_id,
        name: ev.name,
        segment: ev.segment,
        round: ev.round ?? 0,
        engagement: ev.engagement,
      }
      const nodesById = { ...state.nodesById, [ev.persona_id]: node }
      const reactions = [...state.reactions, ev].slice(-REACTION_CAP)
      return {
        ...state,
        nodesById,
        reactions,
        progress: { ...state.progress, reached: Object.keys(nodesById).length },
      }
    }

    case 'message': {
      const from = ev.from || {}
      const to = ev.to || {}
      const messages = [...state.messages, { round: ev.round, from, to, comment: ev.comment }].slice(
        -MSG_CAP,
      )
      const edges = [...state.edges, { source: from.id, target: to.id, round: ev.round }].slice(
        -EDGE_CAP,
      )
      const comment = (ev.comment || '').trim()
      return {
        ...state,
        messages,
        edges,
        ...withLog(
          state,
          'agent',
          `${from.name || 'Someone'} → ${to.name || 'a follower'}`,
          comment ? `“${comment}”` : 'shared it onward',
        ),
      }
    }

    case 'round_done': {
      const rounds = [
        ...state.rounds,
        {
          round: ev.round,
          newReach: ev.new_reach,
          cumulativeReach: ev.cumulative_reach,
          newSharers: ev.new_sharers,
        },
      ]
      return {
        ...state,
        rounds,
        progress: { reached: ev.cumulative_reach, rounds: ev.round + 1 },
        ...withLog(
          state,
          'ok',
          `Round ${ev.round} done · reach ${ev.cumulative_reach}`,
          `${ev.new_sharers} spread it onward`,
        ),
      }
    }

    case 'agent_error':
      return { ...state, dropped: ev.dropped ?? state.dropped + 1 }

    case 'done':
      return {
        ...state,
        running: false,
        result: ev.result || null,
        ...withLog(
          state,
          'done',
          ev.result
            ? `Cascade complete · ${ev.result.total_reached} reached · R=${ev.result.virality_coefficient}`
            : 'Cascade complete',
        ),
      }

    case 'error':
      return {
        ...state,
        running: false,
        error: ev.error || 'Cascade failed.',
        ...withLog(state, 'error', ev.error || 'Cascade failed.'),
      }

    default:
      return state
  }
}

function placeNode(member, x, y, r, pos, out) {
  const label = RING_STYLE[Math.min(member.round, RING_STYLE.length - 1)]
  const name = member.name + (member.segment ? ` · ${member.segment}` : '')
  const node = {
    id: member.id,
    x,
    y,
    r,
    label,
    name,
    description: `Hop ${member.round}${member.engagement ? ` · ${member.engagement}` : ''}`,
  }
  pos.set(member.id, node)
  out.push(node)
}

/**
 * Lay reached agents out as concentric rings by round → `GraphCanvas` data.
 * Returns `{ isEmpty: true }` before anyone has reacted.
 */
export function buildGraphData(nodesById, edges) {
  const all = Object.values(nodesById)
  if (!all.length) return { isEmpty: true }

  const byRound = new Map()
  for (const n of all) {
    const r = n.round ?? 0
    if (!byRound.has(r)) byRound.set(r, [])
    byRound.get(r).push(n)
  }
  const rounds = [...byRound.keys()].sort((a, b) => a - b)

  const pos = new Map()
  const outNodes = []
  for (const round of rounds) {
    const members = byRound.get(round).slice().sort((a, b) => (a.id < b.id ? -1 : 1))
    const count = members.length
    if (round === 0) {
      const innerR = count === 1 ? 0 : Math.min(72, 20 + count * 3)
      members.forEach((m, i) => {
        const angle = (2 * Math.PI * i) / Math.max(1, count) - Math.PI / 2
        placeNode(m, CENTER + innerR * Math.cos(angle), CENTER + innerR * Math.sin(angle), 9, pos, outNodes)
      })
    } else {
      const ringR = Math.min(96 + round * 66, CENTER - 26)
      const offset = round * 0.55
      members.forEach((m, i) => {
        const angle = (2 * Math.PI * i) / Math.max(1, count) + offset - Math.PI / 2
        placeNode(m, CENTER + ringR * Math.cos(angle), CENTER + ringR * Math.sin(angle), 6.5, pos, outNodes)
      })
    }
  }

  const outEdges = []
  edges.forEach((e, i) => {
    const a = pos.get(e.source)
    const b = pos.get(e.target)
    if (!a || !b) return // target not reached yet — edge appears once it reacts
    outEdges.push({ id: `e${i}`, source: e.source, target: e.target, x1: a.x, y1: a.y, x2: b.x, y2: b.y })
  })

  return {
    viewBox: `0 0 ${VIEW} ${VIEW}`,
    width: VIEW,
    height: VIEW,
    nodes: outNodes,
    edges: outEdges,
    clusters: [],
  }
}
