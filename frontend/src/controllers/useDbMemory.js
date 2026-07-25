import { useCallback, useEffect, useState } from 'react'

import { canonHealth, getCanonActivity, getCanonGraph } from '../lib/api'
import { toActivityView, toCanonGraphView } from '../utils/canon'
import { useAsyncLens } from './useAsyncLens'

const POLL_MS = 2500
const ACTIVITY_LIMIT = 100
const identity = (x) => x

/**
 * DB / Memory controller — the judge-facing proof surface.
 *
 * Polls the backend for (a) the live activity feed of graph reads/writes,
 * (b) Neo4j connection health, and (c) the current graph — so the tab shows, in
 * real time, agents reading shared memory and writing verdicts back. All three
 * reuse `useAsyncLens`, which keeps the previous data visible while a poll is in
 * flight, so the feed never flashes empty between ticks.
 *
 * Polling only runs while the tab is `active` (and `live` is on), so the studio
 * doesn't hammer the backend when another tab is showing.
 */
export function useDbMemory(active = false) {
  const [live, setLive] = useState(true)

  const activity = useAsyncLens(getCanonActivity, toActivityView)
  const health = useAsyncLens(canonHealth, identity)
  const graph = useAsyncLens(getCanonGraph, toCanonGraphView)

  const { run: runActivity } = activity
  const { run: runHealth } = health
  const { run: runGraph } = graph

  const refresh = useCallback(() => {
    runActivity(ACTIVITY_LIMIT)
    runHealth()
    runGraph()
  }, [runActivity, runHealth, runGraph])

  // Load immediately when the tab opens; then poll while live.
  useEffect(() => {
    if (!active) return undefined
    refresh()
    if (!live) return undefined
    const id = setInterval(refresh, POLL_MS)
    return () => clearInterval(id)
  }, [active, live, refresh])

  return { activity, health, graph, refresh, live, setLive }
}
