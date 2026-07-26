import { useCallback, useRef, useState } from 'react'

import { a2aCascadeStream } from '../lib/api'
import { fileToDownscaledImage } from '../utils/image'
import { createInitialState, reduceEvent } from '../utils/a2aCascade'

/**
 * Self-contained controller for A2A Word-of-Mouth.
 *
 * Owns the post composer (text + image), the seed size, and the live streaming
 * cascade. Every NDJSON event is folded into one `state` object by the pure
 * reducer in `utils/a2aCascade`; the tab reads `state` and lays it out. Mirrors
 * `useAudienceSim` but never touches it — this is an isolated lens.
 */

const SAMPLE_POST = {
  title: 'Andhera — Episode 6: The Sealed Room',
  text:
    "New episode drops tonight. Naina finally opens the room that's been locked "
    + 'since 1998 — and what she hears inside changes everything. Are you continuing?',
}

export function useA2ACascade() {
  const [post, setPost] = useState({ ...SAMPLE_POST, image: null })
  const [seedN, setSeedN] = useState(24)
  const [state, setState] = useState(() => createInitialState())
  const [running, setRunning] = useState(false)
  const abortRef = useRef(null)

  const setPostField = useCallback((key, value) => {
    setPost((prev) => ({ ...prev, [key]: value }))
  }, [])

  const setImage = useCallback(async (file) => {
    if (!file) return
    try {
      const image = await fileToDownscaledImage(file)
      setPost((prev) => ({ ...prev, image }))
    } catch {
      // A bad image never blocks the composer.
    }
  }, [])

  const clearImage = useCallback(() => setPost((prev) => ({ ...prev, image: null })), [])

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const run = useCallback(async () => {
    if (!post.text.trim() || running) return

    const story = {
      title: post.title.trim() || 'Untitled post',
      text: post.text.trim(),
    }
    if (post.episode) story.episode = post.episode
    if (post.storySoFar) story.story_so_far = post.storySoFar
    if (post.image) {
      story.image_base64 = post.image.base64
      story.image_mime = post.image.mime
    }

    const fresh = createInitialState()
    fresh.running = true
    setState(fresh)
    setRunning(true)

    const controller = new AbortController()
    abortRef.current = controller
    const onEvent = (ev) => setState((prev) => reduceEvent(prev, ev))

    try {
      await a2aCascadeStream({ story, seedN }, onEvent, controller.signal)
    } catch (e) {
      if (e.name !== 'AbortError') {
        setState((prev) => ({ ...prev, error: String(e.message || e) }))
      }
    } finally {
      setRunning(false)
      setState((prev) => ({ ...prev, running: false }))
      abortRef.current = null
    }
  }, [post, seedN, running])

  const canRun = Boolean(post.text.trim()) && !running

  return {
    post,
    setPostField,
    setImage,
    clearImage,
    seedN,
    setSeedN,
    run,
    stop,
    running,
    canRun,
    state,
  }
}
