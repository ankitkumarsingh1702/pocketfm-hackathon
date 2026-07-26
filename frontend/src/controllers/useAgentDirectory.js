import { useCallback, useEffect, useState } from 'react'

import { canonHealth, getCanonActivity, getCanonFacts, getCanonGraph, getPersonas } from '../lib/api'
import { toPersonaRoster } from '../utils/agentDirectory'
import { toActivityView, toCanonGraphView, toFactsView } from '../utils/canon'
import { useAsyncLens } from './useAsyncLens'

const POLL_MS = 3000
const ACTIVITY_LIMIT = 200
const identity = (x) => x

/**
 * Agent Directory controller — the jury-facing roster of every agent.
 *
 * The roster itself is static config (`AGENTS`) and renders instantly. This
 * hook hydrates the *live* half of each profile: the persona cast from
 * `/api/personas` (static, loaded once) and the shared-memory signals — graph
 * size, fact/episode counts, and the read/write activity feed each profile is
 * joined to by `source`. Like `useDbMemory`, the live signals poll only while
 * the tab is `active` (and `live` is on) via `useAsyncLens`, which keeps prior
 * data on screen during a poll so nothing flashes empty.
 */
export function useAgentDirectory(active = false) {
  const [live, setLive] = useState(true)

  const personas = useAsyncLens(getPersonas, toPersonaRoster)
  const activity = useAsyncLens(getCanonActivity, toActivityView)
  const graph = useAsyncLens(getCanonGraph, toCanonGraphView)
  const facts = useAsyncLens(getCanonFacts, toFactsView)
  const health = useAsyncLens(canonHealth, identity)

  const { run: runPersonas } = personas
  const { run: runActivity } = activity
  const { run: runGraph } = graph
  const { run: runFacts } = facts
  const { run: runHealth } = health

  // The live signals worth re-reading on a poll: memory activity + graph size.
  const refresh = useCallback(() => {
    runActivity(ACTIVITY_LIMIT)
    runGraph()
    runFacts()
    runHealth()
  }, [runActivity, runGraph, runFacts, runHealth])

  // On open: load the (static) persona cast once and take a first live read;
  // then poll the live signals while `live` is on.
  useEffect(() => {
    if (!active) return undefined
    runPersonas()
    refresh()
    if (!live) return undefined
    const id = setInterval(refresh, POLL_MS)
    return () => clearInterval(id)
  }, [active, live, refresh, runPersonas])

  return { personas, activity, graph, facts, health, refresh, live, setLive }
}
