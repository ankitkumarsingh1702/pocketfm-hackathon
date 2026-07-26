import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  LONGFORM_MAX_CHARS,
  LONGFORM_POLL_TIMEOUT_MS,
  MAX_CHARS,
  MIN_CHARS,
  POLL_TIMEOUT_MS,
} from '../config/genre'
import * as genreApi from '../lib/genreApi'

// Stable identities, so a poll that changes nothing does not re-render the
// timeline and the scene list along with it.
const NO_EVENTS = []
const NO_PARTIAL = {}

/**
 * Controller for the Genre Converter lens.
 *
 * Owns the whole job lifecycle: validate, submit, poll, surface the result.
 * Deliberately not built on `useAsyncLens` — that primitive models a single
 * request/response, and this is submit-then-poll with live progress in between.
 *
 * Everything the tab renders comes from here; the tab itself has no logic.
 */
export function useGenreConverter() {
  const [source, setSource] = useState('')
  const [genre, setGenre] = useState(null)
  const [genres, setGenres] = useState([])
  const [genresError, setGenresError] = useState(null)

  const [job, setJob] = useState(null)
  const [result, setResult] = useState(null)
  const [kind, setKind] = useState(null) // 'convert' | 'extract'
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const abortRef = useRef(null)
  const startedRef = useRef(0)

  // --- genre catalogue ------------------------------------------------------

  useEffect(() => {
    const controller = new AbortController()
    genreApi
      .listGenres(controller.signal)
      .then((packs) => {
        setGenres(packs)
        setGenre((current) => current ?? packs[0]?.name ?? null)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setGenresError(err.message)
      })
    return () => controller.abort()
  }, [])

  // --- elapsed clock, so a six-minute wait shows it is still alive ----------

  useEffect(() => {
    if (!running) return undefined
    const timer = setInterval(() => {
      setElapsed(Math.round((Date.now() - startedRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [running])

  // --- validation -----------------------------------------------------------

  const chars = source.trim().length
  const tooShort = chars > 0 && chars < MIN_CHARS
  const tooLong = chars > LONGFORM_MAX_CHARS
  /** Past the short pipeline: this convert will run chapter by chapter. */
  const longform = chars > MAX_CHARS && !tooLong

  /** Why the run button is disabled, in words, or null when it is enabled. */
  const blocker = (() => {
    if (running) return 'A conversion is already running.'
    if (chars === 0) return 'Paste a story first.'
    if (tooShort) return `${MIN_CHARS - chars} more characters needed — this is too short to have a plot.`
    if (tooLong) return `${(chars - LONGFORM_MAX_CHARS).toLocaleString()} characters over the long-form ceiling.`
    if (!genre) return 'Choose a genre.'
    return null
  })()

  const canRun = blocker === null

  /** Skeleton-only extraction stays short-lane-only; long stories must Convert. */
  const extractBlocker =
    !blocker && longform
      ? `Skeleton-only extraction runs on stories up to ${MAX_CHARS.toLocaleString()} characters.`
      : blocker
  const canExtract = extractBlocker === null

  // --- running --------------------------------------------------------------

  const start = useCallback(
    async (which) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      startedRef.current = Date.now()
      setElapsed(0)
      setRunning(true)
      setError(null)
      setResult(null)
      setJob(null)
      setKind(which)

      try {
        const text = source.trim()
        const submitted =
          which === 'extract'
            ? await genreApi.submitExtract(text, controller.signal)
            : await genreApi.submitConvert(text, genre, controller.signal)

        setJob(submitted)
        const finished = await genreApi.pollJob(
          submitted.id,
          setJob,
          controller.signal,
          submitted.lane === 'longform' ? LONGFORM_POLL_TIMEOUT_MS : POLL_TIMEOUT_MS,
        )
        setResult(finished.result)
      } catch (err) {
        if (err.name === 'AbortError') return // stopped on purpose; leave state as-is
        setError(err.message || 'The conversion failed.')
      } finally {
        if (abortRef.current === controller) setRunning(false)
      }
    },
    [genre, source],
  )

  const convert = useCallback(() => start('convert'), [start])
  const extract = useCallback(() => start('extract'), [start])

  /** Stop polling. The job itself keeps running server-side. */
  const stopWatching = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setRunning(false)
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setRunning(false)
    setJob(null)
    setResult(null)
    setError(null)
    setKind(null)
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  // --- what the job has finished so far -------------------------------------

  const events = job?.events ?? NO_EVENTS
  const partial = job?.partial ?? NO_PARTIAL

  /**
   * The scene currently being written, or null.
   *
   * Derived from the plan and the scenes already delivered rather than from
   * `job.step`, because the two disagree for the length of a retry: `step`
   * stays put while the service re-asks, and a row that stops saying "writing
   * now" for a minute is exactly the disconnection this is meant to remove.
   */
  const activeScene = useMemo(() => {
    // 'transform' is the short lane's writing stage; 'write' is the long-form one.
    if (!running || (job?.stage !== 'transform' && job?.stage !== 'write')) return null
    const plan = partial.scene_plan ?? []
    const done = new Set((partial.scenes ?? []).map((s) => s.scene))
    return plan.find((entry) => !done.has(entry.scene))?.scene ?? null
  }, [running, job?.stage, partial])

  return {
    // input
    source,
    setSource,
    genre,
    setGenre,
    genres,
    genresError,
    chars,
    tooShort,
    tooLong,
    longform,
    blocker,
    canRun,
    extractBlocker,
    canExtract,
    // lifecycle
    convert,
    extract,
    stopWatching,
    reset,
    running,
    elapsed,
    job,
    result,
    kind,
    error,
    // live detail, published by the service before the job ends
    events,
    partial,
    activeScene,
  }
}
