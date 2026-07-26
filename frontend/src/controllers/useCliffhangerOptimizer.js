import { useCallback, useRef, useState } from 'react'

import { cliffhangerStream } from '../lib/api'
import { toCliffhangerView } from '../utils/cliffhanger'
import { useCliffhangerNarration } from './useCliffhangerNarration'

/** Keep the live log bounded — the DOM isn't virtualized. */
const LOG_CAP = 500

const PHASE_LABEL = {
  rewrite: 'Rewriting the ending',
  panel_before: 'Scoring the original',
  panel_after: 'Scoring the optimized cut',
}

const EMPTY_PROGRESS = { phase: null, label: null, done: 0, total: 0 }

/**
 * Controller for the Cliffhanger Optimizer lens.
 *
 * `run(story, weakExcerpt)` streams the optimizer end to end over NDJSON, so the
 * UI can render a live, CLI-style run log — the rewrite, then every listener's
 * before/after hook score as it lands — instead of an opaque spinner. The
 * terminal `done` event carries the same `CliffhangerResult` the non-streaming
 * lens returns, mapped to the view-model via `toCliffhangerView`.
 *
 * `loading` stays true for the whole stream so the shared Run button reads
 * "Simulating…" exactly as before. The `narration` sub-controller voices both
 * endings on demand so the lift is *audible*; it is reset at the start of every
 * run so stale audio can never play against new text.
 *
 * @returns {{ data:object|null, loading:boolean, running:boolean, error:string|null,
 *   log:object[], progress:object, run:Function, stop:Function, reset:Function,
 *   narration:object }}
 */
export function useCliffhangerOptimizer() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [log, setLog] = useState([])
  const [progress, setProgress] = useState(EMPTY_PROGRESS)

  const narration = useCliffhangerNarration()
  const { reset: resetNarration } = narration

  const abortRef = useRef(null)
  const reqId = useRef(0)
  const lineId = useRef(0)

  const append = useCallback((entry) => {
    setLog((prev) => {
      const next = [...prev, { id: (lineId.current += 1), ...entry }]
      return next.length > LOG_CAP ? next.slice(-LOG_CAP) : next
    })
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const reset = useCallback(() => {
    reqId.current += 1 // invalidate any in-flight stream
    abortRef.current?.abort()
    abortRef.current = null
    resetNarration()
    setData(null)
    setError(null)
    setLog([])
    setProgress(EMPTY_PROGRESS)
    setLoading(false)
  }, [resetNarration])

  const run = useCallback(
    async (story, weakExcerpt) => {
      const id = (reqId.current += 1)
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // A fresh optimize invalidates any prior narration, so stale audio can
      // never play against new text.
      resetNarration()
      setData(null)
      setError(null)
      setLog([])
      setProgress(EMPTY_PROGRESS)
      setLoading(true)
      append({ kind: 'system', text: 'Starting the Cliffhanger Optimizer…' })

      const onEvent = (ev) => {
        if (id !== reqId.current) return // superseded by a newer run
        switch (ev.type) {
          case 'run_started':
            append({
              kind: 'system',
              text: `Panel ready — ${ev.panel_size} simulated listeners`,
              detail: ev.audience_model ? `model ${ev.audience_model}` : undefined,
            })
            break
          case 'phase': {
            const label = PHASE_LABEL[ev.phase] || ev.phase
            if (ev.status === 'start') {
              setProgress({ phase: ev.phase, label, done: 0, total: ev.total || 0 })
              append({ kind: 'phase', text: `${label}…` })
            } else if (ev.status === 'done') {
              if (ev.phase === 'rewrite') {
                append({ kind: 'ok', text: 'Rewrite ready', detail: ev.rewrite })
              } else if (ev.score != null) {
                const which = ev.phase === 'panel_before' ? 'Original' : 'Optimized'
                append({ kind: 'ok', text: `${which} panel done — avg hook ${ev.score}` })
              }
            }
            break
          }
          case 'agent_scored':
            setProgress((p) =>
              p.phase === ev.phase
                ? { ...p, done: ev.done, total: ev.total }
                : {
                    phase: ev.phase,
                    label: PHASE_LABEL[ev.phase] || ev.phase,
                    done: ev.done,
                    total: ev.total,
                  },
            )
            append({
              kind: 'agent',
              text: `${ev.persona?.name || 'Listener'} · ${ev.persona?.segment || 'General'}`,
              score: ev.hook_score,
              cached: ev.cached,
              detail:
                ev.running_mean != null
                  ? `hook ${ev.hook_score}/100 · panel avg ${ev.running_mean}`
                  : `hook ${ev.hook_score}/100`,
            })
            break
          case 'done': {
            const view = toCliffhangerView(ev.result)
            setData(view)
            if (view) {
              const sign = view.lift > 0 ? `+${view.lift}` : `${view.lift}`
              append({
                kind: 'done',
                text: `Done — hook score ${view.before} → ${view.after} (${sign})`,
              })
            }
            break
          }
          case 'error':
            setError(ev.error || 'The run failed.')
            append({ kind: 'error', text: ev.error || 'The run failed.' })
            break
          default:
            break
        }
      }

      try {
        await cliffhangerStream({ story, weakExcerpt }, onEvent, controller.signal)
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
    [append, resetNarration],
  )

  return { data, loading, running: loading, error, log, progress, run, stop, reset, narration }
}
