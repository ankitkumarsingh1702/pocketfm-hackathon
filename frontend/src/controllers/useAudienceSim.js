import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { audienceSimStream, generateAudience, getAudienceLibrary } from '../lib/api'
import { cloneAgent, segmentOptions } from '../lib/agents'
import { fileToDownscaledImage } from '../utils/image'

/** Most-recent reactions kept in the live feed (the DOM isn't virtualized). */
const RECENT_CAP = 60

const SAMPLE_POST = {
  title: 'Andhera — Episode 6: The Sealed Room',
  text:
    "New episode drops tonight. Naina finally opens the room that's been locked "
    + 'since 1998 — and what she hears inside changes everything. Are you continuing?',
}

/**
 * Self-contained controller for the Audience Simulator ("Living Audience").
 *
 * Owns the post composer (text + image), the editable audience roster (loaded
 * from the knowledge-graph library, synthesised on demand), and the live
 * streaming run. Reactions arrive over NDJSON and are folded into a capped live
 * feed plus running progress; the terminal event carries the aggregate result.
 */
export function useAudienceSim() {
  const [library, setLibrary] = useState(null)      // { total, source }
  const [roster, setRoster] = useState([])          // editable Persona[]
  const [activeAgentId, setActiveAgentId] = useState(null)
  const [panelSize, setPanelSize] = useState(1000)  // agents to fan out to on Run

  const [post, setPost] = useState({ ...SAMPLE_POST, image: null })

  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)

  const [running, setRunning] = useState(false)
  const [recent, setRecent] = useState([])          // last RECENT_CAP reactions
  const [progress, setProgress] = useState({ done: 0, dropped: 0, total: 0 })
  const [runMeta, setRunMeta] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const allRef = useRef([])                          // every reaction this run
  const abortRef = useRef(null)

  // --- library / roster ----------------------------------------------------

  const loadLibrary = useCallback(async () => {
    try {
      const lib = await getAudienceLibrary()
      setLibrary({ total: lib.total, source: lib.source })
      setRoster((lib.members || []).map(cloneAgent))
    } catch (e) {
      setGenError(String(e.message || e))
    }
  }, [])

  useEffect(() => {
    loadLibrary()
  }, [loadLibrary])

  const generate = useCallback(async (n, brief) => {
    setGenerating(true)
    setGenError(null)
    try {
      const lib = await generateAudience({ n, brief })
      setLibrary({ total: lib.total, source: lib.source })
      setRoster((lib.members || []).map(cloneAgent))
    } catch (e) {
      setGenError(String(e.message || e))
    } finally {
      setGenerating(false)
    }
  }, [])

  const updateAgent = useCallback((updated) => {
    setRoster((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))
  }, [])

  const openAgent = useCallback((id) => setActiveAgentId(id), [])
  const closeAgent = useCallback(() => setActiveAgentId(null), [])

  const activeAgent = useMemo(
    () => roster.find((a) => a.id === activeAgentId) || null,
    [roster, activeAgentId],
  )
  const segments = useMemo(() => segmentOptions(roster), [roster])
  // Default archetypes are examples, not this session's curated audience.
  const isDefaults = !library || library.source === 'defaults'

  // --- composer ------------------------------------------------------------

  const setPostField = useCallback((key, value) => {
    setPost((prev) => ({ ...prev, [key]: value }))
  }, [])

  const setImage = useCallback(async (file) => {
    if (!file) return
    setGenError(null)
    try {
      const image = await fileToDownscaledImage(file)
      setPost((prev) => ({ ...prev, image }))
    } catch (e) {
      setGenError(String(e.message || e))
    }
  }, [])

  const clearImage = useCallback(() => setPost((prev) => ({ ...prev, image: null })), [])

  // --- run -----------------------------------------------------------------

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const run = useCallback(async () => {
    if (!post.text.trim() || running) return

    const story = {
      title: post.title.trim() || 'Untitled post',
      text: post.text.trim(),
    }
    // Which episode this is, and the story up to it, so agents react in
    // continuity (episode N grounded in episodes 1..N-1). Omitted for standalone
    // posts, where the backend falls back to shared-graph canon.
    if (post.episode) story.episode = post.episode
    if (post.storySoFar) story.story_so_far = post.storySoFar
    if (post.image) {
      story.image_base64 = post.image.base64
      story.image_mime = post.image.mime
    }

    allRef.current = []
    setRecent([])
    setResult(null)
    setError(null)
    setRunMeta(null)
    setProgress({ done: 0, dropped: 0, total: panelSize })
    setRunning(true)

    const controller = new AbortController()
    abortRef.current = controller

    const onEvent = (ev) => {
      switch (ev.type) {
        case 'run_started':
          setRunMeta({
            audienceSource: ev.audience_source,
            model: ev.model,
            hasImage: ev.has_image,
            agentic: ev.agentic,
          })
          setProgress((p) => ({ ...p, total: ev.total }))
          break
        case 'reaction':
          allRef.current.push(ev.reaction)
          setRecent(allRef.current.slice(-RECENT_CAP))
          setProgress({ done: ev.done, dropped: ev.dropped, total: ev.total })
          break
        case 'agent_error':
          setProgress((p) => ({ ...p, dropped: ev.dropped, total: ev.total }))
          break
        case 'done':
          if (ev.result) setResult(ev.result)
          break
        case 'error':
          setError(ev.error || 'Simulation failed.')
          break
        default:
          break
      }
    }

    try {
      // Fan out to the SELECTED panel size. Send the roster only when it's the
      // user's curated audience (so profile edits are honoured); with just the
      // default archetypes, omit it so the server synthesises the full n — Run
      // never silently degrades to the 6 examples.
      await audienceSimStream(
        { story, n: panelSize, audience: isDefaults ? undefined : roster },
        onEvent,
        controller.signal,
      )
    } catch (e) {
      if (e.name !== 'AbortError') setError(String(e.message || e))
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }, [post, roster, running, panelSize, isDefaults])

  const canRun = Boolean(post.text.trim()) && !running

  return {
    // roster / library
    library,
    roster,
    segments,
    activeAgent,
    openAgent,
    closeAgent,
    updateAgent,
    generate,
    generating,
    genError,
    // composer
    post,
    setPostField,
    setImage,
    clearImage,
    // run
    run,
    stop,
    running,
    canRun,
    panelSize,
    setPanelSize,
    recent,
    progress,
    runMeta,
    result,
    error,
  }
}
