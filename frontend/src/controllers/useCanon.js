import { useCallback, useEffect, useState } from 'react'

import { DEFAULT_STORY_META, SAMPLE_STORY } from '../config/constants'
import {
  findPlotHoles,
  getCanonGraph,
  ingestCanon,
  mdpOptimizeStream,
  planCliffhangerStream,
  showrunnerStream,
} from '../lib/api'
import {
  emptyAgent,
  emptyMdp,
  emptyPlanner,
  reduceAgent,
  reduceMdp,
  reducePlanner,
  toCanonGraphView,
  toPlotHolesView,
} from '../utils/canon'
import { isBlank, lastScene } from '../utils/story'
import { useAsyncLens } from './useAsyncLens'

/**
 * Story Canon controller — drives the knowledge-graph tab.
 *
 * Owns its own composer inputs (this tab is self-contained, like the Writers
 * Room) plus the ingest action and the graph read. The graph is loaded once on
 * mount and re-read after every ingest, so the visualization always reflects
 * the current shared memory.
 */
export function useCanon() {
  const [activePanel, setActivePanel] = useState('graph')
  const [title, setTitle] = useState(DEFAULT_STORY_META.title)
  const [episode, setEpisode] = useState(DEFAULT_STORY_META.episode)
  const [text, setText] = useState(SAMPLE_STORY)

  const graph = useAsyncLens(getCanonGraph, toCanonGraphView)
  const { run: loadGraph } = graph

  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState(null)
  const [ingestError, setIngestError] = useState(null)

  // Load the current canon once on mount.
  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  const ingest = useCallback(async () => {
    if (isBlank(text)) return
    setIngesting(true)
    setIngestError(null)
    setIngestResult(null)
    try {
      const res = await ingestCanon({ title, episode, text })
      setIngestResult(res)
      await loadGraph()
    } catch (err) {
      setIngestError(err.message || 'Ingest failed')
    } finally {
      setIngesting(false)
    }
  }, [text, title, episode, loadGraph])

  // --- Plot Hole Hunter (graph-grounded) ---
  const plotHoles = useAsyncLens(findPlotHoles, toPlotHolesView)
  const { run: runPlotHolesLens } = plotHoles
  const runPlotHoles = useCallback(() => {
    if (!isBlank(text)) runPlotHolesLens({ title, episode, text })
  }, [text, title, episode, runPlotHolesLens])

  // --- Cliffhanger planner (streaming beam search) ---
  const [weakExcerpt, setWeakExcerpt] = useState(lastScene(SAMPLE_STORY))
  const [planner, setPlanner] = useState(emptyPlanner())
  const runPlanner = useCallback(async () => {
    if (isBlank(text) || isBlank(weakExcerpt)) return
    setPlanner({ ...emptyPlanner(), running: true })
    try {
      await planCliffhangerStream(
        { story: { title, episode, text }, weakExcerpt, beamWidth: 3, depth: 2 },
        (ev) => setPlanner((prev) => reducePlanner(prev, ev)),
      )
    } catch (err) {
      setPlanner((prev) => ({ ...prev, running: false, error: err.message || 'Search failed' }))
    }
  }, [text, title, episode, weakExcerpt])

  // --- Showrunner state-graph agent (streaming) ---
  const [agent, setAgent] = useState(emptyAgent())
  const runAgent = useCallback(async () => {
    if (isBlank(text)) return
    setAgent({ ...emptyAgent(), running: true })
    try {
      await showrunnerStream(
        { story: { title, episode, text }, weakExcerpt },
        (ev) => setAgent((prev) => reduceAgent(prev, ev)),
      )
    } catch (err) {
      setAgent((prev) => ({ ...prev, running: false, error: err.message || 'Agent failed' }))
    }
  }, [text, title, episode, weakExcerpt])

  // --- MDP policy search (streaming) ---
  const [mdp, setMdp] = useState(emptyMdp())
  const runMdp = useCallback(async () => {
    if (isBlank(text) || isBlank(weakExcerpt)) return
    setMdp({ ...emptyMdp(), running: true })
    try {
      await mdpOptimizeStream(
        { story: { title, episode, text }, weakExcerpt, iterations: 4, candidatesPerIter: 3 },
        (ev) => setMdp((prev) => reduceMdp(prev, ev)),
      )
    } catch (err) {
      setMdp((prev) => ({ ...prev, running: false, error: err.message || 'Optimize failed' }))
    }
  }, [text, title, episode, weakExcerpt])

  return {
    activePanel,
    setActivePanel,
    title,
    setTitle,
    episode,
    setEpisode,
    text,
    setText,
    graph,
    refresh: loadGraph,
    ingest,
    ingesting,
    ingestResult,
    ingestError,
    canIngest: !isBlank(text) && !ingesting,
    // planning
    plotHoles,
    runPlotHoles,
    weakExcerpt,
    setWeakExcerpt,
    planner,
    runPlanner,
    // agent + rl
    agent,
    runAgent,
    mdp,
    runMdp,
  }
}
