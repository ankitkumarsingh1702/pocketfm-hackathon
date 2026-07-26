import { useCallback, useEffect, useRef, useState } from 'react'

import { DEFAULT_STORY_META, SAMPLE_STORY } from '../config/constants'
import {
  findPlotHoles,
  getCanonGraph,
  ingestCanon,
  mdpOptimizeStream,
  planCliffhangerStream,
  previewCanon,
  resetCanonSession,
  showrunnerStream,
} from '../lib/api'
import { SESSION_BATCH } from '../utils/session'
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
  const loadSessionGraph = useCallback(() => loadGraph(SESSION_BATCH), [loadGraph])

  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState(null)
  const [ingestError, setIngestError] = useState(null)

  // Load the current canon once on mount.
  useEffect(() => {
    loadSessionGraph()
  }, [loadSessionGraph])

  // Debounced extract-only preview. It proves what the current script becomes
  // before the user chooses to persist anything into the graph.
  const [preview, setPreview] = useState({ loading: false, data: null, error: null })
  const previewAbort = useRef(null)
  useEffect(() => {
    const trimmed = text.trim()
    if (trimmed.length < 24) {
      previewAbort.current?.abort()
      setPreview({ loading: false, data: null, error: null })
      return undefined
    }
    const timer = setTimeout(async () => {
      previewAbort.current?.abort()
      const controller = new AbortController()
      previewAbort.current = controller
      setPreview((current) => ({ ...current, loading: true, error: null }))
      try {
        const data = await previewCanon({ title, episode, text })
        if (!controller.signal.aborted) setPreview({ loading: false, data, error: null })
      } catch (err) {
        if (!controller.signal.aborted) {
          setPreview({
            loading: false,
            data: null,
            error: err.message || 'Live extraction preview failed',
          })
        }
      }
    }, 900)
    return () => {
      clearTimeout(timer)
      previewAbort.current?.abort()
    }
  }, [text, title, episode])

  const ingest = useCallback(async () => {
    if (isBlank(text)) return
    setIngesting(true)
    setIngestError(null)
    setIngestResult(null)
    try {
      const res = await ingestCanon({ title, episode, text }, SESSION_BATCH)
      setIngestResult(res)
      await loadSessionGraph()
    } catch (err) {
      setIngestError(err.message || 'Ingest failed')
    } finally {
      setIngesting(false)
    }
  }, [text, title, episode, loadSessionGraph])

  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState(null)
  const resetSession = useCallback(async () => {
    setResetting(true)
    setResetError(null)
    try {
      await resetCanonSession(SESSION_BATCH)
      setIngestResult(null)
      await loadSessionGraph()
    } catch (err) {
      setResetError(err.message || 'Session reset failed')
    } finally {
      setResetting(false)
    }
  }, [loadSessionGraph])

  const clearText = useCallback(() => {
    setText('')
    setIngestResult(null)
  }, [])

  // --- Plot Hole Hunter (graph-grounded) ---
  const plotHoles = useAsyncLens(findPlotHoles, toPlotHolesView)
  const { run: runPlotHolesLens } = plotHoles
  const runPlotHoles = useCallback(() => {
    if (!isBlank(text)) runPlotHolesLens({ title, episode, text })
  }, [text, title, episode, runPlotHolesLens])

  // --- Cliffhanger planner (streaming beam search) ---
  const [weakExcerpt, setWeakExcerpt] = useState(lastScene(SAMPLE_STORY))
  const loadStory = useCallback((story) => {
    setTitle(story.title || DEFAULT_STORY_META.title)
    setEpisode(story.episode || DEFAULT_STORY_META.episode)
    setText(story.text || '')
    setWeakExcerpt(lastScene(story.text || ''))
    setIngestResult(null)
  }, [])
  const [planner, setPlanner] = useState(emptyPlanner())
  const plannerAbort = useRef(null)
  const plannerInputKey = `${title}\u0000${episode}\u0000${text}\u0000${weakExcerpt}`
  const previousPlannerInputKey = useRef(plannerInputKey)

  useEffect(() => {
    if (previousPlannerInputKey.current === plannerInputKey) return
    previousPlannerInputKey.current = plannerInputKey
    plannerAbort.current?.abort()
    setPlanner(emptyPlanner())
  }, [plannerInputKey])

  const runPlanner = useCallback(async () => {
    if (isBlank(text) || isBlank(weakExcerpt)) return
    plannerAbort.current?.abort()
    const controller = new AbortController()
    plannerAbort.current = controller
    setPlanner({ ...emptyPlanner(), running: true })
    try {
      await planCliffhangerStream(
        {
          story: { title, episode, text },
          weakExcerpt,
          batch: SESSION_BATCH,
          beamWidth: 3,
          depth: 2,
        },
        (ev) => setPlanner((prev) => reducePlanner(prev, ev)),
        controller.signal,
      )
    } catch (err) {
      if (err.name === 'AbortError') {
        setPlanner((prev) => ({
          ...prev,
          running: false,
          phase: 'cancelled',
          phaseLabel: 'Search stopped',
          candidates: [],
          best: null,
          baseline: null,
        }))
        return
      }
      setPlanner((prev) => ({ ...prev, running: false, error: err.message || 'Search failed' }))
    } finally {
      if (plannerAbort.current === controller) plannerAbort.current = null
    }
  }, [text, title, episode, weakExcerpt])
  const stopPlanner = useCallback(() => plannerAbort.current?.abort(), [])

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
    refresh: loadSessionGraph,
    ingest,
    ingesting,
    ingestResult,
    ingestError,
    canIngest: !isBlank(text) && !ingesting,
    preview,
    resetSession,
    resetting,
    resetError,
    clearText,
    loadStory,
    isSample: text === SAMPLE_STORY,
    sessionBatch: SESSION_BATCH,
    // planning
    plotHoles,
    runPlotHoles,
    weakExcerpt,
    setWeakExcerpt,
    planner,
    runPlanner,
    stopPlanner,
    // agent + rl
    agent,
    runAgent,
    mdp,
    runMdp,
  }
}
