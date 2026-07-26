import { useCallback, useEffect, useRef, useState } from 'react'

import { producerStream } from '../lib/api'
import { audioUrlFromBase64, revokeAudioUrl } from '../utils/audio'

/** Keep the live log bounded — the DOM isn't virtualized. */
const LOG_CAP = 500

const EMPTY_PROGRESS = { phase: null, label: null, done: 0, total: 0 }

/** Blank plan so the four result cards can render placeholders and fill in live. */
const skeleton = (title) => ({
  show_title: title,
  casting: null,
  sound: null,
  pacing: null,
  marketing: null,
  summary: '',
  agents_completed: 0,
  voices_rendered: 0,
})

/**
 * Controller for the AI Producer lens.
 *
 * `run(story, languageCode)` streams the four Sarvam sub-agents (casting, sound,
 * pacing, marketing) over NDJSON so the UI shows a live, CLI-style run log and
 * fills each result card as its agent lands. The terminal `done` carries the full
 * `ProductionPlanResult`. `audio` plays a character's Sarvam-voiced sample line on
 * demand through a single shared `<audio>` element, so casting is *audible*.
 */
export function useAiProducer() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [log, setLog] = useState([])
  const [progress, setProgress] = useState(EMPTY_PROGRESS)
  const [playingKey, setPlayingKey] = useState(null)

  const abortRef = useRef(null)
  const reqId = useRef(0)
  const lineId = useRef(0)
  const dataRef = useRef(null)

  // One shared <audio> element + the object URL currently loaded into it.
  const audioRef = useRef(null)
  const urlRef = useRef(null)

  const append = useCallback((entry) => {
    setLog((prev) => {
      const next = [...prev, { id: (lineId.current += 1), ...entry }]
      return next.length > LOG_CAP ? next.slice(-LOG_CAP) : next
    })
  }, [])

  const stopAudio = useCallback(() => {
    const el = audioRef.current
    if (el) {
      el.pause()
      el.removeAttribute('src')
    }
    revokeAudioUrl(urlRef.current)
    urlRef.current = null
    setPlayingKey(null)
  }, [])

  // Play (or toggle off) one character's base64 clip through the shared element.
  const play = useCallback(
    (key, base64, mime = 'audio/wav') => {
      if (playingKey === key) {
        stopAudio()
        return
      }
      stopAudio()
      const url = audioUrlFromBase64(base64, mime)
      if (!url) return
      let el = audioRef.current
      if (!el) {
        el = new Audio()
        el.addEventListener('ended', () => setPlayingKey(null))
        audioRef.current = el
      }
      urlRef.current = url
      el.src = url
      el.play().then(
        () => setPlayingKey(key),
        () => setPlayingKey(null), // autoplay/decoding blocked — fail quietly
      )
    },
    [playingKey, stopAudio],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const reset = useCallback(() => {
    reqId.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    stopAudio()
    dataRef.current = null
    setData(null)
    setError(null)
    setLog([])
    setProgress(EMPTY_PROGRESS)
    setLoading(false)
  }, [stopAudio])

  // Release the audio URL if the view unmounts mid-clip.
  useEffect(() => () => stopAudio(), [stopAudio])

  const run = useCallback(
    async (story, languageCode = 'en-IN') => {
      const id = (reqId.current += 1)
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      stopAudio()
      dataRef.current = skeleton(story?.title || 'Your episode')
      setData(dataRef.current)
      setError(null)
      setLog([])
      setProgress(EMPTY_PROGRESS)
      setLoading(true)
      append({ kind: 'system', text: 'Briefing the AI Producer’s agents…' })

      const bump = () => setProgress((p) => ({ ...p, done: p.done + 1 }))
      const merge = (patch) => {
        dataRef.current = { ...dataRef.current, ...patch }
        setData(dataRef.current)
      }

      const onEvent = (ev) => {
        if (id !== reqId.current) return // superseded by a newer run
        switch (ev.type) {
          case 'run_started':
            setProgress({ phase: 'agents', label: 'Agents', done: 0, total: ev.agents?.length || 4 })
            append({
              kind: 'system',
              text: `${ev.agents?.length || 4} producer agents on the case — Sarvam LLM`,
            })
            break
          case 'agent_done': {
            if (ev.result && ev.id in dataRef.current) merge({ [ev.id]: ev.result })
            const extra =
              ev.id === 'casting'
                ? ` — ${ev.result?.characters?.length || 0} roles cast, ${ev.voices_rendered || 0} voiced`
                : ''
            append({ kind: 'ok', text: `${ev.name} done${extra}` })
            bump()
            break
          }
          case 'agent_error':
            append({ kind: 'error', text: `${ev.name} failed`, detail: ev.error })
            bump()
            break
          case 'phase':
            if (ev.detail) append({ kind: 'phase', text: ev.detail })
            break
          case 'orchestrator':
            merge({
              summary: ev.summary || '',
              agents_completed: ev.agents_completed || 0,
              voices_rendered: ev.voices_rendered || 0,
            })
            append({ kind: 'ok', text: 'Producer’s memo ready' })
            break
          case 'done':
            if (ev.result) {
              dataRef.current = ev.result
              setData(ev.result)
              append({
                kind: 'done',
                text: `Production plan ready — ${ev.result.agents_completed}/4 agents, ${ev.result.voices_rendered} voices`,
              })
            }
            break
          case 'error':
            setError(ev.error || 'The run failed.')
            append({ kind: 'error', text: ev.error || 'The run failed.' })
            break
          default:
            break
        }
      }

      try {
        await producerStream({ story, languageCode }, onEvent, controller.signal)
      } catch (e) {
        if (e.name === 'AbortError') {
          if (id === reqId.current) append({ kind: 'system', text: 'Stopped.' })
        } else if (id === reqId.current) {
          const message = e.message || 'Request failed'
          setError(message)
          append({ kind: 'error', text: message })
        }
      } finally {
        if (id === reqId.current) {
          setLoading(false)
          setProgress(EMPTY_PROGRESS)
          abortRef.current = null
        }
      }
    },
    [append, stopAudio],
  )

  return {
    data,
    loading,
    running: loading,
    error,
    log,
    progress,
    run,
    stop,
    reset,
    audio: { playingKey, play, stop: stopAudio },
  }
}
